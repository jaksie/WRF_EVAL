#!/usr/bin/env python3
"""
Konwersja natywnych pol `wrfout` do postaci diagnostycznej.

input:
    wrfout_d01_YYYY-MM-DD_HH:MM:SS
output:
    wrfdiag_d01_YYYY-MM-DD_HH.nc

Pola wyjsciowe (Time, south_north, west_east):
    T2       [K]      2 m temperature (natywne)
    PSFC     [hPa]    surface pressure (PSFC / 100)
    WSPD10   [m s-1]  10 m wind speed (uvmet10, earth-relative)
    WDIR10   [deg]    10 m wind direction (uvmet10, earth-relative)
    RH2      [%]      2 m relative humidity (wrf-python: T2, Q2, PSFC)
    TD2      [degC]   2 m dew point (wrf-python: Q2, PSFC)
    SLP      [hPa]    sea level pressure (wrf-python: P, PB, T, QVAPOR, PH, PHB)
    APCP_6H  [mm]     opad 6 h: (RAINC+RAINNC)(t) - (RAINC+RAINNC)(t-6h),
                      NaN gdy brak kroku t-6h w pliku

Metadane:
    - osie projekcji x/y [m] + CF grid_mapping (Lambert)
    - XLAT/XLONG jako aux coordinates
    - forecast_reference_time z SIMULATION_START_DATE
"""

from pathlib import Path
import argparse

import numpy as np
import xarray as xr
from netCDF4 import Dataset
from pyproj import CRS, Transformer
from wrf import getvar, to_np


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def decode_wrf_times(raw_times):
    """WRF Times(Time, DateStrLen) [ASCII] -> datetime64."""
    out = []
    for row in raw_times.values:
        timestamp = bytes(row.tolist()).decode("ascii")
        timestamp = timestamp.strip().replace("_", "T")
        out.append(timestamp)
    return np.array(out, dtype="datetime64[s]")


def make_2d_field(values, valid_time, name):
    """2D numpy array -> DataArray (Time, south_north, west_east)."""
    return xr.DataArray(
        values.astype("float32")[None, :, :],
        dims=("Time", "south_north", "west_east"),
        coords={"Time": np.array([valid_time], dtype="datetime64[s]")},
        name=name,
    )


WRF_GLOBAL_ATTRS_TO_COPY = [
    # identyfikacja biegu symulacji
    "TITLE",
    "START_DATE",
    "SIMULATION_START_DATE", # add_forecast_reference_time

    # wymiary siatki
    "WEST-EAST_GRID_DIMENSION",
    "SOUTH-NORTH_GRID_DIMENSION",
    "BOTTOM-TOP_GRID_DIMENSION",
    "DX", # set_cf_projection_coordinates
    "DY", # set_cf_projection_coordinates
    "GRIDTYPE",

    # zagnieżdźenie domen
    "GRID_ID",
    "PARENT_ID",
    "I_PARENT_START",
    "J_PARENT_START",
    "PARENT_GRID_RATIO",

    # projekcja
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

    # powierzchnia
    "MMINLU",
    "NUM_LAND_CAT",
    "ISWATER",
    "ISLAKE",
    "ISICE",
    "ISURBAN",
    "ISOILWATER",
]

def copy_wrf_global_attrs(src, dst):
    for attr in WRF_GLOBAL_ATTRS_TO_COPY:
        dst.attrs[attr] = src.attrs[attr]
    dst.attrs["source_file"] = src.encoding["source"]
    return dst


def add_forecast_reference_time(out, raw):
    start = raw.attrs["SIMULATION_START_DATE"]  # "YYYY-MM-DD_HH:MM:SS"
    ref = np.datetime64(start.replace("_", "T"), "s")
    out["forecast_reference_time"] = xr.DataArray(
        ref,
        attrs={"standard_name": "forecast_reference_time"},
    )
    return out

