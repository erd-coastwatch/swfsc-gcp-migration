"""
control_crw_daily.py
Controller: checks GCS for missing daily files and calls process_day()
for each one that needs to be built.

Default behavior:
    - process the last LOOKBACK_DAYS days (default: 3), excluding today

Optional backfill behavior:
    - if BACKFILL_START_DATE=YYYY-MM-DD is set, process from that date
      through yesterday (inclusive), skipping days already present in GCS

Examples:
    Default daily mode:
        LOOKBACK_DAYS=3

    Backfill mode:
        BACKFILL_START_DATE=2025-01-01
"""

import os
import sys
import logging
from datetime import datetime, timedelta

from google.cloud import storage

sys.path.insert(0, os.path.dirname(__file__))
from update_sst_ssta_daily import process_day

GCS_BUCKET = os.environ.get('GCS_BUCKET', 'YOUR_PRODUCTION_BUCKET')
GCS_PREFIX = 'satellite/CRW2/1day/'

LOOKBACK_DAYS = int(os.environ.get('LOOKBACK_DAYS', '3'))
BACKFILL_START_DATE = os.environ.get('BACKFILL_START_DATE')

WORK_DIR = '/tmp/work'
DAY_SOURCE_DIR = '/tmp/daily'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
log = logging.getLogger(__name__)


def list_gcs_final_files(bucket_name: str, prefix: str) -> list[str]:
    """Return final CRW output object names under a GCS prefix."""
    client = storage.Client()
    return [b.name for b in client.bucket(bucket_name).list_blobs(prefix=prefix)]


def parse_yyyy_mm_dd(value: str) -> datetime:
    """Parse a YYYY-MM-DD string into a UTC-normalized datetime date."""
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError as exc:
        raise ValueError(
            f"Invalid BACKFILL_START_DATE '{value}'. Expected YYYY-MM-DD."
        ) from exc


def build_date_range() -> list[datetime]:
    """
    Return the dates to evaluate.

    Default mode:
        last LOOKBACK_DAYS days, excluding today

    Backfill mode:
        from BACKFILL_START_DATE through yesterday, inclusive
    """
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    if BACKFILL_START_DATE:
        start = parse_yyyy_mm_dd(BACKFILL_START_DATE).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        if start > yesterday:
            log.warning(
                'BACKFILL_START_DATE=%s is after yesterday (%s); nothing to do.',
                BACKFILL_START_DATE, yesterday.strftime('%Y-%m-%d')
            )
            return []

        dates = []
        dt = start
        while dt <= yesterday:
            dates.append(dt)
            dt += timedelta(days=1)

        return dates

    return [today - timedelta(days=i) for i in range(1, LOOKBACK_DAYS + 1)]


def main() -> None:
    """Identify missing daily CRW files and build them one date at a time."""
    if BACKFILL_START_DATE:
        log.info(
            'CRW daily controller started in backfill mode '
            '(start=%s, end=yesterday)',
            BACKFILL_START_DATE
        )
    else:
        log.info(
            'CRW daily controller started in lookback mode (lookback=%d days)',
            LOOKBACK_DAYS
        )

    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(DAY_SOURCE_DIR, exist_ok=True)

    # Compare requested dates against already-published outputs so reruns are safe.
    blobs = list_gcs_final_files(GCS_BUCKET, GCS_PREFIX)
    have_dates = set()
    for name in blobs:
        base = os.path.basename(name).replace('.nc', '')
        parts = base.split('_')
        # filename pattern: ct5km_sst_ssta_daily_v31_YYYYMMDD
        if len(parts) > 5 and 'ct5km_sst_ssta' in base:
            have_dates.add(parts[5])

    log.info('Dates already in GCS: %s', sorted(have_dates))

    requested_dates = build_date_range()
    if not requested_dates:
        log.info('No dates requested — nothing to do.')
        sys.exit(0)

    # Only process dates whose final ERDDAP-facing file is absent.
    dates_to_get = [
        dt for dt in requested_dates
        if f'{dt:%Y%m%d}' not in have_dates
    ]

    if not dates_to_get:
        log.info('All requested days already in GCS — nothing to do.')
        sys.exit(0)

    log.info('Dates to fetch: %s', [f'{d:%Y%m%d}' for d in dates_to_get])

    errors = []
    for dtc in dates_to_get:
        year = f'{dtc:%Y}'
        month = f'{dtc:%m}'
        day = f'{dtc:%d}'
        log.info('Processing %s-%s-%s', year, month, day)

        try:
            process_day(
                year, month, day,
                gcs_bucket=GCS_BUCKET,
                gcs_prefix=GCS_PREFIX,
                work_dir=WORK_DIR,
                day_source_dir=DAY_SOURCE_DIR
            )
        except Exception as exc:
            msg = str(exc)
            if (
                'Command failed (exit 8): wget' in msg
                or 'Download too small' in msg
                or 'Download empty' in msg
            ):
                log.info(
                    'Skipping %s-%s-%s; upstream CRW file likely not published yet: %s',
                    year, month, day, exc
                )
                continue

            log.exception('Failed for %s-%s-%s: %s', year, month, day, exc)
            errors.append(f'{year}{month}{day}: {exc}')

    if errors:
        log.error('Completed with errors: %s', errors)
        sys.exit(1)

    log.info('All requested days processed successfully.')
    sys.exit(0)


if __name__ == '__main__':
    main()
