#!/usr/bin/env python3
"""
CSV IMGW SYNOP/terminowe -> MET ASCII

input:
  - raw CSV IMGW, np. s_t_09_2025.csv
  - stations.csv z kolumnami: station_id,name,river,lat,lon,elev

output:
  - miesięczne pliki imgw_synop_YYYYMM.ascii w 11-kolumnowym formacie
    MET point observation:
    Message_Type Station_ID Valid_Time Lat Lon Elevation Variable_Name Level Height QC_String Observation_Value
np. ADPSFC 349190600 20260101_110000 49.80667 19.00222 396.0 T2 NA 2 NA 274.150

mapa (IMGW -> MET [jednostki]):

TEMP -> T2 [°C -> K], height = 2 m
PPPS -> PSFC [hPa], height = 0 m
FWR  -> WSPD10 [m/s], height = 10 m
KRWR -> WDIR10 [degree], height = 10 m
WLGW -> RH2 [%], height = 2 m
TPTR -> TD2 [°C], height = 2 m
PPPM -> SLP [hPa], height = 0 m
WO6G -> APCP_6H [mm], level = 21600 s
"""

import argparse
import os
import re
import tempfile
from pathlib import Path

import pandas as pd

"""
IMGW_NAME: (MET_NAME, STATUS_NAME, ADDITIVE_OFFSET, LEVEL, HEIGHT)

MET ASCII:
- level: pressure level [hPa] albo accumulation interval [s]
- height: wysokość [m] nad gruntem / poziomem odniesienia

Dla zmiennych przyziemnych level="NA" i sensownego height:
T2/RH2/TD2 -> Z2
WSPD10/WDIR10 -> Z10
PSFC/SLP -> Z0

Dla APCP_6H level=21600, bo to akumulacja 6 h w sekundach
"""

VARIABLE_MAP = {
    "TEMP": ("T2", "WTEMP", 273.15, "NA", 2.0),
    "PPPS": ("PSFC", "WPPPS", 0.0, "NA", 0.0),
    "FWR": ("WSPD10", "WFWR", 0.0, "NA", 10.0),
    "KRWR": ("WDIR10", "WKRWR", 0.0, "NA", 10.0),
    "WLGW": ("RH2", "WWLGW", 0.0, "NA", 2.0),
    "TPTR": ("TD2", "WTPTR", 0.0, "NA", 2.0),
    "PPPM": ("SLP", "WPPPM", 0.0, "NA", 0.0),
    "WO6G": ("APCP_6H", "WWO6G", 0.0, 21600.0, "NA"),
}

IMGW_USECOLS = {
    "NSP": 0,
    "ROK": 2,
    "MC": 3,
    "DZ": 4,
    "GG": 5,
    "KRWR": 23,
    "WKRWR": 24,
    "FWR": 25,
    "WFWR": 26,
    "TEMP": 29,
    "WTEMP": 30,
    "WLGW": 37,
    "WWLGW": 38,
    "TPTR": 39,
    "WTPTR": 40,
    "PPPS": 41,
    "WPPPS": 42,
    "PPPM": 43,
    "WPPPM": 44,
    "WO6G": 48,
    "WWO6G": 49,
}

IMGW_FILENAME_RE = re.compile(r"s_t_(?P<month>0[1-9]|1[0-2])_(?P<year>[0-9]{4})\.csv")


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--csv",
        required=True,
        nargs="+",
        type=Path,
    )

    parser.add_argument(
        "--stations",
        required=True,
        type=Path,
    )

    parser.add_argument("--output-dir", required=True, type=Path)

    return parser.parse_args()


def output_path_for_csv(csv_path, output_dir):
    match = IMGW_FILENAME_RE.fullmatch(csv_path.name)
    if match is None:
        raise ValueError(
            f"Niepoprawna nazwa pliku IMGW: {csv_path.name!r}; "
            "oczekiwano s_t_MM_YYYY.csv"
        )

    month = match.group("month")
    year = match.group("year")
    return output_dir / f"imgw_synop_{year}{month}.ascii"


def read_stations(path):
    stations = pd.read_csv(
        path,
        usecols=["station_id", "lat", "lon", "elev"],
        dtype={"station_id": str},
    )

    return stations


def read_imgw_csv(path):
    column_names = {idx: name for name, idx in IMGW_USECOLS.items()}
    return pd.read_csv(
        path,
        header=None,
        usecols=sorted(column_names),
        dtype=str,
        encoding="cp1250",
    ).rename(columns=column_names)


