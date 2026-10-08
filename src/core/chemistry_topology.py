"""
Dynamic Multi-Chemistry and Pack Topology Configuration Module.
Provides modular parameter profiles for commercial Li-ion chemistries (NMC 811, LFP, NCA)
and scalable battery topologies (8S, 16S, 96S / 400V class, 192S / 800V class).
NOTE: Labeled as 'Prototype Chemistry Parameters' for configurable engineering simulation.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum


class ChemistryType(Enum):
    NMC_811 = "NMC 811 (Nickel Manganese Cobalt)"
    LFP = "LFP (Lithium Iron Phosphate)"
    NCA = "NCA (Nickel Cobalt Aluminum)"


@dataclass
class ChemistryProfile:
    """Cell-level electrochemical parameters for a specific battery chemistry."""
    name: str
    nominal_cell_voltage_v: float
    min_cell_voltage_v: float
    max_cell_voltage_v: float
    optimal_temp_min_c: float
    optimal_temp_max_c: float
    max_safe_temp_c: float
    recommended_max_c_rate: float
    nominal_cycle_life: int
    thermal_runaway_onset_c: float
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "nominal_cell_voltage_v": self.nominal_cell_voltage_v,
            "voltage_window_v": f"{self.min_cell_voltage_v:.2f}V - {self.max_cell_voltage_v:.2f}V",
            "optimal_temp_range_c": f"{self.optimal_temp_min_c}°C - {self.optimal_temp_max_c}°C",
            "max_safe_temp_c": self.max_safe_temp_c,
            "recommended_max_c_rate": self.recommended_max_c_rate,
            "nominal_cycle_life": self.nominal_cycle_life,
            "description": self.description,
            "parameter_type": "Prototype Chemistry Parameters"
        }


CHEMISTRY_DATABASE: Dict[str, ChemistryProfile] = {
    "NMC_811": ChemistryProfile(
        name="NMC 811 (LiNi0.8Mn0.1Co0.1O2)",
        nominal_cell_voltage_v=3.65,
        min_cell_voltage_v=2.80,
        max_cell_voltage_v=4.20,
        optimal_temp_min_c=15.0,
        optimal_temp_max_c=35.0,
        max_safe_temp_c=55.0,
        recommended_max_c_rate=1.5,
        nominal_cycle_life=2000,
        thermal_runaway_onset_c=210.0,
        description="High energy density chemistry standard in modern long-range EV traction packs."
    ),
    "LFP": ChemistryProfile(
        name="LFP (LiFePO4)",
        nominal_cell_voltage_v=3.20,
        min_cell_voltage_v=2.50,
        max_cell_voltage_v=3.65,
        optimal_temp_min_c=10.0,
        optimal_temp_max_c=45.0,
        max_safe_temp_c=60.0,
        recommended_max_c_rate=2.0,
        nominal_cycle_life=4000,
        thermal_runaway_onset_c=270.0,
        description="Exceptional thermal stability, cobalt-free, long cycle life optimal for stationary ESS."
    ),
    "NCA": ChemistryProfile(
        name="NCA (LiNi0.8Co0.15Al0.05O2)",
        nominal_cell_voltage_v=3.60,
        min_cell_voltage_v=2.85,
        max_cell_voltage_v=4.20,
        optimal_temp_min_c=15.0,
        optimal_temp_max_c=35.0,
        max_safe_temp_c=55.0,
        recommended_max_c_rate=1.5,
        nominal_cycle_life=1800,
        thermal_runaway_onset_c=190.0,
        description="High power capability and energy density with strict thermal management requirements."
    )
}


@dataclass
class TopologyConfig:
    """Pack-level series/parallel topology architecture."""
    name: str
    series_count: int
    parallel_count: int = 1
    cell_rated_capacity_ah: float = 50.0
    architecture_class: str = "Standard Module"
    description: str = ""

    def calculate_pack_specs(self, chemistry: ChemistryProfile) -> Dict[str, Any]:
        """Calculates derived pack-level electrical limits."""
        v_nom = round(self.series_count * chemistry.nominal_cell_voltage_v, 1)
        v_min = round(self.series_count * chemistry.min_cell_voltage_v, 1)
        v_max = round(self.series_count * chemistry.max_cell_voltage_v, 1)
        cap_ah = round(self.parallel_count * self.cell_rated_capacity_ah, 1)
        energy_kwh = round((v_nom * cap_ah) / 1000.0, 3)
        max_cont_current_a = round(cap_ah * chemistry.recommended_max_c_rate, 1)
        max_power_kw = round((v_nom * max_cont_current_a) / 1000.0, 2)

        return {
            "topology_name": self.name,
            "architecture_class": self.architecture_class,
            "series_count": self.series_count,
            "parallel_count": self.parallel_count,
            "total_cells": self.series_count * self.parallel_count,
            "chemistry": chemistry.name,
            "pack_nominal_voltage_v": v_nom,
            "pack_voltage_range_v": f"{v_min}V - {v_max}V",
            "pack_rated_capacity_ah": cap_ah,
            "pack_rated_energy_kwh": energy_kwh,
            "max_continuous_current_a": max_cont_current_a,
            "max_continuous_power_kw": max_power_kw,
            "optimal_temp_range_c": f"{chemistry.optimal_temp_min_c}°C - {chemistry.optimal_temp_max_c}°C",
            "max_safe_temp_c": chemistry.max_safe_temp_c
        }


TOPOLOGY_DATABASE: Dict[str, TopologyConfig] = {
    "8S": TopologyConfig(
        name="8S1P Prototype Module",
        series_count=8,
        parallel_count=1,
        cell_rated_capacity_ah=50.0,
        architecture_class="24V/32V Low-Voltage Submodule",
        description="8-series sub-module for low-voltage testing and light energy storage."
    ),
    "16S": TopologyConfig(
        name="16S1P Telecom/Residential Rack",
        series_count=16,
        parallel_count=1,
        cell_rated_capacity_ah=50.0,
        architecture_class="48V/51V Telecom & Home UPS Rack",
        description="Standard 48V-class telecom base station and residential UPS backup battery."
    ),
    "96S": TopologyConfig(
        name="96S1P 400V-Class EV Pack",
        series_count=96,
        parallel_count=1,
        cell_rated_capacity_ah=50.0,
        architecture_class="400V Commercial EV Traction & C&I BESS",
        description="400V automotive traction pack repurposed for commercial solar peak shaving."
    ),
    "192S": TopologyConfig(
        name="192S1P 800V-Class High-Voltage ESS",
        series_count=192,
        parallel_count=1,
        cell_rated_capacity_ah=50.0,
        architecture_class="800V Utility-Scale High-Voltage Architecture",
        description="High-voltage architecture for grid-scale energy storage systems (BESS)."
    )
}
