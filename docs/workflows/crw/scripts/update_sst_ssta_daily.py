"""
update_sst_ssta_daily.py

Worker: downloads CRW daily SST + SSTA from NOAA, merges them into a
combined NetCDF built from a template, and uploads the result to GCS.

Current CRW source conventions confirmed from inspection:
- SST file:  coraltemp_v3.1_YYYYMMDD.nc
  variable:  analysed_sst
  dims:      (time, lat, lon)

- SSTA file: ct5km_ssta_v3.1_YYYYMMDD.nc
  variable:  sea_surface_temperature_anomaly

Template conventions confirmed from inspection:
- latitude variable name is "latitude" (not "lat")
- sea_surface_temperature dims are (time, latitude, longitude)
- template latitude runs descending: north -> south

Important orientation note:
- SST source latitude runs ascending: south -> north
- therefore SST must be flipped in latitude before writing to template
"""

import os
import shutil
import logging
import subprocess
from datetime import datetime, timezone

import netCDF4
from google.cloud import storage

log = logging.getLogger(__name__)

# Resolve nccopy at runtime. Path can vary by image / distro.
NCCOPY = shutil.which('nccopy')
if not NCCOPY:
    raise EnvironmentError('nccopy not found in PATH — is the nco package installed?')

URL_BASE_SST = (
    'https://www.star.nesdis.noaa.gov'
    '/pub/sod/mecb/crw/data'
    '/5km/v3.1_op/nc/v1.0/daily/sst/{year}/'
)

URL_BASE_SSTA = (
    'https://www.star.nesdis.noaa.gov'
    '/pub/sod/mecb/crw/data'
    '/5km/v3.1_op/nc/v1.0/daily/ssta/{year}/'
)

FILE_SST = 'coraltemp_v3.1_{dtc}.nc'
FILE_SSTA = 'ct5km_ssta_v3.1_{dtc}.nc'

# Raw source archive location
GCS_SOURCE_BUCKET = 'YOUR_WORK_BUCKET'
GCS_SOURCE_PREFIX = 'CRW2/source/'

# Template baked into the container image
LAT_LON_FILE = 'lat_lon_source2023b.nc'
TEMPLATES_DIR = '/app/templates'

# Seconds between Unix epoch and CRW epoch (1981-01-01)
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


def _download_to_temp(url: str, temp_nc: str) -> None:
    """
    Download URL into temp_nc and perform basic sanity checks.

    Notes:
    - wget exit 8 usually means upstream file not yet available (404 or server error)
    - tiny files are often HTML/error payloads, not real NetCDF
    """
    if os.path.exists(temp_nc):
        os.remove(temp_nc)

    _run(f'wget -q -O {temp_nc} {url}')

    if not os.path.exists(temp_nc):
        raise RuntimeError(f'Download missing: {url}')

    size = os.path.getsize(temp_nc)
    if size == 0:
        raise RuntimeError(f'Download empty: {url}')

    if size < 1000:
        raise RuntimeError(f'Download too small to be valid NetCDF ({size} bytes): {url}')


def _get_required_var(nc: netCDF4.Dataset, var_name: str):
    """Return a required variable or raise a helpful KeyError."""
    if var_name not in nc.variables:
        raise KeyError(
            f"Variable '{var_name}' not found. "
            f"Available variables: {list(nc.variables.keys())}"
        )
    return nc.variables[var_name]


def _read_2d_or_3d(var):
    """
    Read a NetCDF variable and always return a 2D array.

    Supported input layouts:
    - (lat, lon)
    - (time, lat, lon) -> use first time slice
    """
    if var.ndim == 2:
        return var[:, :]
    if var.ndim == 3:
        return var[0, :, :]
    raise ValueError(
        f"Unsupported variable rank for '{var.name}': ndim={var.ndim}, "
        f"shape={getattr(var, 'shape', None)}, dims={getattr(var, 'dimensions', None)}"
    )


