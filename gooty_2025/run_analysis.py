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

"""Contains functions for scenarios/cases considered in the paper"""

import json
from pathlib import Path
from idaes.apps.grid_integration import PriceTakerModel
import pyomo.environ as pyo

# pylint: disable = import-error
from default_parameters import (
    DFCParams,
    ASUParams,
    NLUParams,
    LOxTankParams,
    CashflowParams,
)
from npv_model import build_pricetaker
from price_data import CO2_PRICE_DATA, LMP_DATA, NG_PRICE_DATA, PRICE_SIGNALS
from util import partition_variables
from linearize_model import linearize_price_taker_model

# Create a folder called "results", if it does not exist, to store all results
results_folder = Path(__file__).parent / "results"
if not results_folder.exists():
    results_folder.mkdir()


def solve_and_save_results(
    m: PriceTakerModel,
    folder: Path,
    filename: str,
    linearize: bool = True,
    partition_size: int | None = 500,
):
    """Solves the optimization model and writes the results to a file"""

    # Solve the model
    solver = pyo.SolverFactory("gurobi_persistent")
    solver.options["MIPGap"] = 0.01
    solver.options["TimeLimit"] = 10000

    if linearize:
        linearize_price_taker_model(m)
        solver.options["NonConvex"] = 0
    else:
        # Turn of presolve for the MIQCP case
        solver.options["Presolve"] = 0

    solver.set_instance(m)
    if partition_size is not None:
        partition_variables(solver, partition_size)

    solver.solve(tee=True)

    # Write results to files
    m.get_operation_var_values().to_csv(folder / (filename + ".csv"))
    des_var_values = m.get_design_var_values()
    des_var_values["comp_time"] = solver._solver_model.Runtime
    des_var_values["duality_gap"] = solver._solver_model.MIPGap * 100
    _net_power = pyo.value(
        m.dfc_design.max_power
        - m.asu_params.power_o2_flow_ratio * m.asu_design.max_o2_flow
    )
    # If the DFC is not built, then the net power would be zero.
    # So, we include an epsilon to avoid division with zero
    des_var_values["capacity_factor"] = pyo.value(
        sum(m.period[:, :].power_to_grid) / (8760 * max(0.001, _net_power))
    )
    des_var_values["linearized_model"] = linearize
    des_var_values["partition_size"] = partition_size

    # pylint: disable = unspecified-encoding
    with open(folder / (filename + ".json"), "w") as fp:
        json.dump(des_var_values, fp, indent=4)


def model_validation():
    """Solves for standalone DFC and ASU for model validation"""
    # Create a sub-folder in results, if it does not exist
    folder = results_folder / "validation"
    if not folder.exists():
        folder.mkdir()

    # Note: Capex costs in the default model parameters only include
    # plant costs. It does not include owner's costs.
    # Owners costs are roughly 21.3496% of the Total plant cost, so we multiply
    # TPC with 1.213496 to obtain the Total Owner's cost
    # Then, we multiply it with 1.093 to obtain the Total as-spent cost
    # Annualization factor (FCR) is 0.0707
    # Depreciation is included in FRC, so we set corporate tax rate to zero

    # Modify CAPEX coefficients here
    cost_params = CashflowParams(tax_rate=0)
    cost_params.fcr = 0.0707 * 1.093 * 1.213496

    dfc_size = {"V1": 777.685, "V2": 422.049, "V3": 176.032}
    lcoe = {"V1": 80.1, "V2": 87.8, "V3": 102.7}

    for ps in ["V1", "V2", "V3"]:
        m: PriceTakerModel = build_pricetaker(
            lmp_data=[lcoe[ps]] * int(8760 * 0.85),
            dfc_params=DFCParams(ng_cost=4.42, carbon_price=0),
            asu_params=ASUParams(),
            nlu_params=NLUParams(),
            tank_params=LOxTankParams(),
            cashflow_params=cost_params,
        )

        # Fix the capacity of DFC, ensure that NLU is not built,
        # and ensure that the DFC operates throughout.
        m.dfc_design.max_power.fix(dfc_size[ps])
        m.nlu_design.install_unit.fix(0)
        m.fix_operation_var("dfc.op_mode", 1)

        solve_and_save_results(m, folder, ps)


def no_storage_no_ar_no_co2():
    """
    Runs the price-taker model for the base case i.e., without
    storage, without revenue from Argon market, and without
    CO2 credits.
    """
    # Create a sub-folder in results, if it does not exist
    folder = results_folder / "no_storage_no_ar_no_co2"
    if not folder.exists():
        folder.mkdir()

    for signal, filename in PRICE_SIGNALS.items():
        m: PriceTakerModel = build_pricetaker(
            lmp_data=LMP_DATA[signal],
            dfc_params=DFCParams(
                ng_cost=NG_PRICE_DATA[signal], carbon_price=CO2_PRICE_DATA[signal]
            ),
            asu_params=ASUParams(),
            nlu_params=NLUParams(),
            tank_params=LOxTankParams(),
            cashflow_params=CashflowParams(),
        )

        # Ensure that DFC is built
        m.dfc_design.install_unit.fix(1)
        m.nlu_design.install_unit.fix(0)
        solve_and_save_results(m, folder, filename)


