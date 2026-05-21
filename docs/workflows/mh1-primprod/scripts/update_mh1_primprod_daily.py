#!/usr/bin/env python3
"""Manual daily-only wrapper. Cloud Run normally calls control_mh1_primprod.py."""
import os
from src.npp_utils import load_config, target_date_from_env, process_daily_for_date

cfg = load_config(os.environ.get("CONFIG_PATH", "/app/config/config.yml"))
process_daily_for_date(cfg, target_date_from_env(cfg.days_lag))
