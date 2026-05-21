#!/usr/bin/env python3
"""
ASCAT-C Composite Control Script
================================

High-level controller for ASCAT-C composite generation.

This script determines the correct target dates based on the *current UTC
date* and invokes `make_ascat_multiday.py` accordingly.

Modes:
- multi-day : Run 1-, 3-, and 7-day composites for yesterday
- monthly   : Run monthly composite for the previous month

Designed for cron and CoastWatch operational workflows.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer

UTC = timezone.utc

app = typer.Typer(
    help="Control script for ASCAT-C composite generation",
    add_completion=False,
)


def run_cmd(cmd: list[str], dry_run: bool) -> None:
    """Run or log a command."""
    print("CMD:", " ".join(cmd))
    if not dry_run:
        subprocess.run(cmd, check=True)


@app.command()
def multi_day(
    script: Path = typer.Option(
        "scripts/make_ascat_multiday.py",  # Path updated to include scripts/
        help="Path to make_ascat_multiday.py",
    ),
    config: Path = typer.Option(
        "config/config_composite.yaml",   # Filename updated to config_composite.yaml
        help="YAML configuration file",
    ),
    dry_run: bool = typer.Option(
        False,
        help="Log commands without executing",
    ),
    log_level: str = typer.Option(
        "INFO",
        help="Logging level passed to composite script",
    ),
) -> None:
    """
    Trigger 1-, 3-, and 7-day composites for yesterday (UTC).
    """
    today_utc = datetime.now(UTC).date()
    target_date = today_utc - timedelta(days=1)

    cmd = [
        "python",
        str(script),
        "--date",
        target_date.isoformat(),
        "--config",
        str(config),
        "--log-level",
        log_level,
    ]

    run_cmd(cmd, dry_run)


@app.command()
def monthly(
    script: Path = typer.Option(
        "scripts/make_ascat_multiday.py",  # Path updated to include scripts/
        help="Path to make_ascat_multiday.py",
    ),
    config: Path = typer.Option(
        "config/config_composite.yaml",   # Filename updated to config_composite.yaml
        help="YAML configuration file",
    ),
    dry_run: bool = typer.Option(
        False,
        help="Log commands without executing",
    ),
    log_level: str = typer.Option(
        "INFO",
        help="Logging level passed to composite script",
    ),
) -> None:
    """
    Trigger monthly composite for the previous month.
    """
    today = datetime.now(UTC).date()
    first_of_this_month = today.replace(day=1)
    target_date = first_of_this_month - timedelta(days=1)

    cmd = [
        "python",
        str(script),
        "--date",
        target_date.isoformat(),
        "--make-month",
        "--config",
        str(config),
        "--log-level",
        log_level,
    ]

    run_cmd(cmd, dry_run)


if __name__ == "__main__":
    app()