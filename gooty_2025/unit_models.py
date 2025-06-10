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

from pyomo.environ import (
    Var,
    NonNegativeReals,
    Param,
    Constraint,
    Expression,
)

from idaes.apps.grid_integration import (
    DesignModel,
    OperationModel,
    StorageModel,
    PriceTakerModel,
)

from default_parameters import (
    DFCParams,
    ASUParams,
    NLUParams,
    LOxTankParams,
    HR_TO_SEC,
)


def _add_dfc_operation_model(m, ptm):
    """Adds an instance of the Direct-fired cycle model to the flowsheet"""

    params: DFCParams = ptm.dfc_params

    m.dfc = OperationModel(
        polynomial_surrogate_data={
            "operation_var": "power",
            # Surrogate model form: a0 + a1 * power + a2 * power**2 + ....
            "ng_flow": (
                params.perf_curve_coeff[0]
                * params.ng_flow_power_ratio
                * ptm.dfc_design.max_power,
                params.perf_curve_coeff[1] * params.ng_flow_power_ratio,
            ),
            "vom": (
                params.const_vom_coeff[0] * ptm.dfc_design.max_power
                + params.const_vom_coeff[1],
                params.var_vom_coeff,
            ),
        }
    )
    m.dfc.su_sd_ng_flow = Var(
        within=NonNegativeReals,
        doc="Natural gas flowrate required during startup and shutdown [kg/s]",
    )
    m.dfc.total_ng_flow = Expression(expr=m.dfc.ng_flow + m.dfc.su_sd_ng_flow)
    m.dfc.build_expressions(
        expressions={
            "o2_flow": params.o2_ng_ratio * m.dfc.total_ng_flow,
            "carbon_price": (
                params.co2_emission_rate  # kg CO2 / kg NG
                * m.dfc.total_ng_flow  # kg/s of NG
                * HR_TO_SEC  # 3600 s
                * (1 - params.co2_captured)  # Fraction not captured
                * params.carbon_price  # $/kg of CO2
            ),
            "fuel_cost": (
                # $/MMBtu * kg/s * s * MMBtu/kg
                m.dfc.total_ng_flow  # kg/s of NG
                * HR_TO_SEC  # 3600 s
                * params.ng_hhv  # MMBtu / kg NG
                * params.ng_cost  # $/MMBtu
            ),
        },
        declare_variables=True,
    )


def _add_asu_operation_model(m, ptm):
    """Adds an instance of the air separation unit model"""
    params: ASUParams = ptm.asu_params

    m.asu = OperationModel(
        polynomial_surrogate_data={
            "operation_var": "o2_flow",
            "power": (
                params.perf_curve_coeff[0]
                * params.power_o2_flow_ratio
                * ptm.asu_params.ptm.asu_design.max_o2_flow,
                params.perf_curve_coeff[1] * params.power_o2_flow_ratio,
            ),
            "vom": (
                params.const_vom_coeff[0] * ptm.asu_design.max_o2_flow
                + params.const_vom_coeff[1],
                params.var_vom_coeff,
            ),
        }
    )
    m.asu.su_sd_power = Var(
        within=NonNegativeReals,
        doc="Power requirement during startup and shutdown [in MW]",
    )
    m.asu.build_expressions(
        expressions={
            "total_power": m.asu.power + m.asu.su_sd_power,
            "argon_revenue": (
                params.ar_o2_ratio * m.asu.o2_flow * HR_TO_SEC * params.argon_price
            ),
            "nitrogen_revenue": (
                params.n2_o2_ratio * m.asu.o2_flow * HR_TO_SEC * params.nitrogen_price
            ),
        },
        declare_variables=True,
    )


def _add_power_vars_and_constraints(m):
    """
    Adds auxiliary power variables and power balance
    constraints to the flowsheet model
    """
    m.power_to_grid = Var(
        within=NonNegativeReals, doc="Total power sold to the grid [MW]"
    )
    m.power_from_grid = Var(
        within=NonNegativeReals, doc="Power purchased from grid [MW]"
    )
    m.power_dfc_to_asu = Var(within=NonNegativeReals, doc="Power from DFC to ASU")
    m.power_dfc_to_nlu = Var(within=NonNegativeReals, doc="Power from DFC to NLU")
    m.power_dfc_to_tank = Var(within=NonNegativeReals, doc="Power from DFC to tank")
    m.power_grid_to_asu = Var(within=NonNegativeReals, doc="Grid power to ASU")
    m.power_grid_to_nlu = Var(within=NonNegativeReals, doc="Grid power to NLU")
    m.power_grid_to_tank = Var(within=NonNegativeReals, doc="Grid power to tank")
    m.o2

    m.dfc_power_balance = Constraint(
        expr=(
            m.dfc.power
            == m.power_to_grid
            + m.power_dfc_to_asu
            + m.power_dfc_to_nlu
            + m.power_dfc_to_tank
        ),
        doc="Power balance around the direct-fired cycle",
    )
    m.asu_power_balance = Constraint(
        expr=m.asu.power == m.power_dfc_to_asu + m.power_grid_to_asu,
        doc="Power balance around the air separation unit",
    )
    m.nlu_power_balance = Constraint(
        expr=m.nlu.power == m.power_dfc_to_nlu + m.power_grid_to_nlu,
        doc="Power balance around the liquefaction unit",
    )
    m.tank_power_balance = Constraint(
        expr=m.tank.power == m.power_dfc_to_tank + m.power_grid_to_tank,
        doc="Power balance around the storage tank",
    )
    m.grid_power_balance = Constraint(
        expr=m.power_from_grid
        == m.power_grid_to_asu + m.power_grid_to_nlu + m.power_grid_to_tank,
        doc="Power balance at the grid",
    )


