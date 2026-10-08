"""
Core data structures, data contracts, and data taxonomy for RE-TWIN.
Explicitly separates Measured, Recorded, Derived, Simulated, Estimated, AI-Predicted, and Recommended data.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import time


class DataCategory(str, Enum):
    MEASURED = "MEASURED"          # Direct lab test bench measurement
    RECORDED = "RECORDED"          # Raw CAN telemetry frames from vehicle BMS
    DERIVED = "DERIVED"            # Computed from telemetry (e.g. Coulomb counting, Delta V)
    SIMULATED_EIS = "SIMULATED_EIS"# Physics-informed 1-RC ECM simulation
    ESTIMATED = "ESTIMATED"        # Deterministic domain calculations (Capacity Ah, Energy kWh)
    AI_PREDICTED = "AI_PREDICTED"  # Machine learning predictions (SOH)
    RECOMMENDED = "RECOMMENDED"    # Decision engine tiers & Repurposing Score


class SafetyStatus(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    HIGH_RISK = "HIGH_RISK"
    QUARANTINE = "QUARANTINE"


class ApplicationTier(str, Enum):
    QUARANTINE = "Tier 0: Safety Isolation & Inspection (Quarantine)"
    TIER_1_GRID = "Tier 1: High-Demand Stationary Storage (Grid Peak Shaving / Fast Regulation)"
    TIER_2_SOLAR = "Tier 2: Solar & Commercial Storage (C&I Peak Shaving / Smoothing)"
    TIER_3_HOME_UPS = "Tier 3: Home Backup / UPS / Telecom Tower Power"
    TIER_4_LOW_POWER = "Tier 4: Low-Power Applications (Light Utility EVs / Off-Grid Lighting)"
    TIER_5_RECYCLING = "Tier 5: Recycling & Material Recovery (Lithium/Cobalt/Nickel Extraction)"


class SuitabilityCategory(str, Enum):
    SUITABLE = "SUITABLE"
    MARGINALLY_SUITABLE = "MARGINALLY SUITABLE"
    NOT_SUITABLE = "NOT SUITABLE"
    INSPECTION_REQUIRED = "INSPECTION REQUIRED"


@dataclass
class BatteryPackSpec:
    pack_id: str = "BAT-8S-50AH-001"
    chemistry: str = "NMC 811 Lithium-Ion"
    cell_configuration: str = "8S1P (8 Cells in Series)"
    nominal_voltage_v: float = 32.0       # ~4.0V per cell nominal
    rated_capacity_ah: float = 50.0       # 50.0 Ah rated
    rated_energy_kwh: float = 1.60        # 32V * 50Ah / 1000 = 1.6 kWh
    max_voltage_v: float = 33.6           # 4.2V * 8
    min_voltage_v: float = 24.0           # 3.0V * 8
    max_continuous_current_a: float = 100.0 # 2C
    max_safe_temp_c: float = 55.0
    min_safe_temp_c: float = 0.0
    max_cell_imbalance_v: float = 0.050   # 50 mV fault threshold
    first_life_vehicle: str = "Urban Fleet Delivery Van (Decommissioned)"
    first_life_mileage_km: float = 142500.0
    manufacture_year: int = 2020


@dataclass
class BatteryStateSnapshot:
    timestamp: float = 0.0
    pack_voltage_v: float = 32.0
    pack_current_a: float = 0.0
    pack_power_w: float = 0.0
    soc_raw: float = 80.0
    soc_coulomb: float = 80.0
    cell_voltages: List[float] = field(default_factory=lambda: [4.0] * 8)
    cell_voltage_min: float = 4.0
    cell_voltage_max: float = 4.0
    cell_voltage_mean: float = 4.0
    cell_voltage_imbalance_v: float = 0.005
    temperatures: List[float] = field(default_factory=lambda: [25.0] * 4)
    temp_min: float = 25.0
    temp_max: float = 25.0
    temp_mean: float = 25.0
    temp_spread: float = 0.0
    fault_over_voltage: bool = False
    fault_under_voltage: bool = False
    fault_over_temp: bool = False
    fault_under_temp: bool = False
    fault_over_current: bool = False
    contactor_closed: bool = True
    balancing_active: bool = False
    cumulative_throughput_ah: float = 0.0


@dataclass
class ElectrochemicalState:
    r0_ohm: float = 0.024
    rct_ohm: float = 0.020
    cdl_farad: float = 1.95
    z_lowfreq_ohm: float = 0.044
    phase_lowfreq_deg: float = -0.5
    eis_spectrum_frequencies: List[float] = field(default_factory=list)
    eis_spectrum_z_real: List[float] = field(default_factory=list)
    eis_spectrum_z_imag: List[float] = field(default_factory=list)
    eis_spectrum_magnitude: List[float] = field(default_factory=list)
    eis_spectrum_phase_deg: List[float] = field(default_factory=list)
    is_simulated: bool = True


@dataclass
class HealthDecisionState:
    soh_predicted: float = 0.88
    soh_source: str = "LinearRegression (CAN Features)"
    soh_grade: str = "Grade A (Good)"
    remaining_capacity_ah: float = 44.0
    remaining_energy_kwh: float = 1.408
    estimated_rul_cycles: int = 2100
    repurposing_score_rps: float = 85.0
    rps_breakdown: Dict[str, float] = field(default_factory=dict)
    safety_status: SafetyStatus = SafetyStatus.NORMAL
    recommended_tier: ApplicationTier = ApplicationTier.TIER_2_SOLAR
    recommendation_rationale: str = ""
    stress_factors: Dict[str, float] = field(default_factory=dict)
