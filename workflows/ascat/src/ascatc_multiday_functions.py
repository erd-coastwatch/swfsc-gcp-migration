# ascat metop-c multi-day composites functions

from __future__ import annotations

import calendar
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Iterable, List
import yaml

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

LOGGER_NAME = "ascat"
logger = logging.getLogger(LOGGER_NAME)

UTC = timezone.utc

# -----------------------------------------------------------------------------
# Configuration model
# -----------------------------------------------------------------------------


@dataclass
class GCSConfig:
    """Configuration for GCS archive / publish targets.

    Attributes:
        work_bucket: Bucket used for archive/work storage.
        prod_bucket: Bucket used for published outputs.
    """
    work_bucket: str
    prod_bucket: str


@dataclass
class Config:
    """
    Runtime configuration loaded from YAML.

    Attributes:
        base_dir: Root directory for ASCAT processing.
        data_dir: Local data directory for working/intermediate files.
        logs_dir: Local logs directory.
        templates_dir: Local templates directory.
        composite_days: Composite windows to generate.
        gcs: GCS bucket configuration.
        prefixes: Prefix mapping for archive and publish targets.
        nccopy_level: Compression level passed to nccopy (-d flag).
    """

    base_dir: Path
    data_dir: Path
    logs_dir: Path
    templates_dir: Path
    composite_days: List[int]
    gcs: GCSConfig
    prefixes: dict
    nccopy_level: int


# -----------------------------------------------------------------------------
# Configuration / system helpers
# -----------------------------------------------------------------------------


def load_config(path: Path) -> Config:
    """
    Load YAML configuration into a Config object.

    Args:
        path: Path to YAML configuration file.

    Returns:
        Parsed Config instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        KeyError: If required keys are missing.
    """
    with path.open() as f:
        raw = yaml.safe_load(f)

    base = Path(raw["base_dir"])

    return Config(
        base_dir=base,
        data_dir=base / raw["paths"]["data"],
        logs_dir=base / raw["paths"]["logs"],
        templates_dir=base / raw["paths"]["templates"],
        composite_days=list(raw["composite_days"]),
        gcs=GCSConfig(**raw["gcs"]),
        prefixes=raw["prefixes"],
        nccopy_level=int(raw["nccopy_level"]),
    )


def run_cmd(cmd: List[str], dry_run: bool) -> None:
    """
    Execute a shell command with logging and dry-run support.

    Args:
        cmd: Command and arguments as a list.
        dry_run: If True, log but do not execute.

    Raises:
        subprocess.CalledProcessError: If command execution fails.
    """
    logger.debug("CMD: %s", " ".join(cmd))
    if not dry_run:
        subprocess.run(cmd, check=True)


def local_results_dir(cfg: Config) -> Path:
    """
    Return the local results/cache root.

    Expected layout:
        data/results/4hr/<year>/*.nc
        data/results/1day/<year>/*.nc
        data/results/3day/<year>/*.nc
        data/results/7day/<year>/*.nc
        data/results/mday/*.nc
    """
    return cfg.data_dir / "results"


def local_work_dir(cfg: Config, backfill: bool = False) -> Path:
    """
    Return the local working directory.

    Args:
        cfg: Runtime configuration.
        backfill: If True, use the backfill work directory.

    Returns:
        Path to working directory.
    """
    return cfg.data_dir / ("work_bk" if backfill else "work")


# -----------------------------------------------------------------------------
# Date / time utilities (CoastWatch rules)
# -----------------------------------------------------------------------------


def composite_dates(end_date: datetime, days: int) -> List[datetime]:
    """
    Generate UTC datetimes for an N-day composite window.

    The returned list includes `end_date` and extends backwards in whole days.

    Args:
        end_date: End of composite window (UTC).
        days: Length of composite window in days.

    Returns:
        List of UTC datetimes, newest first.

    Example:
        >>> composite_dates(datetime(2025, 6, 3, tzinfo=UTC), 3)
        [2025-06-03, 2025-06-02, 2025-06-01]
    """
    end_date = end_date.astimezone(UTC)
    return [end_date - timedelta(days=i) for i in range(days)]


