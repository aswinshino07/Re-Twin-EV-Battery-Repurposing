"""
Application Suitability & Second-Life Recommendation Engine.
Maps battery health, capacity, safety audit, and impedance state into
the 6-Tier Second-Life Decision Architecture with commercial justification.
"""

from typing import Tuple
from src.core.battery_state import ApplicationTier, SafetyStatus, BatteryPackSpec


class ApplicationRouter:
    def __init__(self, spec: BatteryPackSpec = None):
        self.spec = spec or BatteryPackSpec()

    def route_application(
        self,
        soh: float,
        remaining_capacity_ah: float,
        safety_status: SafetyStatus,
        rps: float,
        cell_imbalance_v: float = 0.005,
        temp_mean_c: float = 25.0
    ) -> Tuple[ApplicationTier, str]:
        """
        Evaluates battery state against 6-Tier Decision Matrix.
        Returns: (ApplicationTier, Decision_Rationale_String)
        """
        soh_val = float(soh)

        # 1. Safety Quarantine Hard Interlock
        if safety_status == SafetyStatus.QUARANTINE or temp_mean_c > 55.0 or cell_imbalance_v > 0.050:
            return (
                ApplicationTier.QUARANTINE,
                "SAFETY INTERLOCK TRIGGERED: Pack exhibits critical safety flags, thermal anomaly, or severe cell voltage imbalance. Immediate diagnostic isolation required."
            )

        # 2. Tier 1: High-Demand Grid & Frequency Regulation (SOH >= 90%, Cap >= 45Ah)
        if soh_val >= 0.90 and remaining_capacity_ah >= (0.90 * self.spec.rated_capacity_ah):
            return (
                ApplicationTier.TIER_1_GRID,
                f"TIER 1 MATCH: Exceptional health ({soh_val*100:.1f}% SOH, {remaining_capacity_ah:.1f} Ah). Suitable for high-stress dynamic cycling, grid peak shaving, and fast frequency regulation."
            )

        # 3. Tier 2: Solar & Commercial Storage (80% <= SOH < 90%)
        if soh_val >= 0.80:
            return (
                ApplicationTier.TIER_2_SOLAR,
                f"TIER 2 MATCH: Robust health ({soh_val*100:.1f}% SOH, {remaining_capacity_ah:.1f} Ah). Ideal for commercial & industrial solar energy storage, load shifting, and EV charging station buffer."
            )

        # 4. Tier 3: Home Backup & Telecom UPS (70% <= SOH < 80%)
        if soh_val >= 0.70:
            return (
                ApplicationTier.TIER_3_HOME_UPS,
                f"TIER 3 MATCH: Moderate health ({soh_val*100:.1f}% SOH, {remaining_capacity_ah:.1f} Ah). Perfectly suited for low-to-medium discharge duty cycles: residential home backup and telecom tower UPS."
            )

        # 5. Tier 4: Low-Power Off-Grid & Light Mobility (60% <= SOH < 70%)
        if soh_val >= 0.60:
            return (
                ApplicationTier.TIER_4_LOW_POWER,
                f"TIER 4 MATCH: Degraded health ({soh_val*100:.1f}% SOH, {remaining_capacity_ah:.1f} Ah). Capable for low-power off-grid solar streetlights, electric golf carts, or agricultural utility equipment."
            )

        # 6. Tier 5: Recycling & Material Recovery (SOH < 60%)
        return (
            ApplicationTier.TIER_5_RECYCLING,
            f"TIER 5 MATCH: End of second-life threshold ({soh_val*100:.1f}% SOH, {remaining_capacity_ah:.1f} Ah). Economic repurposing not viable. Recommended for direct material extraction and lithium/nickel recovery."
        )
