"""
End-to-end MH1 Primary Productivity utilities for Cloud Run.

This intentionally does NOT call the legacy MHPProductivityPart() directly because
that function hard-codes /u00 paths. Instead, this preserves the legacy math and
file naming while making all inputs/outputs config-driven and GCS-staged.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import netCDF4
import numpy as np
import numpy.ma as ma
import yaml
from google.cloud import storage

from src.primprodUtil import BFprimprod
log = logging.getLogger(__name__)

NCCOPY = shutil.which("nccopy")


@dataclass(frozen=True)
class RuntimeConfig:
    bucket: str
    input_prefixes: Dict[str, str]
    output_prefixes: Dict[str, str]
    year_partition_inputs: bool
    year_partition_outputs: bool
    days_lag: int
    work_base: Path
    results_base: Path
    reference_dir: Path
    world_daylength: str
    keep_local_results: bool
    overwrite: bool


def load_config(path: str | Path = "/app/config/config.yml") -> RuntimeConfig:
    """Load YAML and environment overrides into a RuntimeConfig object."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    gcs = raw.get("gcs", {})
    runtime = raw.get("runtime", {})
    reference = raw.get("reference_files", {})

    return RuntimeConfig(
        bucket=os.environ.get("GCS_BUCKET", gcs.get("bucket", "YOUR_PRODUCTION_BUCKET")),
        input_prefixes=gcs.get("input_prefixes", {}),
        output_prefixes=gcs.get("output_prefixes", {}),
        year_partition_inputs=bool(gcs.get("year_partition_inputs", False)),
        year_partition_outputs=bool(gcs.get("year_partition_outputs", False)),
        days_lag=int(os.environ.get("DAYS_LAG", runtime.get("days_lag", 2))),
        work_base=Path(os.environ.get("WORK_BASE", runtime.get("work_base", "/tmp/work"))),
        results_base=Path(os.environ.get("RESULTS_BASE", runtime.get("results_base", "/tmp/results"))),
        reference_dir=Path(runtime.get("reference_dir", "/app/templates")),
        world_daylength=reference.get("world_daylength", "worlddaylen.nc"),
        keep_local_results=str(os.environ.get("KEEP_LOCAL_RESULTS", runtime.get("keep_local_results", False))).lower() in {"1", "true", "yes", "y"},
        overwrite=str(os.environ.get("OVERWRITE", runtime.get("overwrite", False))).lower() in {"1", "true", "yes", "y"},
    )


def target_date_from_env(days_lag: int) -> datetime:
    """Return target date. RUN_DATE=YYYY-MM-DD overrides current UTC minus lag."""
    run_date = os.environ.get("RUN_DATE", "").strip()
    if run_date:
        return datetime.strptime(run_date, "%Y-%m-%d").replace(hour=12)
    return (datetime.utcnow() - timedelta(days=days_lag)).replace(hour=12, minute=0, second=0, microsecond=0)


def doy3(dt: datetime) -> str:
    """Return a three-digit day-of-year string for a datetime."""
    return f"{int(dt.strftime('%j')):03d}"


def _prefix(prefix: str, year: int, year_partition: bool) -> str:
    """Return a normalized GCS prefix, optionally partitioned by year."""
    prefix = prefix.strip("/")
    if year_partition:
        return f"{prefix}/{year}"
    return prefix


def _blob_name(prefix: str, filename: str, year: int, year_partition: bool) -> str:
    """Build a GCS object name from prefix, year, and filename."""
    return f"{_prefix(prefix, year, year_partition)}/{filename}"


def gcs_client() -> storage.Client:
    """Create a Google Cloud Storage client for runtime operations."""
    return storage.Client()


def blob_exists(client: storage.Client, bucket: str, blob_name: str) -> bool:
    """Return True when a GCS object exists."""
    return client.bucket(bucket).blob(blob_name).exists()


def download_blob(client: storage.Client, bucket: str, blob_name: str, local_path: Path) -> bool:
    """Download a GCS object to a local path if it exists."""
    blob = client.bucket(bucket).blob(blob_name)
    if not blob.exists():
        log.warning("Missing GCS input: gs://%s/%s", bucket, blob_name)
        return False
    local_path.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(local_path))
    log.info("GCS → local  gs://%s/%s → %s", bucket, blob_name, local_path)
    return True


