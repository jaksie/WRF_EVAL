from pathlib import Path

import pandas as pd
import xarray as xr


WRF_PATH = Path("/home/jaksie/wrf_eval/input/wrf/wrfout_d01_2026-01-15_03:00:00")
ERA5_ON_WRF_PATH = Path("input/era5/processed/era5_t2m_2026_01_on_wrf_grid.nc")
OUT_PATH = Path("output/moa/error_maps/t2_error_wrf_minus_era5_2026-01-15_03.nc")

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

wrf = xr.open_dataset(WRF_PATH)
era5 = xr.open_dataset(ERA5_ON_WRF_PATH)

wrf_t2 = wrf["T2"]

# WRF Times: char array -> datetime
wrf_times = [
    "".join(row.astype(str)).replace("_", " ")
    for row in wrf["Times"].values
]
wrf_times = pd.to_datetime(wrf_times)

wrf_t2 = wrf_t2.assign_coords(Time=wrf_times)

errors = []

for valid_time in wrf_times:
    wrf_field = wrf_t2.sel(Time=valid_time)
    era5_field = era5["T2_ERA5_ON_WRF"].sel(time=valid_time)

    error = wrf_field - era5_field
    error = error.expand_dims(time=[valid_time])
    errors.append(error)

error_da = xr.concat(errors, dim="time")
error_da.name = "T2_ERROR_WRF_MINUS_ERA5"
error_da.attrs.update({
    "long_name": "WRF T2 minus ERA5 2m temperature interpolated to WRF grid",
    "units": "K",
})

ds_out = error_da.to_dataset()
ds_out["XLAT"] = wrf["XLAT"].isel(Time=0)
ds_out["XLONG"] = wrf["XLONG"].isel(Time=0)

ds_out.to_netcdf(OUT_PATH)

print(f"Saved: {OUT_PATH}")
print(ds_out)

x = ds_out["T2_ERROR_WRF_MINUS_ERA5"]
print("min:", float(x.min(skipna=True)))
print("max:", float(x.max(skipna=True)))
print("mean:", float(x.mean(skipna=True)))
print("std:", float(x.std(skipna=True)))