"""
Rodzina funckji projekcji wyraźnie bardziej skomplikowana niż oryginalna, bo bez założenia:
srodek siatki = poczatek projekcji
(sprawdzone dla tej domeny przy pomocy check_grid.py: max blad ~2e-5 stopnia)

Przy pracy z jednym modelem można uproscić do:
def set_cf_projection_coordinates(ds):
    # zalozenie: srodek siatki = poczatek projekcji (sprawdzone dla tej domeny,
    # check_grid.py: max blad ~2e-5 stopnia)
    assert abs(ds.attrs["CEN_LAT"] - ds.attrs["MOAD_CEN_LAT"]) < 1e-3
    assert abs(ds.attrs["CEN_LON"] - ds.attrs["STAND_LON"]) < 1e-3

    nx, ny = ds.sizes["west_east"], ds.sizes["south_north"]
    dx, dy = float(ds.attrs["DX"]), float(ds.attrs["DY"])
    x = (np.arange(nx) - (nx - 1) / 2.0) * dx
    y = (np.arange(ny) - (ny - 1) / 2.0) * dy
    ...
"""

def lambert_cf_params(ds):
    """
    MOAD_CEN_LAT, nie CEN_LAT:
    projekcja WRF jest definiowana przez domenę macierzysta (MOAD).
    Dla nestóww CEN_LAT to środek nestu, a nie punkt odniesienia projekcji —
    użycie go przesuneloby układ.
    Dla d01 obie wartosci sa zwykle równe; ew. błąd ujawnia się
    dopiero przy domenach zagniezdzonych
    """
    return {
        "grid_mapping_name": GRID_MAPPING_NAME,
        "standard_parallel": [
            float(ds.attrs["TRUELAT1"]),
            float(ds.attrs["TRUELAT2"]),
        ],
        "longitude_of_central_meridian": float(ds.attrs["STAND_LON"]),
        "latitude_of_projection_origin": float(ds.attrs["MOAD_CEN_LAT"]),
        "earth_radius": 6370000.0,
    }


def set_cf_projection_coordinates(ds):
    crs = CRS.from_cf(lambert_cf_params(ds))
    t = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
    xc, yc = t.transform(ds.attrs["CEN_LON"], ds.attrs["CEN_LAT"])

    nx, ny = ds.sizes["west_east"], ds.sizes["south_north"]
    dx, dy = float(ds.attrs["DX"]), float(ds.attrs["DY"])

    x = xc + (np.arange(nx) - (nx - 1) / 2.0) * dx
    y = yc + (np.arange(ny) - (ny - 1) / 2.0) * dy

    ds = ds.assign_coords(
        west_east=("west_east", x.astype("float64")),
        south_north=("south_north", y.astype("float64")),
    )
    ds["west_east"].attrs.update(
        standard_name="projection_x_coordinate",
        long_name="x coordinate of projection",
        units="m",
        axis="X",
    )
    ds["south_north"].attrs.update(
        standard_name="projection_y_coordinate",
        long_name="y coordinate of projection",
        units="m",
        axis="Y",
    )
    return ds


DIAG_FIELDS = ["T2", "PSFC", "WSPD10", "WDIR10", "RH2", "TD2", "SLP", "APCP_6H"]

GRID_MAPPING_NAME = "lambert_conformal_conic"

def add_cf_lambert_grid_mapping(ds):
    params = lambert_cf_params(ds)
    ds[GRID_MAPPING_NAME] = xr.DataArray(
        np.int32(0),
        attrs={
            "grid_mapping_name": params["grid_mapping_name"],
            "standard_parallel": np.array(
                params["standard_parallel"], dtype="float64"
            ),
            "longitude_of_central_meridian": np.float64(
                params["longitude_of_central_meridian"]
            ),
            "latitude_of_projection_origin": np.float64(
                params["latitude_of_projection_origin"]
            ),
            "earth_radius": np.float64(params["earth_radius"]),
        },
    )
    for name in DIAG_FIELDS:
        ds[name].attrs["grid_mapping"] = GRID_MAPPING_NAME
    return ds


