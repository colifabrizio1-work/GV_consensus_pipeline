"""Backfill dello storico sales GV per un sottoinsieme di datest.

Serve quando un datest entra in scope dopo che i parquet annuali sono gia' stati
costruiti (caso reale: lo split UK di settembre 2026 in 028000 EL+3P / 027300 EB /
027150 RX, mai presenti negli scarichi storici).

Differenza rispetto a update_sales_gv.py --source custom: quello fa un rebuild
completo e riscrive OGNI parquet annuale con i soli datest presenti nel CSV,
quindi su uno scarico mono-mercato cancellerebbe tutti gli altri datest. Qui
invece si tocca soltanto la combinazione (datest presenti nel CSV) x (settimane
presenti nel CSV): tutto il resto del parquet resta byte per byte com'era.

Uso tipico:
    python backfill_sales_gv.py --dry-run
    python backfill_sales_gv.py
"""

from __future__ import annotations

import argparse
import logging
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from gv_config import load_config
from gv_samu import send_update_status
from update_sales_gv import (
    KEY_COLUMNS,
    OUTPUT_COLUMNS,
    SALES_DATA_TYPES,
    atomic_write_parquet,
    detect_csv_separator,
    normalize_chunk,
    read_datest_scope,
)

DEFAULT_SOURCE_KEY = "sales_historical_uk"


def setup_logger(log_dir: str, dry_run: bool) -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_dry_run" if dry_run else ""
    log_path = Path(log_dir) / f"backfill_sales_gv_{timestamp}{suffix}.log"

    logger = logging.getLogger("backfill_sales_gv")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.info("Log file: %s", log_path)
    logger.gv_log_path = log_path
    return logger


def resolve_source_path(cfg: dict, args: argparse.Namespace) -> str:
    if args.source_path:
        return args.source_path
    scarichi = cfg["scarichi"]
    if DEFAULT_SOURCE_KEY not in scarichi:
        raise ValueError(f"Missing scarichi.{DEFAULT_SOURCE_KEY} in datasets.json; pass --source-path instead.")
    return scarichi[DEFAULT_SOURCE_KEY]["path"]


def scan_source_scope(
    source_path: str,
    cfg: dict,
    datest_scope: set[str],
    separator: str,
    chunksize: int,
) -> tuple[set[str], set[str], dict[str, set[str]]]:
    """Datest e settimane presenti nel CSV, gia' filtrati sullo scope di config."""
    datests: set[str] = set()
    out_of_scope: set[str] = set()
    weeks_by_year: dict[str, set[str]] = {}

    for chunk in pd.read_csv(
        source_path,
        sep=separator,
        encoding=cfg["business_rules"].get("encoding", "utf-8-sig"),
        dtype=str,
        usecols=["Client Datest", "Fiscal Year", "Fiscal Week"],
        chunksize=chunksize,
    ):
        chunk["Client Datest"] = chunk["Client Datest"].astype(str).fillna("").str.strip().str.zfill(6)
        chunk["Fiscal Year"] = chunk["Fiscal Year"].astype(str).fillna("").str.strip()
        chunk["Fiscal Week"] = chunk["Fiscal Week"].astype(str).fillna("").str.strip()
        chunk = chunk[~chunk["Fiscal Week"].str.lower().isin(["", "nan", "none", "nat"])]

        out_of_scope.update(set(chunk["Client Datest"].unique()) - datest_scope)
        chunk = chunk[chunk["Client Datest"].isin(datest_scope)]
        datests.update(chunk["Client Datest"].unique().tolist())
        for year, part in chunk.groupby("Fiscal Year", sort=False):
            weeks_by_year.setdefault(str(year), set()).update(part["Fiscal Week"].unique().tolist())

    return datests, out_of_scope, weeks_by_year


