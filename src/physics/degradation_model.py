"""
Physics-Informed Non-Linear Battery Degradation and Knee Model.
Formulates multi-stage degradation combining parabolic SEI film growth (t^0.5 / N^0.5)
with accelerated late-life exponential loss (exp(k * N)) past a configurable degradation knee point.
NOTE: Labeled as 'Physics-Informed Prototype Model Assumption'.
"""

from typing import Dict, List, Any, Optional
import math
import numpy as np


class NonLinearDegradationModel:
    """
    Simulates non-linear capacity fade and remaining useful life (RUL) trajectories.
    Formula: Q_loss(N) = a * N^0.5 + b * exp(k * max(0, N - N_knee))
    """

    def __init__(
        self,
        default_knee_soh_pct: float = 75.0,
        base_sei_rate: float = 0.0035,
        exponential_knee_rate: float = 0.0022
    ):
        self.default_knee_soh = default_knee_soh_pct
        self.base_sei_rate = base_sei_rate
        self.exp_rate = exponential_knee_rate

    def project_degradation(
        self,
        initial_soh_pct: float = 86.5,
        knee_soh_pct: Optional[float] = None,
        ambient_temp_c: float = 25.0,
        c_rate: float = 0.5,
        total_projected_cycles: int = 3000,
        step_cycles: int = 100
    ) -> Dict[str, Any]:
        """
        Projects multi-stage SOH fade curve under temperature and C-rate stress.
        """
        soh_0 = float(initial_soh_pct)
        knee_thresh = float(knee_soh_pct) if knee_soh_pct else self.default_knee_soh

        # 1. Stress Acceleration Factors
        # Thermal: Arrhenius-inspired acceleration above 25°C, cold plating stress below 15°C
        if ambient_temp_c >= 25.0:
            thermal_factor = 1.0 + ((ambient_temp_c - 25.0) / 15.0) * 0.45
        else:
            thermal_factor = 1.0 + ((25.0 - ambient_temp_c) / 20.0) * 0.30

        # C-rate overpotential and mechanical stress factor
        c_rate_factor = 1.0 + max(0.0, (c_rate - 0.5)) * 0.70
        composite_stress = thermal_factor * c_rate_factor

        # 2. Simulate cycle progression
        cycle_series = []
        soh_series = []
        rate_series = []

        current_soh = soh_0
        knee_reached_cycle = None
        eol_reached_cycle = None

        # Estimated cycles elapsed prior to second life
        initial_loss_pct = max(0.0, 100.0 - soh_0)
        equiv_prior_cycles = int((initial_loss_pct / (self.base_sei_rate * 100.0)) ** 2.0)

        for n in range(0, total_projected_cycles + 1, step_cycles):
            total_n = equiv_prior_cycles + n
            
            # Parabolic SEI loss component
            sei_loss = self.base_sei_rate * math.sqrt(total_n) * composite_stress * 100.0

            # Non-linear exponential loss past knee threshold
            exp_loss = 0.0
            if current_soh <= knee_thresh:
                if knee_reached_cycle is None:
                    knee_reached_cycle = n
                delta_n_past_knee = n - knee_reached_cycle
                exp_loss = math.exp(self.exp_rate * delta_n_past_knee * composite_stress) - 1.0

            computed_soh = max(40.0, min(100.0, 100.0 - (sei_loss + exp_loss)))
            current_soh = computed_soh

            if current_soh <= 60.0 and eol_reached_cycle is None:
                eol_reached_cycle = n

            # Local degradation rate (% SOH loss per 100 cycles)
            fade_rate_per_100 = 0.0
            if len(soh_series) > 0:
                fade_rate_per_100 = round(soh_series[-1] - computed_soh, 3)

            cycle_series.append(n)
            soh_series.append(round(computed_soh, 2))
            rate_series.append(fade_rate_per_100)

        # Cycles to knee and EOL
        cycles_to_knee = knee_reached_cycle if knee_reached_cycle is not None else "> 3,000 cycles"
        cycles_to_eol = eol_reached_cycle if eol_reached_cycle is not None else "> 3,000 cycles"

        return {
            "initial_soh_pct": soh_0,
            "knee_threshold_soh_pct": knee_thresh,
            "ambient_temp_c": ambient_temp_c,
            "c_rate": c_rate,
            "stress_multiplier": round(composite_stress, 2),
            "estimated_cycles_to_knee": cycles_to_knee,
            "estimated_cycles_to_eol_60pct": cycles_to_eol,
            "degradation_regime": "ACCELERATED_POST_KNEE" if current_soh < knee_thresh else "STABLE_PRE_KNEE",
            "curve_data": {
                "cycles": cycle_series,
                "projected_soh_pct": soh_series,
                "fade_rate_pct_per_100_cycles": rate_series
            },
            "scientific_disclaimer": (
                "The non-linear degradation knee model combines parabolic SEI growth with late-life exponential loss. "
                "The knee point (default 75% SOH) is a configurable prototype assumption, not a universal physical constant. "
                "Actual knee behavior depends on cell chemistry, manufacturing quality, and real-world cycling history."
            )
        }
