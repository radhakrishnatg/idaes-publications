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
This module contains parameter data

Notes:
1. DFC's net power = Gross power - compressor power - all auxiliaries except ASU.

2. We assume that the natural gas (NG) requirement at full load is proportional to the design
   capacity. Let 'ng_flow_power_ratio' denote the proportinality constant. The value can be
   fitted if multiple data points are available. But if only one data point is available,
   then it is the ratio of NG flowrate at full load and design capacity. Since we have data
   for three designs, this value is fitted to the design data.

3. We assume that the CAPEX of DSU = k0 + k1 * design/max power. The max power is defined in
   Note 1. Provide k0 and k1 as a tuple i.e., (k0, k1)

4. The fixed O&M cost is calculated as a fraction of CAPEX, and it includes: Operating labor,
   maintenance labor, labor administration and overhead charges, and property taxes and insurance.

5. Power cycle must operate between a minimum stable load and full load. Let the minimum stable
   load = 0.3 * full load. Then, the operating capacity range, 'op_capacity_range' = (0.3, 1)

6. Off-design performance curve governs the off-design operation. The performance curve is
   r_NG = k0 + k1 * r_P, where r_P = off-design power / design power and r_NG = NG requirement
   at part load / NG requirement at full load. Provide k0 and k1 as a tuple i.e., (k0, k1)

7. Natural gas molar composition is assumed to be 93.1% methane, 3.2% ethane, 0.7% propane,
   0.4% butane, 1% CO2, and 1.6% N2. Therefore, one kmol of natural gas yields 1.042 kmol
   of CO2, or 1.042 * 44.01 = 45.8584 kg of CO2. Molar mass of natural gas is 17.3268 kg/kmol.
   Therefore, 1 kg of natural gas emits 45.8584/17.3268 = 2.6467 kg of CO2.

8. Non-fuel variable O&M costs include consumables (maintenance material, water, water treatment,
   chemicals, etc.) and waste disposal. Non-fuel variable O&M is not available for individual
   units. We split this cost proportional to the capital costs of DFC and ASU. We calculate the
   vom as the sum of const_vom and var_vom. const_vom adds a fixed cost when the power cycle is
   operating regardless of the power output. var_vom adds a variable cost that is a function of
   total power produced. const_vom = k0 + k1 * design/max power and var_vom = m1 * net power.
   Therefore, the total vom = (k0 + k1 * design/max power) + m1 * net power

9. Assumptions for the air separation unit:
    1. 1 kmol/hr of feed air, composition (0.7812, 0.0093, 0.2095) = (N2, Ar, O2)
    2. 0.20603 kmol/hr of GOX, composition (0, 0.005, 0.995)
    3. 0.63597 kmol/hr of GAN, composition (1, 0, 0)
    4. 0.15 kmol/hr of WAN, composition (0.9682, 0.001852, 0.029947)
    5. 0.008 kmol/hr of LAR, composition (0, 0.999, 0.001)

    This implies:
    MW_feed kg air produces 0.20603 * MW_GOX kg of GOX
    ==> 1 kg/s of GOX requires MW_feed / (0.20603 * MW_GOX) of air

    MW_feed kg of air produces 0.63597 * MW_GAN kg of GAN
    ==> MW_feed / (0.20603 * MW_GOX) kg/s of air produces
        (0.63597 * MW_GAN) / (0.20603 * MW_GOX) of GAN

    1 kg/s of GOx product produces:
        (0.15 * MW_WAN) / (0.20603 * MW_GOX) of WAN, and
        (0.008 * MW_LAR) / (0.20603 * MW_GOX) of LAR

    Therefore,
    GAN production rate = ((0.63597 * MW_GAN) / (0.20603 * MW_GOX)) * GOX flowrate
    LAR production rate = ((0.008 * MW_LAR) / (0.20603 * MW_GOX)) * GOX flowrate

    Molecular weight of feed: 28.964759 kg/kmol
    Molecular weight of GOX : 32.03975 kg/kmol
    Molecular weight of GAN : 28.02 kg/kmol
    Molecular weight of WAN : 28.16128601007286 kg/kmol
    Molecular weight of LAR : 39.94205 kg/kmol

