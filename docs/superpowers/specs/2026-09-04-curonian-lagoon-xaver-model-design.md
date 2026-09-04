# Curonian Lagoon SFINCS model — design for the Storm Xaver hindcast (Dec 2013)

**Date:** 2026-09-04 · **Status:** approved in brainstorming, awaiting spec review
**Engine:** SFINCS v2.4.0 Galibier, Linux build at `~/SFINCS/sfincs-linux/bin/sfincs`
**Builder:** hydromt_sfincs 1.2.2 on hydromt 0.10.1, env `hydromt-sfincs`

## 1. Purpose

First version of a compound-flood model of the Curonian Lagoon whose target is
flooding of the Nemunas delta lowlands (Rusnė, Šilutė, the eastern lagoon shore)
by lagoon wind setup, Baltic surge through the Klaipėda strait, and river inflow.

The first hindcast is Storm Xaver, **28 Nov to 11 Dec 2013**: a SW gale peaking at
19.5 m/s at Nida on the morning of 6 Dec, veering NW on 7 Dec. Observed daily
maxima: Uostadvaris 592 cm on 6 Dec (top five of 2010–2014), Klaipėda 588 cm at
06:00 on 6 Dec, Nida 584 cm on 8 Dec (release toward the west shore), Ventė 576 cm
on 8 Dec. Nemunas flow 400–550 m³/s, so the river sets the delta base level but
is not the flood driver.

## 2. Domain and grid

| Item | Value |
| --- | --- |
| CRS | EPSG:3346 (LKS-94 / Lithuania TM), the DEM's CRS |
| Extent | E 270 000–370 000 m, N 6 080 000–6 190 000 m |
| Grid | regular, 100 m cells, `x0=270000 y0=6080000 mmax=1000 nmax=1100 rotation=0` |
| Subgrid | 20 × 20 pixels per cell (5 m), 10 levels, from the elevation stack below |
| Active mask | merged elevation ≤ +10 m and hydraulically connected to the lagoon; dune ridges and uplands inactive. Expected ~300 k active cells |
| Water-level boundary | arc of `msk=2` cells ~2 km seaward of the Klaipėda harbour entrance, so the strait is computed |

## 3. Elevation stack (priority order for `setup_subgrid`)

1. `~/telemac/data/LowerNEMUNASdem_5m.tif` — 5 m DEM, EPSG:3346, E 305.6–435.0 km,
   N 6068.4–6160.7 km. Covers the delta, Šilutė, and the Russian eastern lowlands;
   **not** the Curonian Spit. Inside the lagoon it is a flat 0 and must be replaced.
2. Lagoon bathymetry grid at 50 m interpolated from the 318 in-lagoon isobaths in
   `~/curonian/isobates.gpkg` (depths 0–8.5 m, field `depth`), clipped to the lagoon
   polygon `lagoon_boundary` in `~/curonian/curonian_db.gpkg`. Elevation = −depth.
3. `~/telemac/Curonian/data/curonian_bathymetry_hires.nc` — EMODnet 2022 subset,
   lon 20.4–21.4, lat 54.8–55.8, ~0.06 arcmin. Used only where 1 and 2 are absent:
   the Spit and the Baltic outside the strait. Its land values are crude (Nida
   village shows 32 m) and it closes the strait; both are accepted because the Spit
   is not the target and the strait is burned in (section 4).

Merge: DEM first, isobath grid inside the lagoon polygon, EMODnet as fallback,
`reproj_method="bilinear"`, no buffer smoothing between DEM and bathymetry in v1.

## 4. Channels burned into the subgrid (`datasets_riv`)

| Channel | Geometry | Width | Bed level |
| --- | --- | --- | --- |
| Klaipėda strait | hand-digitised centreline from the lagoon to the boundary arc | 400 m | −12 m |
| Atmata | centreline from the apex near Rusnė to the lagoon | 200 m | −4 m |
| Skirvytė | centreline from the apex to the lagoon | 150 m | −3 m |

Widths and depths are first estimates; where the isobaths or DEM already carry the
channel, the deeper of the two wins.

Centreline source: `prep/make_channels.py` queries OSM Overpass for
`waterway=river` ways named Atmata and Skirvytė, and for the strait uses the OSM
fairway of the Klaipėda harbour channel if present, otherwise a fixed list of
coordinates from the lagoon exit (55.62 N, 21.15 E) through the strait (55.68 N,
21.12 E) to the boundary arc (55.73 N, 21.09 E). Fallback for the distributaries
if Overpass is unreachable: fixed coordinate lists from the apex near Rusnė
(55.30 N, 21.37 E) to the Atmata mouth (55.34 N, 21.25 E) and to the Skirvytė
mouth (55.27 N, 21.28 E). The result is written to `inputs/channels.geojson`
(EPSG:3346, fields `name`, `rivwth`, `rivdph`) and is part of the reviewed inputs.
The local `~/telemac/Curonian/data/curonian_osm.json` is an empty error response
and is not used.

## 5. Vertical datum

- Model datum = the DEM's datum (Lithuanian height system).
- Isobath depths are treated as depth below mean lagoon level, mean lagoon level
  taken as 0 m in the model datum.
- EMODnet's Baltic reference differs by a few cm at most; no correction in v1.
- **Gauge readings:** `level_m = (cm − 500) / 100` in the model datum. This is an
  assumption the user has not yet confirmed; it is a single constant in
  `validate.py` and in the boundary bias correction, so changing it is one edit.
