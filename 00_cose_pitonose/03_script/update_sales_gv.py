from __future__ import annotations

import argparse
import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from gv_config import load_config
from gv_samu import send_update_status

KEY_COLUMNS = ["Client Datest", "UPC", "Fiscal Year", "Fiscal Month", "Fiscal Week"]
HIST_COLUMN = "Hist Weekly Sales"
MINIMO_COLUMN_CANDIDATES = [
    "Hist - Weekly Sales Act MS>0 (Total)",
    "Hist – Weekly Sales Act MS>0 (Total)",  # trattino lungo: e' quello che usa BOXI
    "Hist ? Weekly Sales Act MS>0 (Total)",
]
SALES_DATA_TYPES = ["Sales_hist", "Sales_minimo"]
OUTPUT_COLUMNS = KEY_COLUMNS + ["Qty", "data_type"]


def setup_logger(log_dir: str, dry_run: bool) -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_dry_run" if dry_run else ""
    log_path = Path(log_dir) / f"update_sales_gv_{timestamp}{suffix}.log"

    logger = logging.getLogger("update_sales_gv")
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


def read_datest_scope(cfg: dict) -> set[str]:
    datests = cfg.get("business_rules", {}).get("allowed_gv_datests")
    if not datests:
        raise ValueError("Missing business_rules.allowed_gv_datests in datasets.json")
    return {str(datest).strip().zfill(6) for datest in datests}


def resolve_source_path(cfg: dict, source: str) -> str:
    if source == "historical":
        return cfg["scarichi"]["sales_historical"]["path"]
    if source == "update":
        return cfg["scarichi"]["sales_update"]["path"]
    raise ValueError(f"Unsupported source: {source}")


