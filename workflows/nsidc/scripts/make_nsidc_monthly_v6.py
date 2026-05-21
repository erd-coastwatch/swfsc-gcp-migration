"""
make_nsidc_monthly.py

Worker for NSIDC Sea Ice Concentration CDR monthly files.

For each pole:
  1. Smart Discovery: finds the latest monthly file already in GCS, then
     targets the next calendar month.
  2. Guardrail: before processing month M, verifies that at least one daily
     file for month M+1 already exists in GCS (confirming M is complete).
  3. Scrapes NSIDC for matching monthly .nc files.
  4. Downloads, compresses with nccopy, uploads to GCS.

Manual date-range mode is also supported (bypasses the guardrail).

All URLs, GCS paths, poles, and compression settings come from the
config dict passed in by the controller.
"""

import datetime as dt
import logging
import re
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
    """Return the set of blob names under a GCS prefix."""
    client = storage.Client()
    return {b.name for b in client.bucket(bucket_name).list_blobs(prefix=prefix)}


def gcs_upload(local_path: Path, bucket_name: str, blob_name: str) -> None:
    """Upload a compressed local NetCDF file to GCS."""
    storage.Client().bucket(bucket_name).blob(blob_name).upload_from_filename(str(local_path))
    log.info("local → GCS  %s → gs://%s/%s", local_path.name, bucket_name, blob_name)


# ── Date helpers ──────────────────────────────────────────────────────────────

def next_month(year: int, month: int) -> tuple[int, int]:
    """Return the year and month for the month after year/month."""
    return (year + 1, 1) if month == 12 else (year, month + 1)


def latest_gcs_month(bucket_name: str, prefix: str) -> Optional[dt.date]:
    """
    Scan GCS monthly prefix and return the most recent YYYYMM as a date,
    or None if no monthly files exist yet.
    """
    blobs = list_gcs_blobs(bucket_name, prefix)
    dates = []
    for name in blobs:
        m = re.search(r"(\d{4})(\d{2})", Path(name).stem)
        if m:
            try:
                dates.append(dt.date(int(m.group(1)), int(m.group(2)), 1))
            except ValueError:
                pass
    return max(dates) if dates else None


def guardrail_passed(bucket_name: str, daily_prefix: str, follow_year: int, follow_month: int) -> bool:
    """
    Return True if at least one daily file for follow_year/follow_month exists in GCS.

    The daily prefix pattern checked is:
        <daily_prefix><follow_year>/<any file containing YYYYMM01>
    This mirrors the original logic: presence of the first day of the next
    month confirms the previous month is fully received.
    """
    year_prefix    = f"{daily_prefix}{follow_year}/"
    follow_pattern = f"{follow_year}{follow_month:02d}01"
    blobs          = list_gcs_blobs(bucket_name, year_prefix)
    return any(follow_pattern in Path(b).name for b in blobs)


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


# ── Download + compress ───────────────────────────────────────────────────────

def download_compress(work_dir: Path, src_url: str, fname: str, compression_level: int) -> Optional[Path]:
    """Download and nccopy-compress a single file. Returns work path or None."""
    unique_id = uuid.uuid4().hex[:8]
    temp_path = work_dir / f"{fname}.{unique_id}.tmp"
    work_path = work_dir / fname

    try:
        log.info("Downloading %s", fname)
        with requests.get(f"{src_url.rstrip('/')}/{fname}", stream=True, timeout=120) as r:
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

def process_monthly(
    target_months: list[dt.date],
    cfg: dict,
    work_dir: Path,
    overwrite: bool = False,
    skip_guardrail: bool = False,
) -> list[str]:
    """
    Process NSIDC monthly files for the given list of dt.date objects
    (each representing the first day of a target month).

    Returns a list of error strings (empty = clean run).
    """
    gcs_cfg    = cfg["gcs"]
    bucket     = gcs_cfg["bucket"]
    prefix     = gcs_cfg["prefix"]
    base_url   = cfg["source"]["base_url"].rstrip("/")
    poles      = cfg["source"]["poles"]
    comp_level = cfg["compression"]["level"]

    work_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    for pole in poles:
        source_url     = f"{base_url}/{pole}/monthly"
        gcs_mo_prefix  = f"{prefix}{pole}/monthly/"
        gcs_day_prefix = f"{prefix}{pole}/daily/"

        remote_files = scrape_nc_files(source_url)
        if not remote_files:
            log.warning("No remote monthly files found for %s", pole)
            continue

        if overwrite:
            gcs_present: set[str] = set()
        else:
            gcs_present = {Path(b).name for b in list_gcs_blobs(bucket, gcs_mo_prefix)}

        for m_date in target_months:
            date_str = m_date.strftime("%Y%m")

            # ── Guardrail ─────────────────────────────────────────────────────
            if not skip_guardrail:
                f_year, f_month = next_month(m_date.year, m_date.month)
                if not guardrail_passed(bucket, gcs_day_prefix, f_year, f_month):
                    log.info(
                        "Guardrail: no daily data for %d-%02d yet — skipping %s monthly for %s",
                        f_year, f_month, pole, date_str,
                    )
                    continue
                log.info("Guardrail passed for %s %s", pole, date_str)

            candidates = [f for f in remote_files if date_str in f]
            if not candidates:
                log.warning("No remote monthly file found for %s %s", pole, date_str)
                continue

            for fname in candidates:
                if fname in gcs_present:
                    log.info("Already in GCS, skipping: %s/monthly/%s", pole, fname)
                    continue

                blob_name = f"{prefix}{pole}/monthly/{fname}"
                work_file = download_compress(work_dir, source_url, fname, comp_level)
                if work_file is None:
                    errors.append(f"monthly/{pole}/{fname}: download/compress failed")
                    continue
                try:
                    gcs_upload(work_file, bucket, blob_name)
                except Exception as exc:
                    log.error("GCS upload failed for %s: %s", fname, exc)
                    errors.append(f"monthly/{pole}/{fname}: upload failed: {exc}")
                finally:
                    work_file.unlink(missing_ok=True)

    return errors


def get_smart_discovery_months(cfg: dict) -> list[dt.date]:
    """
    Determine which months to target using Smart Discovery.

    For each pole, finds the latest monthly file in GCS and returns the
    next calendar month as the candidate. The guardrail check happens
    inside process_monthly(), not here.
    """
    bucket = cfg["gcs"]["bucket"]
    prefix = cfg["gcs"]["prefix"]
    poles  = cfg["source"]["poles"]

    candidates: set[dt.date] = set()

    for pole in poles:
        gcs_mo_prefix = f"{prefix}{pole}/monthly/"
        latest = latest_gcs_month(bucket, gcs_mo_prefix)
        if latest is None:
            log.warning("No existing monthly files in GCS for %s. Use START_DATE/END_DATE to bootstrap.", pole)
            continue
        n_year, n_month = next_month(latest.year, latest.month)
        candidates.add(dt.date(n_year, n_month, 1))
        log.info("Smart Discovery: %s latest=%s, targeting %d-%02d", pole, latest, n_year, n_month)

    return sorted(candidates)