"""

from dataclasses import dataclass, InitVar

# HHV of NG = 22499.17034 btu/lb = 0.0496 MMBtu/kg
NG_HHV = 0.0496
HR_TO_SEC = 3600
LBS_TO_KG = 0.453592

MOL_WEIGHTS_ASU = {
    "GAN": 28.02,
    "GOX": 32.03975,
    "LAR": 39.94205,
}  # Molecular weights of products from ASU See Note 9 above.

# Production rate of nitrogen and liquid argon [in kg/s] per kg/s of GOx product
GAN_PROD_RATE = (
    (0.63597 * MOL_WEIGHTS_ASU["GAN"]) / (0.20603 * MOL_WEIGHTS_ASU["GOX"])
)  # See Note 9 above
LAR_PROD_RATE = (
    (0.008 * MOL_WEIGHTS_ASU["LAR"]) / (0.20603 * MOL_WEIGHTS_ASU["GOX"])
)  # See Note 9 above

# NOTE: All correlations/surrogate models are assumed to be of
# the form y = a0 + a1 * x. So, the coefficients are stored as (a0, a1)


# Parameter data for DFC
# Calculating the FOM as 3.157% of the CAPEX. The percentage value is obtained from
# 35,641.27 (FOM) / 1,128,855 (CAPEX). The FOM is also assumed
# to vary linearly with the capacity.
@dataclass
class DFCParams:
    """Parameters for the design and operation of the direct-fired cycle"""

    # DFC Design parameters
    des_capacity_range: tuple  = (176.032, 777.685)          # [MW] Bounds on net power (Note 1)
    ng_flow_power_ratio: float = 0.034774                    # [kg/s/MW] (Note 2)
    o2_ng_ratio: float         = 3.78495                     # [-] Oxygen/NG flowratio
    capex: tuple               = (239897.1320, 1067.8405)    # [$1000] CAPEX of DFC (Note 3)
    fom_factor: float          = 0.03128                     # [-] Multiplier for FOM (Note 4)

    # DFC Operation Parameters
    op_capacity_range: tuple   = (0.3, 1)                    # [-] Norm. operation range (Note 5)
    perf_curve_coeff: tuple    = (0.3248, 0.6752)            # NG Performance curve coeffs. (Note 6)
    co2_emission_rate: float   = 2.6467                      # [kg CO2/kg NG] (See Note 7).
    co2_captured: float        = 0.985                       # [-] Fraction of CO2 captured
    var_vom_coeff: float       = 0                           # [$1000/MWh] Non-fuel VOM (Note 8)
    const_vom_coeff: tuple     = (0.3736672, 0.0018033)      # [$1000/hr] Non-fuel VOM (See Note 8)
    ng_cost: float             = 3                           # [$/MMBtu] Cost of natural gas
    ng_hhv: float              = NG_HHV                      # [MMBtu/kg] HHV of natural gas
    carbon_price: float        = 0.1                         # [$/kg] Carbon price
    carbon_credit: float       = 0                           # [$/kg] Credits for captured CO2

    startup_rate: float        = 0.3                         # As a fraction of the total capacity
    shutdown_rate: float       = 0.3                         # As a fraction of the total capacity
    rampup_rate: float         = 0.3                         # As a fraction of the total capacity
    rampdown_rate: float       = 0.3                         # As a fraction of the total capacity
    min_up_time: int           = 4                           # [hr] Minimum uptime + shutdown time
    min_down_time: int         = 4                           # [hr] Minimum downtime + startup time
    fixed_om: InitVar[list]    = None                        # [$1000/hr]

    def __post_init__(self, fixed_om):
        self._fom = fixed_om

    @property
    def fom(self):
        """Returns the coefficients of FOM correlation"""
        if self._fom is not None:
            # User has a custom correlation for FOM
            return self._fom

        return [coeff * self.fom_factor for coeff in self.capex]

    @fom.setter
    def fom(self, val):
        self._fom = val


# Parameter data for Monolithic ASU
@dataclass
class ASUParams:
    """Parameters for the design and operation of the ASU"""

    # Design parameters for the ASU
    des_capacity_range: tuple  = (20, 110)               # [kg/s] Bounds on O2 flow
    power_o2_flow_ratio: float = 1.3086                  # [MW/kg/s] Power at full load
    capex: tuple               = (17531.4670, 5394.1471) # [$1000] CAPEX of ASU
    fom_factor: float          = 0.03128                 # [-] Multiplier for FOM

    # Operation parameters for the ASU
    op_capacity_range: tuple   = (0.3, 1)                # [-] Operating range of ASU
    perf_curve_coeff: tuple    = (0.0375, 0.9625)        # Coefficients of performance curve
    argon_price: float         = 0                       # [$/kg] Selling price of Argon
    nitrogen_price: float      = 0                       # [$/kg] Selling price of nitrogen
    var_vom_coeff: float       = 0                       # [$1000/MWh] Non-electricity VOM
    const_vom_coeff: tuple     = (0.0205359, 0.00903)    # [$1000/hr] Non-electricity VOM
    n2_o2_ratio: float         = GAN_PROD_RATE           # [kg GAN / kg GOx] N2 production rate
    ar_o2_ratio: float         = LAR_PROD_RATE           # [kg LAR / kg GOx] Ar production rate

    startup_rate: float        = 0.3                     # As a fraction of the total capacity
    shutdown_rate: float       = 0.3                     # As a fraction of the total capacity
    rampup_rate: float         = 0.3                     # As a fraction of the total capacity
    rampdown_rate: float       = 0.3                     # As a fraction of the total capacity
    min_up_time: int           = 12                      # Minimum uptime + shutdown time
    min_down_time: int         = 12                      # Minimum downtime + startup time
    fixed_om: InitVar[list]    = None

    def __post_init__(self, fixed_om):
        self._fom = fixed_om

    @property
    def fom(self):
        """Returns the coefficients of FOM correlation"""
        if self._fom is not None:
            # User has a custom correlation for FOM
            return self._fom

        return [coeff * self.fom_factor for coeff in self.capex]

    @fom.setter
    def fom(self, val):
        self._fom = val


# Parameter data for NLU
@dataclass
class NLUParams:
    """Parameters for the nitrogen liquefaction unit"""

    des_capacity_range: tuple  = (20, 110)                # [kg/s] Bounds on O2 flow
    power_o2_flow_ratio: float = 1.7873                   # [MW] Power at full load
    capex: tuple               = (7023.3325, 1856.93338)  # [$1000] CAPEX of NLU
    fom_factor: float          = 0.03128                  # [-] Multiplier for FOM

    op_capacity_range: tuple   = (0.3, 1)                 # [-] Operating range
    var_vom_coeff: float       = 0                        # [$1000/MWh] Non-electricity VOM
    const_vom_coeff: tuple     = (0, 0.005498)            # [$1000/hr] Non-electricity VOM
    fixed_om: InitVar[list]    = None

    def __post_init__(self, fixed_om):
        self._fom = fixed_om

    @property
    def fom(self):
        """Returns the coefficients of FOM correlation"""
        if self._fom is not None:
            # User has a custom correlation for FOM
            return self._fom

        return [coeff * self.fom_factor for coeff in self.capex]

    @fom.setter
    def fom(self, val):
        self._fom = val


# Parameter data for LOx tank
@dataclass
class LOxTankParams:
    """Parameters for the design and operation of the storage tank"""

    des_capacity_range: tuple  = (2000, 400000)             # [tonne] Tank capacity
    capex: tuple               = (2779.905438, 0.98167214)  # [$1000] CAPEX of tank
    fom_factor: float          = 0.03128                    # [-] Multiplier for FOM
    min_holdup: float          = 0.1                        # [-] Minimum holdup fraction
    power_o2_flow_ratio: float = 1.47054 / 112.0865459      # [MW/kg/s] Pressurization power
    fixed_om: InitVar[list]    = None

    def __post_init__(self, fixed_om):
        self._fom = fixed_om

    @property
    def fom(self):
        """Returns the coefficients of FOM correlation"""
        if self._fom is not None:
            # User has a custom correlation for FOM
            return self._fom

        return [coeff * self.fom_factor for coeff in self.capex]

    @fom.setter
    def fom(self, val):
        self._fom = val


# Cashflow parameters
@dataclass
class CashflowParams:
    """Overall cashflow parameters"""

    plant_life: int         = 30     # [-] Plant lifetime in years
    discount_rate: float    = 0.075  # [-] Discount rate
    tax_rate: float         = 0.2    # [-] Corporate tax rate
    electricity_cost: float = 5      # [$/MWh] Excess penalty for purchasing electricity
    fcr: float | None       = None   # [-] Custom annualization factor
