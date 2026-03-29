import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyomo.environ as pyo
from price_data import PRICE_SIGNALS


# pylint: disable = protected-access
def partition_variables(solver, partition_size):
    """Partitions variables based on time index"""
    pm: pyo.ConcreteModel = solver._pyomo_model
    pm_to_gm = solver._pyomo_var_to_solver_var_map

    # Except operation variables, all other variables
    # must be present in all sub-MIPs
    for v in pm.component_data_objects(pyo.Var):
        if "period" in v.name:
            # This is an operation variable, so continue
            continue

        pm_to_gm[v].Partition = 0

    for d, t in pm.period:
        for v in pm.period[d, t].component_data_objects(pyo.Var):
            pm_to_gm[v].Partition = 1 + ((t - 1) // partition_size)


def set_branch_priorities(solver, mult_factor: float = 10.0):
    """Sets branching priority as t * factor"""
    pm: pyo.ConcreteModel = solver._pyomo_model
    pm_to_gm = solver._pyomo_var_to_solver_var_map

    max_time_steps = len(pm.set_time)
    for d, t in pm.period:
        for v in pm.period[d, t].component_data_objects(pyo.Var):
            if v.is_binary():
                # Ideally, we want to branch on variables sequentially
                # So, setting a higher branch priority on initial time points
                pm_to_gm[v].BranchPriority = (max_time_steps - t + 1) * mult_factor


def make_lower_capacity_constraints_lazy(solver, unit_list: list | None = None):
    """Makes the lower capacity limit constraints lazy"""
    pm = solver._pyomo_model

    if unit_list is None:
        unit_list = ["dfc.power_lb_con", "asu.o2_flow_lb_con", "nlu.o2_flow_lb_con"]

    for blk in pm.period.values():
        for unit in unit_list:
            solver._pyomo_con_to_solver_con_map[blk.find_component(unit)].Lazy = 2


def pseudo_rolling_horizon(m, h1, h2):
    """Solves the optimization problem in a rolling horizon fashion"""
    bin_var_list = {t: [] for _, t in m.period}

    for d, t in m.period:
        for v in m.period[d, t].component_data_objects(pyo.Var):
            if v.is_binary():
                # Relax the binary variable and store a reference
                v.domain = pyo.UnitInterval
                bin_var_list[t].append(v)

    time_step = 1
    while time_step < len(m.period):
        for t in range(time_step, time_step + h1):
            # Add binary requirement back
            for v in bin_var_list[t]:
                v.domain = pyo.Binary

        print("Total horizon: ", (time_step, time_step + h1))
        # solver = pyo.SolverFactory("gurobi_persistent")
        # solver.options["MIPGap"] = 0.001
        # solver.set_instance(m)
        # solver.solve(tee=True)
        solver = pyo.SolverFactory("gurobi")
        solver.solve(m, tee=True, options={"MIPGap": 0.001})

        for t in range(time_step, time_step + h2):
            # Freeze the binaries in this window
            for v in bin_var_list[t]:
                v.fix()

        time_step += h2


def set_variable_hints(solver):
    """Solves an LP relaxation, and sets variable hints"""
    pm: pyo.ConcreteModel = solver._pyomo_model
    pm_to_gm = solver._pyomo_var_to_solver_var_map

    # Clone the model, relax binaries, solve LP
    cm = pm.clone()
    relax_binary_variables(cm)
    relax_solver = pyo.SolverFactory("gurobi_persistent")
    relax_solver.set_instance(cm)
    relax_solver.solve(tee=True)

    for v in pm.component_data_objects(pyo.Var):
        if v.is_binary():
            val = cm.find_component(v.name).value

            if val is None:
                continue

            if np.isclose(val, 1, rtol=1e-3):
                pm_to_gm[v].VarHintVal = 1

            elif np.isclose(val, 0, rtol=1e-3):
                pm_to_gm[v].VarHintVal = 0


def relax_binary_variables(m: pyo.ConcreteModel):
    """Relaxes all binary variables in the model"""
    bin_var_list = []
    for v in m.component_data_objects(pyo.Var):
        if v.is_binary():
            v.domain = pyo.UnitInterval
            bin_var_list.append(v)

    return bin_var_list


def read_results():
    """Reads results from the folders and writes them to a file"""
    folders = {
        "no_storage_no_ar_no_co2": {
            "Storage": "No",
            "Argon Revenue": "No",
            "CO2 Credits": "No",
            "Flexibility": "Restricted",
        },
        "no_storage_with_ar_no_co2": {
            "Storage": "No",
            "Argon Revenue": "Yes",
            "CO2 Credits": "No",
            "Flexibility": "Restricted",
        },
        "no_storage_no_ar_with_co2": {
            "Storage": "No",
            "Argon Revenue": "No",
            "CO2 Credits": "Yes",
            "Flexibility": "Restricted",
        },
        # "no_storage_with_ar_with_co2": {
        #     "Storage": "No",
        #     "Argon Revenue": "Yes",
        #     "CO2 Credits": "Yes",
        #     "Flexibility": "Restricted",
        # },
        # "no_storage_full_flexibility": {
        #     "Storage": "No",
        #     "Argon Revenue": "No",
        #     "CO2 Credits": "No",
        #     "Flexibility": "Full",
        # },
        # "with_storage_full_flexibility": {
        #     "Storage": "No",
        #     "Argon Revenue": "No",
        #     "CO2 Credits": "No",
        #     "Flexibility": "Full",
        # },
        "with_storage_no_ar_no_co2": {
            "Storage": "Yes",
            "Argon Revenue": "No",
            "CO2 Credits": "No",
            "Flexibility": "Restricted",
        },
        "with_storage_with_ar_no_co2": {
            "Storage": "Yes",
            "Argon Revenue": "Yes",
            "CO2 Credits": "No",
            "Flexibility": "Restricted",
        },
        "with_storage_no_ar_with_co2": {
            "Storage": "Yes",
            "Argon Revenue": "No",
            "CO2 Credits": "Yes",
            "Flexibility": "Restricted",
        },
    }
    summary = {}
    results_folder = Path(__file__).parent / "results"

    for folder in folders:
        results = {}
        for filename in PRICE_SIGNALS.values():
            fn = results_folder / folder / (filename + ".json")
            with open(fn, "r") as fp:
                results[filename] = json.load(fp)["cashflows.npv"] / 1000

        summary[folder] = results

    summary_df = pd.DataFrame.from_dict(summary)
    summary_df.to_csv("summary.csv")
    pd.DataFrame.from_dict(folders).to_csv("headers.csv")

    return summary_df


if __name__ == "__main__":
    read_results()
