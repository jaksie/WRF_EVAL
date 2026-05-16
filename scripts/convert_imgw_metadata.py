#!/usr/bin/env python3
import csv
from pathlib import Path

RAW = Path.home() / "wrf_eval/input/imgw/metadata/stations_raw.csv"
OUT = Path.home() / "wrf_eval/input/imgw/metadata/stations.csv"


def dms_to_decimal(value: str) -> float:
    parts = value.strip().replace(",", ".").split()
    if len(parts) != 3:
        raise ValueError(f"Niepoprawny format DMS: {value!r}")

    deg, minute, sec = map(float, parts)
    sign = -1 if deg < 0 else 1
    deg = abs(deg)
    return sign * (deg + minute / 60.0 + sec / 3600.0)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with RAW.open("r", encoding="utf-8-sig", newline="") as fin, \
         OUT.open("w", encoding="utf-8", newline="") as fout:

        reader = csv.DictReader(fin, delimiter=";")
        writer = csv.DictWriter(
            fout,
            fieldnames=["station_id", "name", "river", "lat", "lon", "elev"]
        )
        writer.writeheader()

        n_total = 0
        n_written = 0
        n_skipped = 0

        for row in reader:
            n_total += 1

            station_id = row["ID"].strip()
            name = row["Nazwa"].strip()
            river = row["Rzeka"].strip()
            lat_raw = row["Szerokość geograficzna"].strip()
            lon_raw = row["Długość geograficzna"].strip()
            elev_raw = row["Wysokość n.p.m."].strip().replace(",", ".")

            if not station_id or not lat_raw or not lon_raw:
                n_skipped += 1
                continue

            lat = dms_to_decimal(lat_raw)
            lon = dms_to_decimal(lon_raw)

            try:
                elev = float(elev_raw) if elev_raw else -9999.0
            except ValueError:
                elev = -9999.0

            writer.writerow({
                "station_id": station_id,
                "name": name,
                "river": river,
                "lat": f"{lat:.6f}",
                "lon": f"{lon:.6f}",
                "elev": f"{elev:.1f}",
            })

            n_written += 1

    print(f"Wczytano rekordów:       {n_total}")
    print(f"Zapisano stacji:         {n_written}")
    print(f"Pominięto rekordów:      {n_skipped}")
    print(f"Plik wynikowy:           {OUT}")


if __name__ == "__main__":
    main()