def upload_blob(client: storage.Client, bucket: str, local_path: Path, blob_name: str) -> None:
    """Upload a local file to a GCS object."""
    client.bucket(bucket).blob(blob_name).upload_from_filename(str(local_path))
    log.info("local → GCS  %s → gs://%s/%s", local_path, bucket, blob_name)


def compress_with_nccopy(src: Path, dst: Path) -> None:
    """Compress a NetCDF file with nccopy, or copy it if nccopy is unavailable."""
    if NCCOPY:
        subprocess.run([NCCOPY, "-k4", "-d2", str(src), str(dst)], check=True)
    else:
        shutil.copy2(src, dst)


def legacy_input_names(year: int, doy: int) -> Dict[str, str]:
    """Return legacy MH1 input filenames for one year/day-of-year."""
    dt = datetime(year, 1, 1) + timedelta(days=doy - 1)
    ymd = dt.strftime("%Y%m%d")

    return {
        "chl": f"AQUA_MODIS.{ymd}.L3m.DAY.CHL.chlor_a.4km.NRT.nc",
        "par": f"AQUA_MODIS.{ymd}.L3m.DAY.PAR.par.4km.NRT.nc",
        "sst": f"AQUA_MODIS.{ymd}.L3m.DAY.SST.sstMasked.4km.NRT.nc",
    }


def daily_output_name(year: int, doy: int) -> str:
    """Return the ERDDAP-facing daily primary productivity filename."""
    return f"A{year}{doy:03d}.L3m_DAY_primprod.nc"


def composite_output_name(start_dt: datetime, end_dt: datetime, interval: int) -> str:
    """Return the ERDDAP-facing composite filename for a date window."""
    return (
        f"A{start_dt:%Y}{start_dt:%j}_"
        f"A{end_dt:%Y}{end_dt:%j}_{interval}day_primprod.nc"
    )


def stage_reference_files(cfg: RuntimeConfig, work_dir: Path) -> None:
    """Link required static NetCDF reference files into a working directory."""
    work_dir.mkdir(parents=True, exist_ok=True)

    for f in cfg.reference_dir.glob("*.nc"):
        target = work_dir / f.name
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(f)
        log.info("Linked reference file: %s → %s", target, f)

    required = work_dir / cfg.world_daylength
    if not required.exists():
        raise FileNotFoundError(
            f"Required reference file not found: {required}. "
            f"Put {cfg.world_daylength} in {cfg.reference_dir}."
        )


def stage_daily_inputs(cfg: RuntimeConfig, year: int, doy: int, work_dir: Path) -> Dict[str, Path]:
    """Download chlorophyll, PAR, and SST inputs for one processing date."""
    client = gcs_client()
    names = legacy_input_names(year, doy)
    local = {
        "chl": work_dir / "chla" / names["chl"],
        "par": work_dir / "par" / names["par"],
        "sst": work_dir / "sst" / names["sst"],
    }

    missing = []
    for key in ("chl", "par", "sst"):
        blob = _blob_name(cfg.input_prefixes[key], names[key], year, cfg.year_partition_inputs)
        ok = download_blob(client, cfg.bucket, blob, local[key])
        if not ok:
            missing.append(key)

    if missing:
        raise FileNotFoundError(f"Missing required daily inputs for {year} DOY {doy:03d}: {missing}")

    return local




def read_l3m_nc(path, preferred_vars):
    """
    Read NetCDF L3m file and return masked array.
    Handles:
      - variable detection
      - time dimension squeeze
      - fill value masking
    """
    with netCDF4.Dataset(path, "r") as ds:
        var_name = None

        # Find correct variable
        for v in preferred_vars:
            if v in ds.variables:
                var_name = v
                break

        if var_name is None:
            available = list(ds.variables.keys())
            raise KeyError(
                f"No expected data variable found in {path}. "
                f"Tried {preferred_vars}. Available: {available}"
            )

        var = ds.variables[var_name]

        # Read + squeeze (remove time dim)
        data = np.squeeze(var[:])

        # Start masked array
        arr = ma.masked_invalid(data)

        # Handle fill value dynamically
        fill_value = getattr(var, "_FillValue", None)
        if fill_value is not None:
            arr = ma.masked_where(data == fill_value, arr)

        # Handle missing_value if present
        missing_value = getattr(var, "missing_value", None)
        if missing_value is not None:
            arr = ma.masked_where(data == missing_value, arr)

        return arr