def add_valid_time(df):
    """
    Zwracany czas jest naiwny (bez informacji o strefie czasowej),
    ponieważ IMGW podaje czas w UTC. Oczekiwany format:
    `RRRR-MM-DD GG:00:00`, np. `2026-01-01 00:00:00`.
    """
    time_text = (
        df["ROK"].str.zfill(4)
        + "-"
        + df["MC"].str.zfill(2)
        + "-"
        + df["DZ"].str.zfill(2)
        + " "
        + df["GG"].str.zfill(2)
        + ":00:00"
    )
    df["valid_time"] = pd.to_datetime(time_text)
    df.drop(columns=["ROK", "MC", "DZ", "GG"], inplace=True)
    return df


def attach_station_metadata(obs, stations):
    merged = obs.merge(
        stations,
        left_on="NSP",
        right_on="station_id",
        how="inner",
        validate="many_to_one",
    )
    merged.drop(columns=["station_id"], inplace=True)

    return merged


def prepare_common_met_fields(obs):
    obs["valid_time_met"] = obs["valid_time"].dt.strftime("%Y%m%d_%H%M%S")
    obs["lat_met"] = obs["lat"].astype(float).map("{:.5f}".format)
    obs["lon_met"] = obs["lon"].astype(float).map("{:.5f}".format)
    obs["elev_met"] = obs["elev"].astype(float).map("{:.1f}".format)
    obs.drop(columns=["valid_time", "lat", "lon", "elev"], inplace=True)
    return obs


def build_obs_records(obs):
    records = []

    for imgw_name, (
        out_name,
        status_name,
        offset,
        level,
        height,
    ) in VARIABLE_MAP.items():
        for _, row in obs.iterrows():
            value_raw = row[imgw_name]
            status = row[status_name]

            if pd.isna(value_raw):
                continue
            if str(status) == "8":
                continue

            value = float(value_raw) + offset

            records.append(
                {
                    "station_id": row["NSP"],
                    "valid_time": row["valid_time_met"],
                    "lat": row["lat_met"],
                    "lon": row["lon_met"],
                    "elev": row["elev_met"],
                    "var_name": out_name,
                    "level": level,
                    "height": height,
                    "value": value,
                }
            )

    return pd.DataFrame.from_records(records)


def format_level_or_height(value):
    if value == "NA":
        return "NA"

    value = float(value)

    if value.is_integer():
        return str(int(value))

    return f"{value:.3f}"


def format_met_ascii_line(row):
    level = format_level_or_height(row["level"])
    height = format_level_or_height(row["height"])

    return (
        f"ADPSFC "
        f"{row['station_id']} "
        f"{row['valid_time']} "
        f"{row['lat']} "
        f"{row['lon']} "
        f"{row['elev']} "
        f"{row['var_name']} "
        f"{level} "
        f"{height} "
        f"NA "
        f"{row['value']:.3f}"
    )


def write_met_ascii(records, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        for _, row in records.iterrows():
            line = format_met_ascii_line(row)
            f.write(line + "\n")


def write_met_ascii_atomic(records, output_path):
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)

    try:
        write_met_ascii(records, temporary_path)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main():
    args = parse_args()

    print(f"Stacje: {args.stations}")
    print(f"Pliki CSV: {args.csv}")
    print(f"Katalog wyjściowy: {args.output_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    pending = []
    skipped = 0

    for csv_path in args.csv:
        try:
            output_path = output_path_for_csv(csv_path, args.output_dir)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        if output_path.is_file():
            print(f"Pomijam istniejący wynik: {output_path}")
            skipped += 1
            continue

        if output_path.exists():
            raise SystemExit(f"Ścieżka wyjściowa nie jest plikiem: {output_path}")

        pending.append((csv_path, output_path))

    if not pending:
        print(f"Brak nowych danych (pominięto plików: {skipped})")
        return

    stations = read_stations(args.stations)
    created = 0

    for csv_path, output_path in pending:
        print(f"Przetwarzam: {csv_path} -> {output_path}")

        obs = read_imgw_csv(csv_path)
        obs = add_valid_time(obs)
        obs = attach_station_metadata(obs, stations)
        obs = prepare_common_met_fields(obs)
        records = build_obs_records(obs)

        write_met_ascii_atomic(records, output_path)
        created += 1
        print(f"Zapisano: {output_path} ({len(records)} rekordów)")

    print(f"Utworzono plików: {created}; pominięto plików: {skipped}")


if __name__ == "__main__":
    main()
