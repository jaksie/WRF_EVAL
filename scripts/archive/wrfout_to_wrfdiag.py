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


WRF_GLOBAL_ATTRS_TO_COPY = [
    "TITLE",
    "START_DATE",
    "SIMULATION_START_DATE",
    "WEST-EAST_GRID_DIMENSION",
    "SOUTH-NORTH_GRID_DIMENSION",
    "BOTTOM-TOP_GRID_DIMENSION",
    "DX",
    "DY",
    "GRIDTYPE",
    "GRID_ID",
    "PARENT_ID",
    "I_PARENT_START",
    "J_PARENT_START",
    "PARENT_GRID_RATIO",
    "CEN_LAT",
    "CEN_LON",
    "TRUELAT1",
    "TRUELAT2",
    "MOAD_CEN_LAT",
    "STAND_LON",
    "POLE_LAT",
    "POLE_LON",
    "MAP_PROJ",
    "MAP_PROJ_CHAR",
    "MMINLU",
    "NUM_LAND_CAT",
    "ISWATER",
    "ISLAKE",
    "ISICE",
    "ISURBAN",
    "ISOILWATER",
]


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


def copy_wrf_global_attrs(src, dst):

    copied = []

    for attr in WRF_GLOBAL_ATTRS_TO_COPY:
        dst.attrs[attr] = src.attrs[attr]
        copied.append(attr)

    dst.attrs["source_file"] = src.encoding["source"]

    for attr in copied:
        print(f"  {attr}")

    return dst


def set_wrf_like_var_attrs(ds):

    field_attrs = {
        "T2": {
            "units": "K",
            "description": "2 m temperature",
            "MemoryOrder": "XY ",
        },
        "PSFC_HPA": {
            "units": "hPa",
            "description": "surface pressure",
            "MemoryOrder": "XY ",
        },
        "WSPD10": {
            "units": "m s-1",
            "description": "10 m wind speed",
            "MemoryOrder": "XY ",
        },
        "WDIR10": {
            "units": "degrees",
            "description": "10 m wind direction",
            "MemoryOrder": "XY ",
        },
        "RH2": {
            "units": "%",
            "description": "2 m relative humidity",
            "MemoryOrder": "XY ",
        },
        "TD2": {
            "units": "degC",
            "description": "2 m dew point temperature",
            "MemoryOrder": "XY ",
        },
        "SLP": {
            "units": "hPa",
            "description": "sea level pressure",
            "MemoryOrder": "XY ",
        },
        "APCP_6H": {
            "units": "mm",
            "description": "6 h precipitation from RAINC + RAINNC",
            "MemoryOrder": "XY ",
        },
    }

    for name, attrs in field_attrs.items():
        ds[name].attrs.update(attrs)
        ds[name].attrs["FieldType"] = 104
        ds[name].attrs["stagger"] = ""
        ds[name].attrs["coordinates"] = "XLONG XLAT"

    ds["XLAT"].attrs.update(
        {
            "FieldType": 104,
            "MemoryOrder": "XY ",
            "description": "LATITUDE, SOUTH IS NEGATIVE",
            "units": "degree_north",
            "standard_name": "latitude",
            "stagger": "",
        }
    )

    ds["XLONG"].attrs.update(
        {
            "FieldType": 104,
            "MemoryOrder": "XY ",
            "description": "LONGITUDE, WEST IS NEGATIVE",
            "units": "degree_east",
            "standard_name": "longitude",
            "stagger": "",
        }
    )

    return ds

def add_cf_lambert_grid_mapping(ds):
    grid_mapping_name = "lambert_conformal_conic"

    ds[grid_mapping_name] = xr.DataArray(
        np.int32(0),
        attrs={
            "grid_mapping_name": "lambert_conformal_conic",
            "standard_parallel": np.array(
                [ds.attrs["TRUELAT1"], ds.attrs["TRUELAT2"]],
                dtype="float32",
            ),
            "longitude_of_central_meridian": np.float32(ds.attrs["STAND_LON"]),
            "latitude_of_projection_origin": np.float32(ds.attrs["MOAD_CEN_LAT"]),
            "earth_radius": np.float32(6370000.0),
        },
    )

    for name in ["T2", "PSFC_HPA", "WSPD10", "WDIR10", "RH2", "TD2", "SLP", "APCP_6H"]:
        ds[name].attrs["grid_mapping"] = grid_mapping_name

    print(f"Dodano CF grid_mapping: {grid_mapping_name}")

    return ds

def set_cf_projection_coordinates(ds):
    """
    west_east   -> projection_x_coordinate
    south_north -> projection_y_coordinate

    CEN_LAT/CEN_LON -- center grid point
    """

    nx = ds.sizes["west_east"]
    ny = ds.sizes["south_north"]

    dx = np.float32(ds.attrs["DX"])
    dy = np.float32(ds.attrs["DY"])

    x0 = np.float32((nx - 1) / 2.0)
    y0 = np.float32((ny - 1) / 2.0)

    x = (np.arange(nx, dtype="float32") - x0) * dx
    y = (np.arange(ny, dtype="float32") - y0) * dy

    ds = ds.assign_coords(
        west_east=("west_east", x),
        south_north=("south_north", y),
    )

    ds["west_east"].attrs.update(
        {
            "standard_name": "projection_x_coordinate",
            "long_name": "x coordinate of projection",
            "units": "m",
            "axis": "X",
        }
    )

    ds["south_north"].attrs.update(
        {
            "standard_name": "projection_y_coordinate",
            "long_name": "y coordinate of projection",
            "units": "m",
            "axis": "Y",
        }
    )

    return ds

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
                    raw["RAINC"].isel(Time=i - 6).values.astype("float32")
                    + raw["RAINNC"].isel(Time=i - 6).values.astype("float32")
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

        out = copy_wrf_global_attrs(raw, out)
        out = set_cf_projection_coordinates(out)
        out = set_wrf_like_var_attrs(out)
        out = add_cf_lambert_grid_mapping(out)

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