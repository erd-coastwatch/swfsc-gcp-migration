from pathlib import Path

pages = [
    # =========================================================
    # MH1 / MPOC / MPIC PROCESSOR
    # =========================================================

    ("code-pages/mh1-processor/dockerfile.qmd",
     "Dockerfile",
     "dockerfile",
     "Container environment for the MH1/MPOC/MPIC processor workflow.",
     "workflows/mh1-mpoc-mpic-processor/Dockerfile"),

    ("code-pages/mh1-processor/entrypoint.qmd",
     "entrypoint.sh",
     "bash",
     "Cloud Run entrypoint; runs all NRT then all Science suites in sequence.",
     "workflows/mh1-mpoc-mpic-processor/entrypoint.sh"),

    ("code-pages/mh1-processor/deploy_job.qmd",
     "deploy_job.sh",
     "bash",
     "Builds, pushes, and deploys the Cloud Run job and scheduler.",
     "workflows/mh1-mpoc-mpic-processor/deploy_job.sh"),

    ("code-pages/mh1-processor/config.qmd",
     "config.yml",
     "yaml",
     "Runtime configuration — GCS buckets, NASA endpoints, publish targets.",
     "workflows/mh1-mpoc-mpic-processor/config/config.yml"),

    ("code-pages/mh1-processor/requirements.qmd",
     "requirements.txt",
     "text",
     "Python dependencies.",
     "workflows/mh1-mpoc-mpic-processor/config/requirements.txt"),

    ("code-pages/mh1-processor/roylib.qmd",
     "roylib.py",
     "python",
     "Shared GCS helpers, NASA API queries, and processing utilities.",
     "workflows/mh1-mpoc-mpic-processor/src/roylib.py"),

    ("code-pages/mh1-processor/getMH1OceanColor_NRT.qmd",
     "getMH1OceanColor_NRT.py",
     "python",
     "NRT MODIS-Aqua ocean color retrieval (chlorophyll-a, nFLH, PAR, Kd490).",
     "workflows/mh1-mpoc-mpic-processor/scripts/MH1/getMH1OceanColor_NRT.py"),

    ("code-pages/mh1-processor/getMH1OceanColor_Sci.qmd",
     "getMH1OceanColor_Sci.py",
     "python",
     "Science quality MODIS-Aqua ocean color retrieval (chlorophyll-a, nFLH, PAR, Kd490).",
     "workflows/mh1-mpoc-mpic-processor/scripts/MH1/getMH1OceanColor_Sci.py"),

    ("code-pages/mh1-processor/getMH1SST_NRT.qmd",
     "getMH1SST_NRT.py",
     "python",
     "NRT MODIS-Aqua SST retrieval and qual_sst masking.",
     "workflows/mh1-mpoc-mpic-processor/scripts/MH1/getMH1SST_NRT.py"),

    ("code-pages/mh1-processor/getMH1SST_Sci.qmd",
     "getMH1SST_Sci.py",
     "python",
     "Science quality MODIS-Aqua SST retrieval and qual_sst masking.",
     "workflows/mh1-mpoc-mpic-processor/scripts/MH1/getMH1SST_Sci.py"),

    ("code-pages/mh1-processor/getMPIC_NRT.qmd",
     "getMPIC_NRT.py",
     "python",
     "NRT MODIS-Aqua particulate inorganic carbon (PIC) retrieval.",
     "workflows/mh1-mpoc-mpic-processor/scripts/MPIC/getMPIC_NRT.py"),

    ("code-pages/mh1-processor/getMPIC_Sci.qmd",
     "getMPIC_Sci.py",
     "python",
     "Science quality MODIS-Aqua particulate inorganic carbon (PIC) retrieval.",
     "workflows/mh1-mpoc-mpic-processor/scripts/MPIC/getMPIC_Sci.py"),

    ("code-pages/mh1-processor/getMPOC_NRT.qmd",
     "getMPOC_NRT.py",
     "python",
     "NRT MODIS-Aqua particulate organic carbon (POC) retrieval.",
     "workflows/mh1-mpoc-mpic-processor/scripts/MPOC/getMPOC_NRT.py"),

    ("code-pages/mh1-processor/getMPOC_Sci.qmd",
     "getMPOC_Sci.py",
     "python",
     "Science quality MODIS-Aqua particulate organic carbon (POC) retrieval.",
     "workflows/mh1-mpoc-mpic-processor/scripts/MPOC/getMPOC_Sci.py"),

    # =========================================================
    # MUR SST
    # =========================================================

    ("code-pages/mur-sst/dockerfile.qmd",
     "Dockerfile",
     "dockerfile",
     "Container environment for the MUR SST workflow.",
     "workflows/mur-daily-workflows/Dockerfile"),

    ("code-pages/mur-sst/entrypoint.qmd",
     "entrypoint.sh",
     "bash",
     "Cloud Run entrypoint and job mode selector.",
     "workflows/mur-daily-workflows/entrypoint.sh"),

    ("code-pages/mur-sst/deploy_job.qmd",
     "deploy_job.sh",
     "bash",
     "Builds, deploys, and schedules Cloud Run jobs.",
     "workflows/mur-daily-workflows/deploy_job.sh"),

    ("code-pages/mur-sst/config.qmd",
     "config.yml",
     "yaml",
     "Workflow configuration.",
     "workflows/mur-daily-workflows/config/config.yml"),

    ("code-pages/mur-sst/requirements.qmd",
     "requirements.txt",
     "text",
     "Python dependencies.",
     "workflows/mur-daily-workflows/config/requirements.txt"),

    ("code-pages/mur-sst/roylib.qmd",
     "roylib.py",
     "python",
     "Workflow-specific configuration and GCS publishing utilities for the MUR SST workflow.",
     "workflows/mur-daily-workflows/src/roylib.py"),

    ("code-pages/mur-sst/mur_v41_downloader_dailyproc.qmd",
     "mur_v41_downloader_dailyproc.sh",
     "bash",
     "Daily MUR v4.1 download and processing driver.",
     "workflows/mur-daily-workflows/scripts/mur_v41_downloader_dailyproc.sh"),

    ("code-pages/mur-sst/mur_v42_downloader.qmd",
     "mur_v42_downloader.sh",
     "bash",
     "MUR v4.2 download driver.",
     "workflows/mur-daily-workflows/scripts/mur_v42_downloader.sh"),

    ("code-pages/mur-sst/MURanom1day.qmd",
     "MURanom1day.py",
     "python",
     "Daily anomaly computation for MUR v4.1.",
     "workflows/mur-daily-workflows/scripts/MURanom1day.py"),

    ("code-pages/mur-sst/calc_mur_fronts.qmd",
     "calc_mur_fronts.py",
     "python",
     "Front detection workflow for MUR SST.",
     "workflows/mur-daily-workflows/scripts/fronts/calc_mur_fronts.py"),

    ("code-pages/mur-sst/canny_lib.qmd",
     "canny_lib.py",
     "python",
     "Shared Canny edge-detection utilities.",
     "workflows/mur-daily-workflows/scripts/fronts/canny_lib.py"),

    ("code-pages/mur-sst/Canny1.qmd",
     "Canny1.py",
     "python",
     "First-stage Canny front processing.",
     "workflows/mur-daily-workflows/scripts/fronts/Canny1.py"),

    ("code-pages/mur-sst/Canny2.qmd",
     "Canny2.py",
     "python",
     "Second-stage Canny front processing.",
     "workflows/mur-daily-workflows/scripts/fronts/Canny2.py"),

    ("code-pages/mur-sst/MUR41_MonProc.qmd",
     "MUR41_MonProc.sh",
     "bash",
     "Monthly MUR v4.1 processing driver.",
     "workflows/mur-daily-workflows/scripts/MonthlyProc/MUR41_MonProc.sh"),

    ("code-pages/mur-sst/CompMURmon.qmd",
     "CompMURmon.py",
     "python",
     "Monthly MUR composite generation.",
     "workflows/mur-daily-workflows/scripts/MonthlyProc/CompMURmon.py"),

    ("code-pages/mur-sst/CompMurAnomMon.qmd",
     "CompMurAnomMon.py",
     "python",
     "Monthly MUR anomaly composite generation.",
     "workflows/mur-daily-workflows/scripts/MonthlyProc/CompMurAnomMon.py"),

    # =========================================================
    # VIIRS NETPP
    # =========================================================

    ("code-pages/viirs-netpp/dockerfile.qmd",
     "Dockerfile",
     "dockerfile",
     "Container environment for the VIIRS NetPP workflow.",
     "workflows/viirs-netpp/Dockerfile"),

    ("code-pages/viirs-netpp/entrypoint.qmd",
     "entrypoint.sh",
     "bash",
     "Cloud Run entrypoint and job mode selector.",
     "workflows/viirs-netpp/entrypoint.sh"),

    ("code-pages/viirs-netpp/deploy_job.qmd",
     "deploy_job.sh",
     "bash",
     "Builds, deploys, and schedules Cloud Run jobs.",
     "workflows/viirs-netpp/deploy_job.sh"),

    ("code-pages/viirs-netpp/config.qmd",
     "config.yml",
     "yaml",
     "Workflow configuration.",
     "workflows/viirs-netpp/config/config.yml"),

    ("code-pages/viirs-netpp/requirements.qmd",
     "requirements.txt",
     "text",
     "Python dependencies.",
     "workflows/viirs-netpp/config/requirements.txt"),

    ("code-pages/viirs-netpp/control_viirs_netpp.qmd",
     "control_viirs_netpp.py",
     "python",
     "Daily VIIRS NetPP controller.",
     "workflows/viirs-netpp/scripts/control_viirs_netpp.py"),

    ("code-pages/viirs-netpp/control_viirs_netpp_monthly.qmd",
     "control_viirs_netpp_monthly.py",
     "python",
     "Monthly VIIRS NetPP controller.",
     "workflows/viirs-netpp/scripts/control_viirs_netpp_monthly.py"),

    ("code-pages/viirs-netpp/make_viirs_netpp.qmd",
     "make_viirs_netpp.py",
     "python",
     "Daily Net Primary Productivity generation.",
     "workflows/viirs-netpp/scripts/make_viirs_netpp.py"),

    ("code-pages/viirs-netpp/make_viirs_netpp_monthly.qmd",
     "make_viirs_netpp_monthly.py",
     "python",
     "Monthly Net Primary Productivity generation.",
     "workflows/viirs-netpp/scripts/make_viirs_netpp_monthly.py"),

    # =========================================================
    # CHARM
    # =========================================================

    ("code-pages/charm/dockerfile.qmd",
     "Dockerfile",
     "dockerfile",
     "Container environment for the CHARM workflow.",
     "workflows/charm/Dockerfile"),

    ("code-pages/charm/entrypoint.qmd",
     "entrypoint.sh",
     "bash",
     "Cloud Run entrypoint and job mode selector.",
     "workflows/charm/entrypoint.sh"),

    ("code-pages/charm/deploy_job.qmd",
     "deploy_job.sh",
     "bash",
     "Builds, deploys, and schedules the CHARM Cloud Run job.",
     "workflows/charm/deploy_job.sh"),

    ("code-pages/charm/config.qmd",
     "config.yaml",
     "yaml",
     "Main CHARM workflow configuration.",
     "workflows/charm/config/config.yaml"),

    ("code-pages/charm/requirements.qmd",
     "requirements.txt",
     "text",
     "Python dependencies for the CHARM container.",
     "workflows/charm/config/requirements.txt"),

    ("code-pages/charm/control_charm_cron_v1.qmd",
     "control_charm_cron_v1.py",
     "python",
     "Main CHARM cron controller.",
     "workflows/charm/scripts/control_charm_cron_v1.py"),

    ("code-pages/charm/make_charm_cloud_v1.qmd",
     "make_charm_cloud_v1.py",
     "python",
     "Primary CHARM cloud processing script.",
     "workflows/charm/scripts/make_charm_cloud_v1.py"),

    ("code-pages/charm/charm_data_process_functions.qmd",
     "charm_data_process_functions.py",
     "python",
     "Data processing utilities for CHARM inputs and outputs.",
     "workflows/charm/src/python/charm_data_process_functions.py"),

    ("code-pages/charm/charm_dineof_functions.qmd",
     "charm_dineof_functions.py",
     "python",
     "DINEOF gap-filling utilities used by CHARM.",
     "workflows/charm/src/python/charm_dineof_functions.py"),

    ("code-pages/charm/charm_helper_functions.qmd",
     "charm_helper_functions.py",
     "python",
     "General helper functions for the CHARM workflow.",
     "workflows/charm/src/python/charm_helper_functions.py"),

    ("code-pages/charm/charm_model_functions.qmd",
     "charm_model_functions.py",
     "python",
     "Model functions for CHARM habitat prediction.",
     "workflows/charm/src/python/charm_model_functions.py"),
         # CHARM DINEOF init files
    ("code-pages/charm/for_chlor_a_v4.qmd",
     "for_chlor_a_v4.init",
     "text",
     "DINEOF forecast configuration for chlorophyll-a.",
     "workflows/charm/config/dineof/chlor_a/for_chlor_a_v4.init"),

    ("code-pages/charm/now_chlor_a_v4.qmd",
     "now_chlor_a_v4.init",
     "text",
     "DINEOF nowcast configuration for chlorophyll-a.",
     "workflows/charm/config/dineof/chlor_a/now_chlor_a_v4.init"),

    ("code-pages/charm/for_Rrs_489_v4.qmd",
     "for_Rrs_489_v4.init",
     "text",
     "DINEOF forecast configuration for Rrs_489.",
     "workflows/charm/config/dineof/Rrs_489/for_Rrs_489_v4.init"),

    ("code-pages/charm/now_Rrs_489_v4.qmd",
     "now_Rrs_489_v4.init",
     "text",
     "DINEOF nowcast configuration for Rrs_489.",
     "workflows/charm/config/dineof/Rrs_489/now_Rrs_489_v4.init"),

    ("code-pages/charm/for_Rrs_556_v4.qmd",
     "for_Rrs_556_v4.init",
     "text",
     "DINEOF forecast configuration for Rrs_556.",
     "workflows/charm/config/dineof/Rrs_556/for_Rrs_556_v4.init"),

    ("code-pages/charm/now_Rrs_556_v4.qmd",
     "now_Rrs_556_v4.init",
     "text",
     "DINEOF nowcast configuration for Rrs_556.",
     "workflows/charm/config/dineof/Rrs_556/now_Rrs_556_v4.init"),

    ("code-pages/charm/for_bf_chlor_a_v4.qmd",
     "for_bf_chlor_a_v4.init",
     "text",
     "Backfill DINEOF forecast configuration for chlorophyll-a.",
     "workflows/charm/config/bf_dineof/chlor_a/for_bf_chlor_a_v4.init"),

    ("code-pages/charm/now_bf_chlor_a_v4.qmd",
     "now_bf_chlor_a_v4.init",
     "text",
     "Backfill DINEOF nowcast configuration for chlorophyll-a.",
     "workflows/charm/config/bf_dineof/chlor_a/now_bf_chlor_a_v4.init"),

    ("code-pages/charm/for_bf_Rrs_489_v4.qmd",
     "for_bf_Rrs_489_v4.init",
     "text",
     "Backfill DINEOF forecast configuration for Rrs_489.",
     "workflows/charm/config/bf_dineof/Rrs_489/for_bf_Rrs_489_v4.init"),

    ("code-pages/charm/now_bf_Rrs_489_v4.qmd",
     "now_bf_Rrs_489_v4.init",
     "text",
     "Backfill DINEOF nowcast configuration for Rrs_489.",
     "workflows/charm/config/bf_dineof/Rrs_489/now_bf_Rrs_489_v4.init"),

    ("code-pages/charm/for_bf_Rrs_556_v4.qmd",
     "for_bf_Rrs_556_v4.init",
     "text",
     "Backfill DINEOF forecast configuration for Rrs_556.",
     "workflows/charm/config/bf_dineof/Rrs_556/for_bf_Rrs_556_v4.init"),

    ("code-pages/charm/now_bf_Rrs_556_v4.qmd",
     "now_bf_Rrs_556_v4.init",
     "text",
     "Backfill DINEOF nowcast configuration for Rrs_556.",
     "workflows/charm/config/bf_dineof/Rrs_556/now_bf_Rrs_556_v4.init"),

    ("code-pages/charm/now_Rrs_556_v4.qmd",
     "now_Rrs_556_v4.init",
     "text",
     "Additional backfill DINEOF nowcast configuration for Rrs_556.",
     "workflows/charm/config/bf_dineof/Rrs_556/now_Rrs_556_v4.init"),

    ("code-pages/charm/viirs_L3.qmd",
     "viirs_L3.cdl",
     "text",
     "CDL template for VIIRS L3 NetCDF formatting.",
     "workflows/charm/templates/viirs_L3.cdl"),

         # =========================================================
    # CRW SST / SSTA
    # =========================================================

    ("code-pages/crw/dockerfile.qmd",
     "Dockerfile",
     "dockerfile",
     "Container environment for the CRW SST/SSTA workflow.",
     "workflows/crw/Dockerfile"),

    ("code-pages/crw/entrypoint.qmd",
     "entrypoint.sh",
     "bash",
     "Cloud Run entrypoint; dispatches daily or monthly CRW processing.",
     "workflows/crw/entrypoint.sh"),

    ("code-pages/crw/deploy_job.qmd",
     "deploy_job.sh",
     "bash",
     "Builds, deploys, and schedules the CRW Cloud Run jobs.",
     "workflows/crw/deploy_job.sh"),

    ("code-pages/crw/requirements.qmd",
     "requirements.txt",
     "text",
     "Python dependencies for the CRW container.",
     "workflows/crw/config/requirements.txt"),

    ("code-pages/crw/control_crw_daily.qmd",
     "control_crw_daily.py",
     "python",
     "Daily CRW controller; identifies missing daily SST/SSTA outputs and runs the daily worker.",
     "workflows/crw/scripts/control_crw_daily.py"),

    ("code-pages/crw/control_crw_monthly.qmd",
     "control_crw_monthly.py",
     "python",
     "Monthly CRW controller; identifies missing monthly SST/SSTA outputs and runs the monthly worker.",
     "workflows/crw/scripts/control_crw_monthly.py"),

    ("code-pages/crw/update_sst_ssta_daily.qmd",
     "update_sst_ssta_daily.py",
     "python",
     "Builds one daily combined CRW SST/SSTA NetCDF product.",
     "workflows/crw/scripts/update_sst_ssta_daily.py"),

    ("code-pages/crw/update_sst_ssta_monthly.qmd",
     "update_sst_ssta_monthly.py",
     "python",
     "Builds one monthly combined CRW SST/SSTA NetCDF product.",
     "workflows/crw/scripts/update_sst_ssta_monthly.py"),

    # =========================================================
    # ASCAT-C WIND
    # =========================================================

    ("code-pages/ascat/dockerfile.qmd",
     "Dockerfile",
     "dockerfile",
     "Container environment for the ASCAT-C wind workflow.",
     "workflows/ascat/Dockerfile"),

    ("code-pages/ascat/entrypoint.qmd",
     "entrypoint.sh",
     "bash",
     "Cloud Run entrypoint; dispatches daily or monthly ASCAT processing.",
     "workflows/ascat/entrypoint.sh"),

    ("code-pages/ascat/deploy_job.qmd",
     "deploy_job.sh",
     "bash",
     "Builds, deploys, and schedules the ASCAT Cloud Run jobs.",
     "workflows/ascat/deploy_job.sh"),

    ("code-pages/ascat/config_update.qmd",
     "config_update.yaml",
     "yaml",
     "Runtime configuration for 4-hour ASCAT-C ingestion and product generation.",
     "workflows/ascat/config/config_update.yaml"),

    ("code-pages/ascat/config_composite.qmd",
     "config_composite.yaml",
     "yaml",
     "Runtime configuration for ASCAT-C multi-day and monthly composites.",
     "workflows/ascat/config/config_composite.yaml"),

    ("code-pages/ascat/requirements.qmd",
     "requirements.txt",
     "text",
     "Python dependencies for the ASCAT container.",
     "workflows/ascat/config/requirements.txt"),

    ("code-pages/ascat/download_ascat_4hr.qmd",
     "download_ascat_4hr.py",
     "python",
     "Downloads ASCAT-C 4-hour wind files and generates value-added CoastWatch products.",
     "workflows/ascat/scripts/download_ascat_4hr.py"),

    ("code-pages/ascat/ascat_composite_control.qmd",
     "ascat_composite_control.py",
     "python",
     "Controller for daily multi-day and monthly ASCAT composite jobs.",
     "workflows/ascat/scripts/ascat_composite_control.py"),

    ("code-pages/ascat/make_ascat_multiday.qmd",
     "make_ascat_multiday.py",
     "python",
     "Builds 1-day, 3-day, 7-day, and monthly ASCAT-C wind composites.",
     "workflows/ascat/scripts/make_ascat_multiday.py"),

    ("code-pages/ascat/ascatc_4hr_functions.qmd",
     "ascatc_4hr_functions.py",
     "python",
     "Shared functions for ASCAT-C 4-hour ingestion and derived wind products.",
     "workflows/ascat/src/ascatc_4hr_functions.py"),

    ("code-pages/ascat/ascatc_multiday_functions.qmd",
     "ascatc_multiday_functions.py",
     "python",
     "Shared functions for ASCAT-C multi-day and monthly composite generation.",
     "workflows/ascat/src/ascatc_multiday_functions.py"),

    ("code-pages/ascat/ascat_c_cdl.qmd",
     "ascat_c.cdl",
     "text",
     "CDL template for ASCAT-C CoastWatch-compatible NetCDF outputs.",
     "workflows/ascat/templates/ascat_c.cdl"),

    ("code-pages/ascat/example_cdl.qmd",
     "example.cdl",
     "text",
     "Example CDL template retained with the ASCAT workflow.",
     "workflows/ascat/templates/example.cdl"),

    # =========================================================
    # MODIS-AQUA MH1 PRIMARY PRODUCTIVITY
    # =========================================================

    ("code-pages/mh1-primprod/dockerfile.qmd",
     "Dockerfile",
     "dockerfile",
     "Container environment for the MODIS-Aqua MH1 primary productivity workflow.",
     "workflows/mh1-primprod/Dockerfile"),

    ("code-pages/mh1-primprod/entrypoint.qmd",
     "entrypoint.sh",
     "bash",
     "Cloud Run entrypoint for the MH1 primary productivity workflow.",
     "workflows/mh1-primprod/entrypoint.sh"),

    ("code-pages/mh1-primprod/deploy_job.qmd",
     "deploy_job.sh",
     "bash",
     "Builds, deploys, and schedules the MH1 primary productivity Cloud Run job.",
     "workflows/mh1-primprod/deploy_job.sh"),

    ("code-pages/mh1-primprod/config.qmd",
     "config.yml",
     "yaml",
     "Runtime configuration for MODIS-Aqua primary productivity processing.",
     "workflows/mh1-primprod/config/config.yml"),

    ("code-pages/mh1-primprod/requirements.qmd",
     "requirements.txt",
     "text",
     "Python dependencies for the MH1 primary productivity container.",
     "workflows/mh1-primprod/config/requirements.txt"),

    ("code-pages/mh1-primprod/control_mh1_primprod.qmd",
     "control_mh1_primprod.py",
     "python",
     "Controller for daily and backfill MODIS-Aqua MH1 primary productivity runs.",
     "workflows/mh1-primprod/scripts/control_mh1_primprod.py"),

    ("code-pages/mh1-primprod/npp_utils.qmd",
     "npp_utils.py",
     "python",
     "Cloud Run utilities for downloading inputs, running NPP calculations, and publishing outputs.",
     "workflows/mh1-primprod/src/npp_utils.py"),

    ("code-pages/mh1-primprod/primprodUtil.qmd",
     "primprodUtil.py",
     "python",
     "Primary productivity model utilities and daylength calculations.",
     "workflows/mh1-primprod/src/primprodUtil.py"),

    ("code-pages/mh1-primprod/ppCompositeUtil.qmd",
     "ppCompositeUtil.py",
     "python",
     "Legacy productivity composite helper utilities retained with the workflow.",
     "workflows/mh1-primprod/src/ppCompositeUtil.py"),

         # =========================================================
    # NSIDC SEA ICE
    # =========================================================

    ("code-pages/nsidc/dockerfile.qmd",
     "Dockerfile",
     "dockerfile",
     "Container environment for the NSIDC sea ice workflow.",
     "workflows/nsidc/Dockerfile"),

    ("code-pages/nsidc/entrypoint.qmd",
     "entrypoint.sh",
     "bash",
     "Cloud Run entrypoint for daily and monthly NSIDC processing.",
     "workflows/nsidc/entrypoint.sh"),

    ("code-pages/nsidc/deploy_job.qmd",
     "deploy_job.sh",
     "bash",
     "Builds, deploys, and schedules the NSIDC Cloud Run jobs.",
     "workflows/nsidc/deploy_job.sh"),

    ("code-pages/nsidc/config.qmd",
     "config.yaml",
     "yaml",
     "Runtime configuration for NSIDC daily and monthly processing.",
     "workflows/nsidc/config/config.yaml"),

    ("code-pages/nsidc/requirements.qmd",
     "requirements.txt",
     "text",
     "Python dependencies for the NSIDC container.",
     "workflows/nsidc/config/requirements.txt"),

    ("code-pages/nsidc/control_nsidc.qmd",
     "control_nsidc.py",
     "python",
     "Controller for NSIDC daily and monthly Cloud Run jobs.",
     "workflows/nsidc/scripts/control_nsidc.py"),

    ("code-pages/nsidc/make_nsidc_daily_v6.qmd",
     "make_nsidc_daily_v6.py",
     "python",
     "Builds daily NSIDC G02202 v6 sea ice products.",
     "workflows/nsidc/scripts/make_nsidc_daily_v6.py"),

    ("code-pages/nsidc/make_nsidc_monthly_v6.qmd",
     "make_nsidc_monthly_v6.py",
     "python",
     "Builds monthly NSIDC G02202 v6 sea ice composites.",
     "workflows/nsidc/scripts/make_nsidc_monthly_v6.py"),

]

template = """---
title: "{title}"
toc: false
page-layout: full
number-sections: false
---

[← Back to workflow](../../{workflow}.html)

{description}

::: {{.code-shell}}

```{{.{language}}}
{{{{< include ../../{include_path} >}}}}
```

:::
"""

for out, title, language, description, include_path in pages:
    out_path = Path(out)

    # Create output directories automatically
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # workflow name from folder
    workflow = Path(out).parent.name

    out_path.write_text(
        template.format(
            title=title,
            language=language,
            description=description,
            include_path=include_path,
            workflow=workflow,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {out}")

print("\nDone.")