def collect_rows_by_year(
    source_path: str,
    cfg: dict,
    target_datests: set[str],
    logger: logging.Logger,
    chunksize: int,
    separator: str,
) -> tuple[dict[str, list[pd.DataFrame]], int]:
    by_year: dict[str, list[pd.DataFrame]] = {}
    total_source_rows = 0

    for chunk_idx, chunk in enumerate(
        pd.read_csv(
            source_path,
            sep=separator,
            encoding=cfg["business_rules"].get("encoding", "utf-8-sig"),
            dtype=str,
            chunksize=chunksize,
        ),
        start=1,
    ):
        total_source_rows += len(chunk)
        normalized = normalize_chunk(chunk, target_datests)
        if normalized.empty:
            logger.info("Chunk %s: source_rows=%s output_rows=0", chunk_idx, len(chunk))
            continue
        for year, part in normalized.groupby("Fiscal Year", sort=False):
            by_year.setdefault(str(year), []).append(part.copy())
        logger.info("Chunk %s: source_rows=%s output_rows=%s", chunk_idx, len(chunk), len(normalized))

    return by_year, total_source_rows


def per_datest_summary(df: pd.DataFrame) -> dict[str, tuple[int, int]]:
    if df.empty:
        return {}
    grouped = df.groupby("Client Datest")["Qty"].agg(["size", "sum"])
    return {str(idx): (int(row["size"]), int(row["sum"])) for idx, row in grouped.iterrows()}


