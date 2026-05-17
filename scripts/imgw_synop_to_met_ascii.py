#!/usr/bin/env python3
"""
CSV IMGW SYNOP/terminowe -> MET ASCII 

input:
  - raw CSV IMGW, np. s_t_09_2025.csv
  - stations.csv z kolumnami: station_id,name,river,lat,lon,elev

output:
  - plik ASCII w 11-kolumnowym formacie MET point observation:
    Message_Type Station_ID Valid_Time Lat Lon Elevation Variable_Name Level Height QC_String Observation_Value

mapa (IMGW -> MET [jednostki]):

TEMP -> T2 [°C -> K], height = 2 m
PPPS -> PSFC_HPA [hPa], height = 0 m
FWR  -> WSPD10 [m/s], height = 10 m
KRWR -> WDIR10 [degree], height = 10 m
WLGW -> RH2 [%], height = 2 m
TPTR -> TD2 [°C], height = 2 m
PPPM -> SLP [hPa], height = 0 m
WO6G -> APCP_6H [mm], level = 21600 s
"""

from pathlib import Path
import argparse

import pandas as pd

"""
IMGW_NAME: (MET_NAME, STATUS_NAME, ADDITIVE_OFFSET, LEVEL, HEIGHT)

MET ASCII:
- level: pressure level [hPa] albo accumulation interval [s]
- height: wysokość [m] nad gruntem / poziomem odniesienia

Dla zmiennych przyziemnych level="NA" i sensownego height:
T2/RH2/TD2 -> Z2
WSPD10/WDIR10 -> Z10
PSFC_HPA/SLP -> Z0

Dla APCP_6H level=21600, bo to akumulacja 6 h w sekundach
"""

VARIABLE_MAP = {
    "TEMP": ("T2", "WTEMP", 273.15, "NA", 2.0),
    "PPPS": ("PSFC_HPA", "WPPPS", 0.0, "NA", 0.0),
    "FWR":  ("WSPD10", "WFWR", 0.0, "NA", 10.0),
    "KRWR": ("WDIR10", "WKRWR", 0.0, "NA", 10.0),
    "WLGW": ("RH2", "WWLGW", 0.0, "NA", 2.0),
    "TPTR": ("TD2", "WTPTR", 0.0, "NA", 2.0),
    "PPPM": ("SLP", "WPPPM", 0.0, "NA", 0.0),
    "WO6G": ("APCP_6H", "WWO6G", 0.0, 21600.0, "NA"),
}

IMGW_USECOLS = {
    "NSP": 0,
    "POST": 1,
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

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def read_stations(path):
    stations = pd.read_csv(path)
    return stations


def read_imgw_csv(path):
    raw = pd.read_csv(
        path,
        header=None,
        dtype=str,
        encoding="cp1250"
    )

    df = pd.DataFrame()

    for name, idx in IMGW_USECOLS.items():
        df[name] = raw.iloc[:, idx]

    return df


def add_valid_time(df):
    df = df.copy()

    time_text = (
        df["ROK"].str.zfill(4) + "-"
        + df["MC"].str.zfill(2) + "-"
        + df["DZ"].str.zfill(2) + " "
        + df["GG"].str.zfill(2) + ":00:00"
    )

    local_time = pd.to_datetime(time_text)

    local_time = local_time.dt.tz_localize(
        "Europe/Warsaw",
        nonexistent="shift_forward",
        ambiguous="infer",
    )

    utc_time = local_time.dt.tz_convert("UTC")

    df["valid_time"] = utc_time

    return df


def attach_station_metadata(obs, stations):
    obs = obs.copy()

    obs["NSP"] = obs["NSP"].astype(str)
    stations = stations.copy()
    stations["station_id"] = stations["station_id"].astype(str)

    merged = obs.merge(
        stations,
        left_on="NSP",
        right_on="station_id",
        how="inner"
    )

    return merged


def build_obs_records(obs):
    records = []

    for imgw_name, (out_name, status_name, offset, level, height) in VARIABLE_MAP.items():
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
                    "station_name": row["POST"],
                    "valid_time": row["valid_time"],
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "elev": float(row["elev"]),
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
    valid_time = row["valid_time"].strftime("%Y%m%d_%H%M%S")

    level = format_level_or_height(row["level"])
    height = format_level_or_height(row["height"])

    return (
        f"ADPSFC "
        f"{row['station_id']} "
        f"{valid_time} "
        f"{row['lat']:.5f} "
        f"{row['lon']:.5f} "
        f"{row['elev']:.1f} "
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


def main():
    args = parse_args()
    
    print(f"Stacje: {args.stations}")
    print(f"Pliki CSV: {args.csv}")
    print(f"Wyjście: {args.output}")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    stations = read_stations(args.stations)

    frames = []

    for path in args.csv:
        df = read_imgw_csv(path)
        frames.append(df)

    obs = pd.concat(frames, ignore_index=True)
    obs = add_valid_time(obs)
    obs = attach_station_metadata(obs, stations)

    records = build_obs_records(obs)

    write_met_ascii(records, args.output)


if __name__ == "__main__":
    main()