#################################################################################
# The Institute for the Design of Advanced Energy Systems Integrated Platform
# Framework (IDAES IP) was produced under the DOE Institute for the
# Design of Advanced Energy Systems (IDAES).
#
# Copyright (c) 2018-2025 by the software owners: The Regents of the
# University of California, through Lawrence Berkeley National Laboratory,
# National Technology & Engineering Solutions of Sandia, LLC, Carnegie Mellon
# University, West Virginia University Research Corporation, et al.
# All rights reserved.  Please see the files COPYRIGHT.md and LICENSE.md
# for full copyright and license information.
#################################################################################

"""This module retrieves price data"""

import json
from pathlib import Path
import pandas as pd

current_file_path = Path(__file__)
lmp_dir = current_file_path.parent.parent / "cortes_et_al_2023" / "data"

# pylint: disable = unspecified-encoding
with open(lmp_dir / "lmp_metadata.json") as fp:
    data = json.load(fp)

LMP_DATA = pd.read_csv(lmp_dir / "lmp_data.csv")
NG_PRICE_DATA = {signal: value["ng_price"] for signal, value in data.items()}

NREL_SIGNALS_100 = {
    "MiNg_$100_CAISO_2035": "CAISO_100",
    "MiNg_$100_ERCOT_2035": "ERCOT_100",
    "MiNg_$100_MISO-W_2035": "MISO_100",
    "MiNg_$100_NYISO_2035": "NYISO_100",
    "MiNg_$100_PJM-W_2035": "PJM_100",
}
NREL_SIGNALS_150 = {
    "MiNg_$150_CAISO_2035": "CAISO_150",
    "MiNg_$150_ERCOT_2035": "ERCOT_150",
    "MiNg_$150_MISO-W_2035": "MISO_150",
    "MiNg_$150_NYISO_2035": "NYISO_150",
    "MiNg_$150_PJM-W_2035": "PJM_150",
}
NREL_SIGNALS = {**NREL_SIGNALS_100, **NREL_SIGNALS_150}
NETL_SIGNALS = {
    "NETL_ERCOT_GEN_0": "NETL_0",
    "NETL_ERCOT_GEN_50": "NETL_50",
    "NETL_ERCOT_GEN_100": "NETL_100",
    "NETL_ERCOT_GEN_200": "NETL_200",
}

PRICE_SIGNALS = {**NREL_SIGNALS, **NETL_SIGNALS}
CO2_PRICE_DATA = {
    "MiNg_$100_CAISO_2035": 0.1,
    "MiNg_$100_ERCOT_2035": 0.1,
    "MiNg_$100_MISO-W_2035": 0.1,
    "MiNg_$100_NYISO_2035": 0.1,
    "MiNg_$100_PJM-W_2035": 0.1,
    "MiNg_$150_CAISO_2035": 0.15,
    "MiNg_$150_ERCOT_2035": 0.15,
    "MiNg_$150_MISO-W_2035": 0.15,
    "MiNg_$150_NYISO_2035": 0.15,
    "MiNg_$150_PJM-W_2035": 0.15,
    "NETL_ERCOT_GEN_0": 0,
    "NETL_ERCOT_GEN_50": 0.050,
    "NETL_ERCOT_GEN_100": 0.1,
    "NETL_ERCOT_GEN_200": 0.2,
}

for signal in NREL_SIGNALS:
    # NREL's 2035 signals have data only for 364 days.
    # Using the prices on day 364 for day 365 as well.
    _last_day_lmp = LMP_DATA[signal].to_list()[8712:8736]
    assert len(_last_day_lmp) == 24
    LMP_DATA.loc[list(range(8736, 8760)), signal] = _last_day_lmp
