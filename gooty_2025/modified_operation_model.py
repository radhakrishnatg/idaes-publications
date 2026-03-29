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
This module modifies IDAES OperationModel class by adding a new method that
helps in linearizing products of capacity variables with unit commitment variables
"""

from idaes.apps.grid_integration import OperationModel
from pyomo.environ import Var, NonNegativeReals


def define_linearization_vars(
    self, capacity_var: Var, aux_var_name: str, var_list: list | None = None
):
    """Defines auxiliary variables for linearization"""
    if var_list is None:
        var_list = ["op_mode", "startup", "shutdown"]

    setattr(
        self,
        aux_var_name,
        Var(var_list, within=NonNegativeReals, bounds=(0, capacity_var.ub)),
    )
    aux_var = getattr(self, aux_var_name)

    # McCormick constraints
    @self.Constraint(aux_var.index_set())
    def mccormick_conv_env(blk, v):
        return aux_var[v] >= capacity_var - (1 - getattr(blk, v)) * capacity_var.ub

    @self.Constraint(aux_var.index_set())
    def mccormick_conc_env_1(_, v):
        return aux_var[v] <= capacity_var

    @self.Constraint(aux_var.index_set())
    def mccormick_conc_env_2(blk, v):
        return aux_var[v] <= getattr(blk, v) * capacity_var.ub


OperationModel.define_linearization_vars = define_linearization_vars
