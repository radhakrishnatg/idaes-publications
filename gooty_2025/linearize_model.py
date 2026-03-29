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

"""This module contains functions needed to linearize the price-taker model"""
from idaes.apps.grid_integration import PriceTakerModel
from pyomo.environ import Constraint

# pylint: disable = import-error
from default_parameters import DFCParams, ASUParams, NLUParams
from unit_commitment import Block, startup_shutdown_constraints, ramping_limits


def _linearize_dfc_model(fs, ptm: PriceTakerModel):
    params: DFCParams = ptm.dfc_params

    fs.dfc.define_linearization_vars(
        capacity_var=ptm.dfc_design.max_power, aux_var_name="aux_max_power"
    )
    fs.dfc.compute_ng_flow.set_value(
        fs.dfc.ng_flow
        == params.perf_curve_coeff[0]
        * params.ng_flow_power_ratio
        * fs.dfc.aux_max_power["op_mode"]
        + params.perf_curve_coeff[1] * params.ng_flow_power_ratio * fs.dfc.power
    )

    vom_expr = (
        params.const_vom_coeff[0] * fs.dfc.op_mode
        + params.const_vom_coeff[1] * fs.dfc.aux_max_power["op_mode"]
    )
    if hasattr(fs.dfc, "compute_vom"):
        fs.dfc.compute_vom.set_value(fs.dfc.vom == vom_expr)
    else:
        fs.dfc.vom.set_value(vom_expr)

    fs.dfc.power_lb_con = Constraint(
        expr=params.op_capacity_range[0] * fs.dfc.aux_max_power["op_mode"]
        <= fs.dfc.power
    )
    fs.dfc.power_ub_con = Constraint(
        expr=fs.dfc.power
        <= params.op_capacity_range[1] * fs.dfc.aux_max_power["op_mode"]
    )


def _linearize_asu_model(fs, ptm: PriceTakerModel):
    params: ASUParams = ptm.asu_params

    fs.asu.define_linearization_vars(
        capacity_var=ptm.asu_design.max_o2_flow, aux_var_name="aux_max_o2_flow"
    )
    fs.asu.compute_power.set_value(
        fs.asu.power
        == params.perf_curve_coeff[0]
        * params.power_o2_flow_ratio
        * fs.asu.aux_max_o2_flow["op_mode"]
        + params.perf_curve_coeff[1] * params.power_o2_flow_ratio * fs.asu.o2_flow
    )

    vom_expr = (
        params.const_vom_coeff[0] * fs.asu.op_mode
        + params.const_vom_coeff[1] * fs.asu.aux_max_o2_flow["op_mode"]
    )
    if hasattr(fs.asu, "compute_vom"):
        fs.asu.compute_vom.set_value(fs.asu.vom == vom_expr)
    else:
        fs.asu.vom.set_value(vom_expr)

    fs.asu.o2_flow_lb_con = Constraint(
        expr=params.op_capacity_range[0] * fs.asu.aux_max_o2_flow["op_mode"]
        <= fs.asu.o2_flow
    )
    fs.asu.o2_flow_ub_con = Constraint(
        expr=fs.asu.o2_flow
        <= params.op_capacity_range[1] * fs.asu.aux_max_o2_flow["op_mode"]
    )


def _linearize_nlu_model(fs, ptm: PriceTakerModel):
    params: NLUParams = ptm.nlu_params

    fs.nlu.define_linearization_vars(
        capacity_var=ptm.nlu_design.max_o2_flow,
        aux_var_name="aux_max_o2_flow",
        var_list=["op_mode"],
    )

    vom_expr = (
        params.const_vom_coeff[0] * fs.nlu.op_mode
        + params.const_vom_coeff[1] * fs.nlu.aux_max_o2_flow["op_mode"]
    )
    if hasattr(fs.nlu, "compute_vom"):
        fs.nlu.compute_vom.set_value(fs.nlu.vom == vom_expr)
    else:
        fs.nlu.vom.set_value(vom_expr)

    fs.nlu.o2_flow_lb_con = Constraint(
        expr=params.op_capacity_range[0] * fs.nlu.aux_max_o2_flow["op_mode"]
        <= fs.nlu.o2_flow
    )
    fs.nlu.o2_flow_ub_con = Constraint(
        expr=fs.nlu.o2_flow
        <= params.op_capacity_range[1] * fs.nlu.aux_max_o2_flow["op_mode"]
    )


