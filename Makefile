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
PIPELINE_DATE_TIME ?=
WRFOUT             ?=
WRFDIAG            ?=

IMGW_CSV        ?= input/imgw/raw/*.csv
STATIONS        ?= input/imgw/metadata/stations.csv
OBS_ASCII_DIR   ?= input/obs_ascii
OBS_NC          ?= input/obs_nc/imgw_synop.nc

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
	mkdir -p input/wrf input/wrfdiag \
	         input/imgw/raw input/imgw/metadata \
	         input/obs_ascii input/obs_nc \
	         output/point_stat output/metviewer \
	         config/sql logs tmp

# ============================================================
# Preprocessing
# ============================================================
.PHONY: wrfdiag obs-download obs-ascii obs-nc obs
wrfdiag: dirs 
	conda run -n $(CONDA_ENV) python scripts/wrfout_to_wrfdiag.py \
		--input "$(WRFOUT)" \
		--output "$(WRFDIAG)"

obs-download: dirs
	conda run --no-capture-output -n $(CONDA_ENV) \
		python scripts/download_imgw_raw.py

obs-ascii: obs-download
	conda run --no-capture-output -n $(CONDA_ENV) \
		python scripts/imgw_synop_to_met_ascii.py \
		--csv $(IMGW_CSV) \
		--stations "$(STATIONS)" \
		--output-dir "$(OBS_ASCII_DIR)"

obs-nc: dirs obs-ascii
	for ascii_file in "$(OBS_ASCII_DIR)"/imgw_synop_??????.ascii; do \
		[ -f "$$ascii_file" ] || continue;
		filename=$${ascii_file##*/}; \
		nc_file="$(OBS_NC_DIR)/$${filename%.ascii}.nc"; \
		if [ ! -f "$$nc_file" ]; then \
			echo "Tworzenie $$nc_file"; \
			$(RUNNER) ascii2nc \
				"/work/$$ascii_file" \
				"/work/$$nc_file"; \
		else \
			echo "$$nc_file istnieje, pomijam"; \
		fi; \
	done

obs: obs-nc

# ============================================================
# PointStat
# ============================================================
.PHONY: pointstat
pointstat: wrfdiag obs-nc
	mkdir -p $(POINTSTAT_OUT)
	$(RUNNER) /metplus/METplus/ush/run_metplus.py \
		-c /work/$(POINTSTAT_CONF) \
		config.INIT_BEG=$(PIPELINE_DATE_TIME) \
		config.INIT_END=$(PIPELINE_DATE_TIME)
	@echo "--- laczna liczba plikow .stat ---"
	@find "$(POINTSTAT_OUT)" -maxdepth 1 -type f -name '*.stat' | wc -l

# ============================================================
# Baza danych
# ============================================================
.PHONY: db-up db-reset db-load db-verify db-build
db-up:
	$(COMPOSE) up -d mariadb

db-reset: db-up
	$(MYSQL) -e "DROP DATABASE IF EXISTS $(DB_NAME); CREATE DATABASE $(DB_NAME);"
	$(MYSQL) $(DB_NAME) < $(DB_SCHEMA)
	@echo "Baza $(DB_NAME) zresetowana"

db-load: db-up
	@stat_file=$$(find "$(POINTSTAT_OUT)" -maxdepth 1 -type f -name '*.stat' \
		-print | sort | head -n 1); \
	valid_time=$$(awk 'NR == 2 { gsub("_", "", $$5); print substr($$5, 1, 10); exit }' \
		"$$stat_file"); \
	$(RUNNER) /metplus/METplus/ush/run_metplus.py \
		-c /work/$(DBLOAD_CONF) \
		config.VALID_BEG=$$valid_time \
		config.VALID_END=$$valid_time

db-verify: db-up
	$(MYSQL) $(DB_NAME) -e "\
	SELECT COUNT(*) AS cnt_rows FROM line_data_cnt; \
	SELECT COUNT(DISTINCT fcst_lead) AS leads FROM line_data_cnt; \
	SELECT sh.fcst_var, COUNT(*) AS n FROM stat_header sh \
	  JOIN line_data_cnt c ON c.stat_header_id=sh.stat_header_id \
	  GROUP BY sh.fcst_var; \
	SELECT DISTINCT model FROM stat_header;"

db-build: 
	$(MAKE) db-reset
	$(MAKE) db-load
	$(MAKE) db-verify

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
pipeline: pointstat
	$(MAKE) db-build

clean-output:
	rm -rf output/point_stat/*
