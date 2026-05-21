# ASCAT-C Wind Processing Cloud Run Workflow

This repository contains the containerized Google Cloud Run workflow used to generate CoastWatch-style ASCAT-C wind products for ERDDAP publication.

The workflow ingests Metop-C ASCAT 4-hour wind files, derives value-added wind products, writes CoastWatch-compatible NetCDF outputs, and builds temporal composites from those 4-hour products.

The workflow produces:

- 4-hour ASCAT-C wind products
- 1-day composites
- 3-day composites
- 7-day composites
- monthly composites

Derived variables include zonal and meridional wind components, wind stress, wind curl, wind divergence, wind-driven currents, and Ekman upwelling.

## Repository layout

```text
.
├── config/
│   ├── config_update.yaml       # 4-hour ingestion configuration
│   ├── config_composite.yaml    # composite-generation configuration
│   └── requirements.txt         # Python dependencies
├── scripts/
│   ├── download_ascat_4hr.py        # 4-hour ingestion driver
│   ├── make_ascat_multiday.py       # multi-day/monthly composite builder
│   └── ascat_composite_control.py   # Cloud Run composite controller
├── src/
│   ├── ascatc_4hr_functions.py
│   ├── ascatc_multiday_functions.py
│   └── __init__.py
├── templates/
│   ├── ascat_c.cdl
│   ├── ascat_c.nc
│   └── example.cdl
├── Dockerfile
├── entrypoint.sh
├── deploy_job.sh
├── CHANGELOG.md
├── LICENSE
└── README.md
```

## Cloud Run execution model

The same container image supports both daily and monthly processing. Runtime behavior is selected by the `JOB_MODE` environment variable in `entrypoint.sh`.

| Mode | Description |
|---|---|
| `daily` | Warms recent 4-hour input cache, ingests new 4-hour ASCAT-C files, and builds 1-, 3-, and 7-day composites. |
| `monthly` | Warms the previous month of daily products and builds the monthly composite. |

The deployment script creates two Cloud Run Jobs:

| Cloud Run Job | Runtime mode | Schedule |
|---|---|---|
| `ascat-daily-processor` | `JOB_MODE=daily` | Daily at 18:15 America/Los_Angeles |
| `ascat-monthly-processor` | `JOB_MODE=monthly` | 22:30 America/Los_Angeles on the 3rd of each month |

## Daily workflow

The daily Cloud Run job performs two stages.

First, the container warms its local `/tmp` cache by copying recent 4-hour ASCAT-C outputs from cloud storage. This gives the composite step enough input files to build 1-, 3-, and 7-day products even though Cloud Run starts with an empty filesystem.

Second, the workflow runs the 4-hour ingestion and composite drivers:

```text
entrypoint.sh
  -> scripts.download_ascat_4hr
  -> scripts.ascat_composite_control multi-day
  -> scripts.make_ascat_multiday
```

The 4-hour ingestion step:

1. Scrapes the remote NOAA ASCAT-C source directory.
2. Compares remote files to already-published 4-hour files in cloud storage.
3. Downloads only missing source files.
4. Computes derived wind products.
5. Writes CoastWatch-compatible NetCDF outputs from the configured template.
6. Uploads final 4-hour outputs to cloud storage.
7. Cleans local staging files.

The multi-day composite step:

1. Selects the target date, usually yesterday in UTC.
2. Finds the required 4-hour inputs for each composite window.
3. Uses NCO tools to concatenate and average input files.
4. Applies time and global metadata.
5. Compresses the final NetCDF products.
6. Publishes 1-, 3-, and 7-day outputs to cloud storage.

## Monthly workflow

The monthly job builds monthly ASCAT-C composites from daily products.

At startup, the container warms the previous month of daily files from cloud storage. It then runs:

```text
entrypoint.sh
  -> scripts.ascat_composite_control monthly
  -> scripts.make_ascat_multiday --make-month
```

The monthly composite step:

1. Selects the previous completed month.
2. Finds the daily files for that month.
3. Uses NCO tools to average the daily inputs.
4. Sets the monthly center time to the 16th day of the month.
5. Compresses the monthly output.
6. Publishes the monthly product to cloud storage.

## Runtime configuration

Runtime behavior is controlled by two YAML files:

| File | Purpose |
|---|---|
| `config/config_update.yaml` | 4-hour ingestion settings, including source URL, local paths, buckets, and 4-hour archive/publish prefixes. |
| `config/config_composite.yaml` | Composite settings, including composite windows, local paths, buckets, publish prefixes, and NetCDF compression level. |

The container also uses environment variables set by `deploy_job.sh` and Cloud Run:

| Variable | Default | Purpose |
|---|---|---|
| `JOB_MODE` | `daily` | Selects `daily` or `monthly` entrypoint behavior. |
| `PROD_BUCKET` | production bucket | Bucket used to warm local cache from prior outputs. |
| `ARCHIVE_4HR` | `edge/ASCAT/4hr` | Prefix for cached 4-hour products. |
| `ARCHIVE_1DAY` | `edge/ASCAT/1day` | Prefix for cached daily products used by monthly composites. |
| `LOG_LEVEL` | `INFO` | Logging level passed to Python drivers. |
| `DRY_RUN` | unset | When set, passes dry-run behavior to supported scripts. |
| `OVERWRITE` | unset | When set, allows supported composite outputs to be overwritten. |
| `BACKFILL` | unset | When set, passes backfill behavior to supported composite scripts. |

## External tools

The workflow uses NetCDF Operators inside the container:

- `ncks`
- `ncra`
- `nccopy`

These are used to concatenate, average, edit, and compress NetCDF files.

## Output organization

Outputs are published under ASCAT-specific cloud-storage prefixes. The active configuration uses separate prefixes for 4-hour products, multi-day composites, and monthly composites.

Expected product families are:

| Product family | Typical prefix |
|---|---|
| 4-hour products | `edge/ASCAT/4hr` |
| 1-day composites | `edge/ASCAT/1day` |
| 3-day composites | `edge/ASCAT/3day` |
| 7-day composites | `edge/ASCAT/7day` |
| monthly composites | `edge/ASCAT/mday` |

## Templates

The workflow uses NetCDF/CDL templates in `templates/` to define the structure and metadata of generated products.

The main template files are:

- `ascat_c.cdl`
- `ascat_c.nc`
- `example.cdl`

Binary NetCDF templates should be included in the repository copy but should not be rendered as Quarto code pages.

## Notes for public documentation copies

Do not commit real project IDs, service accounts, private bucket names, credential files, local machine paths, or deployment-specific secrets to a public documentation copy of this repository.
