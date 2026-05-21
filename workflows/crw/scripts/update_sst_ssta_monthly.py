"""
update_sst_ssta_monthly.py
Worker: downloads CRW monthly SST + SSTA from NOAA, merges them into a
combined NetCDF, and uploads the result to GCS.
"""

import os
import shutil
import logging
import subprocess
from datetime import datetime, timezone

import netCDF4
from google.cloud import storage

log = logging.getLogger(__name__)

# resolve nccopy at runtime — path varies by distro
NCCOPY = shutil.which('nccopy')
if not NCCOPY:
    raise EnvironmentError('nccopy not found in PATH — is the nco package installed?')

URL_BASE = ('https://www.star.nesdis.noaa.gov'
            '/pub/sod/mecb/crw/data'
            '/5km/v3.1_op/nc/v1.0/monthly/{}')

FILE_PTS = ['ct5km_sst-mean_v3.1_', 'ct5km_ssta-mean_v3.1_']

GCS_SOURCE_BUCKET = 'YOUR_WORK_BUCKET'
GCS_SOURCE_PREFIX = 'CRW2/source/'

# template is baked into the container image
LAT_LON_FILE  = 'lat_lon_source2023b.nc'
TEMPLATES_DIR = '/app/templates'

# seconds between 1970-01-01 and 1981-01-01 (CRW time reference)
SEC_OFFSET = (datetime(1981, 1, 1) - datetime(1970, 1, 1)).total_seconds()


def _gcs_upload(local_path: str, bucket_name: str, blob_name: str) -> None:
    """Upload a local file to GCS."""
    storage.Client().bucket(bucket_name).blob(blob_name).upload_from_filename(local_path)
    log.info('local → GCS  %s → gs://%s/%s', local_path, bucket_name, blob_name)


def _run(cmd: str) -> None:
    """Run a shell command and raise on non-zero exit."""
    log.info('CMD: %s', cmd)
    rc = subprocess.call(cmd, shell=True)
    if rc != 0:
        raise RuntimeError(f'Command failed (exit {rc}): {cmd}')


def process_month(year: str,
                  month: str,
                  gcs_bucket: str,
                  gcs_prefix: str,
                  work_dir: str,
                  mo_source_dir: str) -> None:
    """
    Download, merge, compress, and upload one month of CRW SST+SSTA data.

    Final file lands at:
        gs://<gcs_bucket>/<gcs_prefix>ct5km_sst_ssta_monthly_v31_YYYYMM.nc
    e.g.:
        gs://YOUR_PRODUCTION_BUCKET/satellite/CRW2/mday/ct5km_sst_ssta_monthly_v31_202301.nc
    """
    os.makedirs(work_dir,      exist_ok=True)
    os.makedirs(mo_source_dir, exist_ok=True)

    today = datetime(int(year), int(month), 16, tzinfo=timezone.utc)
    dtc   = '{0:%Y%m}'.format(today)

    temp_nc  = os.path.join(work_dir, 'temp.nc')
    temp2_nc = os.path.join(work_dir, 'temp2.nc')

    for f in (temp_nc, temp2_nc):
        if os.path.exists(f):
            os.remove(f)

    # copy template from container into working temp2.nc (output file)
    _run(f'cp {os.path.join(TEMPLATES_DIR, LAT_LON_FILE)} {temp2_nc}')

    # Download SST and SSTA from NOAA, compress them, and archive source copies.
    for fp in FILE_PTS:
        myfile    = fp + dtc + '.nc'
        myurl     = '/'.join([URL_BASE.format(year), myfile])
        local_src = os.path.join(mo_source_dir, myfile)

        log.info('Downloading %s', myurl)
        _run(f'wget -q -O {temp_nc} {myurl}')

        if not os.path.exists(temp_nc) or os.path.getsize(temp_nc) == 0:
            raise RuntimeError(f'Download empty or missing: {myurl}')

        _run(f'{NCCOPY} -d4 {temp_nc} {local_src}')
        _gcs_upload(local_src, GCS_SOURCE_BUCKET, GCS_SOURCE_PREFIX + myfile)

    # Merge SST and mask into the output template.
    nc_out = netCDF4.Dataset(temp2_nc, 'a')

    nc_sst   = netCDF4.Dataset(os.path.join(mo_source_dir, FILE_PTS[0] + dtc + '.nc'), 'r')
    sst_data = nc_sst.variables['sea_surface_temperature'][:, :, :]
    themask  = nc_sst.variables['mask'][:, :, :]
    nc_sst.close()

    nc_out['sea_surface_temperature'][:, :, :] = sst_data
    nc_out['mask'][:, :, :]                    = themask
    nc_out.variables['time'][0]                = today.timestamp() - SEC_OFFSET
    del sst_data, themask

    # Merge SSTA into the same output template.
    nc_ssta   = netCDF4.Dataset(os.path.join(mo_source_dir, FILE_PTS[1] + dtc + '.nc'), 'r')
    ssta_data = nc_ssta.variables['sea_surface_temperature_anomaly'][:, :, :]
    nc_ssta.close()

    nc_out['sea_surface_temperature_anomaly'][:, :, :] = ssta_data
    nc_out.close()
    del ssta_data

    # Compress the merged file and upload the final ERDDAP-facing output.
    final_file  = f'ct5km_sst_ssta_monthly_v31_{dtc}.nc'
    final_local = os.path.join(work_dir, final_file)
    _run(f'{NCCOPY} -d4 {temp2_nc} {final_local}')
    _gcs_upload(final_local, gcs_bucket, gcs_prefix + final_file)

    for f in (temp_nc, temp2_nc, final_local):
        if os.path.exists(f):
            os.remove(f)

    log.info('Done: %s', final_file)


# CLI entry point for local testing
if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    if len(sys.argv) != 3:
        print('Usage: python update_sst_ssta_monthly.py YYYY MM')
        sys.exit(1)

    process_month(sys.argv[1], sys.argv[2],
                  gcs_bucket=os.environ.get('GCS_BUCKET', 'YOUR_PRODUCTION_BUCKET'),
                  gcs_prefix='satellite/CRW2/mday/',
                  work_dir='/tmp/work',
                  mo_source_dir='/tmp/monthly')
