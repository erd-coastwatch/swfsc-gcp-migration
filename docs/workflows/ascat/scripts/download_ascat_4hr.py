#!/usr/bin/env python3
"""
ASCAT-C 4-Hour Source Ingestion Pipeline.

This script identifies ASCAT-C 4-hour NetCDF files that are available online
but missing from the GCS archive, downloads only those missing files,
processes them, and uploads the results to GCS.

Design principles:
- Remote NOAA directory is the source of truth for available files
- GCS archive bucket is authoritative for what has already been processed
- The pipeline is idempotent and safe to re-run
- No date arguments are required

External dependencies:
- NetCDF Operators (NCO): ncks, ncra, nccopy

Typical usage:
    python download_ascat_4hr.py run --config config/config_update.yaml

Dry-run (no downloads, no file changes):
    python download_ascat_4hr.py run --dry-run --log-level DEBUG
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer

from src.ascatc_4hr_functions import (
    current_year,
    delete_files_in_directory,
    download_file,
    filter_files_by_year,
    load_config,
    local_4hr_archive_dir,
    local_4hr_stage_dir,
    process_ascat_4hr_file,
    scrape_remote_files,
    template_nc_path,
    upload_file_to_gcs,
)

logger = logging.getLogger(__name__)

app = typer.Typer(help="ASCAT 4-hour source ingestion pipeline")


def gcs_files(bucket_name: str, prefix: str, year: int) -> set[str]:
    """List processed ASCAT 4-hour filenames already in GCS.

    Checks both the current year and previous year (matching the two-year
    window used by local_files).

    Args:
        bucket_name: GCS bucket to list.
        prefix: Object prefix for the 4hr archive (e.g. 'edge/ASCAT/4hr').
        year: Target year.

    Returns:
        Set of upstream-format filenames (e.g. 'AS2025010100Cas_WW.nc').
    """
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    output: set[str] = set()

    for yr in {year, year - 1}:
        blob_prefix = f"{prefix.strip('/')}/{yr}/"
        for blob in bucket.list_blobs(prefix=blob_prefix):
            fname = Path(blob.name).name  # ascatc_YYYYMMDDHH_XX_WW.nc
            try:
                ts = fname.split("_")[1]   # YYYYMMDDHH
                dt = datetime.strptime(ts, "%Y%m%d%H").replace(tzinfo=timezone.utc)
                doy = f"{dt.timetuple().tm_yday:03d}"
                updn = fname.split("_")[2]
                converted = f"AS{dt.year}{doy}{dt.hour:02d}C{updn}_WW.nc"
                output.add(converted)
            except Exception:
                logger.debug("Skipping malformed GCS blob: %s", blob.name)

    return output


@app.command()
def run(
    config: Path = typer.Option(
        "config/config_update.yaml",
        help="YAML configuration file",
    ),
    year: int = typer.Option(
        default_factory=current_year,
        help="Year to compare against GCS archive (UTC, defaults to current year)",
    ),
    dry_run: bool = typer.Option(False, help="Log actions only"),
    log_level: str = typer.Option(
        "INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    ),
):
    """Download, process, and upload missing ASCAT 4-hour NetCDF files.

    This command:
    1. Scrapes the remote ASCAT 4-hour directory
    2. Compares against the GCS archive bucket to find missing files
    3. Downloads only missing files
    4. Processes each file (wind stress, curl, Ekman, etc.)
    5. Uploads archive and publish copies to GCS
    6. Caches the result locally for the composite step

    The command is safe to re-run and requires no date arguments.
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    cfg = load_config(config)

    work_dir = local_4hr_stage_dir(cfg)
    results_dir = local_4hr_archive_dir(cfg)
    template_nc = template_nc_path(cfg)

    work_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    if not dry_run:
        delete_files_in_directory(work_dir)

    # ------------------------------------------------------------------
    # Discover remote files and compare against GCS archive
    # ------------------------------------------------------------------
    remote_files_all = scrape_remote_files(cfg.source_url)
    remote_files = filter_files_by_year(remote_files_all, year)

    logger.info("Checking GCS archive for already-processed files...")
    archived_files = gcs_files(cfg.gcs.work_bucket, cfg.prefixes.archive_4hr, year)

    missing_files = sorted(remote_files - archived_files)
    missing_files = [f for f in missing_files if "_WW.nc" in f]

    if not missing_files:
        logger.info("GCS archive is up to date — nothing to process.")
        raise typer.Exit(0)

    logger.info("Found %d missing ASCAT 4-hour files", len(missing_files))

    if not template_nc.exists():
        logger.error("Missing template file: %s", template_nc)
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # Process each missing file
    # ------------------------------------------------------------------
    for fname in missing_files:
        logger.info("Starting processing for %s", fname)

        remote_url = f"{cfg.source_url}/{fname}"
        source_nc = work_dir / fname

        download_file(remote_url, source_nc, dry_run)

        # Parse date components from filename (e.g. AS202500100Cas_WW.nc)
        yr   = int(fname[2:6])
        doy  = int(fname[6:9])
        hour = int(fname[9:11])

        file_date = (
            datetime(yr, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1)
        ).replace(hour=hour)

        updn = fname.split("_")[0][-2:]  # 'as' or 'ds'
        output_name = f"ascatc_{file_date:%Y%m%d%H}_{updn}_WW.nc"
        output_nc = work_dir / output_name

        if not dry_run:
            process_ascat_4hr_file(
                source_nc=source_nc,
                template_nc=template_nc,
                output_nc=output_nc,
                file_date=file_date,
            )

        # Cache locally so the composite step can find it
        year_dir = results_dir / str(yr)
        year_dir.mkdir(parents=True, exist_ok=True)
        archived_nc = year_dir / output_name

        if dry_run:
            logger.info("dry_run: would archive %s", archived_nc)
        else:
            shutil.move(output_nc, archived_nc)
            if source_nc.exists():
                source_nc.unlink()

        # Upload to GCS
        archive_object = f"{cfg.prefixes.archive_4hr}/{yr}/{output_name}"
        publish_object = f"{cfg.prefixes.publish_4hr}/{yr}/{output_name}"

        upload_file_to_gcs(
            local_path=archived_nc if not dry_run else output_nc,
            bucket_name=cfg.gcs.work_bucket,
            object_name=archive_object,
            dry_run=dry_run,
        )

        upload_file_to_gcs(
            local_path=archived_nc if not dry_run else output_nc,
            bucket_name=cfg.gcs.prod_bucket,
            object_name=publish_object,
            dry_run=dry_run,
        )

        logger.info("Completed %s", output_name)

    logger.info("ASCAT 4-hour ingestion completed successfully")


if __name__ == "__main__":
    app()