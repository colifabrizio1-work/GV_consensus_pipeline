from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from gv_config import load_config
from gv_samu import send_update_status

KEY_COLUMNS = ["Client Datest", "UPC", "Fiscal Week"]
APPROVED_COLUMN = "Forecast Approved (with COV)"
OUTPUT_COLUMNS = KEY_COLUMNS + ["Qty", "data_type", "snapshot_timestamp", "source_file", "source_last_modified"]


def setup_logger(log_dir: str, dry_run: bool) -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_dry_run" if dry_run else ""
    log_path = Path(log_dir) / f"update_forecast_gv_{timestamp}{suffix}.log"

    logger = logging.getLogger("update_forecast_gv")
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


def to_qty(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    has_comma = text.str.contains(",", regex=False, na=False)
    european = text.where(~has_comma, text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    qty = pd.to_numeric(european, errors="coerce").fillna(0)
    return qty.round().astype("int64")


def normalize_chunk(
    chunk: pd.DataFrame,
    datest_scope: set[str],
    snapshot_timestamp: str,
    source_path: Path,
    source_last_modified: str,
) -> pd.DataFrame:
    missing = [col for col in KEY_COLUMNS + [APPROVED_COLUMN] if col not in chunk.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")

    out = chunk[KEY_COLUMNS].copy()
    for col in KEY_COLUMNS:
        out[col] = out[col].astype(str).str.strip()
    out["Client Datest"] = out["Client Datest"].str.zfill(6)
    out = out[out["Client Datest"].isin(datest_scope)]
    out = out[~out["Fiscal Week"].str.lower().isin(["", "nan", "none", "nat"])]
    if out.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    approved = chunk.loc[out.index, APPROVED_COLUMN]
    out["Qty"] = to_qty(approved)
    out["data_type"] = "Forecast_approved"
    out["snapshot_timestamp"] = snapshot_timestamp
    out["source_file"] = source_path.name
    out["source_last_modified"] = source_last_modified
    out = out[out["Qty"] != 0]
    if out.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return out.groupby(KEY_COLUMNS + ["data_type", "snapshot_timestamp", "source_file", "source_last_modified"], as_index=False, sort=False)["Qty"].sum()[OUTPUT_COLUMNS]


def atomic_write_parquet(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    df.to_parquet(tmp_path, index=False, engine="pyarrow")
    os.replace(tmp_path, output_path)


def build_forecast_parquet(cfg: dict, logger: logging.Logger, dry_run: bool, chunksize: int) -> int:
    datest_scope = read_datest_scope(cfg)
    source_path = Path(cfg["scarichi"]["forecast"]["path"])
    output_path = Path(cfg["parquet"]["forecast"])
    snapshot_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_last_modified = datetime.fromtimestamp(source_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    logger.info("Datest scope from config/scarichi: %s", ", ".join(sorted(datest_scope)))
    logger.info("Reading source: %s", source_path)
    logger.info("Snapshot timestamp: %s", snapshot_timestamp)
    logger.info("Source last modified: %s", source_last_modified)

    parts: list[pd.DataFrame] = []
    total_source_rows = 0
    total_output_rows = 0

    for chunk_idx, chunk in enumerate(
        pd.read_csv(
            source_path,
            sep=cfg["business_rules"].get("csv_separator", ","),
            encoding=cfg["business_rules"].get("encoding", "utf-8-sig"),
            dtype=str,
            chunksize=chunksize,
        ),
        start=1,
    ):
        total_source_rows += len(chunk)
        normalized = normalize_chunk(chunk, datest_scope, snapshot_timestamp, source_path, source_last_modified)
        total_output_rows += len(normalized)
        if not normalized.empty:
            parts.append(normalized)
        logger.info("Chunk %s: source_rows=%s output_rows=%s", chunk_idx, len(chunk), len(normalized))

    if not parts:
        logger.warning("No rows produced from source.")
        return 0

    df = pd.concat(parts, ignore_index=True)
    df = df.groupby(
        KEY_COLUMNS + ["data_type", "snapshot_timestamp", "source_file", "source_last_modified"],
        as_index=False,
        sort=False,
    )["Qty"].sum()[OUTPUT_COLUMNS]
    df = df.sort_values(KEY_COLUMNS + ["data_type"], kind="stable").reset_index(drop=True)

    logger.info("Final rows: %s", len(df))
    logger.info("Qty sum: %s", int(df["Qty"].sum()))
    logger.info("Fiscal week range: %s-%s", df["Fiscal Week"].min(), df["Fiscal Week"].max())
    logger.info("Output latest parquet: %s", output_path)
    if not dry_run:
        atomic_write_parquet(df, output_path)
        logger.info("Parquet files written: 1")
    else:
        logger.info("Parquet files written: 0")

    logger.info("Source rows read: %s", total_source_rows)
    logger.info("Intermediate output rows: %s", total_output_rows)
    return 1 if not dry_run else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Update GV latest approved forecast parquet file.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without writing parquet.")
    parser.add_argument("--no-mail", action="store_true", help="Do not send S.A.M. status email.")
    parser.add_argument("--chunksize", type=int, default=250_000)
    args = parser.parse_args()

    cfg = load_config()
    logger = setup_logger(cfg["gv"]["log"], args.dry_run)
    try:
        logger.info("Starting GV forecast update | dry_run=%s | chunksize=%s", args.dry_run, args.chunksize)
        written = build_forecast_parquet(cfg, logger, args.dry_run, args.chunksize)
        logger.info("Completed GV forecast update")
        send_update_status(
            pipeline_name="Forecast",
            status="OK",
            lines=[
                "Update Forecast GV completato correttamente.",
                "Modalita: latest-only overwrite",
                f"Sorgente: {cfg['scarichi']['forecast']['path']}",
                f"Output: {cfg['parquet']['forecast']}",
                f"Dry-run: {args.dry_run}",
                f"Parquet scritti: {written}",
                f"Log: {getattr(logger, 'gv_log_path', '')}",
            ],
            log_path=getattr(logger, "gv_log_path", None),
            active=not args.no_mail,
        )
        return 0
    except Exception as exc:
        logger.exception("GV forecast update failed")
        try:
            send_update_status(
                pipeline_name="Forecast",
                status="ERRORE",
                lines=[
                    "Update Forecast GV terminato con errore.",
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