def center_date(
    dates: Iterable[datetime],
    make_month: bool = False,
) -> datetime:
    """
    Compute the CoastWatch-compliant center time of a composite.

    Rules:
    - Multi-day composites:
        * Center = midpoint date
        * Time fixed to 12:00 UTC
    - Monthly composites:
        * Center = 16th day of month
        * Time fixed to 00:00 UTC

    Args:
        dates: Iterable of datetime objects defining the composite window.
        make_month: If True, apply monthly center rules.

    Returns:
        Timezone-aware UTC datetime.

    Raises:
        ValueError: If `dates` is empty.

    Examples:
        >>> dates = [
        ...   datetime(2025, 6, 1, tzinfo=UTC),
        ...   datetime(2025, 6, 2, tzinfo=UTC),
        ...   datetime(2025, 6, 3, tzinfo=UTC),
        ... ]
        >>> center_date(dates)
        datetime(2025, 6, 2, 12, 0, tzinfo=datetime.timezone.utc)

        >>> center_date(dates, make_month=True)
        datetime(2025, 6, 16, 0, 0, tzinfo=datetime.timezone.utc)
    """
    dates_list = sorted(
        d.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        for d in dates
    )

    if not dates_list:
        raise ValueError("dates must not be empty")

    if make_month:
        ref = dates_list[0]
        return ref.replace(day=16, hour=0)

    else:
        # CoastWatch WCN convention: midpoint rounded toward newer date
        return dates_list[len(dates_list) // 2].replace(hour=12)


def all_dates_in_month_OLD(end_date: datetime) -> List[datetime]:
    """
    Return UTC datetimes for every day in the target month.
    """
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)

    today = datetime.now(UTC)

    if (end_date.year, end_date.month) == (today.year, today.month):
        first = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last = first - timedelta(days=1)
        year, month = last.year, last.month
    else:
        year, month = end_date.year, end_date.month

    _, last_day = calendar.monthrange(year, month)

    return [
        datetime(year, month, day, tzinfo=UTC)
        for day in range(1, last_day + 1)
    ]


def all_dates_in_month(date_val: datetime) -> List[datetime]:
    """
    Return UTC datetimes for every day in the month.
    """
    current = datetime(date_val.year, date_val.month, 1, tzinfo=timezone.utc)
    target_month = current.month
    dates = []

    while current.month == target_month:
        dates.append(current)
        current += timedelta(days=1)

    return dates


# -----------------------------------------------------------------------------
# File discovery
# -----------------------------------------------------------------------------


def find_source_files(
    results_dir: Path,
    dates: Iterable[date | datetime],
    make_month: bool,
) -> List[Path]:
    """
    Locate required NetCDF input files for a composite.

    Args:
        results_dir: Base results directory.
        dates: Dates required for the composite.
        make_month: Select daily (monthly) or 4-hourly inputs.

    Returns:
        Sorted list of NetCDF file paths.

    Raises:
        FileNotFoundError: If expected directories are missing.
    """
    files: List[Path] = []

    for d in dates:
        year = d.year
        subdir = "1day" if make_month else "4hr"
        year_dir = results_dir / subdir / f"{year}"

        if not year_dir.exists():
            raise FileNotFoundError(f"Missing directory: {year_dir}")

        files.extend(sorted(year_dir.glob(f"ascatc_{d:%Y%m%d}*.nc")))

    return files


def publish_prefix_for_window(cfg: Config, window: str | int) -> str:
    """
    Return the GCS publish prefix for a composite window.
    """
    if window == "m":
        return cfg.prefixes["publish_mday"]

    window = int(window)
    if window == 1:
        return cfg.prefixes["publish_1day"]
    if window == 3:
        return cfg.prefixes["publish_3day"]
    if window == 7:
        return cfg.prefixes["publish_7day"]

    raise ValueError(f"Unsupported composite window: {window}")


def upload_to_erddap(
    path: Path,
    cfg: Config,
    dry_run: bool,
    year: int,
    window: str | int,
) -> None:
    """
    Upload composite output to the production ERDDAP bucket only.
    """
    prefix = publish_prefix_for_window(cfg, window)

    if window == "m":
        dest = f"gs://{cfg.gcs.prod_bucket}/{prefix}/{path.name}"
    else:
        dest = f"gs://{cfg.gcs.prod_bucket}/{prefix}/{year}/{path.name}"

    logger.info("Uploading to %s", dest)
    if not dry_run:
        subprocess.run(["gsutil", "cp", str(path), dest], check=True)