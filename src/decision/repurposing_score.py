"""
Multi-Criteria Repurposing Score (RPS) Module.
Calculates an explainable 0-100 score weighing SOH, usable capacity,
projected RUL, safety audit status, and cell voltage balance.
"""

from typing import Dict, Tuple
from src.core.battery_state import SafetyStatus, BatteryPackSpec

DEFAULT_WEIGHTS = {
    "soh": 0.30,
    "capacity": 0.25,
    "rul": 0.15,
    "safety": 0.20,
    "cell_balance": 0.10
}


class RepurposingScoreCalculator:
    def __init__(self, weights: Dict[str, float] = None, spec: BatteryPackSpec = None):
        self.weights = weights or DEFAULT_WEIGHTS
        self.spec = spec or BatteryPackSpec()

    def calculate_score(
        self,
        soh: float,
        remaining_capacity_ah: float,
        safety_status: SafetyStatus,
        cell_imbalance_v: float = 0.005,
        temp_mean_c: float = 25.0,
        usable_energy_kwh: float = None
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculates the composite Repurposing Score (RPS) out of 100
        and provides full sub-score breakdown for radar charts & explainability.
        """
        soh_norm = float(soh)

        # 1. SOH Sub-score (0-100) scaled from 0.50 (degraded) to 1.0 (pristine)
        soh_sub = max(0.0, min(100.0, (soh_norm - 0.50) / 0.50 * 100.0))

        # 2. Capacity Sub-score (0-100)
        cap_ratio = remaining_capacity_ah / self.spec.rated_capacity_ah if self.spec.rated_capacity_ah > 0 else 0
        cap_sub = max(0.0, min(100.0, cap_ratio * 100.0))

        # 3. Energy Sub-score (0-100)
        if usable_energy_kwh is not None:
            energy_ratio = usable_energy_kwh / self.spec.rated_energy_kwh if self.spec.rated_energy_kwh > 0 else 0
            energy_sub = max(0.0, min(100.0, energy_ratio * 100.0))
        else:
            energy_sub = cap_sub

        # 4. RUL Sub-score (0-100)
        rul_sub = max(0.0, min(100.0, (soh_norm - 0.60) / 0.35 * 100.0))

        # 5. Safety Sub-score (0 or 100)
        if safety_status == SafetyStatus.QUARANTINE or temp_mean_c > 55.0 or cell_imbalance_v > 0.050:
            safety_sub = 0.0
        elif safety_status == SafetyStatus.WARNING:
            safety_sub = 65.0
        else:
            safety_sub = 100.0

        # 6. Cell Balance Sub-score (0-100) - Normal < 15 mV, heavily penalized towards 30+ mV
        imb_mv = abs(float(cell_imbalance_v)) * 1000.0
        balance_sub = max(0.0, min(100.0, 100.0 - (imb_mv / 25.0 * 100.0)))

        # Composite score
        if "energy" in self.weights:
            rps = (
                self.weights.get("soh", 0.25) * soh_sub +
                self.weights.get("capacity", 0.20) * cap_sub +
                self.weights.get("energy", 0.15) * energy_sub +
                self.weights.get("rul", 0.10) * rul_sub +
                self.weights.get("safety", 0.20) * safety_sub +
                self.weights.get("cell_balance", 0.10) * balance_sub
            )
        else:
            rps = (
                self.weights.get("soh", 0.30) * soh_sub +
                self.weights.get("capacity", 0.25) * cap_sub +
                self.weights.get("rul", 0.15) * rul_sub +
                self.weights.get("safety", 0.20) * safety_sub +
                self.weights.get("cell_balance", 0.10) * balance_sub
            )

        breakdown = {
            "soh_subscore": round(soh_sub, 1),
            "capacity_subscore": round(cap_sub, 1),
            "energy_subscore": round(energy_sub, 1),
            "rul_subscore": round(rul_sub, 1),
            "safety_subscore": round(safety_sub, 1),
            "balance_subscore": round(balance_sub, 1),
            "total_rps": round(float(rps), 1)
        }

        return round(float(rps), 1), breakdown
