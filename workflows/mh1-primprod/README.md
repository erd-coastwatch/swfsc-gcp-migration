# MODIS-Aqua MH1 Primary Productivity Cloud Run Workflow

This repository contains the containerized Google Cloud Run workflow used to generate MODIS-Aqua MH1 net primary productivity products for ERDDAP publication.

The workflow reads daily MH1 NRT chlorophyll-a, PAR, and SST-mask inputs, calculates primary productivity using the Behrenfeld-Falkowski formulation, writes ERDDAP-facing NetCDF outputs, and builds 3-day and 8-day composite products from the daily outputs.

## Repository layout

```text
.
├── config/
│   ├── config.yml          # Runtime configuration
│   └── requirements.txt    # Python dependencies
├── scripts/
│   ├── control_mh1_primprod.py
│   └── update_mh1_primprod_daily.py
├── src/
│   ├── npp_utils.py
│   ├── ppCompositeUtil.py
│   ├── primprodUtil.py
│   └── __init__.py
├── templates/
│   ├── LatLon.nc
│   ├── daylen.nc
│   └── worlddaylen.nc
├── Dockerfile
├── entrypoint.sh
├── deploy_job.sh
├── backfill_temp.sh
├── CHANGELOG.md
├── LICENSE
└── README.md
```

## Products

The workflow produces three ERDDAP-ready product streams:

| Product stream | Output prefix | Example output |
|---|---|---|
| Daily MH1 primary productivity | `satellite/PPMH/1day/` | `AYYYYDDD.L3m_DAY_primprod.nc` |
| 3-day composite | `satellite/PPMH/3day/` | `AYYYYDDD_AYYYYDDD_3day_primprod.nc` |
| 8-day composite | `satellite/PPMH/8day/` | `AYYYYDDD_AYYYYDDD_8day_primprod.nc` |

The processing inputs are MH1 NRT chlorophyll-a, PAR, and SST-mask files staged in cloud storage.

## Cloud Run execution model

The container entrypoint prepares `/tmp` working directories, checks that reference files are available, and launches the controller:

```text
entrypoint.sh
  -> scripts/control_mh1_primprod.py
     -> src/npp_utils.py
```

The controller uses the `MODE` environment variable to select the processing branch.

| `MODE` | Description |
|---|---|
| `daily` | Builds one daily MH1 primary productivity file. |
| `composite_3` | Builds one 3-day composite from daily productivity files. |
| `composite_8` | Builds one 8-day composite from daily productivity files. |

The deployed Cloud Run Jobs are:

| Job | Mode | Schedule |
|---|---|---|
| `mh1-primprod-daily` | `daily` | Daily at 12:00 America/Los_Angeles |
| `mh1-primprod-3day` | `composite_3` | Daily at 12:30 America/Los_Angeles |
| `mh1-primprod-8day` | `composite_8` | Daily at 12:35 America/Los_Angeles |

## Daily workflow

For each target date, the daily workflow:

1. Resolves the target processing date from `RUN_DATE` or current UTC date minus `DAYS_LAG`.
2. Checks whether the final daily output already exists in cloud storage.
3. Stages the required chlorophyll-a, PAR, and SST-mask input files from cloud storage.
4. Links static reference files from `templates/` into the temporary working directory.
5. Reads the Level-3 mapped inputs as masked arrays.
6. Loads the matching daylength grid.
7. Calculates net primary productivity using the Behrenfeld-Falkowski method.
8. Writes a daily NetCDF product with ERDDAP-facing metadata.
9. Compresses the result with `nccopy` when available.
10. Uploads the final product to cloud storage.
11. Removes temporary working files unless local retention is enabled.

## Composite workflow

The 3-day and 8-day workflows use daily productivity files as inputs.

For each composite run, the workflow:

1. Builds the date window ending on the target date.
2. Downloads the available daily productivity files for that window.
3. Reads each daily `MHPProd` field.
4. Updates a pixel-wise running mean and observation count.
5. Writes a composite NetCDF product with time bounds, mean productivity, and `nobs`.
6. Compresses and uploads the final composite product.
7. Removes temporary working files unless local retention is enabled.

## Runtime configuration

Runtime behavior is controlled by `config/config.yml` and environment variables.

Important configuration sections include:

| Section | Purpose |
|---|---|
| `gcs.bucket` | Target bucket used for inputs and outputs. |
| `gcs.input_prefixes` | Cloud prefixes for MH1 chlorophyll-a, PAR, and SST-mask inputs. |
| `gcs.output_prefixes` | Cloud prefixes for daily, 3-day, and 8-day productivity outputs. |
| `runtime` | Working directories, default lag, local retention, and overwrite behavior. |
| `reference_files` | Static daylength reference file names. |

Important environment variables include:

| Variable | Default | Purpose |
|---|---|---|
| `MODE` | `daily` | Selects daily, 3-day composite, or 8-day composite processing. |
| `GCS_BUCKET` | configured bucket | Overrides the configured cloud bucket. |
| `RUN_DATE` | unset | Optional target date in `YYYY-MM-DD` format. |
| `DAYS_LAG` | configured lag | Days subtracted from current UTC when `RUN_DATE` is unset. |
| `OVERWRITE` | configured value | Allows outputs to be regenerated when set true. |
| `KEEP_LOCAL_RESULTS` | configured value | Retains temporary results when set true. |
| `WORK_BASE` | configured path | Base temporary working directory. |
| `RESULTS_BASE` | configured path | Base temporary results directory. |

## Static reference files

The workflow uses binary NetCDF reference files in `templates/`:

| File | Purpose |
|---|---|
| `LatLon.nc` | Static latitude/longitude reference file retained with the workflow. |
| `daylen.nc` | Legacy daylength reference file; large binary file. |
| `worlddaylen.nc` | Daylength reference used by the Cloud Run workflow. |

Binary NetCDF reference files should be included only when operationally required. They should not be rendered as Quarto code pages. Large binary files may need to be managed outside Git or with Git LFS.

## Legacy utilities

The repository keeps legacy productivity and composite utility modules in `src/primprodUtil.py` and `src/ppCompositeUtil.py`. The Cloud Run path uses `src/npp_utils.py` for config-driven processing, while preserving the legacy productivity math and file naming conventions.

## Notes for public documentation copies

Do not commit real project IDs, service accounts, private bucket names, credential files, local machine paths, or deployment-specific secrets to a public documentation copy of this repository.