def read_sst(path):
    """Read an SST or SST-mask NetCDF input as a masked array."""
    return read_l3m_nc(
        path,
        preferred_vars=[
            "sstMasked",
            "sst",
            "sea_surface_temperature",
        ],
    )


def load_daylength_grid(worlddaylen: Path, doy: int, n_lon: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load latitude, longitude, and daylength fields for one day-of-year."""
    with netCDF4.Dataset(worlddaylen, "r") as ds:
        lat = ds.variables["lat"][:]
        lon = ds.variables["lon"][:]
        daylen1 = ds.variables["daylen"]
        temp = daylen1[doy - 1, :]
        temp = np.tile(temp, (n_lon, 1))
        daylen = np.transpose(temp)
    return lat, lon, daylen


def write_daily_npp(
    out_tmp: Path,
    year: int,
    doy: int,
    lat: np.ndarray,
    lon: np.ndarray,
    prod: ma.MaskedArray,
    source_data: str,
) -> None:
    """Write one daily primary productivity NetCDF output file."""
    my_date = datetime(year, 1, 1) + timedelta(doy - 1)
    my_time = my_date.replace(tzinfo=timezone.utc).timestamp() + 43200
    today = datetime.utcnow().date().isoformat()

    out_tmp.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(out_tmp, "w") as nc:
        nc.createDimension("latitude", lat.shape[0])
        nc.createDimension("longitude", lon.shape[0])
        nc.createDimension("time", 1)
        nc.createDimension("altitude", 1)

        latitude = nc.createVariable("latitude", "f4", ("latitude",))
        longitude = nc.createVariable("longitude", "f4", ("longitude",))
        altitude = nc.createVariable("altitude", "f4", ("altitude",))
        time = nc.createVariable("time", "i4", ("time",))
        primprod = nc.createVariable(
            "MHPProd", "f4", ("time", "altitude", "latitude", "longitude"), fill_value=-99999.0
        )

        time.actual_range = f"{my_time}, {my_time}"
        time.long_name = "Centered Time"
        time.units = "seconds since 1970-01-01T00:00:00Z"
        time.standard_name = "time"
        time.axis = "T"
        time._CoordinateAxisType = "Time"

        altitude.actual_range = "0.0, 0.0"
        altitude.long_name = "Altitude"
        altitude.positive = "up"
        altitude.standard_name = "altitude"
        altitude.units = "m"
        altitude.axis = "Z"
        altitude._CoordinateAxisType = "Height"
        altitude._CoordinateZisPositive = "up"

        latitude._CoordinateAxisType = "Lat"
        latitude.actual_range = "89.97918, -89.97918"
        latitude.coordsys = "geographic"
        latitude.long_name = "Latitude"
        latitude.point_spacing = "even"
        latitude.standard_name = "latitude"
        latitude.units = "degrees_north"
        latitude.axis = "Y"

        longitude._CoordinateAxisType = "Lon"
        longitude.actual_range = "-179.9792, 179.9792"
        longitude.coordsys = "geographic"
        longitude.long_name = "Longitude"
        longitude.point_spacing = "even"
        longitude.standard_name = "longitude"
        longitude.units = "degrees_east"
        longitude.axis = "X"

        primprod.coordsys = "geographic"
        primprod.long_name = "Primary Productivity, Aqua MODIS L3M, NPP, Global, EXPERIMENTAL"
        primprod.missing_value = -99999.0
        primprod.standard_name = "net_primary_productivity_of_carbon"
        primprod.units = "mg C m-2 day-1"

        nc.Conventions = "CF-1.6, COARDS, Unidata Dataset Discovery v1.0"
        nc.title = "Primary Productivity, Aqua MODIS L3M, NPP, Global, EXPERIMENTAL"
        nc.references = "Behrenfield and Falkowski, L&O 1997"
        nc.summary = (
            "Calculates vertically integrated primary productivity using the Behrenfield-Falkowski method "
            "and satellite-based chlorophyll a, incident visible surface irradiance, and sea surface temperature."
        )
        nc.institution = "NOAA NMFS SWFSC ERD"
        nc.contact = "erd.data@noaa.gov"
        nc.creator_name = "erd.data"
        nc.creator_email = "erd.data@noaa.gov"
        nc.creation_date = today
        nc.spatial_resolution = "0.0417 degree"
        nc.source_data = source_data
        nc.Southernmost_Northing = -89.97918
        nc.Northernmost_Northing = 89.97918
        nc.Westernmost_Easting = -179.9792
        nc.Easternmost_Easting = 179.9792
        nc.rights = (
            "The data may be used and redistributed for free but is not intended for legal use, since it may "
            "contain inaccuracies. Neither the data Contributor, CoastWatch, NOAA, nor the United States Government, "
            "nor any of their employees or contractors, makes any warranty, express or implied, including warranties "
            "of merchantability and fitness for a particular purpose, or assumes any legal liability for the accuracy, "
            "completeness, or usefulness of this information."
        )
        nc.history = ""

        altitude[0] = 0.0
        latitude[:] = lat
        longitude[:] = lon
        primprod[0, 0, :, :] = prod
        time[0] = int(my_time)


def process_daily_for_date(cfg: RuntimeConfig, target_dt: datetime) -> Optional[str]:
    """Build and publish one daily MH1 primary productivity product."""
    year = target_dt.year
    doy = int(target_dt.strftime("%j"))
    fname = daily_output_name(year, doy)
    out_blob = _blob_name(cfg.output_prefixes["daily"], fname, year, cfg.year_partition_outputs)
    client = gcs_client()

    if blob_exists(client, cfg.bucket, out_blob) and not cfg.overwrite:
        log.info("Daily output already exists, skipping: gs://%s/%s", cfg.bucket, out_blob)
        return None

    work_dir = cfg.work_base / "mh1_primprod_daily" / f"{year}{doy:03d}"
    results_dir = cfg.results_base / "mh1_primprod_daily"
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    stage_reference_files(cfg, work_dir)

    inputs = stage_daily_inputs(cfg, year, doy, work_dir)
    names = legacy_input_names(year, doy)

    chl = read_l3m_nc(inputs["chl"], preferred_vars=["chlor_a", "chl", "chla"])
    par = read_l3m_nc(inputs["par"], preferred_vars=["par"])
    sst = read_sst(inputs["sst"])
    lat, lon, daylen = load_daylength_grid(work_dir / cfg.world_daylength, doy, sst.shape[1])

    log.info("Calculating NPP for %s DOY %03d", year, doy)
    prod = BFprimprod(chl, par, sst, daylen)
    ma.set_fill_value(prod, -99999.0)

    tmp = work_dir / "temp_daily.nc"
    final = results_dir / fname
    write_daily_npp(tmp, year, doy, lat, lon, prod, ", ".join([names["chl"], names["par"], names["sst"]]))
    compress_with_nccopy(tmp, final)
    upload_blob(client, cfg.bucket, final, out_blob)

    if not cfg.keep_local_results:
        shutil.rmtree(work_dir, ignore_errors=True)
        final.unlink(missing_ok=True)

    return out_blob


def daily_window(end_dt: datetime, interval: int) -> List[datetime]:
    """Return the dates included in a composite ending on end_dt."""
    start = end_dt - timedelta(days=interval - 1)
    return [start + timedelta(days=i) for i in range(interval)]


def download_daily_npp_for_composite(cfg: RuntimeConfig, dates: List[datetime], work_dir: Path) -> Dict[datetime, Path]:
    """Download available daily NPP files needed for a composite window."""
    client = gcs_client()
    out = {}
    for dt in dates:
        doy = int(dt.strftime("%j"))
        fname = daily_output_name(dt.year, doy)
        blob = _blob_name(cfg.output_prefixes["daily"], fname, dt.year, cfg.year_partition_outputs)
        local = work_dir / fname
        if download_blob(client, cfg.bucket, blob, local):
            out[dt] = local
    return out


def update_mean(mean: ma.MaskedArray, num: np.ndarray, obs: ma.MaskedArray):
    """Update a running masked-array mean and valid-observation count."""
    num_add = np.ones(num.shape, dtype=np.int32)
    num_add[obs.mask] = 0
    temp = np.subtract(obs, mean, dtype=np.single)
    num = np.add(num, num_add, dtype=np.int32)
    temp_num = ma.array(num, mask=(num == 0), dtype=np.int32)
    temp = temp / temp_num.astype("float")
    mean = np.add(mean, temp.filled(0.0), dtype=np.single)
    return mean, num


def write_composite_npp(
    out_tmp: Path,
    interval: int,
    start_dt: datetime,
    end_dt: datetime,
    lat: np.ndarray,
    lon: np.ndarray,
    mean: ma.MaskedArray,
    num: np.ndarray,
    source_files: List[str],
) -> None:
    """Write a composite productivity NetCDF file with metadata and bounds."""
    center_dt = start_dt + timedelta(days=interval / 2.0)
    center_time = center_dt.replace(tzinfo=timezone.utc).timestamp()
    start_time = start_dt.replace(tzinfo=timezone.utc).timestamp()
    end_time = (start_dt + timedelta(days=interval)).replace(tzinfo=timezone.utc).timestamp()

    out_tmp.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(out_tmp, "w") as nc:
        nc.createDimension("nav", 2)
        nc.createDimension("altitude", 1)
        nc.createDimension("latitude", len(lat))
        nc.createDimension("longitude", len(lon))
        nc.createDimension("time", 1)

        latitude = nc.createVariable("latitude", "f8", ("latitude",))
        longitude = nc.createVariable("longitude", "f8", ("longitude",))
        altitude = nc.createVariable("altitude", "f8", ("altitude",))
        time = nc.createVariable("time", "f8", ("time",))
        time_bnds = nc.createVariable("time_bnds", "f8", ("time", "nav"))
        nobs = nc.createVariable("nobs", "i4", ("time", "altitude", "latitude", "longitude"))
        primprod = nc.createVariable("MHPProd", "f4", ("time", "altitude", "latitude", "longitude"), fill_value=-99999.0)

        time.actual_range = f"{center_time}, {center_time}"
        time.long_name = "Centered Time"
        time.units = "seconds since 1970-01-01T00:00:00Z"
        time.standard_name = "time"
        time.axis = "T"
        time._CoordinateAxisType = "Time"
        time_bnds.units = "seconds since 1970-01-01T00:00:00Z"
        time_bnds.standard_name = "time"

        altitude.actual_range = "0.0, 0.0"
        altitude.long_name = "Altitude"
        altitude.positive = "up"
        altitude.standard_name = "altitude"
        altitude.units = "m"
        altitude.axis = "Z"
        altitude._CoordinateAxisType = "Height"
        altitude._CoordinateZisPositive = "up"

        latitude._CoordinateAxisType = "Lat"
        latitude.actual_range = "-89.97918, 89.97918"
        latitude.coordsys = "geographic"
        latitude.long_name = "Latitude"
        latitude.point_spacing = "even"
        latitude.standard_name = "latitude"
        latitude.units = "degrees_north"
        latitude.axis = "Y"

        longitude._CoordinateAxisType = "Lon"
        longitude.actual_range = "-179.9792, 179.9792"
        longitude.coordsys = "geographic"
        longitude.long_name = "Longitude"
        longitude.point_spacing = "even"
        longitude.standard_name = "longitude"
        longitude.units = "degrees_east"
        longitude.axis = "X"

        primprod.coordsys = "geographic"
        primprod.long_name = "Primary Productivity, Aqua MODIS L3M, NPP, Global, EXPERIMENTAL"
        primprod.missing_value = -99999.0
        primprod.standard_name = "net_primary_productivity_of_carbon"
        primprod.units = "mg C m-2 day-1"
        nobs.long_name = "Number of observations in composite"
        nobs.missing_value = -99999

        nc.Conventions = "CF-1.6, COARDS, ACDD-1.3"
        nc.title = f"{interval}-day composite mean of Primary Productivity, Aqua MODIS L3M, NPP, Global, EXPERIMENTAL"
        nc.references = "Behrenfield and Falkowski, L&O 1997"
        nc.summary = (
            "Composite mean of vertically integrated primary productivity one-day files using the "
            "Behrenfield-Falkowski method."
        )
        nc.institution = "NOAA NMFS SWFSC ERD"
        nc.contact = "erd.data@noaa.gov"
        nc.creator_name = "erd.data"
        nc.creator_email = "erd.data@noaa.gov"
        nc.creation_date = datetime.utcnow().strftime("%c")
        nc.spatial_resolution = "0.0417 degree"
        nc.source_data = f" {interval}-day composite mean of files " + " ".join(source_files)
        nc.Southernmost_Northing = -89.97918
        nc.Northernmost_Northing = 89.97918
        nc.Westernmost_Easting = -179.9792
        nc.Easternmost_Easting = 179.9792
        nc.rights = (
            "The data may be used and redistributed for free but is not intended for legal use, since it may "
            "contain inaccuracies. Neither the data Contributor, CoastWatch, NOAA, nor the United States Government, "
            "nor any of their employees or contractors, makes any warranty, express or implied."
        )
        nc.history = ""

        latitude[:] = lat
        longitude[:] = lon
        altitude[0] = 0.0
        primprod[0, 0, :, :] = mean
        nobs[0, 0, :, :] = num
        time[0] = center_time
        time_bnds[0, 0] = start_time
        time_bnds[0, 1] = end_time


def process_composite_for_date(cfg: RuntimeConfig, end_dt: datetime, interval: int) -> Optional[str]:
    """Build and publish a 3-day or 8-day MH1 productivity composite."""
    if interval not in (3, 8):
        raise ValueError("Only 3-day and 8-day composites are configured for this workflow.")

    dates = daily_window(end_dt, interval)
    start_dt = dates[0]
    fname = composite_output_name(start_dt, end_dt, interval)
    stream = f"composite_{interval}"
    out_blob = _blob_name(cfg.output_prefixes[stream], fname, end_dt.year, cfg.year_partition_outputs)
    client = gcs_client()

    if blob_exists(client, cfg.bucket, out_blob) and not cfg.overwrite:
        log.info("Composite output already exists, skipping: gs://%s/%s", cfg.bucket, out_blob)
        return None

    work_dir = cfg.work_base / f"mh1_primprod_{interval}day" / f"{end_dt:%Y%j}"
    results_dir = cfg.results_base / f"mh1_primprod_{interval}day"
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    day_files = download_daily_npp_for_composite(cfg, dates, work_dir)
    if not day_files:
        raise RuntimeError(f"No daily NPP files available for {interval}-day composite ending {end_dt.date()}")

    mean = None
    num = None
    lat = lon = None
    source_files = []

    for dt in dates:
        f = day_files.get(dt)
        if f is None:
            log.warning("Missing daily NPP for composite date: %s", dt.date())
            continue
        source_files.append(f.name)
        with netCDF4.Dataset(f, "r") as ds:
            pprod = ma.masked_invalid(np.squeeze(ds.variables["MHPProd"][:]))
            if lat is None:
                lat = ds.variables["latitude"][:]
                lon = ds.variables["longitude"][:]

        if mean is None:
            mean = np.zeros(pprod.shape, np.single)
            num = np.zeros(pprod.shape, dtype=np.int32)
        mean, num = update_mean(mean, num, pprod)

    if mean is None or num.max() == 0:
        raise RuntimeError(f"No valid pixels for {interval}-day composite ending {end_dt.date()}")

    mean = ma.array(mean, mask=(num == 0), fill_value=-99999.0)
    tmp = work_dir / "temp_composite.nc"
    final = results_dir / fname
    write_composite_npp(tmp, interval, start_dt, end_dt, lat, lon, mean, num, source_files)
    compress_with_nccopy(tmp, final)
    upload_blob(client, cfg.bucket, final, out_blob)

    if not cfg.keep_local_results:
        shutil.rmtree(work_dir, ignore_errors=True)
        final.unlink(missing_ok=True)

    return out_blob
