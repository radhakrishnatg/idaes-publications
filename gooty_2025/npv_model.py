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

"""Contains function that returns an instance of the price-taker model"""

from idaes.apps.grid_integration import DesignModel, PriceTakerModel
from pyomo.environ import Expression

# pylint: disable = import-error
from default_parameters import (
    DFCParams,
    ASUParams,
    NLUParams,
    LOxTankParams,
    CashflowParams,
)
import dfc_flowsheet as fs
from unit_commitment import Block, startup_shutdown_constraints, ramping_limits


def build_pricetaker(
    lmp_data: list,
    dfc_params: DFCParams,
    asu_params: ASUParams,
    nlu_params: NLUParams,
    tank_params: LOxTankParams,
    cashflow_params: CashflowParams,
):
    """Returns an instance of the PriceTakerModel"""
    m = PriceTakerModel()

    # Save a pointer to the parameters for convenience
    m.dfc_params = dfc_params
    m.asu_params = asu_params
    m.nlu_params = nlu_params
    m.tank_params = tank_params
    m.cashflow_params = cashflow_params

    # Append LMP data to the model
    # All cashflows are in 1000$, so dividing the LMPs by 1000
    # Setting small values to zero to avoid numerical issues
    _lmp = [(i / 1000 if abs(i) > 0.1 else 0) for i in lmp_data]
    m.append_lmp_data(lmp_data=_lmp)

    # Build design surrogate models for all units
    m.dfc_design = DesignModel(
        variable_design_data={
            "design_var": "max_power",
            "design_var_bounds": dfc_params.des_capacity_range,
            "capex": dfc_params.capex,
            "fom": dfc_params.fom,
        }
    )
    m.asu_design = DesignModel(
        variable_design_data={
            "design_var": "max_o2_flow",
            "design_var_bounds": asu_params.des_capacity_range,
            "capex": asu_params.capex,
            "fom": asu_params.fom,
        }
    )
    m.nlu_design = DesignModel(
        variable_design_data={
            "design_var": "max_o2_flow",
            "design_var_bounds": nlu_params.des_capacity_range,
            "capex": nlu_params.capex,
            "fom": nlu_params.fom,
        }
    )
    m.tank_design = DesignModel(
        variable_design_data={
            "design_var": "tank_capacity",
            "design_var_bounds": tank_params.des_capacity_range,
            "capex": tank_params.capex,
            "fom": tank_params.fom,
        }
    )

    # Build multiperiod flowsheet model
    m.build_multiperiod_model(
        flowsheet_func=fs.flowsheet_model, flowsheet_options={"ptm": m}
    )

    # Add startup/shutdown fuel/power requirement for DFC and ASU
    fs.add_dfc_startup_fuel(m)
    fs.add_asu_startup_power(m)

    # # Add capacity limit constraints on all units
    # m.add_capacity_limits(
    #     op_block_name="dfc",
    #     commodity="power",
    #     capacity=m.dfc_design.max_power,
    #     op_range_lb=dfc_params.op_capacity_range[0],
    # )
    # m.add_capacity_limits(
    #     op_block_name="asu",
    #     commodity="o2_flow",
    #     capacity=m.asu_design.max_o2_flow,
    #     op_range_lb=asu_params.op_capacity_range[0],
    # )
    # m.add_capacity_limits(
    #     op_block_name="nlu",
    #     commodity="o2_flow",
    #     capacity=m.nlu_design.max_o2_flow,
    #     op_range_lb=nlu_params.op_capacity_range[0],
    # )

    # Add minimum uptime-downtime constraints
    # m.add_startup_shutdown(
    #     op_block_name="dfc",
    #     des_block_name="dfc_design",
    #     up_time=dfc_params.min_up_time,
    #     down_time=dfc_params.min_down_time,
    # )
    # m.add_startup_shutdown(
    #     op_block_name="asu",
    #     des_block_name="asu_design",
    #     up_time=asu_params.min_up_time,
    #     down_time=asu_params.min_down_time,
    # )
    m.dfc_startup_shutdown = Block(m.set_days)
    startup_shutdown_constraints(
        blk=m.dfc_startup_shutdown[1],
        op_blocks=dict(m.period[1, :].dfc.wildcard_items()),
        install_unit=m.dfc_design.install_unit,
        up_time=dfc_params.min_up_time,
        down_time=dfc_params.min_down_time,
        set_time=m.set_time,
        capacity_var=m.dfc_design.max_power,
        aux_var_name="aux_max_power",
    )
    m.asu_startup_shutdown = Block(m.set_days)
    startup_shutdown_constraints(
        blk=m.asu_startup_shutdown[1],
        op_blocks=dict(m.period[1, :].asu.wildcard_items()),
        install_unit=m.asu_design.install_unit,
        up_time=asu_params.min_up_time,
        down_time=asu_params.min_down_time,
        set_time=m.set_time,
        capacity_var=m.asu_design.max_o2_flow,
        aux_var_name="aux_max_o2_flow",
    )

    # Add ramping constraints
    # m.add_ramping_limits(
    #     op_block_name="dfc",
    #     commodity="power",
    #     capacity=m.dfc_design.max_power,
    #     startup_rate=dfc_params.startup_rate,
    #     shutdown_rate=dfc_params.shutdown_rate,
    #     rampup_rate=dfc_params.rampup_rate,
    #     rampdown_rate=dfc_params.rampdown_rate,
    # )
    # m.add_ramping_limits(
    #     op_block_name="asu",
    #     commodity="o2_flow",
    #     capacity=m.asu_design.max_o2_flow,
    #     startup_rate=asu_params.startup_rate,
    #     shutdown_rate=asu_params.shutdown_rate,
    #     rampup_rate=asu_params.rampup_rate,
    #     rampdown_rate=asu_params.rampdown_rate,
    # )
    m.dfc_power_ramping = Block(m.set_days)
    ramping_limits(
        blk=m.dfc_power_ramping[1],
        op_blocks=dict(m.period[1, :].dfc.wildcard_items()),
        commodity_name="power",
        ru_rate=dfc_params.rampup_rate,
        rd_rate=dfc_params.rampdown_rate,
        su_rate=dfc_params.startup_rate,
        sd_rate=dfc_params.shutdown_rate,
        set_time=m.set_time,
        aux_var_name="aux_max_power",
    )

    m.asu_o2_flow_ramping = Block(m.set_days)
    ramping_limits(
        blk=m.asu_o2_flow_ramping[1],
        op_blocks=dict(m.period[1, :].asu.wildcard_items()),
        commodity_name="o2_flow",
        ru_rate=asu_params.rampup_rate,
        rd_rate=asu_params.rampdown_rate,
        su_rate=asu_params.startup_rate,
        sd_rate=asu_params.shutdown_rate,
        set_time=m.set_time,
        aux_var_name="aux_max_o2_flow",
    )

    # Add hourly cashflow expressions
    m.add_hourly_cashflows(
        revenue_streams=[
            "electricity_revenue",
            "argon_revenue",
            "nitrogen_revenue",
            "carbon_credit",
        ],
        operational_costs=["vom", "fuel_cost", "power_cost", "carbon_price"],
    )

    # Add overall cashflows
    m.add_overall_cashflows(
        lifetime=cashflow_params.plant_life,
        discount_rate=cashflow_params.discount_rate,
        corporate_tax_rate=cashflow_params.tax_rate,
        annualization_factor=cashflow_params.fcr,
    )

    # Add the objective function
    m.add_objective_function(objective_type="npv")

    # Useful expressions
    m.total_vom = Expression(
        expr=sum(m.period[:, :].dfc.vom)
        + sum(m.period[:, :].asu.vom)
        + sum(m.period[:, :].nlu.vom)
    )
    m.total_electricity_revenue = Expression(
        expr=sum(m.period[:, :].electricity_revenue)
    )
    m.total_power_cost = Expression(expr=sum(m.period[:, :].power_cost))
    m.total_fuel_cost = Expression(expr=sum(m.period[:, :].dfc.fuel_cost))
    m.total_carbon_price = Expression(expr=sum(m.period[:, :].dfc.carbon_price))
    m.total_carbon_credit = Expression(expr=sum(m.period[:, :].dfc.carbon_credit))
    m.total_argon_revenue = Expression(expr=sum(m.period[:, :].asu.argon_revenue))
    m.total_nitrogen_revenue = Expression(expr=sum(m.period[:, :].asu.nitrogen_revenue))

    return m


# if __name__ == "__main__":
#     mdl = build_pricetaker(
#         [2, 4, 6, 8],
#         DFCParams(),
#         ASUParams(),
#         NLUParams(),
#         LOxTankParams(),
#         CashflowParams(),
#     )