def no_storage_with_ar_no_co2():
    """
    Runs the price-taker model for the base case i.e., without
    storage, without revenue from Argon market, and without
    CO2 credits.
    """
    # Create a sub-folder in results, if it does not exist
    folder = results_folder / "no_storage_with_ar_no_co2"
    if not folder.exists():
        folder.mkdir()

    for signal, filename in PRICE_SIGNALS.items():
        print("Solving for price signal: ", signal)
        m: PriceTakerModel = build_pricetaker(
            lmp_data=LMP_DATA[signal],
            dfc_params=DFCParams(
                ng_cost=NG_PRICE_DATA[signal], carbon_price=CO2_PRICE_DATA[signal]
            ),
            asu_params=ASUParams(argon_price=0.4),
            nlu_params=NLUParams(),
            tank_params=LOxTankParams(),
            cashflow_params=CashflowParams(),
        )

        # Ensure that DFC is built
        m.dfc_design.install_unit.fix(1)
        m.nlu_design.install_unit.fix(0)
        solve_and_save_results(m, folder, filename)


def no_storage_no_ar_with_co2():
    """
    Runs the price-taker model for the base case i.e., without
    storage, without revenue from Argon market, and without
    CO2 credits.
    """
    # Create a sub-folder in results, if it does not exist
    folder = results_folder / "no_storage_no_ar_with_co2"
    if not folder.exists():
        folder.mkdir()

    for signal, filename in PRICE_SIGNALS.items():
        print("Solving for price signal: ", signal)
        m: PriceTakerModel = build_pricetaker(
            lmp_data=LMP_DATA[signal],
            dfc_params=DFCParams(
                ng_cost=NG_PRICE_DATA[signal],
                carbon_price=CO2_PRICE_DATA[signal],
                carbon_credit=0.06,
            ),
            asu_params=ASUParams(),
            nlu_params=NLUParams(),
            tank_params=LOxTankParams(),
            cashflow_params=CashflowParams(),
        )

        # Ensure that DFC is built
        m.dfc_design.install_unit.fix(1)
        m.nlu_design.install_unit.fix(0)
        solve_and_save_results(m, folder, filename)


def no_storage_with_ar_with_co2():
    """
    Runs the price-taker model for the base case i.e., without
    storage, without revenue from Argon market, and without
    CO2 credits.
    """
    # Create a sub-folder in results, if it does not exist
    folder = results_folder / "no_storage_with_ar_with_co2"
    if not folder.exists():
        folder.mkdir()

    for signal, filename in PRICE_SIGNALS.items():
        print("Solving for price signal: ", signal)
        m: PriceTakerModel = build_pricetaker(
            lmp_data=LMP_DATA[signal],
            dfc_params=DFCParams(
                ng_cost=NG_PRICE_DATA[signal],
                carbon_price=CO2_PRICE_DATA[signal],
                carbon_credit=0.06,
            ),
            asu_params=ASUParams(argon_price=0.4),
            nlu_params=NLUParams(),
            tank_params=LOxTankParams(),
            cashflow_params=CashflowParams(),
        )

        # Ensure that DFC is built
        m.dfc_design.install_unit.fix(1)
        m.nlu_design.install_unit.fix(0)
        solve_and_save_results(m, folder, filename)


def no_storage_full_flexibility():
    """
    Runs the price-taker model for the base case i.e., without
    storage, without revenue from Argon market, and without
    CO2 credits.
    """
    # Create a sub-folder in results, if it does not exist
    folder = results_folder / "no_storage_full_flexibility"
    if not folder.exists():
        folder.mkdir()

    for signal, filename in PRICE_SIGNALS.items():
        print("Solving for price signal: ", signal)
        m: PriceTakerModel = build_pricetaker(
            lmp_data=LMP_DATA[signal],
            dfc_params=DFCParams(
                ng_cost=NG_PRICE_DATA[signal], carbon_price=CO2_PRICE_DATA[signal]
            ),
            asu_params=ASUParams(),
            nlu_params=NLUParams(),
            tank_params=LOxTankParams(),
            cashflow_params=CashflowParams(),
        )

        # Ensure that DFC is built
        m.dfc_design.install_unit.fix(1)
        m.nlu_design.install_unit.fix(0)

        # Ensure that all units are fully flexible:
        m.del_component(m.dfc_startup_shutdown)
        m.del_component(m.asu_startup_shutdown)
        m.del_component(m.dfc_power_ramping)
        m.del_component(m.asu_o2_flow_ramping)
        solve_and_save_results(m, folder, filename)


def with_storage_full_flexibility():
    """
    Runs the price-taker model for the base case i.e., without
    storage, without revenue from Argon market, and without
    CO2 credits.
    """
    # Create a sub-folder in results, if it does not exist
    folder = results_folder / "with_storage_full_flexibility"
    if not folder.exists():
        folder.mkdir()

    for signal, filename in PRICE_SIGNALS.items():
        print("Solving for price signal: ", signal)
        m: PriceTakerModel = build_pricetaker(
            lmp_data=LMP_DATA[signal],
            dfc_params=DFCParams(
                ng_cost=NG_PRICE_DATA[signal], carbon_price=CO2_PRICE_DATA[signal]
            ),
            asu_params=ASUParams(),
            nlu_params=NLUParams(),
            tank_params=LOxTankParams(),
            cashflow_params=CashflowParams(),
        )

        # Ensure that DFC is built
        m.dfc_design.install_unit.fix(1)

        # Ensure that all units are fully flexible:
        m.del_component(m.dfc_startup_shutdown)
        m.del_component(m.asu_startup_shutdown)
        m.del_component(m.dfc_power_ramping)
        m.del_component(m.asu_o2_flow_ramping)
        solve_and_save_results(m, folder, filename)


if __name__ == "__main__":
    # model_validation()
    # no_storage_no_ar_no_co2()
    # no_storage_with_ar_no_co2()
    # no_storage_no_ar_with_co2()
    # no_storage_with_ar_with_co2()
    # no_storage_full_flexibility()
    with_storage_full_flexibility()