def _linearize_dfc_startup_fuel(m: PriceTakerModel):
    params: DFCParams = m.dfc_params
    min_fuel = (
        params.perf_curve_coeff[0]
        + params.perf_curve_coeff[1] * params.op_capacity_range[0]
    ) * params.ng_flow_power_ratio
    num_time_steps = len(m.period)

    for (d, t), con in m.dfc_su_sd_fuel_requirement.items():
        k1 = (
            0.25 * min_fuel * m.period[d, t + 2].dfc.aux_max_power["startup"]
            if t + 2 <= num_time_steps
            else 0
        )
        k2 = (
            0.75 * min_fuel * m.period[d, t + 1].dfc.aux_max_power["startup"]
            if t + 1 <= num_time_steps
            else 0
        )
        k3 = 0.75 * min_fuel * m.period[d, t].dfc.aux_max_power["shutdown"]
        k4 = (
            0.25 * min_fuel * m.period[d, t - 1].dfc.aux_max_power["shutdown"]
            if t - 1 > 0
            else 0
        )
        con.set_value(m.period[d, t].dfc.su_sd_ng_flow == k1 + k2 + k3 + k4)


def _linearize_asu_startup_power(m: PriceTakerModel):
    params: ASUParams = m.asu_params

    # Assuming that the power requirement during startup is 80% of full load power
    # Assuming that the power requirement during shutdown is 50% of full load power
    # Assuming that the time required for startup is 8 hours
    # Assuming that the time required for shutdown is 1 hour
    start_power = 0.8 * params.power_o2_flow_ratio
    shutdown_power = 0.5 * params.power_o2_flow_ratio
    su_time = 8
    num_time_steps = len(m.period)

    for (d, t), con in m.asu_su_sd_fuel_requirement.items():
        _startup_power = sum(
            start_power * m.period[d, t + i].asu.aux_max_o2_flow["startup"]
            for i in range(1, su_time + 1)
            if t + i <= num_time_steps
        )
        con.set_value(
            m.period[d, t].asu.su_sd_power
            == _startup_power
            + shutdown_power * m.period[d, t].asu.aux_max_o2_flow["shutdown"]
        )


def linearize_price_taker_model(m: PriceTakerModel):
    """Linearizes the bilinear constraints in the price-taker model"""
    for fs in m.period.values():
        _linearize_dfc_model(fs, m)
        _linearize_asu_model(fs, m)
        _linearize_nlu_model(fs, m)

        fs.total_hourly_cost.set_value(
            fs.dfc.vom
            + fs.asu.vom
            + fs.nlu.vom
            + fs.power_cost
            + fs.dfc.fuel_cost
            + fs.dfc.carbon_price
        )

    # Linearize startup and shutdown cost constraints
    _linearize_dfc_startup_fuel(m)
    _linearize_asu_startup_power(m)

    # Remove capacity limits, uptime/downtime and ramping constraints
    m.del_component("dfc_power_limits")
    m.del_component("asu_o2_flow_limits")
    m.del_component("nlu_o2_flow_limits")
    m.del_component("dfc_startup_shutdown")
    m.del_component("asu_startup_shutdown")
    m.del_component("dfc_power_ramping")
    m.del_component("asu_o2_flow_ramping")

    # Add linearized startup and shutdown constraints
    m.dfc_startup_shutdown = Block(m.set_days)
    startup_shutdown_constraints(
        blk=m.dfc_startup_shutdown[1],
        op_blocks=dict(m.period[1, :].dfc.wildcard_items()),
        install_unit=m.dfc_design.install_unit,
        up_time=m.dfc_params.min_up_time,
        down_time=m.dfc_params.min_down_time,
        set_time=m.set_time,
        capacity_var=m.dfc_design.max_power,
        aux_var_name="aux_max_power",
    )
    m.asu_startup_shutdown = Block(m.set_days)
    startup_shutdown_constraints(
        blk=m.asu_startup_shutdown[1],
        op_blocks=dict(m.period[1, :].asu.wildcard_items()),
        install_unit=m.asu_design.install_unit,
        up_time=m.asu_params.min_up_time,
        down_time=m.asu_params.min_down_time,
        set_time=m.set_time,
        capacity_var=m.asu_design.max_o2_flow,
        aux_var_name="aux_max_o2_flow",
    )
    # Add linearized ramping constraints
    m.dfc_power_ramping = Block(m.set_days)
    ramping_limits(
        blk=m.dfc_power_ramping[1],
        op_blocks=dict(m.period[1, :].dfc.wildcard_items()),
        commodity_name="power",
        ru_rate=m.dfc_params.rampup_rate,
        rd_rate=m.dfc_params.rampdown_rate,
        su_rate=m.dfc_params.startup_rate,
        sd_rate=m.dfc_params.shutdown_rate,
        set_time=m.set_time,
        aux_var_name="aux_max_power",
    )

    m.asu_o2_flow_ramping = Block(m.set_days)
    ramping_limits(
        blk=m.asu_o2_flow_ramping[1],
        op_blocks=dict(m.period[1, :].asu.wildcard_items()),
        commodity_name="o2_flow",
        ru_rate=m.asu_params.rampup_rate,
        rd_rate=m.asu_params.rampdown_rate,
        su_rate=m.asu_params.startup_rate,
        sd_rate=m.asu_params.shutdown_rate,
        set_time=m.set_time,
        aux_var_name="aux_max_o2_flow",
    )
