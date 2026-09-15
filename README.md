# SFINCS on Linux, and the Curonian Lagoon model built with it

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22772337.svg)](https://doi.org/10.5281/zenodo.22772337)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

Two things live here:

- **A native Linux build of SFINCS 2026.01 (v2.4.0 Galibier)** — Deltares ships
  only a Windows executable, so this is compiled from the upstream source tag
  `v2.4.0_Galibier_release` (GNU GPL-3.0), plus the `hydromt-sfincs` environment
  used to build models. Everything below documents that.
- **[`curonian/`](curonian/README.md) — a whole-lagoon compound-flood model of the
  Curonian Lagoon (Lithuania)**, hindcasting Storm Xaver, 28 Nov – 11 Dec 2013.
  Validated against four gauges in three forcing variants; all four success
  criteria met. That directory has its own README with the build and run
  commands, the results tables and the findings.

## What a clone does not contain

The SFINCS executable, its source checkout and the release zip are git-ignored,
as are the models' run directories and large derived inputs — so a clone is
small and carries no Deltares binary. `SFINCS_2026_01_release.zip` must be
obtained from Deltares (its licence terms are in this repo), the binary rebuilt
per **Rebuilding** below, and the model's derived inputs regenerated per
`curonian/README.md`. The raw data sources the Curonian model reads are
absolute paths in `curonian/data_catalog.yml`, specific to the machine this was
built on; a different machine needs those four sources and an edit there.

## Layout

| Path | What it is |
| --- | --- |
| `SFINCS_2026_01_release/` | Unpacked official release: Windows exe, manual, testbed reports |
| `sfincs-src/` | Git checkout of Deltares/SFINCS at `v2.4.0_Galibier_release` (built in place) |
| `sfincs-linux/bin/sfincs` | The Linux executable (gfortran 13, OpenMP, NetCDF-4) |
| `run_sfincs.sh` | Convenience runner, see below |
| `test_model/` | Minimal plane-beach test case that verifies the build |
| `logs/` | configure/make output and micromamba transaction logs |
| `test_model_hydromt/` | Same test case built via HydroMT-SFINCS |
| `hydromt-sfincs*.yml`, `hydromt-sfincs.sitecustomize.py` | Model-builder env spec, lock, and zlib fix |

## Running a model

```bash
# from anywhere: run the model in a directory, using 8 threads
~/sfincs/run_sfincs.sh /path/to/model 8

# or call the binary directly from inside the model directory
cd /path/to/model && OMP_NUM_THREADS=8 ~/sfincs/sfincs-linux/bin/sfincs
```

SFINCS reads `sfincs.inp` from the current directory and writes
`sfincs_map.nc`, `sfincs_his.nc`, and `sfincs.log` next to it.
To put `sfincs` on your PATH, add `export PATH="$HOME/sfincs/sfincs-linux/bin:$PATH"` to `~/.bashrc`.

## Rebuilding

```bash
cd ~/sfincs/sfincs-src/source
autoreconf -vif
./configure FC=gfortran \
  FCFLAGS="-fopenmp -O3 -fallow-argument-mismatch -w" \
  FFLAGS="-fopenmp -O3 -fallow-argument-mismatch -w" \
  --disable-openacc --disable-shared --prefix="$HOME/sfincs/sfincs-linux"
make            # serial on purpose: the Makefile does not declare Fortran module deps, so -j breaks
make install
```

Requirements already present on this machine: gfortran, autoconf/automake/libtool,
`libnetcdf-dev` (NetCDF-C 4.9.2). NetCDF-Fortran 4.6.1 is bundled in the source
tree and linked statically, so no separate install is needed.

## Test model

`test_model/make_test_model.py` writes a 50x20 cell plane beach (100 m cells,
bed from -5 m to +4.8 m) with a water-level boundary on the west edge that
ramps from 0 to +2 m over 6 h. Run it with `../run_sfincs.sh test_model` and
check `sfincs_his.nc`: all three observation points should end near 2.0 m.

## Building models: the `hydromt-sfincs` environment

HydroMT-SFINCS (Deltares' recommended model builder) is installed in a dedicated
micromamba env, `hydromt-sfincs`: hydromt_sfincs 1.2.2 on hydromt 0.10.1, Python 3.11,
plus JupyterLab, matplotlib and netCDF4.

```bash
micromamba activate hydromt-sfincs          # or: micromamba run -n hydromt-sfincs <cmd>
micromamba run -n hydromt-sfincs jupyter lab # kernel "Python (hydromt-sfincs)" is registered
```

Files: `hydromt-sfincs.yml` (spec), `hydromt-sfincs.lock.yml` (full pinned export),
`hydromt-sfincs.sitecustomize.py` (copy of the fix below).

Two things had to be fixed for the stock conda-forge install to work:

1. **`pandas<3`** — hydromt_sfincs 1.2.2 calls `Index.is_integer()`, removed in pandas 3.
2. **zlib symbol clash** — `orc` 2.0.3 (forced by libarrow 15, forced by hydromt 0.10's
   `pyarrow<16`) exports a bundled zlib. Once pyarrow is imported (pandas does it
   implicitly), any deflate-compressed GeoTIFF write, which is hydromt_sfincs' default
   for the `gis/` folder, aborts with `free(): invalid pointer`. The env's
   `site-packages/sitecustomize.py` loads the real `libz.so.1` with `RTLD_GLOBAL` at
   interpreter start, which makes zlib resolve its own symbols first. Drop it when
   moving to hydromt_sfincs 2.x (Arrow >= 16 / orc >= 2.1 no longer have the bug).

To recreate the env: `micromamba create -n hydromt-sfincs -f hydromt-sfincs.yml`, then
copy `hydromt-sfincs.sitecustomize.py` to `<env>/lib/python3.11/site-packages/sitecustomize.py`
and run `python -m ipykernel install --user --name hydromt-sfincs` inside the env.

### Round-trip test

`test_model/build_with_hydromt.py` rebuilds the plane beach through the HydroMT API
(GeoTIFF elevation, binary SFINCS files, GeoJSON exports in `gis/`) into
`test_model_hydromt/`, which `run_sfincs.sh test_model_hydromt` then runs. Station
water levels match the ASCII model to a few mm at the end of the run. The transient
difference at the shoreline station (up to 7 cm) comes from HydroMT's default config,
which writes `manning_sea = 0.02` for cells below datum instead of the uniform 0.04.

hydromt_sfincs 2.0.0 (component-based API, `sf.grid.create()` etc.) exists only as a
release candidate on PyPI as of September 2026; it needs hydromt >= 1.3 and would go in
a separate env. Docs: https://deltares.github.io/hydromt_sfincs/

## Citation

If you use this repository, please cite the software and data it is built on.
Every reference below was verified against its published record; the two marked
"no paper" are software/data and take a software or dataset citation, not a
literature one.

**This repository**

> Razinkovas-Baziukas, A. (2026). *Curonian Lagoon SFINCS model: Storm Xaver
> 2013 hindcast* (Version v1.0.0) [Software]. Zenodo.
> https://doi.org/10.5281/zenodo.22772337

Two DOIs exist, and which one you want depends on the claim you are making:

| DOI | Resolves to | Use it when |
| --- | --- | --- |
| [10.5281/zenodo.22772337](https://doi.org/10.5281/zenodo.22772337) | always the newest version | citing the software in general |
| [10.5281/zenodo.22772338](https://doi.org/10.5281/zenodo.22772338) | v1.0.0 specifically | reproducing a published result |

For a paper, cite the **version** DOI — it is the one that pins the exact code a
result came from.

Machine-readable metadata is in [`CITATION.cff`](CITATION.cff) (GitHub renders it
as a "Cite this repository" button) and [`.zenodo.json`](.zenodo.json), which
Zenodo reads when archiving each release. Both carry the references below as
related identifiers, so the citation graph records what this model is built on.

**Model engine**

> Leijnse, T., van Ormondt, M., Nederhoff, K., & van Dongeren, A. (2021).
> Modeling compound flooding in coastal systems using a computationally
> efficient reduced-physics solver: Including fluvial, pluvial, tidal, wind- and
> wave-driven processes. *Coastal Engineering*, 163, 103796.
> https://doi.org/10.1016/j.coastaleng.2020.103796

**Model builder**

> Eilander, D., Boisgontier, H., Bouaziz, L., Buitink, J., Couasnon, A.,
> Dalmijn, B., Hegnauer, M., de Jong, T., Loos, S., Marth, I., & van Verseveld,
> W. (2023). HydroMT: Automated and reproducible model building and analysis.
> *The Journal of Open Source Software*, 8(83), 4897.
> https://doi.org/10.21105/joss.04897

The `hydromt_sfincs` plugin (v1.2.2 here) has **no paper of its own** — it is
documented within the HydroMT reference above. Cite it as software:
https://github.com/Deltares/hydromt_sfincs

**Forcing data**

> Hersbach, H., Bell, B., Berrisford, P., Hirahara, S., Horányi, A.,
> Muñoz-Sabater, J., … Thépaut, J.-N. (2020). The ERA5 global reanalysis.
> *Quarterly Journal of the Royal Meteorological Society*, 146(730), 1999–2049.
> https://doi.org/10.1002/qj.3803

> Muis, S., Irazoqui Apecechea, M., Dullaart, J., de Lima Rego, J., Madsen,
> K. S., Su, J., Yan, K., & Verlaan, M. (2020). A high-resolution global dataset
> of extreme sea levels, tides, and storm surges, including future projections.
> *Frontiers in Marine Science*, 7, 263.
> https://doi.org/10.3389/fmars.2020.00263

Muis et al. describe GTSM v3.0, the model behind the sea-boundary series used
here. The series itself was downloaded from the Copernicus Climate Data Store
(`sis-water-level-change-timeseries-cmip6`, reanalysis experiment, v3) — cite
that CDS entry alongside the paper, since the dataset and the model description
are not the same artefact.

**Bathymetry, topography and gauges**

EMODnet Bathymetry has **no paper**; it is cited as a dataset, conventionally as
"EMODnet Bathymetry Consortium (2018)". Take the exact DOI and product version
from your own download rather than copying one — the DTM is reissued
periodically and the version matters.

Gauge water levels and river discharge come from the Lithuanian
Hydrometeorological Service (LHMT), whose open data is CC BY-SA 4.0 and
**requires attribution**. Channel centrelines come from OpenStreetMap
contributors, ODbL. The 5 m DEM of the lower Nemunas is a third-party dataset
held locally (see `curonian/data_catalog.yml`) and is not redistributed here.

## Licence

This repository's own code — the `curonian/` model pipeline, `run_sfincs.sh`,
the test models and the documentation — is licensed under the **GNU GPL-3.0-or-later**
([`LICENSE`](LICENSE)), matching SFINCS itself, which it builds and drives.

That licence does **not** extend to the third-party material referenced here,
which keeps its own terms:

| Material | Terms |
| --- | --- |
| SFINCS source and executable (not redistributed here) | GNU GPL-3.0 upstream; the Deltares freeware executable has its own conditions, kept in this repo |
| Gauge water levels and river discharge | © Lithuanian Hydrometeorological Service, CC BY-SA 4.0 — **attribution required** |
| Channel centrelines | © OpenStreetMap contributors, ODbL |
| ERA5, GTSM, EMODnet | Each provider's own terms; see the Citation section |
| 5 m DEM of the lower Nemunas | Third-party, held locally, not redistributed |

## Models built on this SFINCS build

`curonian/` (see the top of this file) is built with the `hydromt-sfincs`
environment above and run with this folder's Linux `sfincs` binary via
`run_sfincs.sh`. Its design, plan and follow-up records are in
`docs/superpowers/`. Full build and run commands, the validation tables and the
findings are in [`curonian/README.md`](curonian/README.md).