def detect_csv_separator(source_path: str, default: str = ",") -> str:
    with open(source_path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        sample = fh.read(8192)
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,|\t").delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample.splitlines() else ""
        if first.count(";") > first.count(default):
            return ";"
        return default


def find_minimo_column(columns: Iterable[str]) -> str:
    columns_set = set(columns)
    for candidate in MINIMO_COLUMN_CANDIDATES:
        if candidate in columns_set:
            return candidate
    for col in columns:
        normalized = str(col).replace("?", "-").replace("?", "-").strip().lower()
        if "weekly sales act ms>0" in normalized:
            return str(col)
    raise ValueError("Missing minimo sales column. Available columns: " + ", ".join(map(str, columns)))


def to_qty(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    text = text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    qty = pd.to_numeric(text, errors="coerce").fillna(0)
    return qty.round().astype("int64")


def normalize_chunk(chunk: pd.DataFrame, datest_scope: set[str], allowed_weeks: set[str] | None = None) -> pd.DataFrame:
    missing = [col for col in KEY_COLUMNS + [HIST_COLUMN] if col not in chunk.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")
    minimo_column = find_minimo_column(chunk.columns)

    base = chunk.copy()
    for col in KEY_COLUMNS:
        # fillna dopo astype(str): da pandas 3 astype(str) lascia i mancanti come NA
        # invece di scriverli "nan", quindi senza questo i filtri qui sotto non li
        # intercettano piu' e le righe senza settimana finiscono a parquet.
        base[col] = base[col].astype(str).fillna("").str.strip()
    base["Client Datest"] = base["Client Datest"].str.zfill(6)
    base = base[base["Client Datest"].isin(datest_scope)]
    base = base[~base["UPC"].str.lower().isin(["", "nan", "none", "nat"])]
    base = base[~base["Fiscal Week"].str.lower().isin(["", "nan", "none", "nat"])]
    # Un Fiscal Year vuoto creerebbe un parquet annuale spazzatura (GV_Sales_.parquet).
    base = base[~base["Fiscal Year"].str.lower().isin(["", "nan", "none", "nat"])]
    if allowed_weeks is not None:
        base = base[base["Fiscal Week"].isin(allowed_weeks)]
    if base.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    hist = base[KEY_COLUMNS].copy()
    hist["Qty"] = to_qty(base[HIST_COLUMN])
    hist["data_type"] = "Sales_hist"

    minimo = base[KEY_COLUMNS].copy()
    minimo["Qty"] = to_qty(base[minimo_column])
    minimo["data_type"] = "Sales_minimo"

    out = pd.concat([hist, minimo], ignore_index=True)
    out = out[out["Qty"] != 0]
    if out.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return out.groupby(KEY_COLUMNS + ["data_type"], as_index=False, sort=False)["Qty"].sum()[OUTPUT_COLUMNS]


def atomic_write_parquet(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    df.to_parquet(tmp_path, index=False, engine="pyarrow")
    os.replace(tmp_path, output_path)


def read_latest_weeks(source_path: str, cfg: dict, datest_scope: set[str], n_weeks: int, separator: str) -> tuple[list[str], set[str]]:
    """Settimane da sostituire e datest effettivamente presenti nello scarico."""
    weeks: set[str] = set()
    datests: set[str] = set()
    for chunk in pd.read_csv(
        source_path,
        sep=separator,
        encoding=cfg["business_rules"].get("encoding", "utf-8-sig"),
        dtype=str,
        usecols=["Client Datest", "Fiscal Week"],
        chunksize=250_000,
    ):
        chunk["Client Datest"] = chunk["Client Datest"].astype(str).fillna("").str.strip().str.zfill(6)
        chunk["Fiscal Week"] = chunk["Fiscal Week"].astype(str).fillna("").str.strip()
        chunk = chunk[chunk["Client Datest"].isin(datest_scope)]
        chunk = chunk[~chunk["Fiscal Week"].str.lower().isin(["", "nan", "none", "nat"])]
        weeks.update(chunk["Fiscal Week"].unique().tolist())
        datests.update(chunk["Client Datest"].unique().tolist())
    ordered = sorted(weeks)
    # n_weeks <= 0 significa: sostituisci tutte le settimane presenti nello scarico.
    # Limitare la finestra alle ultime N settimane lascia buchi quando due run
    # distano piu' di N settimane (caso reale: settimana 202629 mai caricata).
    if n_weeks and n_weeks > 0:
        return ordered[-n_weeks:], datests
    return ordered, datests


def collect_normalized_rows(
    source_path: str,
    cfg: dict,
    datest_scope: set[str],
    logger: logging.Logger,
    chunksize: int,
    allowed_weeks: set[str] | None = None,
    separator: str | None = None,
) -> tuple[dict[str, list[pd.DataFrame]], int, int]:
    by_year: dict[str, list[pd.DataFrame]] = {}
    total_source_rows = 0
    total_output_rows = 0

    for chunk_idx, chunk in enumerate(
        pd.read_csv(
            source_path,
            sep=separator or cfg["business_rules"].get("csv_separator", ","),
            encoding=cfg["business_rules"].get("encoding", "utf-8-sig"),
            dtype=str,
            chunksize=chunksize,
        ),
        start=1,
    ):
        total_source_rows += len(chunk)
        normalized = normalize_chunk(chunk, datest_scope, allowed_weeks=allowed_weeks)
        total_output_rows += len(normalized)
        if normalized.empty:
            logger.info("Chunk %s: source_rows=%s output_rows=0", chunk_idx, len(chunk))
            continue
        for year, part in normalized.groupby("Fiscal Year", sort=False):
            by_year.setdefault(str(year), []).append(part.copy())
        logger.info("Chunk %s: source_rows=%s output_rows=%s", chunk_idx, len(chunk), len(normalized))
    return by_year, total_source_rows, total_output_rows


def write_full_rebuild(source_path: str, cfg: dict, logger: logging.Logger, dry_run: bool, chunksize: int, separator: str | None = None) -> int:
    datest_scope = read_datest_scope(cfg)
    logger.info("Datest scope from config/scarichi: %s", ", ".join(sorted(datest_scope)))
    logger.info("Full rebuild source: %s", source_path)
    by_year, total_source_rows, total_output_rows = collect_normalized_rows(source_path, cfg, datest_scope, logger, chunksize, separator=separator)
    if not by_year:
        logger.warning("No rows produced from source.")
        return 0

    written = 0
    pattern = cfg["parquet"]["sales_annual_pattern"]
    for year in sorted(by_year):
        year_df = pd.concat(by_year[year], ignore_index=True)
        year_df = year_df.groupby(KEY_COLUMNS + ["data_type"], as_index=False, sort=False)["Qty"].sum()[OUTPUT_COLUMNS]
        year_df = year_df.sort_values(KEY_COLUMNS + ["data_type"], kind="stable").reset_index(drop=True)
        output_path = Path(pattern.format(year=year))
        logger.info("Year %s full rebuild: rows=%s qty_sum=%s output=%s", year, len(year_df), int(year_df["Qty"].sum()), output_path)
        if not dry_run:
            atomic_write_parquet(year_df, output_path)
            written += 1

    logger.info("Source rows read: %s", total_source_rows)
    logger.info("Intermediate output rows: %s", total_output_rows)
    logger.info("Parquet files written: %s", written)
    return written


def write_incremental_update(source_path: str, cfg: dict, logger: logging.Logger, dry_run: bool, chunksize: int, n_weeks: int, separator: str | None = None) -> int:
    datest_scope = read_datest_scope(cfg)
    logger.info("Datest scope from config/scarichi: %s", ", ".join(sorted(datest_scope)))
    sep = separator or cfg["business_rules"].get("csv_separator", ",")
    latest_weeks, source_datests = read_latest_weeks(source_path, cfg, datest_scope, n_weeks, sep)
    if not latest_weeks:
        raise ValueError("No Fiscal Week found in update source after datest filtering.")
    latest_week_set = set(latest_weeks)
    logger.info("Update source: %s", source_path)
    logger.info("Weeks replaced in toto: %s", ", ".join(latest_weeks))
    logger.info("Datest present in the update source: %s", ", ".join(sorted(source_datests)))
    missing_datests = sorted(datest_scope - source_datests)
    if missing_datests:
        # Lo scarico BOXI puo' non coprire ancora un datest entrato da poco in scope
        # (caso reale: 028000 dopo lo split UK). Le loro righe gia' a parquet vengono
        # conservate invece di essere cancellate insieme alle settimane sostituite.
        logger.warning(
            "Datest in scope but absent from the update source, left untouched in the parquet: %s",
            ", ".join(missing_datests),
        )

    by_year, total_source_rows, total_output_rows = collect_normalized_rows(
        source_path, cfg, datest_scope, logger, chunksize, allowed_weeks=latest_week_set, separator=sep
    )
    if not by_year:
        logger.warning("No rows produced for latest weeks.")
        return 0

    written = 0
    pattern = cfg["parquet"]["sales_annual_pattern"]
    for year in sorted(by_year):
        new_df = pd.concat(by_year[year], ignore_index=True)
        new_df = new_df.groupby(KEY_COLUMNS + ["data_type"], as_index=False, sort=False)["Qty"].sum()[OUTPUT_COLUMNS]
        output_path = Path(pattern.format(year=year))
        if output_path.exists():
            old_df = pd.read_parquet(output_path)
            old_rows = len(old_df)
            # Solo i datest presenti nello scarico: quelli assenti tengono le loro righe.
            remove_mask = (
                old_df["Fiscal Week"].astype(str).isin(latest_week_set)
                & old_df["Client Datest"].astype(str).str.zfill(6).isin(source_datests)
                & old_df["data_type"].isin(SALES_DATA_TYPES)
            )
            removed_rows = int(remove_mask.sum())
            kept_df = old_df.loc[~remove_mask, OUTPUT_COLUMNS].copy()
        else:
            old_rows = 0
            removed_rows = 0
            kept_df = pd.DataFrame(columns=OUTPUT_COLUMNS)
            logger.warning("Missing existing parquet for year %s; creating it from update rows only.", year)

        final_df = pd.concat([kept_df, new_df], ignore_index=True)
        final_df = final_df.groupby(KEY_COLUMNS + ["data_type"], as_index=False, sort=False)["Qty"].sum()[OUTPUT_COLUMNS]
        final_df = final_df.sort_values(KEY_COLUMNS + ["data_type"], kind="stable").reset_index(drop=True)
        logger.info(
            "Year %s update: old_rows=%s removed_rows=%s new_rows=%s final_rows=%s qty_sum=%s output=%s",
            year,
            old_rows,
            removed_rows,
            len(new_df),
            len(final_df),
            int(final_df["Qty"].sum()),
            output_path,
        )
        if not dry_run:
            atomic_write_parquet(final_df, output_path)
            written += 1

    logger.info("Source rows read: %s", total_source_rows)
    logger.info("Intermediate update rows: %s", total_output_rows)
    logger.info("Parquet files written: %s", written)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Update GV sales parquet files.")
    parser.add_argument("--source", choices=["update", "historical", "custom"], default="update")
    parser.add_argument("--source-path", help="CSV path to use with --source custom.")
    parser.add_argument("--years", nargs="*", help="Optional fiscal years to keep, mostly useful with --source custom.")
    parser.add_argument(
        "--latest-weeks",
        type=int,
        default=0,
        help="Number of latest fiscal weeks to replace for --source update. 0 (default) replaces every fiscal week present in the update scarico.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without writing parquet.")
    parser.add_argument("--no-mail", action="store_true", help="Do not send S.A.M. status email.")
    parser.add_argument("--chunksize", type=int, default=250_000)
    args = parser.parse_args()

    cfg = load_config()
    logger = setup_logger(cfg["gv"]["log"], args.dry_run)
    try:
        logger.info(
            "Starting GV sales update | source=%s | latest_weeks=%s | dry_run=%s | chunksize=%s",
            args.source,
            args.latest_weeks,
            args.dry_run,
            args.chunksize,
        )
        if args.source == "custom":
            if not args.source_path:
                raise ValueError("--source-path is required with --source custom")
            source_path = args.source_path
        else:
            source_path = resolve_source_path(cfg, args.source)
        separator = detect_csv_separator(source_path, cfg["business_rules"].get("csv_separator", ","))
        logger.info("CSV separator detected: %r", separator)

        if args.source == "historical":
            written = write_full_rebuild(source_path, cfg, logger, args.dry_run, args.chunksize, separator=separator)
            mode_line = "Modalita: rebuild storico completo"
        elif args.source == "custom":
            written = write_full_rebuild(source_path, cfg, logger, args.dry_run, args.chunksize, separator=separator)
            mode_line = "Modalita: rebuild da CSV custom"
        else:
            written = write_incremental_update(source_path, cfg, logger, args.dry_run, args.chunksize, args.latest_weeks, separator=separator)
            mode_line = (
                "Modalita: update di tutte le settimane presenti nello scarico"
                if args.latest_weeks <= 0
                else f"Modalita: update ultime {args.latest_weeks} settimane"
            )
        logger.info("Completed GV sales update")
        send_update_status(
            pipeline_name="Sales",
            status="OK",
            lines=[
                "Update Sales GV completato correttamente.",
                mode_line,
                f"Sorgente: {source_path}",
                f"Dry-run: {args.dry_run}",
                f"Parquet scritti: {written}",
                f"Log: {getattr(logger, 'gv_log_path', '')}",
            ],
            log_path=getattr(logger, "gv_log_path", None),
            active=not args.no_mail,
        )
        return 0
    except Exception as exc:
        logger.exception("GV sales update failed")
        try:
            send_update_status(
                pipeline_name="Sales",
                status="ERRORE",
                lines=[
                    "Update Sales GV terminato con errore.",
                    f"Source: {args.source}",
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
