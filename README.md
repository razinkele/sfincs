# SFINCS 2026.01 (v2.4.0 Galibier) on Linux

Deltares ships only a Windows executable in `SFINCS_2026_01_release.zip`.
This folder holds a native Linux build of the same release, compiled from the
upstream source tag `v2.4.0_Galibier_release` (GNU GPL-3.0).

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
~/SFINCS/run_sfincs.sh /path/to/model 8

# or call the binary directly from inside the model directory
cd /path/to/model && OMP_NUM_THREADS=8 ~/SFINCS/sfincs-linux/bin/sfincs
```

SFINCS reads `sfincs.inp` from the current directory and writes
`sfincs_map.nc`, `sfincs_his.nc`, and `sfincs.log` next to it.
To put `sfincs` on your PATH, add `export PATH="$HOME/SFINCS/sfincs-linux/bin:$PATH"` to `~/.bashrc`.

## Rebuilding

```bash
cd ~/SFINCS/sfincs-src/source
autoreconf -vif
./configure FC=gfortran \
  FCFLAGS="-fopenmp -O3 -fallow-argument-mismatch -w" \
  FFLAGS="-fopenmp -O3 -fallow-argument-mismatch -w" \
  --disable-openacc --disable-shared --prefix="$HOME/SFINCS/sfincs-linux"
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
