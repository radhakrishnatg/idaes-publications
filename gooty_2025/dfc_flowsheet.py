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

"""
This module contains functions for building a flowsheet with a direct-fired cycle,
air separation unit, liquefaction unit, and a liquid oxygen storage tank. It
also contains functions for computing fuel requirement for startup/shutdown of
the direct-fired cycle, and for computing power requirement for startup/shutdown
of the air separation unit.
"""

from idaes.apps.grid_integration import OperationModel, StorageModel, PriceTakerModel
from pyomo.environ import (
    Var,
    NonNegativeReals,
    Param,
    Constraint,
    Expression,
)

# pylint: disable = import-error
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
                params.const_vom_coeff[0]
                + params.const_vom_coeff[1] * ptm.dfc_design.max_power,
                params.var_vom_coeff,
            ),
        },
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
                / 1000  # Converting the cost to $1000
            ),
            "carbon_credit": (
                params.co2_emission_rate  # kg CO2 / kg NG
                * m.dfc.total_ng_flow  # kg/s of NG
                * HR_TO_SEC  # 3600 s
                * params.co2_captured  # Fraction not captured
                * params.carbon_credit  # $/kg of CO2
                / 1000  # Converting the revenue to $1000
            ),
            "fuel_cost": (
                # $/MMBtu * kg/s * s * MMBtu/kg
                m.dfc.total_ng_flow  # kg/s of NG
                * HR_TO_SEC  # 3600 s
                * params.ng_hhv  # MMBtu / kg NG
                * params.ng_cost  # $/MMBtu
                / 1000  # Converting the cost to $1000
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
                * ptm.asu_design.max_o2_flow,
                params.perf_curve_coeff[1] * params.power_o2_flow_ratio,
            ),
            "vom": (
                params.const_vom_coeff[0]
                + params.const_vom_coeff[1] * ptm.asu_design.max_o2_flow,
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
                params.ar_o2_ratio  # kg Ar / kg GOx
                * m.asu.o2_flow  # kg/s of GOx
                * HR_TO_SEC  # 3600 s
                * params.argon_price  # $/kg Ar
                / 1000  # Converting the revenue to $1000
            ),
            "nitrogen_revenue": (
                params.n2_o2_ratio  # kg GAN / kg GOx
                * m.asu.o2_flow  # kg/s of GOx
                * HR_TO_SEC  # 3600 s
                * params.nitrogen_price  # $/kg GAN
                / 1000  # Converting the revenue to $1000
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
        expr=m.asu.total_power == m.power_dfc_to_asu + m.power_grid_to_asu,
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
                nlu_params.const_vom_coeff[0]
                + nlu_params.const_vom_coeff[1] * ptm.nlu_design.max_o2_flow,
                nlu_params.var_vom_coeff,
            ),
        }
    )
    m.minimum_tank_holdup = Expression(
        expr=tank_params.min_holdup * ptm.tank_design.tank_capacity,
    )
    m.tank = StorageModel(
        time_interval=(3600 / 1000),
        min_holdup=m.minimum_tank_holdup,
        max_holdup=ptm.tank_design.tank_capacity,
    )
    m.tank.power = Expression(
        expr=tank_params.power_o2_flow_ratio * m.tank.discharge_rate,
        doc="Power required to pressurize liquid oxygen [in MW]",
    )

    # Declare auxiliary variables needed to complete the flowsheet
    _add_power_vars_and_constraints(m)
    _add_o2_flow_vars_and_constraints(m)

    # Add electricity revenue and cost expressions
    m.electricity_revenue = Expression(expr=m.LMP * m.power_to_grid)
    m.power_cost = Expression(
        # Dividing the electricity_cost by 1000 for scaling
        expr=(m.LMP + ptm.cashflow_params.electricity_cost / 1000)
        * m.power_from_grid
    )


def add_dfc_startup_fuel(m: PriceTakerModel):
    """Computes the fuel requirement for DFC startup and shutdown"""

    params: DFCParams = m.dfc_params
    min_fuel = (
        (
            params.perf_curve_coeff[0]
            + params.perf_curve_coeff[1] * params.op_capacity_range[0]
        )
        * params.ng_flow_power_ratio
        * m.dfc_design.max_power
    )
    num_time_steps = len(m.period)

    @m.Constraint(m.period.index_set())
    def dfc_su_sd_fuel_requirement(blk, d, t):
        k1 = (
            0.25 * min_fuel * blk.period[d, t + 2].dfc.startup
            if t + 2 <= num_time_steps
            else 0
        )
        k2 = (
            0.75 * min_fuel * blk.period[d, t + 1].dfc.startup
            if t + 1 <= num_time_steps
            else 0
        )
        k3 = 0.75 * min_fuel * blk.period[d, t].dfc.shutdown
        k4 = 0.25 * min_fuel * blk.period[d, t - 1].dfc.shutdown if t - 1 > 0 else 0
        return blk.period[d, t].dfc.su_sd_ng_flow == k1 + k2 + k3 + k4


def add_asu_startup_power(m: PriceTakerModel):
    """Computes the power requirement for ASU startup and shutdown"""

    params: ASUParams = m.asu_params

    # Assuming that the power requirement during startup is 80% of full load power
    # Assuming that the power requirement during shutdown is 50% of full load power
    # Assuming that the time required for startup is 8 hours
    # Assuming that the time required for shutdown is 1 hour
    start_power = 0.8 * params.power_o2_flow_ratio * m.asu_design.max_o2_flow
    shutdown_power = 0.5 * params.power_o2_flow_ratio * m.asu_design.max_o2_flow
    su_time = 8
    num_time_steps = len(m.period)

    @m.Constraint(m.period.index_set())
    def asu_su_sd_fuel_requirement(blk, d, t):
        _startup_power = sum(
            start_power * blk.period[d, t + i].asu.startup
            for i in range(1, su_time + 1)
            if t + i <= num_time_steps
        )
        return (
            blk.period[d, t].asu.su_sd_power
            == _startup_power + shutdown_power * blk.period[d, t].asu.shutdown
        )
