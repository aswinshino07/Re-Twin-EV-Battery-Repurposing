"""
Unit Tests for RE-TWIN Repurposing Decision & Application Matching Engine.

Validates:
1. Healthy battery second-life suitability & solar match
2. Low SOH battery retirement & recycling recommendation
3. High cell imbalance detection & safety interlock
4. Over-temperature condition safety interlock
5. Critical BMS fault override (safety interlock overrides 95% SOH)
6. Insufficient capacity / usable energy rejection with explainable reasons
7. Suitable solar battery full multi-criteria pass
8. Unsuitable high-power application power failure detection
9. Configurable scoring weights and normalization
10. Custom application profile evaluation and dictionary serialization
"""

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.battery_state import SafetyStatus, ApplicationTier, BatteryPackSpec, SuitabilityCategory
from src.decision.repurposing_engine import (
    RepurposingEngine,
    BatteryCapability,
    RepurposingWeights,
    ApplicationRequirement,
    DEFAULT_APPLICATION_PROFILES,
    SuitabilityCategory
)
from src.twin.digital_twin_core import DigitalTwinEngine


class TestRepurposingEngine(unittest.TestCase):
    def setUp(self):
        self.spec = BatteryPackSpec(
            nominal_voltage_v=32.0,
            rated_capacity_ah=50.0,
            rated_energy_kwh=1.60,
            max_safe_temp_c=55.0,
            max_cell_imbalance_v=0.050
        )
        self.engine = RepurposingEngine(spec=self.spec)

    def test_healthy_battery(self):
        """
        Healthy Battery: SOH 92%, 46 Ah, 1.47 kWh, 25°C, 5 mV balance, 0 faults.
        Should recommend Solar Energy Storage with SUITABLE status and high RPS.
        """
        cap = BatteryCapability(
            soh=0.92,
            remaining_capacity_ah=46.0,
            usable_energy_kwh=1.472,
            available_power_kw=2.2,
            temperature_c=25.0,
            cell_imbalance_v=0.005,
            bms_fault_active=False,
            rul_cycles=2400,
            safety_status=SafetyStatus.NORMAL
        )

        assessment = self.engine.evaluate_battery(cap)

        self.assertTrue(assessment.is_suitable_for_second_life)
        self.assertFalse(assessment.safety_override_triggered)
        self.assertEqual(assessment.suitability_category, SuitabilityCategory.SUITABLE)
        self.assertEqual(assessment.recommended_application, "Solar Energy Storage")
        self.assertGreaterEqual(assessment.repurposing_score, 80.0)
        self.assertTrue(len(assessment.reasons) > 0)
        self.assertIn("Solar Energy Storage", assessment.application_evaluations)
        solar_eval = assessment.application_evaluations["Solar Energy Storage"]
        self.assertEqual(solar_eval.suitability_category, SuitabilityCategory.SUITABLE)
        self.assertEqual(len(solar_eval.failed_requirements), 0)

    def test_low_soh_battery(self):
        """
        Low SOH Battery: SOH 52%, 26 Ah, 0.83 kWh.
        Should recommend Recycling/Material Recovery, failing stationary second-life requirements.
        """
        cap = BatteryCapability(
            soh=0.52,
            remaining_capacity_ah=26.0,
            usable_energy_kwh=0.832,
            available_power_kw=1.0,
            temperature_c=24.0,
            cell_imbalance_v=0.012,
            bms_fault_active=False,
            rul_cycles=0,
            safety_status=SafetyStatus.NORMAL
        )

        assessment = self.engine.evaluate_battery(cap)

        self.assertFalse(assessment.is_suitable_for_second_life)
        self.assertEqual(assessment.recommended_application, "Recycling/Material Recovery")
        self.assertIn("52.0%", assessment.reasons[0])
        # Solar, UPS, Telecom, Low-Power should all be NOT SUITABLE
        self.assertEqual(
            assessment.application_evaluations["Solar Energy Storage"].suitability_category,
            SuitabilityCategory.NOT_SUITABLE
        )
        self.assertEqual(
            assessment.application_evaluations["Low-Power Stationary Storage"].suitability_category,
            SuitabilityCategory.NOT_SUITABLE
        )

    def test_high_cell_imbalance(self):
        """
        High Cell Imbalance: SOH 88%, but cell imbalance is 55 mV (> 50 mV critical limit).
        Safety Interlock MUST trigger INSPECTION REQUIRED.
        """
        cap = BatteryCapability(
            soh=0.88,
            remaining_capacity_ah=44.0,
            usable_energy_kwh=1.408,
            available_power_kw=2.1,
            temperature_c=26.0,
            cell_imbalance_v=0.055, # 55 mV > 50 mV limit
            bms_fault_active=False,
            rul_cycles=2100,
            safety_status=SafetyStatus.NORMAL
        )

        assessment = self.engine.evaluate_battery(cap)

        self.assertTrue(assessment.safety_override_triggered)
        self.assertEqual(assessment.suitability_category, SuitabilityCategory.INSPECTION_REQUIRED)
        self.assertIn("Quarantine", assessment.recommended_tier)
        self.assertFalse(assessment.is_suitable_for_second_life)
        self.assertTrue(any("Cell Voltage Imbalance" in r for r in assessment.reasons))

    def test_over_temperature_condition(self):
        """
        Over-Temperature Condition: SOH 90%, but Temp = 58°C (> 55°C max safe limit).
        Safety Interlock MUST trigger INSPECTION REQUIRED regardless of 90% SOH.
        """
        cap = BatteryCapability(
            soh=0.90,
            remaining_capacity_ah=45.0,
            usable_energy_kwh=1.44,
            available_power_kw=2.1,
            temperature_c=58.0, # 58°C > 55°C safe limit
            cell_imbalance_v=0.008,
            bms_fault_active=False,
            rul_cycles=2250,
            safety_status=SafetyStatus.NORMAL
        )

        assessment = self.engine.evaluate_battery(cap)

        self.assertTrue(assessment.safety_override_triggered)
        self.assertEqual(assessment.suitability_category, SuitabilityCategory.INSPECTION_REQUIRED)
        self.assertFalse(assessment.is_suitable_for_second_life)
        self.assertTrue(any("Over-Temperature" in r for r in assessment.reasons))

    def test_critical_bms_fault_overrides_high_soh(self):
        """
        IMPORTANT SAFETY RULE TEST:
        Battery with SOH = 95% (Grade A+) has an active critical BMS fault flag.
        The Safety Interlock MUST strictly override the 95% SOH recommendation
        and set Recommendation = INSPECTION REQUIRED.
        """
        cap = BatteryCapability(
            soh=0.95, # 95% SOH pristine
            remaining_capacity_ah=47.5,
            usable_energy_kwh=1.52,
            available_power_kw=2.3,
            temperature_c=25.0,
            cell_imbalance_v=0.004,
            bms_fault_active=True,
            bms_fault_details=["OverTemp", "OverVoltage"],
            rul_cycles=2600,
            safety_status=SafetyStatus.QUARANTINE
        )

        assessment = self.engine.evaluate_battery(cap)

        # Must trigger safety override
        self.assertTrue(assessment.safety_override_triggered)
        self.assertEqual(assessment.suitability_category, SuitabilityCategory.INSPECTION_REQUIRED)
        self.assertEqual(assessment.recommended_tier, ApplicationTier.QUARANTINE.value)
        self.assertFalse(assessment.is_suitable_for_second_life)

        # Ensure safety rationale explicitly mentions overriding the high SOH
        joined_reasons = " ".join(assessment.reasons)
        self.assertIn("95.0%", joined_reasons)
        self.assertIn("overrides AI health score", joined_reasons)
        self.assertIn("BMS Hardware Fault", joined_reasons)

    def test_insufficient_capacity_rejection(self):
        """
        Insufficient Usable Energy / Capacity:
        SOH 82%, but usable energy is 0.90 kWh (below Solar requirement 1.20 kWh and Home/UPS 1.00 kWh).
        Solar and Home/UPS must fail with explicit reasons; Telecom Backup (req 0.80 kWh) should be selected.
        """
        cap = BatteryCapability(
            soh=0.82,
            remaining_capacity_ah=32.0, # Deliberately low capacity pack
            usable_energy_kwh=0.90,     # 0.90 kWh < 1.20 kWh (Solar) and < 1.00 kWh (Home/UPS)
            available_power_kw=1.5,
            temperature_c=25.0,
            cell_imbalance_v=0.008,
            bms_fault_active=False,
            rul_cycles=1600,
            safety_status=SafetyStatus.NORMAL
        )

        assessment = self.engine.evaluate_battery(cap)

        self.assertTrue(assessment.is_suitable_for_second_life)
        # Solar should fail energy requirement
        solar_eval = assessment.application_evaluations["Solar Energy Storage"]
        self.assertEqual(solar_eval.suitability_category, SuitabilityCategory.NOT_SUITABLE)
        self.assertTrue(any("Usable energy" in f and "0.90 kWh" in f for f in solar_eval.failed_requirements))

        # Home/UPS should fail energy requirement
        home_eval = assessment.application_evaluations["Home/UPS Backup"]
        self.assertEqual(home_eval.suitability_category, SuitabilityCategory.NOT_SUITABLE)

        # Telecom Backup (requires 0.80 kWh) should match
        self.assertEqual(assessment.recommended_application, "Telecom Backup")
        self.assertIn("Telecom", assessment.recommended_tier)

    def test_suitable_solar_battery(self):
        """
        Suitable Solar Battery: Meets all Solar Energy Storage requirements.
        SOH 85%, 1.36 kWh usable energy, 2.0 kW power, 10 mV imbalance, 25°C.
        """
        cap = BatteryCapability(
            soh=0.85,
            remaining_capacity_ah=42.5,
            usable_energy_kwh=1.36,
            available_power_kw=2.0,
            temperature_c=25.0,
            cell_imbalance_v=0.010,
            bms_fault_active=False,
            rul_cycles=1850,
            safety_status=SafetyStatus.NORMAL
        )

        assessment = self.engine.evaluate_battery(cap)

        self.assertTrue(assessment.is_suitable_for_second_life)
        self.assertEqual(assessment.recommended_application, "Solar Energy Storage")
        self.assertEqual(assessment.suitability_category, SuitabilityCategory.SUITABLE)

        solar_eval = assessment.application_evaluations["Solar Energy Storage"]
        self.assertEqual(solar_eval.suitability_category, SuitabilityCategory.SUITABLE)
        self.assertTrue(len(solar_eval.passed_requirements) >= 6)
        self.assertEqual(len(solar_eval.failed_requirements), 0)

    def test_unsuitable_high_power_application(self):
        """
        Unsuitable High-Power Application:
        Battery has restricted power capability (0.4 kW) evaluated against high-power demand profile (1.5 kW).
        Should fail power requirement with explicit failed message.
        """
        cap = BatteryCapability(
            soh=0.84,
            remaining_capacity_ah=42.0,
            usable_energy_kwh=1.344,
            available_power_kw=0.40, # Deficient power capability (0.4 kW < 1.5 kW)
            temperature_c=25.0,
            cell_imbalance_v=0.007,
            bms_fault_active=False,
            rul_cycles=1800,
            safety_status=SafetyStatus.NORMAL
        )

        solar_eval = self.engine.evaluate_application(cap, DEFAULT_APPLICATION_PROFILES["Solar Energy Storage"])

        self.assertEqual(solar_eval.suitability_category, SuitabilityCategory.NOT_SUITABLE)
        self.assertTrue(any("Available power" in f and "0.40 kW" in f for f in solar_eval.failed_requirements))

    def test_configurable_weights_and_normalization(self):
        """
        Weights Configuration:
        Custom unnormalized weights should automatically normalize to 1.0 and adjust composite score.
        """
        custom_weights = RepurposingWeights(
            soh=50.0,
            capacity=20.0,
            energy=10.0,
            safety=10.0,
            cell_balance=5.0,
            rul=5.0
        )
        self.assertAlmostEqual(
            custom_weights.soh + custom_weights.capacity + custom_weights.energy +
            custom_weights.safety + custom_weights.cell_balance + custom_weights.rul,
            1.0,
            places=5
        )
        self.assertAlmostEqual(custom_weights.soh, 0.50, places=3)

        custom_engine = RepurposingEngine(weights=custom_weights, spec=self.spec)
        cap = BatteryCapability(
            soh=0.90,
            remaining_capacity_ah=45.0,
            usable_energy_kwh=1.44,
            available_power_kw=2.0,
            temperature_c=25.0,
            cell_imbalance_v=0.005,
            bms_fault_active=False,
            rul_cycles=2200,
            safety_status=SafetyStatus.NORMAL
        )
        score, breakdown = custom_engine.calculate_repurposing_score(cap)
        self.assertIsInstance(score, float)
        self.assertIn("energy_subscore", breakdown)
        self.assertIn("total_rps", breakdown)

    def test_custom_application_profile(self):
        """
        Custom Application Profile:
        User adds a strict custom profile (e.g. EV Fast-Charging Buffer).
        """
        custom_profiles = dict(DEFAULT_APPLICATION_PROFILES)
        custom_profiles["EV Fast-Charging Buffer"] = ApplicationRequirement(
            name="EV Fast-Charging Buffer",
            min_soh=0.92,
            min_usable_energy_kwh=1.50,
            required_power_kw=3.0,
            max_acceptable_risk=SafetyStatus.NORMAL,
            min_temp_c=15.0,
            max_temp_c=40.0,
            max_cell_imbalance_v=0.010,
            min_rul_cycles=2500,
            priority=0, # Highest priority
            description="Ultra-fast peak power buffer for DC fast chargers."
        )

        engine = RepurposingEngine(application_profiles=custom_profiles, spec=self.spec)

        # 88% SOH pack cannot meet EV Fast-Charging Buffer (needs 92%), falls back to Solar
        cap = BatteryCapability(
            soh=0.88,
            remaining_capacity_ah=44.0,
            usable_energy_kwh=1.408,
            available_power_kw=2.1,
            temperature_c=25.0,
            cell_imbalance_v=0.006,
            bms_fault_active=False,
            rul_cycles=2100,
            safety_status=SafetyStatus.NORMAL
        )

        assessment = engine.evaluate_battery(cap)
        self.assertEqual(assessment.recommended_application, "Solar Energy Storage")
        self.assertIn("EV Fast-Charging Buffer", assessment.unsuitable_reasons)
        self.assertTrue(any("SOH" in r for r in assessment.unsuitable_reasons["EV Fast-Charging Buffer"]))

    def test_serialization_and_to_dict(self):
        """
        Serialization Test:
        Ensures RepurposingAssessment.to_dict() produces a full, serializable payload for web dashboards.
        """
        cap = BatteryCapability(
            soh=0.86,
            remaining_capacity_ah=43.0,
            usable_energy_kwh=1.376,
            available_power_kw=2.0,
            temperature_c=25.0,
            cell_imbalance_v=0.006,
            bms_fault_active=False,
            rul_cycles=1950,
            safety_status=SafetyStatus.NORMAL
        )
        assessment = self.engine.evaluate_battery(cap)
        data = assessment.to_dict()

        self.assertIn("repurposing_score", data)
        self.assertIn("score_breakdown", data)
        self.assertIn("suitability_category", data)
        self.assertIn("recommended_application", data)
        self.assertIn("reasons", data)
        self.assertIn("unsuitable_reasons", data)
        self.assertIn("application_evaluations", data)
        self.assertIn("battery_capability", data)
        self.assertEqual(data["recommended_application"], "Solar Energy Storage")

    def test_digital_twin_integration(self):
        """
        Integration with DigitalTwinEngine:
        Verifies DigitalTwinEngine.evaluate_repurposing() successfully runs.
        """
        twin = DigitalTwinEngine(spec=self.spec)
        telemetry = {
            "PackVoltage": 32.2,
            "PackCurrent": 10.0,
            "PackPower_W": 322.0,
            "SOC": 85.0,
            "TempMean": 26.0,
            "CellVoltageImbalance": 0.006,
            "Throughput_Ah": 100.0,
            "Fault_OverVoltage": 0,
            "Fault_UnderVoltage": 0,
            "Fault_OverTemp": 0,
            "Fault_UnderTemp": 0,
            "Fault_OverCurrent": 0
        }
        assessment = twin.evaluate_repurposing(telemetry, soh_override=0.87)
        self.assertEqual(assessment.recommended_application, "Solar Energy Storage")
        self.assertTrue(assessment.is_suitable_for_second_life)

    def test_what_if_battery_simulator_healthy(self):
        """
        Interactive Simulator Test: Healthy battery (SOH 86%, Temp 28°C, 8mV imbalance).
        Recalculates Solar Energy Storage, Low Risk, and RPS ~90.
        """
        from src.twin.what_if_sim import WhatIfSimulator
        sim = WhatIfSimulator()
        res = sim.simulate_battery_parameters(
            soh=0.86,
            soc=80.0,
            rated_capacity_ah=50.0,
            temperature_c=28.0,
            cell_imbalance_v=0.008,
            safety_status="NORMAL"
        )
        self.assertEqual(res["simulation_label"], "WHAT-IF SIMULATION")
        self.assertFalse(res["original_dataset_modified"])
        self.assertEqual(res["decision"]["recommended_application"], "Solar Energy Storage")
        self.assertEqual(res["safety_risk"]["risk_level"], "LOW RISK / SAFE")
        self.assertGreaterEqual(res["decision"]["repurposing_score"], 80.0)
        self.assertAlmostEqual(res["health_status"]["usable_energy_kwh"], 1.376, places=2)

    def test_what_if_battery_simulator_degraded(self):
        """
        Interactive Simulator Test: Degraded battery (SOH 68%, Temp 43°C, 35mV imbalance).
        Recalculates updated lower tier and elevated risk warning.
        """
        from src.twin.what_if_sim import WhatIfSimulator
        sim = WhatIfSimulator()
        res = sim.simulate_battery_parameters(
            soh=0.68,
            soc=65.0,
            rated_capacity_ah=50.0,
            temperature_c=43.0,
            cell_imbalance_v=0.035,
            safety_status="WARNING"
        )
        self.assertEqual(res["simulation_label"], "WHAT-IF SIMULATION")
        self.assertFalse(res["original_dataset_modified"])
        self.assertEqual(res["decision"]["recommended_application"], "Low-Power Stationary Storage")
        self.assertEqual(res["safety_risk"]["safety_status"], "WARNING")
        self.assertIn("MODERATE", res["safety_risk"]["risk_level"])

    def test_what_if_battery_simulator_safety_override(self):
        """
        Interactive Simulator Test: 95% SOH battery with active BMS fault.
        Recalculates Safety Interlock override to Quarantine / Inspection Required.
        """
        from src.twin.what_if_sim import WhatIfSimulator
        sim = WhatIfSimulator()
        res = sim.simulate_battery_parameters(
            soh=0.95,
            soc=90.0,
            rated_capacity_ah=50.0,
            temperature_c=25.0,
            cell_imbalance_v=0.005,
            fault_flags={"Fault_OverTemp": True}
        )
        self.assertTrue(res["safety_risk"]["safety_override_triggered"])
        self.assertEqual(res["safety_risk"]["risk_level"], "CRITICAL SAFETY INTERLOCK")
        self.assertEqual(res["decision"]["suitability_category"], "INSPECTION REQUIRED")
        self.assertIn("Quarantine", res["decision"]["recommended_tier"])

    def test_battery_pack_comparer(self):
        """
        Tests multi-pack comparison engine functionality.
        """
        from src.decision.battery_comparison import BatteryPackComparer
        twin = DigitalTwinEngine(spec=self.spec)

        eval1 = twin.evaluate_state({"PackVoltage": 32.1, "PackCurrent": 10.0, "SOC": 85.0, "TempMean": 25.0}, soh_override=0.92)
        eval2 = twin.evaluate_state({"PackVoltage": 30.0, "PackCurrent": 12.0, "SOC": 70.0, "TempMean": 32.0}, soh_override=0.78)
        eval1["pack_id"] = "PACK-A"
        eval2["pack_id"] = "PACK-B"

        comparer = BatteryPackComparer()
        res = comparer.compare_packs([eval1, eval2])

        self.assertEqual(res["pack_count"], 2)
        self.assertEqual(res["benchmark_summary"]["top_performing_pack"], "PACK-A")
        self.assertGreater(res["ranked_packs"][0]["repurposing_score_rps"], res["ranked_packs"][1]["repurposing_score_rps"])


if __name__ == "__main__":
    unittest.main()
