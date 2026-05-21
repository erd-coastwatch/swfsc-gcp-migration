# ascat metop-c 4hr file processing functions

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Set

import math
import numpy as np
import numpy.ma as ma
import requests
import yaml
from bs4 import BeautifulSoup
from netCDF4 import Dataset
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google.cloud import storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GCSConfig:
    """Bucket configuration for ASCAT products."""

    work_bucket: str
    prod_bucket: str


@dataclass(frozen=True)
class PrefixConfig:
    """GCS object prefixes for archive and publish targets."""

    archive_4hr: str
    publish_4hr: str


@dataclass(frozen=True)
class Config:
    """Top-level application configuration.

    Attributes:
        base_dir: Root directory of the ASCAT processing tree.
        data_dir: Local data/work area on the VM.
        logs_dir: Local logs directory.
        templates_dir: Directory containing NetCDF templates.
        source_url: Base URL for remote 4-hour ASCAT files.
        gcs: Work/prod bucket configuration.
        prefixes: Archive/publish prefixes for this product family.
    """

    base_dir: Path
    data_dir: Path
    logs_dir: Path
    templates_dir: Path
    source_url: str
    gcs: GCSConfig
    prefixes: PrefixConfig


def load_config(path: Path) -> Config:
    """Load application configuration from YAML.

    Expected YAML structure:

    base_dir: /home/edge/ascat

    paths:
      data: data
      logs: logs
      templates: templates

    source:
      base_url: https://.../ascat/netcdf

    gcs:
      work_bucket: YOUR_WORK_BUCKET
      prod_bucket: YOUR_PRODUCTION_BUCKET

    prefixes:
      archive_4hr: ascat/data/4hr
      publish_4hr: edge/ASCAT/4hr
    """
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    base = Path(raw["base_dir"])

    return Config(
        base_dir=base,
        data_dir=base / raw["paths"]["data"],
        logs_dir=base / raw["paths"]["logs"],
        templates_dir=base / raw["paths"]["templates"],
        source_url=f"{raw['source']['base_url'].rstrip('/')}/4hr",
        gcs=GCSConfig(
            work_bucket=raw["gcs"]["work_bucket"],
            prod_bucket=raw["gcs"]["prod_bucket"],
        ),
        prefixes=PrefixConfig(
            archive_4hr=raw["prefixes"]["archive_4hr"].strip("/"),
            publish_4hr=raw["prefixes"]["publish_4hr"].strip("/"),
        ),
    )


# -----------------------------------------------------------------------------
# Local path helpers
# -----------------------------------------------------------------------------


def local_4hr_stage_dir(cfg: Config) -> Path:
    """Local scratch/staging directory for downloaded and processed 4hr files."""
    return cfg.data_dir / "staging" / "4hr"


def local_4hr_archive_dir(cfg: Config) -> Path:
    """Local VM-side archive/cache for processed 4hr files."""
    return cfg.data_dir / "results" / "4hr"


def template_nc_path(cfg: Config) -> Path:
    """Path to the ASCAT template NetCDF."""
    return cfg.templates_dir / "ascat_c.nc"


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def delete_files_in_directory(directory: Path) -> None:
    """Delete all files in a directory, preserving subdirectories."""
    if not directory.exists():
        raise FileNotFoundError(f"Directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    for path in directory.iterdir():
        if path.is_file():
            logger.debug("Deleting file: %s", path)
            path.unlink()


def ensure_directory(path: Path, dry_run: bool = False) -> None:
    """Create a directory if needed."""
    logger.debug("Ensuring directory exists: %s", path)
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)


def archive_object_name(prefix: str, year: int, filename: str) -> str:
    """Build GCS object path for archived 4hr output."""
    return f"{prefix.strip('/')}/{year}/{filename}"


def publish_object_name(prefix: str, year: int, filename: str) -> str:
    """Build GCS object path for published 4hr output."""
    return f"{prefix.strip('/')}/{year}/{filename}"


