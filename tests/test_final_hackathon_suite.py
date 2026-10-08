"""
Comprehensive Automated Test Suite for RE-TWIN Final Hackathon Scenarios.
Tests 13 critical engineering, safety, ML, and decision scenarios:
  TEST 1: Healthy battery
  TEST 2: Low SOH (<60%)
  TEST 3: High cell imbalance (>50 mV)
  TEST 4: High temperature (>55°C)
  TEST 5: Rapid temperature increase (dT/dt >= 1.0°C/min)
  TEST 6: Critical BMS fault (OverTemp, OverVoltage, etc.)
  TEST 7: Insufficient capacity for selected application
  TEST 8: Different chemistry (LFP, NCA, NMC 811)
  TEST 9: Different topology (8S, 16S, 96S, 192S)
  TEST 10: What-If degradation scenario (Non-linear knee model)
  TEST 11: Missing/malformed CAN data (Graceful decoding)
  TEST 12: Missing SOH (Safe default imputation)
  TEST 13: Missing capacity (Automatic Ah & kWh derivation)
"""

import unittest
import numpy as np
import pandas as pd
from pathlib import Path

from src.core.battery_state import BatteryPackSpec, SafetyStatus, ApplicationTier
from src.core.chemistry_topology import CHEMISTRY_DATABASE, TOPOLOGY_DATABASE
from src.core.safety_monitor import AdvancedSafetyMonitor
from src.physics.degradation_model import NonLinearDegradationModel
from src.decision.repurposing_engine import RepurposingEngine, BatteryCapability
from src.twin.digital_twin_core import DigitalTwinEngine
from src.twin.what_if_sim import WhatIfSimulator
from src.core.decoder import CANDecoder