def _add_o2_flow_vars_and_constraints(m):
    """Adds auxiliary oxygen flow variables and oxygen balance constraints"""
    m.o2_asu_to_dfc = Var(within=NonNegativeReals, doc="O2 flow from ASU to DFC")
    m.o2_asu_to_nlu = Var(within=NonNegativeReals, doc="O2 flow from ASU to NLU")
    m.o2_asu_to_vent = Var(within=NonNegativeReals, doc="O2 flow vented")

    m.dfc_o2_balance = Constraint(
        expr=m.dfc.o2_flow == m.o2_asu_to_dfc + m.tank.discharge_rate,
        doc="Oxygen flow balance around the direct fired cycle",
    )
    m.asu_o2_balance = Constraint(
        expr=m.asu.o2_flow == m.o2_asu_to_dfc + m.o2_asu_to_nlu + m.o2_asu_to_vent,
        doc="Oxygen flow balance around the air separation unit",
    )
    m.nlu_o2_balance = Constraint(
        expr=m.nlu.o2_flow == m.o2_asu_to_nlu,
        doc="Oxygen flow balance around the liquefaction unit",
    )
    m.tank_o2_balance = Constraint(
        expr=m.nlu.o2_flow == m.tank.charge_rate,
        doc="Oxygen flow balance at the tank inlet",
    )


def flowsheet_model(m, ptm):
    """Builds an instance of the flowsheet model"""
    m.LMP = Param(
        initialize=1, mutable=True, doc="Locational Marginal Price [in 1000$/MWh]"
    )

    # Build an instance of the direct-fired cycle and air separation unit
    _add_dfc_operation_model(m, ptm)
    _add_asu_operation_model(m, ptm)

    nlu_params: NLUParams = ptm.nlu_params
    tank_params: LOxTankParams = ptm.tank_params
    m.nlu = OperationModel(
        polynomial_surrogate_data={
            "operation_var": "o2_flow",
            "power": nlu_params.power_o2_flow_ratio,
            "vom": (
                nlu_params.const_vom_coeff[0] * ptm.nlu_design.max_o2_flow
                + nlu_params.const_vom_coeff[1],
                nlu_params.var_vom_coeff,
            ),
        }
    )
    m.tank = StorageModel(
        min_holdup=tank_params.min_holdup * ptm.tank_design.tank_capacity,
        max_holdup=ptm.tank_design.tank_capacity,
    )

    # Declare auxiliary variables needed to complete the flowsheet
    _add_power_vars_and_constraints(m)
    _add_o2_flow_vars_and_constraints(m)


def build_pricetaker(
    dfc_params: DFCParams,
    asu_params: ASUParams,
    nlu_params: NLUParams,
    tank_params: LOxTankParams,
):
    """Returns an instance of the PriceTakerModel"""
    m = PriceTakerModel()

    # Save a pointer to the parameters for convenience
    m.dfc_params = dfc_params
    m.asu_params = asu_params
    m.nlu_params = nlu_params
    m.tank_params = tank_params

    # Append LMP data to the model
    m.append_lmp_data(lmp_data=[2, 4, 6, 8])

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

    # # Build multiperiod flowsheet model
    # m.build_multiperiod_model(
    #     flowsheet_func=flowsheet_model, flowsheet_options={"ptm": m}
    # )

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

    # # Add minimum uptime-downtime constraints
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

    # # Add ramping constraints
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

    # # Add hourly cashflow expressions
    # m.add_hourly_cashflows(
    #     revenue_streams=["electricity_revenue", "argon_revenue", "nitrogen_revenue"],
    #     operational_costs=["vom", "fuel_cost", "power_cost"],
    # )

    # # Add overall cashflows
    # m.add_overall_cashflows()

    # # Add the objective function
    # m.add_objective_function()

    return m


if __name__ == "__main__":
    mdl = build_pricetaker(DFCParams(), ASUParams(), NLUParams(), LOxTankParams())
