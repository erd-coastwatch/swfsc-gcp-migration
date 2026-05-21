#!/usr/bin/env python3
import logging
import os
import sys

from src.npp_utils import (
    load_config,
    target_date_from_env,
    process_daily_for_date,
    process_composite_for_date,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

VALID_MODES = {"daily", "composite_3", "composite_8"}


def main() -> int:
    """Run the selected MH1 primary productivity processing mode."""
    cfg = load_config(os.environ.get("CONFIG_PATH", "/app/config/config.yml"))
    mode = os.environ.get("MODE", "daily").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported MODE={mode!r}; use one of {sorted(VALID_MODES)}")

    target_dt = target_date_from_env(cfg.days_lag)
    log.info("MH1 PrimProd controller started | MODE=%s | target=%s", mode, target_dt.date())
    log.info("Bucket: %s", cfg.bucket)

    if mode == "daily":
        result = process_daily_for_date(cfg, target_dt)
    elif mode == "composite_3":
        result = process_composite_for_date(cfg, target_dt, 3)
    else:
        result = process_composite_for_date(cfg, target_dt, 8)

    if result:
        log.info("Produced: gs://%s/%s", cfg.bucket, result)
    else:
        log.info("Nothing produced; output already existed and OVERWRITE=false.")

    log.info("MH1 PrimProd controller completed successfully.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log.exception("MH1 PrimProd failed: %s", exc)
        sys.exit(1)
