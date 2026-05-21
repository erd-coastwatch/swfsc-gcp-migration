# NSIDC Sea Ice Concentration CDR Cloud Run Workflow

This repository contains the containerized Google Cloud Run workflow used to mirror and publish NOAA/NSIDC Climate Data Record (CDR) sea ice concentration products for ERDDAP publication.

The workflow downloads daily and monthly NSIDC G02202 Version 6 NetCDF files, compresses them with `nccopy`, and publishes the final files to cloud storage using the same north/south pole directory structure expected by ERDDAP.

## Repository layout

```text
.
├── config/
│   ├── config.yaml        # Runtime configuration
│   └── requirements.txt   # Python dependencies
├── deploy_job.sh          # Build, deploy, and schedule Cloud Run jobs
├── Dockerfile             # Container definition
├── entrypoint.sh          # Cloud Run startup script
├── scripts/
│   ├── control_nsidc.py
│   ├── make_nsidc_daily_v6.py
│   └── make_nsidc_monthly_v6.py
├── src/
│   └── __init__.py
├── templates/
│   └── example.cdl        # Placeholder template retained with the repo
├── CHANGELOG.md
├── LICENSE
└── README.md
```

## Products

The workflow publishes NSIDC G02202 Version 6 sea ice concentration CDR products for both hemispheres.

| Product stream | Source cadence | Output organization |
|---|---|---|
| Daily sea ice concentration CDR | daily | `<prefix>/<pole>/daily/<year>/<file>.nc` |
| Monthly sea ice concentration CDR | monthly | `<prefix>/<pole>/monthly/<file>.nc` |

The configured poles are:

- `north`
- `south`

## Cloud Run execution model

The same container image supports both daily and monthly processing. Runtime behavior is selected with the `MODE` environment variable.

| Mode | Worker | Description |
|---|---|---|
| `daily` | `make_nsidc_daily_v6.py` | Checks recent daily NSIDC files and publishes missing daily products. |
| `monthly` | `make_nsidc_monthly_v6.py` | Uses Smart Discovery and a daily-data guardrail to publish complete monthly products. |

The deployment script creates two Cloud Run Jobs:

| Cloud Run Job | Runtime mode | Schedule |
|---|---|---|
| `nsidc-cdr-daily` | `MODE=daily` | Daily at 10:00 America/Los_Angeles |
| `nsidc-cdr-monthly` | `MODE=monthly` | 09:00 America/Los_Angeles on the 5th and 15th of each month |

## Daily workflow

The daily job checks a configurable lookback window and processes files that are missing from the publication bucket.

For each pole and date, the daily worker:

1. Builds the NSIDC source URL from the configured base URL, pole, and year.
2. Scrapes the NSIDC HTTP directory for matching `.nc` files.
3. Compares remote filenames with files already present in cloud storage.
4. Downloads missing files to a temporary work directory.
5. Compresses each file with `nccopy`.
6. Uploads the compressed file to the configured cloud-storage prefix.
7. Removes local temporary files.

When `START_DATE` and `END_DATE` are supplied, the daily job processes that exact date range. Otherwise, it uses the configured recent lookback window.

## Monthly workflow

The monthly job is designed to avoid publishing incomplete months.

In normal Smart Discovery mode, the workflow:

1. Finds the latest monthly file already present in cloud storage for each pole.
2. Targets the next calendar month.
3. Checks for at least one daily file from the following month before processing.
4. Scrapes the NSIDC monthly source directory.
5. Downloads, compresses, and uploads missing monthly files.

The daily-data guardrail helps confirm that the target month is complete before the monthly product is published. Explicit `START_DATE` and `END_DATE` backfills bypass this guardrail.

## Runtime configuration

Runtime behavior is controlled by `config/config.yaml`.

Major configuration sections include:

| Section | Purpose |
|---|---|
| `logging` | Runtime log level and message format. |
| `source` | NSIDC source base URL and pole list. |
| `gcs` | Publication bucket and output prefix. |
| `work` | Writable runtime work directory and local cleanup behavior. |
| `compression` | `nccopy` compression level. |
| `processing` | Default daily lookback window. |

The container also supports runtime environment overrides:

| Variable | Purpose |
|---|---|
| `MODE` | Selects `daily` or `monthly` processing. |
| `GCS_BUCKET` | Overrides the configured publication bucket. |
| `LOG_LEVEL` | Overrides the configured log level. |
| `START_DATE` | Optional explicit start date in `YYYY-MM-DD` format. |
| `END_DATE` | Optional explicit end date in `YYYY-MM-DD` format. |

## External tools

The workflow uses NetCDF Operators inside the container:

- `nccopy`

`nccopy` is used to apply compression before uploading files to cloud storage.

## Public documentation notes

Do not commit real project IDs, service accounts, private bucket names, credential files, local machine paths, or deployment-specific secrets to a public documentation copy of this repository.
