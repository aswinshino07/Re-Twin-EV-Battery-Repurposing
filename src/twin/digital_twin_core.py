"""
Master Digital Twin Core Module.
Encapsulates the complete virtual battery state representation and orchestrates
telemetry ingestion, physics ECM simulation, AI inference, and second-life decisions.
"""

from typing import Dict, Any, Tuple
import pandas as pd

from src.core.battery_state import (
    BatteryPackSpec,
    BatteryStateSnapshot,
    ElectrochemicalState,
    HealthDecisionState,
    SafetyStatus,
    ApplicationTier,
    DataCategory
)
from src.physics.ecm_eis import VirtualBatteryECM
from src.ml.soh_predictor import SOHPredictor
from src.decision.safety_checker import SafetyChecker
from src.decision.capacity_rul import CapacityRULCalculator
from src.decision.repurposing_score import RepurposingScoreCalculator
from src.decision.application_router import ApplicationRouter
from src.decision.repurposing_engine import RepurposingEngine, BatteryCapability, RepurposingAssessment
from src.decision.battery_comparison import BatteryPackComparer
from src.twin.health_risk_engine import HealthRiskEngine


class DigitalTwinEngine:
    def __init__(self, spec: BatteryPackSpec = None, model_path: str = None):
        self.spec = spec or BatteryPackSpec()
        self.ecm = VirtualBatteryECM()
        self.soh_predictor = SOHPredictor(model_path)
        self.safety_checker = SafetyChecker(self.spec)
        self.capacity_calculator = CapacityRULCalculator(self.spec)
        self.rps_calculator = RepurposingScoreCalculator(spec=self.spec)
        self.app_router = ApplicationRouter(self.spec)
        self.repurposing_engine = RepurposingEngine(spec=self.spec)
        self.comparer = BatteryPackComparer()
        self.health_risk_engine = HealthRiskEngine(spec=self.spec)

    def compare_packs(self, evaluations: list) -> dict:
        """Compares multiple battery state evaluations side-by-side."""
        return self.comparer.compare_packs(evaluations)

    def evaluate_health_and_risk(self, telemetry_dict: Dict[str, Any], soh_override: float = None, history_frames: list = None) -> Dict[str, Any]:
        """
        Executes comprehensive Battery Diagnostic & Prognostic Intelligence evaluation.
        Consumes the Digital Twin state and returns structured Health & Risk workstation outputs.
        """
        twin_state = self.evaluate_state(telemetry_dict, soh_override=soh_override)
        return self.health_risk_engine.evaluate(telemetry_dict, twin_state, history_frames=history_frames)


    def evaluate_state(self, telemetry_dict: Dict[str, Any], soh_override: float = None) -> Dict[str, Any]:
        """
        Runs comprehensive Digital Twin evaluation on a single telemetry state dictionary.
        Returns a rich nested dictionary with all physical, electrochemical, and decision outputs.
        """
        # 1. SOH Estimation
        if soh_override is not None:
            soh = float(soh_override)
            soh_source = "User / Laboratory Override"
            attribution = {"override": soh}
        else:
            soh, attribution = self.soh_predictor.predict_single(telemetry_dict)
            soh_source = "Interpretable Linear Regression (CAN Features)"

        # 2. Electrochemical State (Simulated 1-RC ECM)
        soc_norm = float(telemetry_dict.get("SOC", 80.0) or 80.0) / 100.0
        temp_mean = float(telemetry_dict.get("TempMean", 25.0) or 25.0)
        eis_data = self.ecm.compute_impedance_spectrum(soc_norm=soc_norm, temp_c=temp_mean, soh_norm=soh)

        # 3. Capacity & Energy
        cap_ah, energy_kwh = self.capacity_calculator.calculate_usable_capacity_and_energy(soh)

        # 4. RUL Estimation
        rul_dict = self.capacity_calculator.estimate_rul_cycles(soh)

        # 5. Safety Audit
        safety_status, alarms = self.safety_checker.evaluate_safety(telemetry_dict)

        # 6. Repurposing Score (RPS)
        cell_imb_v = float(telemetry_dict.get("CellVoltageImbalance", 0.005) or 0.005)
        rps, rps_breakdown = self.rps_calculator.calculate_score(
            soh=soh,
            remaining_capacity_ah=cap_ah,
            safety_status=safety_status,
            cell_imbalance_v=cell_imb_v,
            temp_mean_c=temp_mean
        )

        # 7. 6-Tier Second Life Recommendation
        rec_tier, rationale = self.app_router.route_application(
            soh=soh,
            remaining_capacity_ah=cap_ah,
            safety_status=safety_status,
            rps=rps,
            cell_imbalance_v=cell_imb_v,
            temp_mean_c=temp_mean
        )

        # SOH Grade
        if soh >= 0.90:
            soh_grade = "Grade A+ (Pristine / Utility Grade)"
        elif soh >= 0.80:
            soh_grade = "Grade A (Good / Commercial Grade)"
        elif soh >= 0.70:
            soh_grade = "Grade B (Moderate / Residential Grade)"
        elif soh >= 0.60:
            soh_grade = "Grade C (Degraded / Low-Duty Grade)"
        else:
            soh_grade = "Grade D (End-of-Life / Recycling)"

        # Stress Factor Breakdown (0-100% Index)
        stress_factors = {
            "thermal_stress": round(min(100.0, max(0.0, (abs(temp_mean - 25.0) / 25.0) * 100.0)), 1),
            "c_rate_stress": round(min(100.0, max(0.0, (abs(float(telemetry_dict.get("PackCurrent", 0) or 0)) / self.spec.rated_capacity_ah) * 50.0)), 1),
            "cell_imbalance_stress": round(min(100.0, max(0.0, (abs(cell_imb_v) * 1000.0 / 30.0) * 100.0)), 1),
            "ohmic_rise_stress": round(min(100.0, max(0.0, ((eis_data["r0_ohm"] - 0.020) / 0.025) * 100.0)), 1),
            "depth_of_discharge_stress": round(min(100.0, max(0.0, 100.0 - (soc_norm * 100.0))), 1)
        }

        # Packaged Digital Twin Snapshot
        return {
            "timestamp": telemetry_dict.get("timestamp", 0.0),
            "pack_id": self.spec.pack_id,
            "telemetry": {
                "voltage_v": telemetry_dict.get("PackVoltage", 32.0),
                "current_a": telemetry_dict.get("PackCurrent", 0.0),
                "power_w": telemetry_dict.get("PackPower_W", 0.0),
                "soc_pct": round(soc_norm * 100.0, 1),
                "temp_mean_c": temp_mean,
                "cell_imbalance_mv": round(cell_imb_v * 1000.0, 1),
                "throughput_ah": telemetry_dict.get("Throughput_Ah", 0.0),
            },
            "electrochemical_eis": {
                "r0_mohm": round(eis_data["r0_ohm"] * 1000.0, 3),
                "rct_mohm": round(eis_data["rct_ohm"] * 1000.0, 3),
                "cdl_f": eis_data["cdl_farad"],
                "z_lowfreq_mohm": round(eis_data["z_lowfreq_ohm"] * 1000.0, 3),
                "phase_lowfreq_deg": eis_data["phase_lowfreq_deg"],
                "is_simulated": True,
                "data_category": DataCategory.SIMULATED_EIS.value,
                "frequency_hz": eis_data["frequency_hz"],
                "z_real_ohm": eis_data["z_real_ohm"],
                "z_imag_ohm": eis_data["z_imag_ohm"],
                "magnitude_ohm": eis_data["magnitude_ohm"],
                "phase_deg": eis_data["phase_deg"]
            },
            "health_assessment": {
                "soh": round(soh, 4),
                "soh_pct": round(soh * 100.0, 2),
                "soh_grade": soh_grade,
                "soh_source": soh_source,
                "feature_attribution": attribution,
                "remaining_capacity_ah": cap_ah,
                "remaining_energy_kwh": energy_kwh,
                "rated_capacity_ah": self.spec.rated_capacity_ah,
                "rated_energy_kwh": self.spec.rated_energy_kwh,
                "capacity_retention_pct": round((cap_ah / self.spec.rated_capacity_ah) * 100.0, 1),
                "estimated_rul_cycles": rul_dict["base_cycles"],
                "rul_profiles": rul_dict,
                "stress_factors": stress_factors
            },
            "safety_audit": {
                "status": safety_status.value,
                "is_safe": safety_status != SafetyStatus.QUARANTINE,
                "active_alarms": alarms
            },
            "decision": {
                "repurposing_score_rps": rps,
                "rps_breakdown": rps_breakdown,
                "recommended_tier": rec_tier.value,
                "rationale": rationale,
                "suitable_for_second_life": rec_tier != ApplicationTier.QUARANTINE and rec_tier != ApplicationTier.TIER_5_RECYCLING
            }
        }

    def evaluate_repurposing(self, telemetry_dict: Dict[str, Any], soh_override: float = None) -> RepurposingAssessment:
        """
        Executes the comprehensive RE-TWIN Repurposing Engine evaluation.
        Compares battery capabilities against all application requirements,
        enforces safety overrides, and returns the full explainable RepurposingAssessment.
        """
        state = self.evaluate_state(telemetry_dict, soh_override=soh_override)
        capability = BatteryCapability(
            soh=state["health_assessment"]["soh"],
            remaining_capacity_ah=state["health_assessment"]["remaining_capacity_ah"],
            usable_energy_kwh=state["health_assessment"]["remaining_energy_kwh"],
            temperature_c=state["telemetry"]["temp_mean_c"],
            cell_imbalance_v=state["telemetry"]["cell_imbalance_mv"] / 1000.0,
            bms_fault_active=not state["safety_audit"]["is_safe"],
            bms_fault_details=state["safety_audit"]["active_alarms"],
            rul_cycles=state["health_assessment"]["estimated_rul_cycles"],
            safety_status=SafetyStatus(state["safety_audit"]["status"]),
            internal_resistance_mohm=state["electrochemical_eis"]["r0_mohm"],
            nominal_voltage_v=self.spec.nominal_voltage_v,
            rated_capacity_ah=self.spec.rated_capacity_ah,
            rated_energy_kwh=self.spec.rated_energy_kwh
        )
        return self.repurposing_engine.evaluate_battery(capability)
