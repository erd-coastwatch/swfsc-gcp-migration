"""
make_nsidc_daily.py

Worker for NSIDC Sea Ice Concentration CDR daily files.

For each pole and each date in the requested window:
  1. Scrapes the NSIDC HTTP directory for .nc files matching the date.
  2. Skips files already present in GCS.
  3. Downloads matching files to a unique temp path in /tmp/work.
  4. Compresses with nccopy -d<level>.
  5. Uploads to gs://<bucket>/<prefix><pole>/daily/<year>/<fname>.
  6. Deletes the local temp file.

All URLs, GCS paths, poles, and compression settings come from the
config dict passed in by the controller.
"""

import logging
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from google.cloud import storage

log = logging.getLogger(__name__)

# ── NCO binary ────────────────────────────────────────────────────────────────
NCCOPY = shutil.which("nccopy")
if not NCCOPY:
    raise EnvironmentError("nccopy not found in PATH — is netcdf-bin installed?")


# ── GCS helpers ───────────────────────────────────────────────────────────────

def list_gcs_blobs(bucket_name: str, prefix: str) -> set[str]:
    """Return the set of blob names under prefix."""
    client = storage.Client()
    return {b.name for b in client.bucket(bucket_name).list_blobs(prefix=prefix)}


def gcs_upload(local_path: Path, bucket_name: str, blob_name: str) -> None:
    """Upload a compressed local NetCDF file to GCS."""
    storage.Client().bucket(bucket_name).blob(blob_name).upload_from_filename(str(local_path))
    log.info("local → GCS  %s → gs://%s/%s", local_path.name, bucket_name, blob_name)


# ── NSIDC HTTP scraping ───────────────────────────────────────────────────────

def scrape_nc_files(url: str) -> list[str]:
    """Return sorted list of .nc filenames linked from an NSIDC directory page."""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.error("Failed to scrape %s: %s", url, exc)
        return []
    soup = BeautifulSoup(r.content, "html.parser")
    return sorted(
        ln["href"] for ln in soup.find_all("a", href=True)
        if ln["href"].endswith(".nc")
    )


def scrape_year_dirs(url: str) -> list[str]:
    """Return sorted list of numeric year directory names from an NSIDC listing."""
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.error("Failed to scrape year dirs at %s: %s", url, exc)
        return []
    soup = BeautifulSoup(r.content, "html.parser")
    return sorted(
        ln["href"].strip("/") for ln in soup.find_all("a", href=True)
        if ln["href"].strip("/").isdigit()
    )


# ── Download + compress ───────────────────────────────────────────────────────

