# Curonian Lagoon SFINCS model

Whole-lagoon compound-flood model, first hindcast Storm Xaver (28 Nov – 11 Dec 2013).
Design: `../docs/superpowers/specs/2026-09-04-curonian-lagoon-xaver-model-design.md`.

All commands run from this folder inside the `hydromt-sfincs` env:

    micromamba run -n hydromt-sfincs python -m prep.make_bathymetry
    micromamba run -n hydromt-sfincs python -m prep.make_channels
    micromamba run -n hydromt-sfincs python -m prep.make_geometries
    micromamba run -n hydromt-sfincs python -m prep.fetch_gtsm
    micromamba run -n hydromt-sfincs python -m prep.make_forcing
    micromamba run -n hydromt-sfincs python build_model.py
    ../run_sfincs.sh runs/xaver_2013 16
    micromamba run -n hydromt-sfincs python validate.py

Tests: `micromamba run -n hydromt-sfincs python -m pytest tests -q`
