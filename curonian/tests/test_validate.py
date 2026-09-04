import numpy as np
import pandas as pd

import validate as va


def test_skill_on_synthetic_series():
    t = pd.date_range("2013-12-01", periods=240, freq="h")
    model = pd.Series(np.sin(np.arange(240) / 20), index=t)
    obs_t = t[6::12]                                    # 06:00 and 18:00 readings
    obs = pd.Series(np.sin(np.arange(240)[6::12] / 20) + 0.1, index=obs_t)
    s = va.skill(model, obs)
    assert abs(s["bias"] + 0.1) < 1e-9 and abs(s["rmse"] - 0.1) < 1e-9 and s["r"] > 0.999
    assert abs(s["peak_err_m"] + 0.1) < 0.02 and abs(s["peak_dt_h"]) <= 12 and s["n"] == len(obs)


def test_obs_order_parsing(tmp_path):
    (tmp_path / "sfincs.obs").write_text("1 2 Klaipeda\n3 4 'Nida'\n")
    assert va.station_names(tmp_path) == ["Klaipeda", "Nida"]
