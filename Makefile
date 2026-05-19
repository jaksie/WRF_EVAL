SHELL := /bin/bash

PROJECT_DIR := $(HOME)/wrf_eval
MET_IMAGE := dtcenter/metplus:6.2.1
CONDA_ENV := wrfdiag
ENV_FILE := environment-wrfdiag.yml

DOCKER_RUN := docker run --rm -it \
	-v "$(PROJECT_DIR):/work" \
	-w /work \
	$(MET_IMAGE)


WRFOUT ?= input/wrf/wrfout_d01_2026-01-15_03:00:00
WRFDIAG ?= input/wrf_diag/wrfdiag_d01_2026-01-15_03.nc

IMGW_CSV ?= input/imgw/raw/*.csv
STATIONS ?= input/imgw/metadata/stations.csv
OBS_ASCII ?= input/obs_ascii/imgw_synop.ascii
OBS_NC ?= input/obs_nc/imgw_synop.nc

METPLUS_INSTANT_CONF := config/metplus/PointStat_surface_instant_wrfdiag.conf
METPLUS_APCP_CONF := config/metplus/PointStat_apcp6h_wrfdiag.conf

OUT_INSTANT := output/point_stat/metplus_surface_instant
OUT_APCP := output/point_stat/metplus_apcp6h


.PHONY: pull-metplus
pull-metplus:
	docker pull $(MET_IMAGE)


.PHONY: env-create
env-create:
	conda env create -f $(ENV_FILE)


.PHONY: env-update
env-update:
	conda env update -n $(CONDA_ENV) -f $(ENV_FILE) --prune


.PHONY: dirs
dirs:
	mkdir -p input/wrf
	mkdir -p input/wrf_diag
	mkdir -p input/imgw/raw
	mkdir -p input/imgw/metadata
	mkdir -p input/obs_ascii
	mkdir -p input/obs_nc
	mkdir -p output/point_stat
	mkdir -p logs
	mkdir -p tmp


.PHONY: wrfdiag
wrfdiag: dirs
	conda run -n $(CONDA_ENV) python scripts/wrfout_to_wrfdiag.py \
		--input $(WRFOUT) \
		--output $(WRFDIAG)


.PHONY: obs-ascii
obs-ascii: dirs
	conda run -n $(CONDA_ENV) python scripts/imgw_synop_to_met_ascii.py \
		--csv $(IMGW_CSV) \
		--stations $(STATIONS) \
		--output $(OBS_ASCII)


.PHONY: obs-nc
obs-nc: dirs
	rm -f $(OBS_NC)
	$(DOCKER_RUN) ascii2nc \
		/work/$(OBS_ASCII) \
		/work/$(OBS_NC)


.PHONY: obs
obs: obs-ascii obs-nc


.PHONY: pointstat-instant
pointstat-instant:
	rm -rf $(OUT_INSTANT)
	mkdir -p $(OUT_INSTANT)
	$(DOCKER_RUN) /metplus/METplus/ush/run_metplus.py \
		/work/$(METPLUS_INSTANT_CONF)


# .PHONY: pointstat-apcp
# pointstat-apcp:
# 	rm -rf $(OUT_APCP)
# 	mkdir -p $(OUT_APCP)
# 	$(DOCKER_RUN) /metplus/METplus/ush/run_metplus.py \
# 		/work/$(METPLUS_APCP_CONF)


.PHONY: clean-output
clean-output:
	rm -rf output/point_stat/*