- Sea boundary: GTSM is shifted by one constant so that its mean over 28 Nov–4 Dec
  equals the Klaipėda 06:00 gauge mean over the same days (in metres, model datum).

## 6. Forcing

| Forcing | Source | Treatment |
| --- | --- | --- |
| Sea level | GTSM-ERA5 hourly reanalysis, CDS dataset `sis-water-level-change-timeseries-cmip6`, variable total water level, coastal point nearest Klaipėda (55.72 N, 21.10 E) | bias-corrected as in section 5; written as `bzs` on all boundary-arc points |
| Nemunas | `river_discharge` table, gauge Smalininkai, daily | shifted +1 day travel time, linearly interpolated to hourly, one `src` point at the delta apex near Rusnė (≈55.30 N, 21.37 E) |
| Minija | no 2013 record | constant **46 m³/s** (Lankupiai December mean 2004–2010), one `src` point at the Minija mouth; flagged placeholder |
| Wind | ERA5 hourly u10/v10 at Nida, `~/eutropy/era5_raw/era5_wind_nida_2013.nc` | spatially uniform `wnd` file (speed, direction); default SFINCS drag table |
| Pressure | omitted | inverse barometer is inside the sea boundary; gradient over 100 km negligible |
| Rain, infiltration | omitted | December wind event |
| Ice | omitted | early Dec 2013 was mild |
| Russian rivers (Deima, Matrosovka) | omitted in v1 | note in limitations |

Fallback for the sea boundary if GTSM proves poor at Klaipėda: daily Copernicus cache
`~/curonian/shyfem_box/cmems_boundary/cmems_bal_boundary_2009_2014.nc` (`sla`)
plus the 06:00 gauge, interpolated. Hourly observed Klaipėda data, if the user
obtains it from LHMT, replaces GTSM directly through the same `bzs` writer.

## 7. Run settings

- `tref = tstart = 20131128 000000`, `tstop = 20131211 000000`
- `zsini` = corrected boundary level at `tstart` (flat start, 3-day spin-up)
- `advection = 1`, subgrid mode, `alpha = 0.5`, `huthresh = 0.05`, `viscosity = 1`,
  other solver settings at SFINCS defaults
- Manning: 0.02 below +0.3 m, 0.06 above (`manning_sea`, `manning_land`,
  `rgh_lev_land`)
- Outputs: map hourly (`zs`, `h`, `zsmax`), his every 600 s
- Threads: `OMP_NUM_THREADS=16`

## 8. Observation points (`obs`)

Klaipėda (harbour), Juodkrantė, Nida, Ventė, Uostadvaris, Rusnė, Šilutė, Atmata mouth,
Polessk shore. Gauge coordinates from `station_pts` in `curonian_db.gpkg` where
present, otherwise from the place names.

## 9. Verification and success criteria

`validate.py` compares modelled levels at the 06:00 and 18:00 reading times with
`physical_daily` for Nida, Ventė, Uostadvaris and the 06:00 series at Klaipėda,
after converting cm to metres (section 5). It reports bias, RMSE and peak error
(magnitude and timing) per station and writes a time-series figure and a delta
flood-extent map (`zsmax` minus 5 m ground, cells wetter than 5 cm).

Targets for accepting v1:

- Uostadvaris peak on 6 Dec within ±15 cm and ±6 h.
- Nida rise to 584 cm on 8 Dec reproduced in sign and within ±15 cm.
- Klaipėda 06:00 series through the storm within ±15 cm RMSE (checks the boundary).
- No spurious flooding of the Šilutė uplands; flood extent at Rusnė plausible.

## 10. Project layout

```
~/SFINCS/curonian/
├── data_catalog.yml        # hydromt catalogue: dem_5m, lagoon_bathy_50m, emodnet_2022,
│                           #   lagoon_boundary, channels, stations
├── inputs/                 # derived, reproducible inputs (bathy grid, channels.geojson,
│                           #   boundary/wind/discharge time series as CSV)
├── prep/
│   ├── make_bathymetry.py  # isobaths -> 50 m lagoon bathymetry GeoTIFF
│   ├── make_channels.py    # writes channels.geojson (strait, Atmata, Skirvytė)
│   ├── fetch_gtsm.py       # CDS download of GTSM hourly water level, Dec 2013
│   ├── make_forcing.py     # boundary (bias-corrected), wind, discharge CSVs
│   └── make_stations.py    # observation points GeoJSON
├── build_model.py          # hydromt_sfincs build -> runs/xaver_2013/
├── validate.py             # skill statistics + figures
├── runs/xaver_2013/        # SFINCS input files, outputs (gitignored)
└── README.md
```

Every prep script asserts on its own output before writing: CRS and extent, nodata
fraction, monotone hourly time axis without gaps, no NaN in forcing. `build_model.py`
asserts the active-cell count is within 200–400 k, that boundary cells exist only on
the arc, and that the strait is hydraulically connected to the lagoon (flood fill on
the mask). A one-day dry run precedes the full event run.

Environment addition: `cdsapi` in `hydromt-sfincs` (pip), using `~/.cdsapirc`.

## 11. Known limitations and later refinements

- Uniform wind; gridded ERA5 via CDS is the first upgrade.
- Minija constant; Russian rivers absent.
- Spit land heights from EMODnet only.
- Gauge-zero assumption unverified (section 5).
- Quadtree refinement of the delta and a CORINE-based roughness map are candidates
  after v1 validates.
- Second event, the April 2013 Nemunas flood, reuses everything except forcing.
