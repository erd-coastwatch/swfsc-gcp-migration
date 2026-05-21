# CRW SST/SSTA Cloud Run Workflow

This repository contains the containerized Google Cloud Run workflow used to generate NOAA Coral Reef Watch (CRW) 5 km sea surface temperature (SST) and sea surface temperature anomaly (SSTA) products for ERDDAP publication.

The workflow downloads daily and monthly CRW NetCDF source files, combines SST and SSTA fields into ERDDAP-facing NetCDF products, compresses the outputs, archives source files, and publishes final products to cloud storage.

## Repository layout

```text
.
├── config/
│   ├── config.yml          # Reserved for future runtime configuration
│   └── requirements.txt    # Python dependencies
├── scripts/
│   ├── control_crw_daily.py          # Daily controller
│   ├── control_crw_monthly.py        # Monthly controller
│   ├── update_sst_ssta_daily.py      # Daily SST/SSTA product builder
│   └── update_sst_ssta_monthly.py    # Monthly SST/SSTA product builder
├── templates/
│   └── lat_lon_source2023b.nc        # Output template/grid source
├── Dockerfile
├── entrypoint.sh
├── deploy_job.sh
├── CHANGELOG.md
├── LICENSE
└── README.md
```

## Products

The workflow publishes two ERDDAP-ready product streams:

| Product | Output prefix | Example output |
|---|---|---|
| Daily SST/SSTA | `satellite/CRW2/1day/` | `ct5km_sst_ssta_daily_v31_YYYYMMDD.nc` |
| Monthly SST/SSTA | `satellite/CRW2/mday/` | `ct5km_sst_ssta_monthly_v31_YYYYMM.nc` |

Raw CRW source files are also archived to the work/source bucket under `CRW2/source/`.

## Cloud Run execution model

The container entrypoint prepares writable runtime directories under `/tmp`, resolves the target cloud bucket, and dispatches to either the daily or monthly controller based on the `JOB_TYPE` environment variable.

```text
entrypoint.sh
  -> JOB_TYPE=daily
     -> scripts/control_crw_daily.py
        -> scripts/update_sst_ssta_daily.py

entrypoint.sh
  -> JOB_TYPE=monthly
     -> scripts/control_crw_monthly.py
        -> scripts/update_sst_ssta_monthly.py
```

Supported runtime modes are:

| `JOB_TYPE` | Description |
|---|---|
| `daily` | Builds missing daily CRW SST/SSTA products over a recent lookback window. |
| `monthly` | Builds missing monthly CRW SST/SSTA products over the recent two-year monthly window. |

## Daily workflow

The daily controller checks the production bucket for existing daily outputs, identifies missing dates, and runs the daily worker only for dates that need to be built.

By default, the daily job evaluates the last `LOOKBACK_DAYS` days, excluding today. For backfills, `BACKFILL_START_DATE=YYYY-MM-DD` can be set to process from that date through yesterday, while still skipping dates already present in cloud storage.

For each date, the daily worker:

1. Downloads the CRW daily SST source file.
2. Downloads the CRW daily SSTA source file.
3. Archives both source files to the work/source bucket.
4. Copies the static latitude/longitude template into a working NetCDF output.
5. Reads SST, SSTA, and mask variables from the source files.
6. Flips the SST latitude orientation when needed to match the output template.
7. Writes SST, SSTA, mask, and time values into the output file.
8. Compresses the merged NetCDF file with `nccopy`.
9. Uploads the final ERDDAP-facing daily file to cloud storage.
10. Removes temporary runtime files.

## Monthly workflow

The monthly controller checks the production bucket for existing monthly outputs and evaluates a rolling two-year monthly window through the previous completed month.

For each missing month, the monthly worker:

1. Downloads the CRW monthly SST mean file.
2. Downloads the CRW monthly SSTA mean file.
3. Archives both source files to the work/source bucket.
4. Copies the static latitude/longitude template into a working NetCDF output.
5. Writes monthly SST, SSTA, mask, and time values into the output file.
6. Compresses the merged NetCDF file with `nccopy`.
7. Uploads the final ERDDAP-facing monthly file to cloud storage.
8. Removes temporary runtime files.

## Runtime configuration

Most runtime behavior is currently controlled through environment variables and constants in the controller/worker scripts.

Important environment variables include:

| Variable | Default | Purpose |
|---|---|---|
| `GCS_BUCKET` | `YOUR_PRODUCTION_BUCKET` | Production/publication bucket for final ERDDAP-facing outputs. |
| `JOB_TYPE` | `monthly` | Selects `daily` or `monthly` mode in `entrypoint.sh`. |
| `LOOKBACK_DAYS` | `3` | Number of recent days evaluated by the daily controller. |
| `BACKFILL_START_DATE` | unset | Optional daily backfill start date in `YYYY-MM-DD` format. |

The current `config/config.yml` file is reserved for future configuration centralization. At present, the workflow is primarily configured through environment variables and script-level constants.

## Deployment

`deploy_job.sh` builds and pushes the container image, deploys separate Cloud Run Jobs for daily and monthly processing, and configures Cloud Scheduler triggers.

The deployed jobs are:

| Job | Schedule |
|---|---|
| `crw-daily-processor` | Daily at 10:00 America/Los_Angeles |
| `crw-monthly-processor` | 04:00 America/Los_Angeles on days 2, 4, 10, 12, 15, and 18 of each month |

The monthly schedule mirrors the legacy on-premises retry cadence and allows late-arriving CRW monthly files to be picked up after publication.

## Notes for public documentation copies

Do not commit real project IDs, service accounts, private bucket names, local paths, credential files, or deployment-specific secrets to a public documentation copy of this repository.