def log_gcs_targets_for_4hr(
    cfg: Config,
    output_name: str,
    year: int,
) -> None:
    """Log the intended archive/publish GCS targets.

    This is a placeholder for the next refactor step where actual GCS uploads
    will replace the legacy SCP publish flow.
    """
    archive_obj = archive_object_name(cfg.prefixes.archive_4hr, year, output_name)
    publish_obj = publish_object_name(cfg.prefixes.publish_4hr, year, output_name)

    logger.info(
        "Archive target: gs://%s/%s",
        cfg.gcs.work_bucket,
        archive_obj,
    )
    logger.info(
        "Publish target: gs://%s/%s",
        cfg.gcs.prod_bucket,
        publish_obj,
    )


def process_ascat_4hr_file(
    source_nc: Path,
    template_nc: Path,
    output_nc: Path,
    file_date: datetime,
    rho_air: float = 1.22,
    rho_water: float = 1025.0,
    omega: float = 7.29e-5,
) -> None:
    """Process a single ASCAT-C 4-hour NetCDF file.

    This function:
    - Reads ASCAT wind variables
    - Computes wind stress, divergence, curl
    - Computes Ekman currents and upwelling
    - Writes results into a CoastWatch-compatible NetCDF
    - Applies time and metadata updates
    """
    logger.info("Processing %s", source_nc.name)

    with Dataset(source_nc, "r") as nc:
        xlon = nc.variables["cols"][:]
        ylat = nc.variables["rows"][:]
        u_wind = nc.variables["u_wind"][0, 0, :, :]
        v_wind = nc.variables["v_wind"][0, 0, :, :]
        wind_sp = nc.variables["windspeed"][0, 0, :, :]
        direction = nc.variables["direction"][0, 0, :, :]

    shutil.copy2(template_nc, output_nc)

    with Dataset(output_nc, "a") as dst:
        u10ref = np.array([0, 1, 2, 5, 10, 15, 20, 25, 30, 35, 40, 45])
        cdref = np.array(
            [1, 0.99, 0.98, 1.03, 1.30, 1.56, 1.80, 2.04, 2.28, 2.52, 2.76, 3.0]
        ) * 1e-3

        cd = np.interp(wind_sp, u10ref, cdref)
        taux = rho_air * cd * wind_sp * u_wind
        tauy = rho_air * cd * wind_sp * v_wind

        delx = np.ma.median(np.diff(xlon))
        dely = np.ma.median(np.diff(ylat))

        xlon_2d, ylat_2d = np.meshgrid(xlon, ylat)

        fee = np.cos(2 * math.pi * ylat_2d / 360)
        dx = delx * 1.11e5 * fee
        dy = dely * 1.11e5

        u_filled = u_wind.filled(0)
        v_filled = v_wind.filled(0)
        du_dy, du_dx = np.gradient(u_filled)
        dv_dy, dv_dx = np.gradient(v_filled)
        divw = (du_dx / dx) + (dv_dy / dy)

        taux_filled = taux.filled(0)
        tauy_filled = tauy.filled(0)
        dtaux_dy, dtaux_dx = np.gradient(taux_filled)
        dtauy_dy, dtauy_dx = np.gradient(tauy_filled)
        curl = (dtauy_dx / dx) - (dtaux_dy / dy)
        curl = ma.masked_array(curl, mask=taux.mask)

        lat_mask = ma.masked_inside(ylat_2d, -1.0, 1.0)
        fspin = 2 * omega * np.sin(np.deg2rad(lat_mask))

        eld = 4.3 * wind_sp / np.sqrt(np.abs(np.sin(np.deg2rad(lat_mask))))

        uekm = tauy / (eld * fspin * rho_water)
        vekm = -taux / (eld * fspin * rho_water)
        wekm = curl / (fspin * rho_water)

        dst["time"][:] = [file_date.timestamp()]
        dst["wind_speed"][0, 0, :, :] = ma.masked_invalid(wind_sp)
        dst["wind_direction"][0, 0, :, :] = ma.masked_invalid(direction)
        dst["wind_u"][0, 0, :, :] = ma.masked_invalid(u_wind)
        dst["wind_v"][0, 0, :, :] = ma.masked_invalid(v_wind)
        dst["stress_u"][0, 0, :, :] = ma.masked_invalid(taux)
        dst["stress_v"][0, 0, :, :] = ma.masked_invalid(tauy)
        dst["stress"][0, 0, :, :] = ma.masked_invalid(np.hypot(taux, tauy))
        dst["curl"][0, 0, :, :] = ma.masked_invalid(curl)
        dst["divergence"][0, 0, :, :] = ma.masked_invalid(divw)
        dst["ekman_current_u"][0, 0, :, :] = ma.masked_invalid(uekm)
        dst["ekman_current_v"][0, 0, :, :] = ma.masked_invalid(vekm)
        dst["ekman_current"][0, 0, :, :] = np.hypot(uekm, vekm)
        dst["ekman_upwelling"][0, 0, :, :] = ma.masked_invalid(wekm)

                # --------------------------------------------------------------
        # Global metadata corrections to match on-prem 4hr product
        # --------------------------------------------------------------
        dst.id = "erdQCwind4hour"
        dst.time_coverage_duration = "P4H"
        dst.time_coverage_resolution = "P1D"

        dst.title = (
            "Merge Windspeed, Stress, Curl, Divergence, and Ekman Upwelling, "
            "Metop-C ASCAT, 0.25 degree, Global, Near Real Time, "
            "2020-present, 4 hour"
        )

        dst.institution = (
            "NOAA/NESDIS/CoastWatch/West Coast Node, NOAA/NMFS/SWFSC/ERD"
        )

        dst.creator_name = (
            "NOAA/NESDIS/CoastWatch/West Coast Node, NOAA/NMFS/SWFSC/ERD"
        )

    logger.info("Finished processing %s", output_nc.name)


