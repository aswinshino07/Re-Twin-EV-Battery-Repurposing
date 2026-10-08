"""
Usable Capacity, Energy & Remaining Useful Life (RUL) Estimation Module.
Models remaining usable charge and energy, and projects cycle life across
different second-life operational stress profiles (gentle stationary vs heavy cycling).
"""

from typing import Dict, Tuple
from src.core.battery_state import BatteryPackSpec


class CapacityRULCalculator:
    def __init__(self, spec: BatteryPackSpec = None):
        self.spec = spec or BatteryPackSpec()

    def calculate_usable_capacity_and_energy(self, soh: float) -> Tuple[float, float]:
        """
        Calculates remaining usable capacity (Ah) and usable energy (kWh).
        C_remaining = C_rated * SOH
        E_remaining = (V_nominal * C_remaining) / 1000
        """
        soh_norm = max(0.0, min(1.0, float(soh)))
        c_rem_ah = round(self.spec.rated_capacity_ah * soh_norm, 2)
        e_rem_kwh = round((self.spec.nominal_voltage_v * c_rem_ah) / 1000.0, 3)
        return c_rem_ah, e_rem_kwh

    def estimate_rul_cycles(self, soh: float, profile: str = "standard") -> Dict[str, int]:
        """
        Estimates Remaining Useful Life (RUL) in cycles until the second-life retirement cutoff (60% SOH).
        Provides projections for multiple operational duty cycles:
        - gentle: Low C-rate (0.2C), optimal 20-25°C (e.g. Solar Home UPS)
        - standard: Moderate C-rate (0.5C), 25-30°C (e.g. C&I peak shaving)
        - aggressive: High C-rate (1C), dynamic loads (e.g. Fast grid regulation)
        """
        soh_norm = float(soh)
        if soh_norm <= 0.60:
            return {"gentle_cycles": 0, "standard_cycles": 0, "aggressive_cycles": 0, "base_cycles": 0}

        delta_soh = soh_norm - 0.60  # Usable headroom down to 60%

        base_cycles = int(delta_soh * 7500)
        gentle_cycles = int(delta_soh * 9200)
        aggressive_cycles = int(delta_soh * 5400)

        return {
            "base_cycles": max(0, base_cycles),
            "gentle_cycles": max(0, gentle_cycles),
            "standard_cycles": max(0, base_cycles),
            "aggressive_cycles": max(0, aggressive_cycles)
        }