class TestFinalHackathonSuite(unittest.TestCase):

    def setUp(self):
        self.spec = BatteryPackSpec()
        self.twin = DigitalTwinEngine(self.spec)
        self.what_if = WhatIfSimulator(self.twin)
        self.repurposing = RepurposingEngine(self.spec)
        self.safety_mon = AdvancedSafetyMonitor()
        self.degradation = NonLinearDegradationModel()

    # TEST 1: Healthy battery
    def test_01_healthy_battery(self):
        res = self.what_if.simulate_battery_parameters(
            soh=0.88, soc=80.0, temperature_c=25.0, cell_imbalance_v=0.005,
            safety_status="NORMAL"
        )
        self.assertEqual(res["safety_risk"]["safety_status"], "NORMAL")
        self.assertTrue(res["decision"]["is_suitable_for_second_life"])
        self.assertGreater(res["decision"]["repurposing_score"], 80.0)
        self.assertIn("Solar", res["decision"]["recommended_application"])

    # TEST 2: Low SOH (<60%)
    def test_02_low_soh(self):
        res = self.what_if.simulate_battery_parameters(
            soh=0.52, temperature_c=25.0, cell_imbalance_v=0.010, safety_status="NORMAL"
        )
        self.assertIn("Recycling", res["decision"]["recommended_tier"])
        self.assertFalse(res["decision"]["is_suitable_for_second_life"])

    # TEST 3: High cell imbalance (>50 mV)
    def test_03_high_cell_imbalance(self):
        res = self.what_if.simulate_battery_parameters(
            soh=0.88, cell_imbalance_v=0.055, temperature_c=25.0
        )
        self.assertEqual(res["safety_risk"]["safety_status"], "QUARANTINE")
        self.assertTrue(res["safety_risk"]["safety_override_triggered"])

    # TEST 4: High temperature (>55°C)
    def test_04_high_temperature(self):
        res = self.what_if.simulate_battery_parameters(
            soh=0.88, temperature_c=58.0
        )
        self.assertEqual(res["safety_risk"]["safety_status"], "QUARANTINE")
        self.assertIn("Quarantine", res["decision"]["recommended_tier"])

    # TEST 5: Rapid temperature increase (dT/dt >= 1.0°C/min)
    def test_05_rapid_temperature_increase(self):
        res = self.what_if.simulate_battery_parameters(
            soh=0.88, temperature_c=35.0, dt_dt_c_per_min=1.25
        )
        self.assertEqual(res["safety_risk"]["safety_status"], "QUARANTINE")
        self.assertTrue(res["safety_risk"]["thermal_rate_critical"])

    # TEST 6: Critical BMS fault
    def test_06_critical_bms_fault(self):
        res = self.what_if.simulate_battery_parameters(
            soh=0.95, fault_flags={"Fault_OverTemp": True}
        )
        self.assertEqual(res["safety_risk"]["safety_status"], "QUARANTINE")
        self.assertFalse(res["decision"]["is_suitable_for_second_life"])

    # TEST 7: Insufficient capacity for selected application
    def test_07_insufficient_capacity(self):
        cap = BatteryCapability(
            soh=0.85, remaining_capacity_ah=20.0, usable_energy_kwh=0.64,
            temperature_c=25.0, cell_imbalance_v=0.005, rul_cycles=1500
        )
        eval_res = self.repurposing.evaluate_battery(cap)
        # Solar requires >= 1.20 kWh -> should fail Solar and fall back to low-power / residential
        self.assertIn("Solar Energy Storage", eval_res.unsuitable_reasons)

    # TEST 8: Different chemistry (LFP, NCA, NMC 811)
    def test_08_different_chemistry(self):
        lfp = CHEMISTRY_DATABASE["LFP"]
        nca = CHEMISTRY_DATABASE["NCA"]
        topo = TOPOLOGY_DATABASE["16S"]
        
        lfp_specs = topo.calculate_pack_specs(lfp)
        nca_specs = topo.calculate_pack_specs(nca)
        
        self.assertEqual(lfp_specs["pack_nominal_voltage_v"], 51.2)
        self.assertEqual(nca_specs["pack_nominal_voltage_v"], 57.6)

    # TEST 9: Different topology (8S, 16S, 96S, 192S)
    def test_09_different_topology(self):
        nmc = CHEMISTRY_DATABASE["NMC_811"]
        t96 = TOPOLOGY_DATABASE["96S"].calculate_pack_specs(nmc)
        t192 = TOPOLOGY_DATABASE["192S"].calculate_pack_specs(nmc)
        
        self.assertAlmostEqual(t96["pack_nominal_voltage_v"], 350.4, places=1)
        self.assertAlmostEqual(t192["pack_nominal_voltage_v"], 700.8, places=1)

    # TEST 10: What-If degradation scenario (Non-linear knee model)
    def test_10_what_if_degradation_knee(self):
        proj = self.degradation.project_degradation(
            initial_soh_pct=85.0, knee_soh_pct=75.0, ambient_temp_c=35.0, c_rate=1.0
        )
        self.assertIn("curve_data", proj)
        self.assertGreater(len(proj["curve_data"]["cycles"]), 10)
        self.assertLess(proj["curve_data"]["projected_soh_pct"][-1], 75.0)

    # TEST 11: Missing/malformed CAN data
    def test_11_missing_malformed_can_data(self):
        decoder = CANDecoder()
        corrupt_df = pd.DataFrame([
            {"timestamp": 0.0, "arbitration_id": "0x180", "data": "ZZINVALIDHEX", "is_extended": True},
            {"timestamp": 0.1, "arbitration_id": "0x280", "data": "1234", "is_extended": True}
        ])
        decoded, summary = decoder.decode_dataframe(corrupt_df)
        self.assertEqual(len(decoded), 2)
        self.assertIn("PackVoltage", decoded.columns)

    # TEST 12: Missing SOH
    def test_12_missing_soh(self):
        pred_soh, attr = self.twin.soh_predictor.predict_single({})
        self.assertGreaterEqual(pred_soh, 0.50)
        self.assertLessEqual(pred_soh, 0.99)

    # TEST 13: Missing capacity (Auto derivation)
    def test_13_missing_capacity(self):
        cap = BatteryCapability(soh=0.80, remaining_capacity_ah=40.0, usable_energy_kwh=0.0)
        self.assertGreater(cap.usable_energy_kwh, 1.0)
        self.assertIsNotNone(cap.available_power_kw)


if __name__ == "__main__":
    unittest.main()
