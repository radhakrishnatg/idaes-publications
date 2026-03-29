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

from typing import Union
from pyomo.environ import (
    Block,
    Constraint,
    RangeSet,
    Var,
)


def startup_shutdown_constraints(
    blk: Block,
    op_blocks: dict,
    install_unit: Union[int, Var],
    up_time: int,
    down_time: int,
    set_time: RangeSet,
    capacity_var: Var,
    aux_var_name: str,
):
    """
    Appends startup and shutdown constraints for a given unit/process
    """
    aux_var = {t: getattr(op_blk, aux_var_name) for t, op_blk in op_blocks.items()}

    @blk.Constraint(set_time)
    def binary_relationship_con(_, t):
        if t == 1:
            return Constraint.Skip

        return (
            op_blocks[t].op_mode - op_blocks[t - 1].op_mode
            == op_blocks[t].startup - op_blocks[t].shutdown
        )

    @blk.Constraint(set_time)
    def capacity_binary_relationship_con(_, t):
        if t == 1:
            return Constraint.Skip

        return (
            aux_var[t]["op_mode"] - aux_var[t - 1]["op_mode"]
            == aux_var[t]["startup"] - aux_var[t]["shutdown"]
        )

    @blk.Constraint(set_time)
    def minimum_up_time_con_lbf(_, t):
        if t < up_time:
            return Constraint.Skip

        return (
            sum(aux_var[i]["startup"] for i in range(t - up_time + 1, t + 1))
            <= aux_var[t]["op_mode"]
        )

    @blk.Constraint(set_time)
    def minimum_up_time_con_ubf(_, t):
        if t < up_time:
            return Constraint.Skip

        return (
            sum(
                op_blocks[i].startup * capacity_var.ub - aux_var[i]["startup"]
                for i in range(t - up_time + 1, t + 1)
            )
            <= op_blocks[t].op_mode * capacity_var.ub - aux_var[t]["op_mode"]
        )

    @blk.Constraint(set_time)
    def minimum_down_time_con_lbf(_, t):
        if t < down_time:
            return Constraint.Skip

        return (
            sum(aux_var[i]["shutdown"] for i in range(t - down_time + 1, t + 1))
            <= capacity_var - aux_var[t]["op_mode"]
        )

    @blk.Constraint(set_time)
    def minimum_down_time_con_ubf(_, t):
        if t < down_time:
            return Constraint.Skip

        return (
            sum(
                op_blocks[i].shutdown * capacity_var.ub - aux_var[i]["shutdown"]
                for i in range(t - down_time + 1, t + 1)
            )
            <= install_unit * capacity_var.ub
            - capacity_var
            - op_blocks[t].op_mode * capacity_var.ub
            + aux_var[t]["op_mode"]
        )


def ramping_limits(
    blk: Block,
    op_blocks: dict,
    commodity_name: str,
    ru_rate: float,
    rd_rate: float,
    su_rate: float,
    sd_rate: float,
    set_time: RangeSet,
    aux_var_name: str,
):
    """
    Appends ramping constraints
    """
    aux_var = {t: getattr(op_blk, aux_var_name) for t, op_blk in op_blocks.items()}
    ramping_var = {t: getattr(blk, commodity_name) for t, blk in op_blocks.items()}

    @blk.Constraint(set_time)
    def ramp_up_con(_, t):
        if t == 1:
            return Constraint.Skip

        return (
            ramping_var[t] - ramping_var[t - 1]
            <= su_rate * aux_var[t]["startup"] + ru_rate * aux_var[t - 1]["op_mode"]
        )

    @blk.Constraint(set_time)
    def ramp_down_con(_, t):
        if t == 1:
            return Constraint.Skip

        return (
            ramping_var[t - 1] - ramping_var[t]
            <= sd_rate * aux_var[t]["shutdown"] + rd_rate * aux_var[t]["op_mode"]
        )