def _lat_is_descending(lat_values) -> bool:
    """True if latitude runs north -> south."""
    return bool(lat_values[0] > lat_values[-1])


def process_day(
    year: str,
    month: str,
    day: str,
    gcs_bucket: str,
    gcs_prefix: str,
    work_dir: str,
    day_source_dir: str
) -> None:
    """
    Download, merge, compress, and upload one day of CRW SST+SSTA data.

    Final file lands at:
        gs://<gcs_bucket>/<gcs_prefix>ct5km_sst_ssta_daily_v31_YYYYMMDD.nc
    """
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(day_source_dir, exist_ok=True)

    today = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
    dtc = f'{today:%Y%m%d}'

    temp_nc = os.path.join(work_dir, 'temp.nc')
    temp2_nc = os.path.join(work_dir, 'temp2.nc')

    # Clean any leftovers from earlier runs
    for f in (temp_nc, temp2_nc):
        if os.path.exists(f):
            os.remove(f)

    # Start from the template file
    _run(f'cp {os.path.join(TEMPLATES_DIR, LAT_LON_FILE)} {temp2_nc}')

    # ------------------------------------------------------------------
    # Download and archive raw SST source file
    # ------------------------------------------------------------------
    sst_file = FILE_SST.format(dtc=dtc)
    sst_url = URL_BASE_SST.format(year=year) + sst_file
    sst_local = os.path.join(day_source_dir, sst_file)

    log.info('Downloading SST %s', sst_url)
    _download_to_temp(sst_url, temp_nc)
    _run(f'{NCCOPY} -d4 {temp_nc} {sst_local}')
    _gcs_upload(sst_local, GCS_SOURCE_BUCKET, GCS_SOURCE_PREFIX + sst_file)

    # ------------------------------------------------------------------
    # Download and archive raw SSTA source file
    # ------------------------------------------------------------------
    ssta_file = FILE_SSTA.format(dtc=dtc)
    ssta_url = URL_BASE_SSTA.format(year=year) + ssta_file
    ssta_local = os.path.join(day_source_dir, ssta_file)

    log.info('Downloading SSTA %s', ssta_url)
    _download_to_temp(ssta_url, temp_nc)
    _run(f'{NCCOPY} -d4 {temp_nc} {ssta_local}')
    _gcs_upload(ssta_local, GCS_SOURCE_BUCKET, GCS_SOURCE_PREFIX + ssta_file)

    # ------------------------------------------------------------------
    # Read SST source
    #
    # Confirmed source layout:
    # - variable name: analysed_sst
    # - dims: (time, lat, lon)
    # - source lat ascends south -> north
    # ------------------------------------------------------------------
    nc_sst = netCDF4.Dataset(sst_local, 'r')
    try:
        sst_var = _get_required_var(nc_sst, 'analysed_sst')
        lat_sst_var = _get_required_var(nc_sst, 'lat')

        sst_data = _read_2d_or_3d(sst_var)
        lat_sst = lat_sst_var[:]

        log.info(
            'SST source dims=%s shape=%s lat_first=%s lat_last=%s',
            sst_var.dimensions, sst_var.shape, lat_sst[0], lat_sst[-1]
        )
    finally:
        nc_sst.close()

    # ------------------------------------------------------------------
    # Read SSTA source
    #
    # We keep SSTA and mask as-is unless later evidence shows otherwise.
    # Based on your visual check, SSTA already looks correct in output.
    # ------------------------------------------------------------------
    nc_ssta = netCDF4.Dataset(ssta_local, 'r')
    try:
        ssta_var = _get_required_var(nc_ssta, 'sea_surface_temperature_anomaly')
        mask_var = _get_required_var(nc_ssta, 'mask')

        ssta_data = _read_2d_or_3d(ssta_var)
        themask = _read_2d_or_3d(mask_var)

        log.info(
            'SSTA source dims=%s shape=%s',
            ssta_var.dimensions, ssta_var.shape
        )
        log.info(
            'MASK source dims=%s shape=%s',
            mask_var.dimensions, mask_var.shape
        )
    finally:
        nc_ssta.close()

    # ------------------------------------------------------------------
    # Open output template and align source arrays to template orientation
    #
    # Confirmed template:
    # - latitude variable name: "latitude"
    # - dims: (time, latitude, longitude)
    # - template latitude descends north -> south
    # ------------------------------------------------------------------
    nc_out = netCDF4.Dataset(temp2_nc, 'a')
    try:
        # Validate required output variables
        if 'latitude' not in nc_out.variables:
            raise KeyError(
                "Output template missing variable 'latitude'. "
                f"Available: {list(nc_out.variables.keys())}"
            )
        if 'sea_surface_temperature' not in nc_out.variables:
            raise KeyError(
                "Output template missing variable 'sea_surface_temperature'. "
                f"Available: {list(nc_out.variables.keys())}"
            )
        if 'sea_surface_temperature_anomaly' not in nc_out.variables:
            raise KeyError(
                "Output template missing variable 'sea_surface_temperature_anomaly'. "
                f"Available: {list(nc_out.variables.keys())}"
            )
        if 'mask' not in nc_out.variables:
            raise KeyError(
                "Output template missing variable 'mask'. "
                f"Available: {list(nc_out.variables.keys())}"
            )
        if 'time' not in nc_out.variables:
            raise KeyError(
                "Output template missing variable 'time'. "
                f"Available: {list(nc_out.variables.keys())}"
            )

        lat_out = nc_out.variables['latitude'][:]

        log.info(
            'OUT template dims=%s shape=%s lat_first=%s lat_last=%s',
            nc_out.variables['sea_surface_temperature'].dimensions,
            nc_out.variables['sea_surface_temperature'].shape,
            lat_out[0], lat_out[-1]
        )

        # Flip SST only if source latitude orientation differs from template
        # Source SST: ascending
        # Template:   descending
        if _lat_is_descending(lat_sst) != _lat_is_descending(lat_out):
            log.info('Flipping SST latitude orientation to match output template')
            sst_data = sst_data[::-1, :]

        # Write 2D source arrays into first time slice of 3D template arrays
        nc_out.variables['sea_surface_temperature'][0, :, :] = sst_data
        nc_out.variables['sea_surface_temperature_anomaly'][0, :, :] = ssta_data
        nc_out.variables['mask'][0, :, :] = themask

        # Template uses CRW time convention: seconds since 1981-01-01
        nc_out.variables['time'][0] = today.timestamp() - SEC_OFFSET

    finally:
        nc_out.close()

    # ------------------------------------------------------------------
    # Compress merged output and upload final product
    # ------------------------------------------------------------------
    final_file = f'ct5km_sst_ssta_daily_v31_{dtc}.nc'
    final_local = os.path.join(work_dir, final_file)

    _run(f'{NCCOPY} -d4 {temp2_nc} {final_local}')
    _gcs_upload(final_local, gcs_bucket, gcs_prefix + final_file)

    # Clean transient files
    for f in (temp_nc, temp2_nc, final_local):
        if os.path.exists(f):
            os.remove(f)

    log.info('Done: %s', final_file)


# ----------------------------------------------------------------------
# CLI entry point for local testing
# ----------------------------------------------------------------------
if __name__ == '__main__':
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s'
    )

    if len(sys.argv) != 4:
        print('Usage: python update_sst_ssta_daily.py YYYY MM DD')
        sys.exit(1)

    process_day(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
        gcs_bucket=os.environ.get('GCS_BUCKET', 'YOUR_PRODUCTION_BUCKET'),
        gcs_prefix='satellite/CRW2/1day/',
        work_dir='/tmp/work',
        day_source_dir='/tmp/daily'
    )