def backfill(cfg: dict, args: argparse.Namespace, logger: logging.Logger) -> int:
    datest_scope = read_datest_scope(cfg)
    source_path = resolve_source_path(cfg, args)
    separator = detect_csv_separator(source_path, cfg["business_rules"].get("csv_separator", ","))
    logger.info("Source: %s", source_path)
    logger.info("CSV separator detected: %r", separator)
    logger.info("Datest scope from config: %s", ", ".join(sorted(datest_scope)))

    found_datests, out_of_scope, weeks_by_year = scan_source_scope(
        source_path, cfg, datest_scope, separator, args.chunksize
    )
    if out_of_scope:
        logger.warning("Datest present in the source but NOT in allowed_gv_datests (ignored): %s", ", ".join(sorted(out_of_scope)))
    if not found_datests:
        raise ValueError("No in-scope datest found in the source file.")

    if args.datests:
        requested = {str(d).strip().zfill(6) for d in args.datests}
        unknown = requested - datest_scope
        if unknown:
            raise ValueError(f"Requested datests outside allowed_gv_datests: {', '.join(sorted(unknown))}")
        absent = requested - found_datests
        if absent:
            raise ValueError(f"Requested datests not present in the source file: {', '.join(sorted(absent))}")
        target_datests = requested
    else:
        target_datests = found_datests

    logger.info("Target datests: %s", ", ".join(sorted(target_datests)))
    for year in sorted(weeks_by_year):
        weeks = sorted(weeks_by_year[year])
        logger.info("Source year %s: weeks %s-%s (n=%s)", year, weeks[0], weeks[-1], len(weeks))

    by_year, total_source_rows = collect_rows_by_year(
        source_path, cfg, target_datests, logger, args.chunksize, separator
    )
    if not by_year:
        raise ValueError("No rows produced from source after normalization.")

    pattern = cfg["parquet"]["sales_annual_pattern"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    written = 0

    for year in sorted(by_year):
        new_df = pd.concat(by_year[year], ignore_index=True)
        new_df = new_df.groupby(KEY_COLUMNS + ["data_type"], as_index=False, sort=False)["Qty"].sum()[OUTPUT_COLUMNS]
        source_weeks = weeks_by_year.get(year, set())
        output_path = Path(pattern.format(year=year))

        if output_path.exists():
            old_df = pd.read_parquet(output_path)
            # Si rimuove solo (datest di questo backfill) x (settimane presenti nel CSV):
            # cosi' il rilancio e' idempotente e gli altri datest non vengono toccati.
            remove_mask = (
                old_df["Client Datest"].astype(str).isin(target_datests)
                & old_df["Fiscal Week"].astype(str).isin(source_weeks)
                & old_df["data_type"].isin(SALES_DATA_TYPES)
            )
            removed_rows = int(remove_mask.sum())
            kept_df = old_df.loc[~remove_mask, OUTPUT_COLUMNS].copy()
        else:
            old_df = pd.DataFrame(columns=OUTPUT_COLUMNS)
            removed_rows = 0
            kept_df = pd.DataFrame(columns=OUTPUT_COLUMNS)
            logger.warning("Missing existing parquet for year %s; creating it from backfill rows only.", year)

        final_df = pd.concat([kept_df, new_df], ignore_index=True)
        final_df = final_df.groupby(KEY_COLUMNS + ["data_type"], as_index=False, sort=False)["Qty"].sum()[OUTPUT_COLUMNS]
        final_df = final_df.sort_values(KEY_COLUMNS + ["data_type"], kind="stable").reset_index(drop=True)

        # Guardia: i datest fuori dal backfill devono restare identici riga per riga.
        before = per_datest_summary(old_df)
        after = per_datest_summary(final_df)
        for datest in sorted(set(before) | set(after)):
            if datest in target_datests:
                continue
            if before.get(datest) != after.get(datest):
                raise RuntimeError(
                    f"Year {year}: datest {datest} is outside the backfill scope but changed "
                    f"({before.get(datest)} -> {after.get(datest)}). Aborting without writing."
                )

        logger.info(
            "Year %s: old_rows=%s removed_rows=%s backfill_rows=%s final_rows=%s qty_sum=%s output=%s",
            year,
            len(old_df),
            removed_rows,
            len(new_df),
            len(final_df),
            int(final_df["Qty"].sum()),
            output_path,
        )
        for datest in sorted(target_datests):
            rows, qty = after.get(datest, (0, 0))
            logger.info("   %s -> rows=%s qty=%s", datest, rows, qty)

        if args.dry_run:
            continue

        if not args.no_backup and output_path.exists():
            backup_path = output_path.with_name(f"{output_path.name}.bak_backfill_{timestamp}")
            shutil.copy2(output_path, backup_path)
            logger.info("Backup: %s", backup_path)
        atomic_write_parquet(final_df, output_path)
        written += 1

    logger.info("Source rows read: %s", total_source_rows)
    logger.info("Parquet files written: %s", written)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill GV sales parquet for datests missing from the historical scarichi.")
    parser.add_argument("--source-path", help=f"CSV to backfill from. Default: scarichi.{DEFAULT_SOURCE_KEY} from datasets.json.")
    parser.add_argument("--datests", nargs="*", help="Restrict the backfill to these datests. Default: every in-scope datest found in the CSV.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing parquet.")
    parser.add_argument("--no-backup", action="store_true", help="Do not copy the existing parquet to a .bak_backfill_* file.")
    parser.add_argument("--no-mail", action="store_true", help="Do not send S.A.M. status email.")
    parser.add_argument("--chunksize", type=int, default=250_000)
    args = parser.parse_args()

    cfg = load_config()
    logger = setup_logger(cfg["gv"]["log"], args.dry_run)
    try:
        logger.info("Starting GV sales backfill | dry_run=%s | chunksize=%s", args.dry_run, args.chunksize)
        written = backfill(cfg, args, logger)
        logger.info("Completed GV sales backfill")
        send_update_status(
            pipeline_name="Sales backfill",
            status="OK",
            lines=[
                "Backfill storico Sales GV completato correttamente.",
                f"Sorgente: {resolve_source_path(cfg, args)}",
                f"Datest: {', '.join(args.datests) if args.datests else 'tutti quelli in scope trovati nel CSV'}",
                f"Dry-run: {args.dry_run}",
                f"Parquet scritti: {written}",
                f"Log: {getattr(logger, 'gv_log_path', '')}",
            ],
            log_path=getattr(logger, "gv_log_path", None),
            active=not args.no_mail,
        )
        return 0
    except Exception as exc:
        logger.exception("GV sales backfill failed")
        try:
            send_update_status(
                pipeline_name="Sales backfill",
                status="ERRORE",
                lines=[
                    "Backfill storico Sales GV terminato con errore.",
                    f"Dry-run: {args.dry_run}",
                    f"Log: {getattr(logger, 'gv_log_path', '')}",
                ],
                log_path=getattr(logger, "gv_log_path", None),
                error=exc,
                active=not args.no_mail,
            )
        except Exception:
            logger.exception("S.A.M. failure notification failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