def set_wrflike_var_attrs(ds):
    field_attrs = {
        "T2": {"units": "K", "description": "2 m temperature"},
        "PSFC": {"units": "hPa", "description": "surface pressure"},
        "WSPD10": {"units": "m s-1", "description": "10 m wind speed"},
        "WDIR10": {"units": "degrees", "description": "10 m wind direction"},
        "RH2": {"units": "%", "description": "2 m relative humidity"},
        "TD2": {"units": "degC", "description": "2 m dew point temperature"},
        "SLP": {"units": "hPa", "description": "sea level pressure"},
        "APCP_6H": {"units": "mm", "description": "6 h precipitation from RAINC + RAINNC"},
    }

    for name, attrs in field_attrs.items():
        ds[name].attrs.update(attrs)
        ds[name].attrs["FieldType"] = 104
        ds[name].attrs["MemoryOrder"] = "XY "
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


def main():
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")

    raw = xr.open_dataset(args.input, decode_times=False)
    nc = Dataset(args.input)

    try:
        times = decode_wrf_times(raw["Times"])
        dt6 = np.timedelta64(6, "h")

        parts = []

        for i, valid_time in enumerate(times):
            t2 = raw["T2"].isel(Time=i).values.astype("float32")
            psfc = raw["PSFC"].isel(Time=i).values.astype("float32") / 100.0

            wspd_wdir = getvar(nc, "uvmet10_wspd_wdir", timeidx=i)
            wspd10 = to_np(wspd_wdir[0]).astype("float32")
            wdir10 = to_np(wspd_wdir[1]).astype("float32")

            rain = (
                raw["RAINC"].isel(Time=i).values.astype("float32")
                + raw["RAINNC"].isel(Time=i).values.astype("float32")
            )
            j = np.where(times == valid_time - dt6)[0]
            if j.size:
                rain_prev = (
                    raw["RAINC"].isel(Time=int(j[0])).values.astype("float32")
                    + raw["RAINNC"].isel(Time=int(j[0])).values.astype("float32")
                )
                apcp_6h = np.maximum(rain - rain_prev, 0.0).astype("float32")
            else:
                apcp_6h = np.full_like(rain, np.nan, dtype="float32")

            rh2 = to_np(getvar(nc, "rh2", timeidx=i)).astype("float32")
            td2 = to_np(getvar(nc, "td2", timeidx=i, units="degC")).astype("float32")
            slp = to_np(getvar(nc, "slp", timeidx=i, units="hPa")).astype("float32")

            parts.append(
                xr.Dataset(
                    {
                        "T2": make_2d_field(t2, valid_time, "T2"),
                        "PSFC": make_2d_field(psfc, valid_time, "PSFC"),
                        "WSPD10": make_2d_field(wspd10, valid_time, "WSPD10"),
                        "WDIR10": make_2d_field(wdir10, valid_time, "WDIR10"),
                        "RH2": make_2d_field(rh2, valid_time, "RH2"),
                        "TD2": make_2d_field(td2, valid_time, "TD2"),
                        "SLP": make_2d_field(slp, valid_time, "SLP"),
                        "APCP_6H": make_2d_field(apcp_6h, valid_time, "APCP_6H"),
                    }
                )
            )

        out = xr.concat(parts, dim="Time")

        out["XLAT"] = xr.DataArray(
            raw["XLAT"].isel(Time=0).values.astype("float32"),
            dims=("south_north", "west_east"),
        )
        out["XLONG"] = xr.DataArray(
            raw["XLONG"].isel(Time=0).values.astype("float32"),
            dims=("south_north", "west_east"),
        )

        out = copy_wrf_global_attrs(raw, out)
        out = add_forecast_reference_time(out, raw)
        out = set_cf_projection_coordinates(out)
        out = set_wrflike_var_attrs(out)
        out = add_cf_lambert_grid_mapping(out)
        
        print(out)

        out["Time"].attrs["standard_name"] = "time"

        enc = {v: {"zlib": True, "complevel": 4} for v in out.data_vars}
        enc["Time"] = {
            "units": "hours since 1900-01-01 00:00:00",
            "dtype": "float64",
        }
        enc["forecast_reference_time"] = {
            "units": "seconds since 1970-01-01 00:00:00",
            "dtype": "float64",
        }

        out.to_netcdf(args.output, encoding=enc)
        print(f"Zapisano: {args.output}  ({len(times)} krokow czasowych)")

    finally:
        nc.close()
        raw.close()


if __name__ == "__main__":
    main()