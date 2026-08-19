SHELL := /bin/bash

# ============================================================
# Konfiguracja
# ============================================================
# PROJECT_DIR := $(HOME)/wrf_eval
COMPOSE_DIR := docker/mariadb
COMPOSE     := docker compose -f $(COMPOSE_DIR)/docker-compose.yml

MET_IMAGE   := local/metplus-metplotpy:6.2.1
CONDA_ENV   := wrfdiag
ENV_FILE    := environment-wrfdiag.yml

DB_CONTAINER := met_mariadb
DB_NAME      ?= mv_wrf_surface
DB_USER      ?= metuser
DB_PASS      ?= 123
DB_SCHEMA    := config/sql/mv_mysql.sql

# Runner w sieci compose (dostep do mariadb); -T = bez TTY (serwer/CI)
RUNNER := $(COMPOSE) run --rm -T metplus-runner
MYSQL  := docker exec -i $(DB_CONTAINER) mariadb -u$(DB_USER) -p$(DB_PASS)

# ============================================================
# Dane wejsciowe
# ============================================================
WRFOUT ?= /home/WRF-operational-archive/2026/06/20260613/Results/wrfout_d01_2026-06-28_03:00:00
WRFDIAG ?= input/wrf_diag/wrfdiag_d01_2026-06-28_03.nc

IMGW_CSV  ?= input/imgw/raw/*.csv
STATIONS  ?= input/imgw/metadata/stations.csv
OBS_ASCII ?= input/obs_ascii/imgw_synop.ascii
OBS_NC    ?= input/obs_nc/imgw_synop.nc

# ============================================================
# Konfiguracje METplus
# ============================================================
POINTSTAT_CONF ?= config/metplus/PointStat_surface_wrfdiag.conf
DBLOAD_CONF    ?= config/metplus/metdbload/load_pointstat_surface.conf

POINTSTAT_OUT  ?= output/point_stat/metplus_surface

# ============================================================
# Przygotowanie srodowiska
# ============================================================
.PHONY: env-create env-update dirs
env-create:
	conda env create -f $(ENV_FILE)

env-update:
	conda env update -n $(CONDA_ENV) -f $(ENV_FILE) --prune

dirs:
	mkdir -p input/wrf input/wrf_diag \
	         input/imgw/raw input/imgw/metadata \
	         input/obs_ascii input/obs_nc \
	         output/point_stat output/metviewer \
	         config/sql logs tmp

# ============================================================
# Preprocessing
# ============================================================
.PHONY: wrfdiag obs-ascii obs-nc obs check-inputs
wrfdiag: dirs
	conda run -n $(CONDA_ENV) python scripts/wrfout_to_wrfdiag.py \
		--input $(WRFOUT) \
		--output $(WRFDIAG)

obs-ascii: dirs
	conda run -n $(CONDA_ENV) python scripts/imgw_synop_to_met_ascii.py \
		--csv $(IMGW_CSV) \
		--stations $(STATIONS) \
		--output $(OBS_ASCII)

obs-nc: dirs
	rm -f $(OBS_NC)
	$(RUNNER) ascii2nc /work/$(OBS_ASCII) /work/$(OBS_NC)

obs: obs-ascii obs-nc

# ============================================================
# PointStat
# ============================================================
.PHONY: pointstat
pointstat:
	rm -rf $(POINTSTAT_OUT)
	mkdir -p $(POINTSTAT_OUT)
	$(RUNNER) /metplus/METplus/ush/run_metplus.py -c /work/$(POINTSTAT_CONF)
	@echo "--- liczba plikow .stat ---"
	@ls $(POINTSTAT_OUT)/*.stat | wc -l

# ============================================================
# Baza danych
# ============================================================
.PHONY: db-up db-reset db-load db-verify
db-up:
	$(COMPOSE) up -d mariadb

db-reset: db-up
	$(MYSQL) -e "DROP DATABASE IF EXISTS $(DB_NAME); CREATE DATABASE $(DB_NAME);"
	$(MYSQL) $(DB_NAME) < $(DB_SCHEMA)
	@echo "Baza $(DB_NAME) zresetowana"

db-load:
	$(RUNNER) /metplus/METplus/ush/run_metplus.py -c /work/$(DBLOAD_CONF)

db-verify:
	$(MYSQL) $(DB_NAME) -e "\
	SELECT COUNT(*) AS cnt_rows FROM line_data_cnt; \
	SELECT COUNT(DISTINCT fcst_lead) AS leads FROM line_data_cnt; \
	SELECT sh.fcst_var, COUNT(*) AS n FROM stat_header sh \
	  JOIN line_data_cnt c ON c.stat_header_id=sh.stat_header_id \
	  GROUP BY sh.fcst_var; \
	SELECT DISTINCT model FROM stat_header;"

# ============================================================
# METviewer
# ============================================================
.PHONY: metviewer-up metviewer-down metviewer-logs
metviewer-up: db-up
	$(COMPOSE) up -d metviewer
	@echo "UI: http://localhost:8080/metviewer/metviewer1.jsp"

metviewer-down:
	$(COMPOSE) stop metviewer

# ============================================================
# Sekwencje
# ============================================================
.PHONY: pipeline clean-output
pipeline: wrfdiag obs pointstat db-reset db-load db-verify

clean-output:
	rm -rf output/point_stat/*