
"""
control_nsidc.py

Controller for NSIDC Sea Ice Concentration CDR processing.

Reads config.yaml and routes to the daily or monthly worker based on MODE.

MODE=daily (default):
    - If START_DATE/END_DATE are set: processes that exact date range.
    - Otherwise: scrapes NSIDC for the latest year, processes all files
      missing from GCS (lookback_days buffer applied).

MODE=monthly:
    - If START_DATE/END_DATE are set: processes all months in that range,
      bypassing the guardrail.
    - Otherwise (Smart Discovery): finds the latest monthly file in GCS
      per pole, targets the next month, applies the GCS guardrail.

Optional env var overrides:
    START_DATE=YYYY-MM-DD
    END_DATE=YYYY-MM-DD
    GCS_BUCKET=...          overrides gcs.bucket in config
    LOG_LEVEL=...           overrides logging.level in config
    MODE=daily|monthly      selects processing stream
"""

import datetime as dt
import logging
import os
import shutil
import sys
from pathlib import Path

import yaml

from make_nsidc_daily_v6 import process_daily, get_latest_year_dates
from make_nsidc_monthly_v6 import process_monthly, get_smart_discovery_months

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path("/app/config/config.yaml")


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load the NSIDC workflow YAML configuration file."""
    with open(path) as f:
        return yaml.safe_load(f)


def setup_logging(cfg: dict) -> None:
    """Configure root logging from config, with optional LOG_LEVEL override."""
    log_cfg   = cfg["logging"]
    level_str = os.environ.get("LOG_LEVEL", log_cfg["level"])
    level     = getattr(logging, level_str.upper(), logging.INFO)
    logging.basicConfig(level=level, format=log_cfg["format"])


# ── Date helpers ──────────────────────────────────────────────────────────────

def _parse_date_env(var: str) -> dt.date | None:
    """Parse an optional YYYY-MM-DD environment variable into a date."""
    log = logging.getLogger(__name__)
    raw = os.environ.get(var, "").strip()
    if not raw:
        return None
    try:
        return dt.datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        log.error("Invalid %s=%r — expected YYYY-MM-DD, ignoring.", var, raw)
        return None


def build_date_range_daily(cfg: dict) -> list[str]:
    """Return YYYYMMDD strings for the configured window, or [] to trigger latest-mode."""
    start = _parse_date_env("START_DATE")
    end   = _parse_date_env("END_DATE")
    if start and end:
        if start > end:
            raise ValueError(f"START_DATE ({start}) is after END_DATE ({end})")
        days = (end - start).days + 1
        return [(start + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]
    elif start or end:
        raise ValueError("Provide both START_DATE and END_DATE, or neither.")
    # Fall back to lookback window
    lookback = cfg["processing"]["lookback_days"]
    today    = dt.date.today()
    return [
        (today - dt.timedelta(days=i)).strftime("%Y%m%d")
        for i in range(lookback + 1)
    ]


def build_month_range(cfg: dict) -> tuple[list[dt.date], bool]:
    """
    Return (target_months, skip_guardrail).
    skip_guardrail=True when explicit dates are provided (manual backfill).
    """
    start = _parse_date_env("START_DATE")
    end   = _parse_date_env("END_DATE")
    if start and end:
        months = []
        curr = start.replace(day=1)
        while curr <= end.replace(day=1):
            months.append(curr)
            y, m = (curr.year + 1, 1) if curr.month == 12 else (curr.year, curr.month + 1)
            curr = dt.date(y, m, 1)
        return months, True   # bypass guardrail for explicit backfills
    return [], False          # signal: use Smart Discovery


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Route daily or monthly NSIDC processing based on runtime MODE."""
    cfg = load_config()
    setup_logging(cfg)
    log = logging.getLogger(__name__)

    mode = os.environ.get("MODE", "daily").strip().lower()
    if mode not in {"daily", "monthly"}:
        log.error("Unsupported MODE=%r. Use 'daily' or 'monthly'.", mode)
        sys.exit(1)

    # Allow GCS bucket override at runtime without rebuilding the image
    if os.environ.get("GCS_BUCKET"):
        cfg["gcs"]["bucket"] = os.environ["GCS_BUCKET"]

    log.info("NSIDC CDR controller started (MODE=%s)", mode)

    work_dir = Path(cfg["work"]["dir"])
    work_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    try:
        if mode == "daily":
            date_strs = build_date_range_daily(cfg)
            log.info("Daily mode: %d date(s) to check (%s → %s)", len(date_strs), date_strs[0], date_strs[-1])
            errors = process_daily(date_strs=date_strs, cfg=cfg, work_dir=work_dir)

        else:  # monthly
            target_months, skip_guardrail = build_month_range(cfg)
            if not target_months:
                log.info("Monthly mode: running Smart Discovery")
                target_months = get_smart_discovery_months(cfg)
            else:
                log.info(
                    "Monthly mode: explicit range %s → %s (guardrail bypassed)",
                    target_months[0], target_months[-1],
                )
            if not target_months:
                log.info("No monthly targets identified — nothing to do.")
            else:
                errors = process_monthly(
                    target_months=target_months,
                    cfg=cfg,
                    work_dir=work_dir,
                    skip_guardrail=skip_guardrail,
                )

    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
            log.info("Removed work directory: %s", work_dir)
        except Exception as exc:
            log.warning("Could not remove %s: %s", work_dir, exc)

    if errors:
        log.error("Completed with %d error(s):\n  %s", len(errors), "\n  ".join(errors))
        sys.exit(1)

    log.info("NSIDC CDR processing complete (MODE=%s).", mode)
    sys.exit(0)


if __name__ == "__main__":
    main()