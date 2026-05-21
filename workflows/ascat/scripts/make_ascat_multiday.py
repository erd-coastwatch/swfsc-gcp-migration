#!/usr/bin/env python3
"""
ASCAT-C Multi-day and Monthly Composite Generator
=================================================

Generate CoastWatch-compliant ASCAT-C wind composites from locally available
NetCDF inputs.

This script produces:
- N-day composites (e.g., 1-, 3-, 7-day) from 4-hourly ASCAT-C files
- Monthly composites from daily ASCAT-C files

The script is designed for:
- Near–real-time (NRT) operations
- Historical backfill processing
- NOAA CoastWatch / ERD production environments

All processing follows strict CoastWatch conventions:
- All timestamps are normalized to UTC
- Composite center times are deterministic
- CF-style time metadata is enforced
- Outputs are compressed and archived in a stable directory layout

External dependencies:
- NetCDF Operators (NCO): ncks, ncra, nccopy

Typical usage:
    python ascat_make_multday.py --date 2025-06-01
    python ascat_make_multday.py --date 2025-06-01 --make-month
    python ascat_make_multday.py --date 2023-08-15 --backfill --dry-run
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import List

import typer
from netCDF4 import Dataset

# import general helper functions
from src.ascatc_multiday_functions import (
    all_dates_in_month,
    center_date,
    composite_dates,
    find_source_files,
    load_config,
    local_results_dir,
    local_work_dir,
    run_cmd,
    upload_to_erddap,
)

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


app = typer.Typer(
    help="ASCAT-C CoastWatch multi-day and monthly composite generator",
    add_completion=False,
)


@app.command()
def run(
    date: datetime = typer.Option(..., help="End date (YYYY-MM-DD, UTC)"),
    config: Path = typer.Option(
        "config/config_composite.yaml", help="YAML configuration file"
    ),
    overwrite: bool = typer.Option(False, help="Overwrite existing outputs"),
    backfill: bool = typer.Option(False, help="Use backfill work directory"),
    make_month: bool = typer.Option(False, help="Generate monthly composite"),
    dry_run: bool = typer.Option(False, help="Log actions only"),
    log_level: str = typer.Option(
        "INFO", help="DEBUG, INFO, WARNING, ERROR"
    ),
) -> None:
    """
    Generate ASCAT-C composites for a given end date.

    Operational steps:
    1. Identify required input files
    2. Normalize time dimension with ncks
    3. Average inputs using ncra
    4. Apply CoastWatch time metadata
    5. Compress with nccopy
    6. Archive to results directory
    7. Publish to ERDDAP GCS bucket

    Examples:
        NRT daily run:
            ascat_make_multday.py --date 2025-06-01

        Monthly composite:
            ascat_make_multday.py --date 2025-06-01 --make-month

        Backfill dry-run:
            ascat_make_multday.py --date 2023-08-15 --backfill --dry-run
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    cfg = load_config(config)
    results_dir = local_results_dir(cfg)
    work_dir = local_work_dir(cfg, backfill=backfill)
    work_dir.mkdir(parents=True, exist_ok=True)

    end_date = date
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)
    else:
        end_date = end_date.astimezone(UTC)

    year = end_date.year
    composite_windows = ["m"] if make_month else cfg.composite_days

    for window in composite_windows:
        logger.info("Starting composite window: %s", window)

        if window == "m":
            dates = all_dates_in_month(end_date)
            archive_dir = results_dir / "mday"
            out_name = f"ascatc_{max(dates):%Y%m}_monthly_WW.nc"
        else:
            dates = composite_dates(end_date, int(window))
            archive_dir = results_dir / f"{window}day" / f"{year}"
            out_name = (
                f"ascatc_{min(dates):%Y%m%d}_"
                f"{max(dates):%Y%m%d}_WW.nc"
            )

        archive_dir.mkdir(parents=True, exist_ok=True)
        out_path = archive_dir / out_name

        if out_path.exists() and not overwrite:
            logger.warning("Output exists, skipping: %s", out_path)
            continue

        files = find_source_files(results_dir, dates, window == "m")

        if window != "m":
            expected_files = 1
        else:
            expected_files = 1

        if len(files) < expected_files:
            logger.warning("Incomplete day: %d files", len(files))
            continue

        center = center_date(dates, make_month=(window == "m"))

        out_path = archive_dir / out_name

        if out_path.exists() and not overwrite:
            logger.warning("Results file exists %s", out_path)
            continue

        logger.info(
            "Building %s-day composite (%d files)",
            window,
            len(files),
        )

        work_files: List[Path] = []

        for src in files:
            dst = work_dir / src.name

            run_cmd(
                [
                    "ncks",
                    "-O",
                    "--mk_rec_dmn",
                    "time",
                    str(src),
                    str(dst),
                ],
                dry_run,
            )

            work_files.append(dst)

        temp_mean = work_dir / "temp_mean.nc"
        run_cmd(
            ["ncra", "-O", *map(str, work_files), str(temp_mean)],
            dry_run,
        )

        if not dry_run:
            with Dataset(temp_mean, "a") as nc:
                nc["time"][:] = center.timestamp()

                # Match on-prem global metadata
                nc.institution = (
                    "NOAA/NESDIS/CoastWatch/West Coast Node, NOAA/NMFS/SWFSC/ERD"
                )
                nc.creator_name = (
                    "NOAA/NESDIS/CoastWatch/West Coast Node, NOAA/NMFS/SWFSC/ERD"
                )

                if make_month:
                    nc.id = "erdQCwindmday"
                    nc.time_coverage_duration = "P1M"
                    nc.time_coverage_resolution = "P1M"
                    nc.title = (
                        "Merge Windspeed, Stress, Curl, Divergence, and "
                        "Ekman Upwelling, Metop-C ASCAT, 0.25 degree, Global, "
                        "Near Real Time, 2020-present, Monthly Composite"
                    )

                else:
                    nc.id = f"erdQCwind{window}day"
                    nc.time_coverage_duration = f"P{window}D"
                    nc.time_coverage_resolution = "P1D"
                    nc.title = (
                        "Merge Windspeed, Stress, Curl, Divergence, and "
                        f"Ekman Upwelling, Metop-C ASCAT, 0.25 degree, Global, "
                        f"Near Real Time, 2020-present, {window}-Day Composite"
                    )


        copy_path = work_dir / out_name
        run_cmd(
            [
                "nccopy",
                "-u",
                "-w",
                "-c", "time/1,altitude/1,latitude/540,longitude/1080",
                f"-d{cfg.nccopy_level}",
                str(temp_mean),
                str(copy_path),
            ],
            dry_run,
        )

        if dry_run:
            logger.info("dry_run: would archive %s", out_path)
        else:
            shutil.move(copy_path, out_path)
            logger.info("Archived %s", out_path)

            upload_to_erddap(
                path=out_path,
                cfg=cfg,
                dry_run=dry_run,
                year=year,
                window=window,
            )

        for f in work_files:
            f.unlink(missing_ok=True)
        temp_mean.unlink(missing_ok=True)

        logger.info("Finished %s-day composite", window)


if __name__ == "__main__":
    app()