def download_compress(work_dir: Path, src_url: str, fname: str, compression_level: int) -> Optional[Path]:
    """
    Download fname from src_url into work_dir and compress with nccopy.

    Uses a UUID-suffixed temp file for the raw download so interrupted runs
    never leave a partially-written file at the final work path.

    Returns the path to the compressed file, or None on failure.
    """
    unique_id  = uuid.uuid4().hex[:8]
    temp_path  = work_dir / f"{fname}.{unique_id}.tmp"
    work_path  = work_dir / fname
    file_url   = f"{src_url.rstrip('/')}/{fname}"

    try:
        log.info("Downloading %s", fname)
        with requests.get(file_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(r.raw, f)

        log.info("Compressing %s (level %d)", fname, compression_level)
        subprocess.run(
            [NCCOPY, f"-d{compression_level}", str(temp_path), str(work_path)],
            check=True,
            capture_output=True,
        )
        return work_path

    except Exception as exc:
        log.error("Failed to download/compress %s: %s", fname, exc)
        work_path.unlink(missing_ok=True)
        return None

    finally:
        temp_path.unlink(missing_ok=True)


# ── Main worker ───────────────────────────────────────────────────────────────

def process_daily(
    date_strs: list[str],
    cfg: dict,
    work_dir: Path,
    overwrite: bool = False,
) -> list[str]:
    """
    Process NSIDC daily files for the given list of YYYYMMDD date strings.

    For each pole × date, scrapes NSIDC, skips GCS-present files, then
    downloads, compresses, and uploads matching files.

    Returns a list of error strings (empty = clean run).
    """
    import datetime as dt

    gcs_cfg    = cfg["gcs"]
    bucket     = gcs_cfg["bucket"]
    prefix     = gcs_cfg["prefix"]
    base_url   = cfg["source"]["base_url"].rstrip("/")
    poles      = cfg["source"]["poles"]
    comp_level = cfg["compression"]["level"]

    work_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    # Group date_strs by year so we only scrape each year-directory once per pole
    from collections import defaultdict
    by_year: dict[str, list[str]] = defaultdict(list)
    for ds in date_strs:
        by_year[ds[:4]].append(ds)

    for pole in poles:
        for year, dates in sorted(by_year.items()):
            source_url  = f"{base_url}/{pole}/daily/{year}"
            gcs_year_prefix = f"{prefix}{pole}/daily/{year}/"

            # Fetch remote file listing once per pole/year
            remote_files = scrape_nc_files(source_url)
            if not remote_files:
                log.warning("No remote files found for %s/%s", pole, year)
                continue

            # Fetch GCS inventory once per pole/year
            if overwrite:
                gcs_present: set[str] = set()
            else:
                gcs_present = {
                    Path(b).name
                    for b in list_gcs_blobs(bucket, gcs_year_prefix)
                }

            for date_str in sorted(dates):
                candidates = [f for f in remote_files if date_str in f]
                if not candidates:
                    log.debug("No remote files for %s %s/%s", date_str, pole, year)
                    continue

                for fname in candidates:
                    if fname in gcs_present:
                        log.info("Already in GCS, skipping: %s/%s/%s", pole, year, fname)
                        continue

                    blob_name = f"{prefix}{pole}/daily/{year}/{fname}"
                    work_file = download_compress(work_dir, source_url, fname, comp_level)
                    if work_file is None:
                        errors.append(f"daily/{pole}/{year}/{fname}: download/compress failed")
                        continue
                    try:
                        gcs_upload(work_file, bucket, blob_name)
                    except Exception as exc:
                        log.error("GCS upload failed for %s: %s", fname, exc)
                        errors.append(f"daily/{pole}/{year}/{fname}: upload failed: {exc}")
                    finally:
                        work_file.unlink(missing_ok=True)

    return errors


def get_latest_year_dates(cfg: dict) -> list[str]:
    """
    Determine which YYYYMMDD date strings to process in default (no date args) mode.

    Scrapes NSIDC for the latest available year directory, then returns date
    strings for all files present remotely but missing from GCS.  Also checks
    the previous year during the first week of January.
    """
    import datetime as dt

    base_url = cfg["source"]["base_url"].rstrip("/")
    poles    = cfg["source"]["poles"]
    bucket   = cfg["gcs"]["bucket"]
    prefix   = cfg["gcs"]["prefix"]
    now      = dt.datetime.utcnow()

    date_set: set[str] = set()

    for pole in poles:
        base = f"{base_url}/{pole}/daily"
        year_dirs = scrape_year_dirs(base)
        if not year_dirs:
            continue

        active_year = year_dirs[-1]
        years_to_check = [active_year]
        if now.month == 1 and now.day <= 7:
            prev = str(now.year - 1)
            if prev in year_dirs:
                years_to_check.append(prev)

        for year in years_to_check:
            source_url      = f"{base}/{year}"
            gcs_year_prefix = f"{prefix}{pole}/daily/{year}/"
            remote_files    = scrape_nc_files(source_url)
            gcs_present     = {Path(b).name for b in list_gcs_blobs(bucket, gcs_year_prefix)}
            missing         = [f for f in remote_files if f not in gcs_present]

            # Extract YYYYMMDD tokens from missing filenames
            import re
            for fname in missing:
                m = re.search(r"(\d{8})", fname)
                if m:
                    date_set.add(m.group(1))

    return sorted(date_set)