def scrape_remote_files(url: str) -> Set[str]:
    """Scrape the remote ASCAT 4-hour directory with retries."""
    logger.info("Scraping remote directory: %s", url)

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)

    with requests.Session() as session:
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        response = session.get(url, timeout=30)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    files = {
        a["href"]
        for a in soup.find_all("a", href=True)
        if a["href"].endswith("_WW.nc") and "C" in a["href"]
    }

    logger.info("Found %d remote files", len(files))
    return files


def local_files(results_dir: Path, year: int) -> Set[str]:
    """List locally archived ASCAT 4-hour files and convert them to upstream format.

    Input format:
        ascatc_YYYYMMDDHH_WW.nc

    Output format:
        ASYYYYJJJHHCas_WW.nc
        ASYYYYJJJHHCds_WW.nc

    depending on the up/down suffix encoded in the processed filename stem.
    """
    output: Set[str] = set()
    years = {year, year - 1}

    for yr in years:
        year_dir = results_dir / str(yr)
        if not year_dir.exists():
            continue

        for path in year_dir.glob("ascatc_*.nc"):
            try:
                ts = path.stem.split("_")[1]  # YYYYMMDDHH
                dt = datetime.strptime(ts, "%Y%m%d%H").replace(tzinfo=timezone.utc)

                doy = f"{dt.timetuple().tm_yday:03d}"
                hour = f"{dt.hour:02d}"

                updn = path.stem.split("_")[2]
                converted = f"AS{dt.year}{doy}{hour}C{updn}_WW.nc"
                output.add(converted)

            except Exception:
                logger.debug("Skipping malformed local file: %s", path.name)
                continue

    return output


def filter_files_by_year(
    files: Set[str],
    target_year: int,
) -> Set[str]:
    """Filter ASCAT filenames to a two-year window."""
    allowed_years = {target_year, target_year - 1}
    filtered: Set[str] = set()

    for fname in files:
        try:
            year = int(fname[2:6])
        except (ValueError, IndexError):
            logger.debug("Skipping malformed filename: %s", fname)
            continue

        if year in allowed_years:
            filtered.add(fname)

    return filtered


def download_file(url: str, dest: Path, dry_run: bool) -> None:
    """Download a NetCDF file from a remote URL."""
    logger.info("Downloading %s", dest.name)
    if dry_run:
        return

    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def current_year() -> int:
    """Return the current UTC year."""
    return datetime.now(timezone.utc).year


def upload_file_to_gcs(local_path: Path, bucket_name: str, object_name: str, dry_run: bool) -> None:
    """Upload a local product file to GCS unless dry-run mode is enabled."""
    logger.info("Uploading to gs://%s/%s", bucket_name, object_name)
    if dry_run:
        return

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_filename(str(local_path))