#!/usr/bin/env python3
"""
Konwersja natywnych pól `wrfout` do postaci diagnostycznej.

intput:
    wrfout_d01_YYYY-MM-DD_HH:MM:SS
output:
wrfdiag_d01_YYYY-MM-DD_HH.nc

Wyjściowe pola:
- analiza powierzchniowa:
    T2,
    PSFC_HPA (Pa do hP),
    WSP10 ({U10, V10}), WDIR10 ({U10, V10}),
    RH2 ({T2, Q2, PSFC}),
    TD2 ({Q2, PSFC}),
    APCP_6H ({RAINC, RAINNC, ???}),
    SLP ({P, PB, T, QVAPOR, PH, PHB}),
    XLAT, XLONG [stopień dziesiętny] ((i, j) -> (lat, lon))

    - cała siatka, bo dla jednego poziomu (Time, south_north, west_east)

- analiza profilowa:
    todo
"""

from pathlib import Path
import argparse

import xarray as xr
from netCDF4 import Dataset

import numpy as np

from wrf import getvar, to_np

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    return parser.parse_args()

def decode_wrf_times(raw_times):
    """
    WRF Times(Time, DateStrLen) [ASCII] -> datetime64
    """

    out = []

    for row in raw_times.values:
        timestamp = bytes(row.tolist()).decode("ascii")
        timestamp = timestamp.strip().replace("_", "T")
        out.append(timestamp)

    return np.array(out, dtype="datetime64[s]")

def make_2d_field(values, valid_time, template, name):
    """
    2D numpy array -> 3D xarray DataArray:
    Time, south_north, west_east
    """
    return xr.DataArray(
        values.astype("float32")[None, :, :],
        dims=("Time", "south_north", "west_east"),
        coords={
            "Time": np.array([valid_time], dtype="datetime64[s]"),
            "south_north": template.coords["south_north"],
            "west_east": template.coords["west_east"],
        },
        name=name,
    )

def main():
    args = parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Input: {args.input}")
    print(f"Output: {args.output}")

    raw = xr.open_dataset(args.input, decode_times=False) 
    nc = Dataset(args.input) 

    try: 
        times = decode_wrf_times(raw["Times"])
        template = raw["T2"].isel(Time=0)

        parts = []

        for i, valid_time in enumerate(times):
            # print(f"Processing time {i + 1}/{len(times)}: {valid_time}")
            t2 = raw["T2"].isel(Time=i).values.astype("float32")
            psfc = raw["PSFC"].isel(Time=i).values.astype("float32")
            u10 = raw["U10"].isel(Time=i).values.astype("float32")
            v10 = raw["V10"].isel(Time=i).values.astype("float32")

            rain = (
                raw["RAINC"].isel(Time=i).values.astype("float32")
                + raw["RAINNC"].isel(Time=i).values.astype("float32")
            )

            psfc_hpa = psfc / 100.0

            wspd10 = np.hypot(u10, v10)
            wdir10 = (270 - np.degrees(np.arctan2(v10, u10))) % 360

            if i >= 6:
                rain_prev = (
                    raw["RAINC"].isel(Time=i).values.astype("float32")
                    + raw["RAINNC"].isel(Time=i).values.astype("float32")
            )
                acpc_6h = rain - rain_prev
            else:
                acpc_6h = np.full_like(rain, np.nan, dtype="float32")

            rh2 = to_np(
                getvar(nc, "rh2", timeidx=i)
            ).astype("float32")

            td2 = to_np(
                getvar(nc, "td2", timeidx=i, units="degC")
            ).astype("float32")

            slp = to_np(
                getvar(nc, "slp", timeidx=i, units="hPa")
            ).astype("float32")

            ds_i = xr.Dataset(
                {
                    "T2": make_2d_field(t2, valid_time, template, "T2"),
                    "PSFC_HPA": make_2d_field(psfc_hpa, valid_time, template, "PSFC_HPA"),
                    "WSPD10": make_2d_field(wspd10, valid_time, template, "WSPD10"),
                    "WDIR10": make_2d_field(wdir10, valid_time, template, "WDIR10"),
                    "RH2": make_2d_field(rh2, valid_time, template, "RH2"),
                    "TD2": make_2d_field(td2, valid_time, template, "TD2"),
                    "SLP": make_2d_field(slp, valid_time, template, "SLP"),
                    "APCP_6H": make_2d_field(acpc_6h, valid_time, template, "APCP_6H"),
                }
            )

            parts.append(ds_i)
            print(parts[-1])

        out = xr.concat(parts, dim="Time")
        out["XLAT"] = xr.DataArray(
            raw["XLAT"].isel(Time=0).values.astype("float32"),
            dims=("south_north", "west_east"),
            coords={
                "south_north": template.coords["south_north"],
                "west_east": template.coords["west_east"],
            },
        )
        out["XLONG"] = xr.DataArray(
            raw["XLONG"].isel(Time=0).values.astype("float32"),
            dims=("south_north", "west_east"),
            coords={
                "south_north": template.coords["south_north"],
                "west_east": template.coords["west_east"],
            },
        )

        out["T2"].attrs.update(
            units="K",
            description="2 m temperature",
        )

        out["PSFC_HPA"].attrs.update(
            units="hPa",
            description="surface pressure",
        )

        out["WSPD10"].attrs.update(
            units="m s-1",
            description="10 m wind speed",
        )

        out["WDIR10"].attrs.update(
            units="degree",
            description="10 m wind direction",
        )

        out["RH2"].attrs.update(
            units="%",
            description="2 m relative humidity",
        )

        out["TD2"].attrs.update(
            units="degC",
            description="2 m dew point",
        )

        out["SLP"].attrs.update(
            units="hPa",
            description="sea-level pressure",
        )

        out["APCP_6H"].attrs.update(
            units="mm",
            description="6 h precipitation from RAINC + RAINNC + ...",
        )

        out["XLAT"].attrs.update(
            units="degree_north",
            description="latitude",
        )

        out["XLONG"].attrs.update(
            units="degree_east",
            description="longitude",
        )

        print(out)

        out.to_netcdf(args.output)
        print(f"Zapisano w {args.output}")
        

            # print(
            #     "   ra:",
            #     rain.shape,
            #     "min=", np.nanmin(rain),
            #     "max=", np.nanmax(rain),
            # )


    finally:
        nc.close()
        raw.close()

    # print(f"Liczba czasów: {len(times)}")
    # print(f"Pierwszy: {times[0]}")
    # print(f"Ostatni:  {times[-1]}")

if __name__ == "__main__":
    main()