"""
control_crw_monthly.py
Controller: checks GCS for missing monthly files and calls process_month()
for each one that needs to be built.
"""

import os
import sys
import logging
from datetime import datetime, timedelta

from dateutil import rrule
from google.cloud import storage

sys.path.insert(0, os.path.dirname(__file__))
from update_sst_ssta_monthly import process_month

GCS_BUCKET  = os.environ.get('GCS_BUCKET', 'YOUR_PRODUCTION_BUCKET')
GCS_PREFIX  = 'satellite/CRW2/mday/'

WORK_DIR      = '/tmp/work'
MO_SOURCE_DIR = '/tmp/monthly'

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)


def list_gcs_final_files(bucket_name: str, prefix: str) -> list[str]:
    """Return final CRW monthly output object names under a GCS prefix."""
    client = storage.Client()
    return [b.name for b in client.bucket(bucket_name).list_blobs(prefix=prefix)]


def build_date_range() -> list[datetime]:
    """Return monthly center dates for the recent two-year processing window."""
    now            = datetime.utcnow()
    first          = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    now_minus_1mo  = (first - timedelta(days=1)).replace(day=16)
    now_minus_2yrs = now_minus_1mo.replace(year=now_minus_1mo.year - 2)
    return list(rrule.rrule(rrule.MONTHLY,
                            dtstart=now_minus_2yrs,
                            until=now_minus_1mo))


def main() -> None:
    """Identify missing monthly CRW files and build them one month at a time."""
    log.info('CRW monthly controller started')

    os.makedirs(WORK_DIR,      exist_ok=True)
    os.makedirs(MO_SOURCE_DIR, exist_ok=True)

    # Compare requested months against already-published outputs so reruns are safe.
    blobs     = list_gcs_final_files(GCS_BUCKET, GCS_PREFIX)
    have_yrmo = set()
    for name in blobs:
        base  = os.path.basename(name).replace('.nc', '')
        parts = base.split('_')
        if len(parts) > 5 and 'ct5km_sst_ssta' in base:
            have_yrmo.add(parts[5])

    log.info('Months already in GCS: %s', sorted(have_yrmo))

    # Only process months whose final ERDDAP-facing file is absent.
    dates_to_get = [dt for dt in build_date_range()
                    if '{0:%Y%m}'.format(dt) not in have_yrmo]

    if not dates_to_get:
        log.info('All months up to date — nothing to do.')
        sys.exit(0)

    log.info('Months to fetch: %s', ['{0:%Y%m}'.format(d) for d in dates_to_get])

    errors = []
    for dtc in dates_to_get:
        year  = '{0:%Y}'.format(dtc)
        month = '{0:%m}'.format(dtc)
        log.info('Processing %s-%s', year, month)
        try:
            process_month(year, month,
                          gcs_bucket=GCS_BUCKET,
                          gcs_prefix=GCS_PREFIX,
                          work_dir=WORK_DIR,
                          mo_source_dir=MO_SOURCE_DIR)
        except Exception as exc:
            log.exception('Failed for %s-%s: %s', year, month, exc)
            errors.append(f'{year}{month}: {exc}')

    if errors:
        log.error('Completed with errors: %s', errors)
        sys.exit(1)

    log.info('All months processed successfully.')
    sys.exit(0)


if __name__ == '__main__':
    main()
