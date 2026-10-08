import unittest
import numpy as np
import urllib.request
import json
from src.physics.ecm_eis import VirtualBatteryECM

class TestEisLaboratory(unittest.TestCase):

    def setUp(self):
        self.ecm = VirtualBatteryECM()

    def test_compute_impedance_spectrum_default(self):
        spectrum = self.ecm.compute_impedance_spectrum(soc_norm=0.80, temp_c=25.3, soh_norm=0.884, n_points=60)
        
        self.assertEqual(len(spectrum["frequency_hz"]), 60)
        self.assertEqual(len(spectrum["z_real_ohm"]), 60)
        self.assertEqual(len(spectrum["z_imag_ohm"]), 60)
        self.assertEqual(len(spectrum["magnitude_ohm"]), 60)
        self.assertEqual(len(spectrum["phase_deg"]), 60)
        self.assertEqual(len(spectrum["spectrum_points"]), 60)
        
        self.assertAlmostEqual(spectrum["frequency_hz"][0], 0.01, places=3)
        self.assertAlmostEqual(spectrum["frequency_hz"][-1], 10000.0, places=1)
        self.assertGreater(spectrum["r0_ohm"], 0)
        self.assertGreater(spectrum["rct_ohm"], 0)
        self.assertGreater(spectrum["cdl_farad"], 0)

    def test_extract_fingerprint(self):
        spectrum = self.ecm.compute_impedance_spectrum(soc_norm=0.80, temp_c=25.3, soh_norm=0.884, n_points=60)
        fp = self.ecm.extract_fingerprint(spectrum)
        
        self.assertIn("r0_mohm", fp)
        self.assertIn("rct_mohm", fp)
        self.assertIn("cdl_farad", fp)
        self.assertIn("characteristic_frequency_fc_hz", fp)
        self.assertIn("selected_frequency_points", fp)
        
        rct_sec = fp["rct_mohm"] / 1000.0
        expected_fc = 1.0 / (2.0 * np.pi * rct_sec * fp["cdl_farad"])
        self.assertAlmostEqual(fp["characteristic_frequency_fc_hz"], expected_fc, delta=0.05)
        self.assertEqual(len(fp["selected_frequency_points"]), 6)

    def test_evaluate_reference_spectrum(self):
        ref_data = self.ecm.evaluate_reference_spectrum()
        
        self.assertIn("spectrum", ref_data)
        self.assertIn("fingerprint", ref_data)
        self.assertEqual(ref_data["soh_pct"], 100.0)
        self.assertEqual(len(ref_data["spectrum"]["frequency_hz"]), 60)

    def test_evaluate_laboratory_state(self):
        lab_state = self.ecm.evaluate_laboratory_state(soc_norm=0.80, temp_c=25.3, soh_norm=0.884)
        
        self.assertIn("operating_state", lab_state)
        self.assertIn("spectrum", lab_state)
        self.assertIn("fingerprint", lab_state)
        self.assertIn("reference_comparison", lab_state)
        self.assertIn("health_indicators", lab_state)
        
        self.assertEqual(lab_state["operating_state"]["soh_pct"], 88.4)
        self.assertGreaterEqual(len(lab_state["health_indicators"]), 4)

    def test_api_eis_laboratory_endpoint(self):
        try:
            req = urllib.request.urlopen("http://localhost:8050/api/eis-laboratory")
            self.assertEqual(req.status, 200)
            data = json.loads(req.read().decode('utf-8'))
            self.assertIn("operating_state", data)
            self.assertIn("spectrum", data)
            self.assertIn("fingerprint", data)
            self.assertIn("reference_comparison", data)
            self.assertIn("health_indicators", data)
        except Exception as e:
            self.fail(f"HTTP request to /api/eis-laboratory failed: {e}")

    def test_api_eis_laboratory_with_query_params(self):
        try:
            req = urllib.request.urlopen("http://localhost:8050/api/eis-laboratory?soh=75.0&temp=35.0")
            self.assertEqual(req.status, 200)
            data = json.loads(req.read().decode('utf-8'))
            self.assertEqual(data["operating_state"]["soh_pct"], 75.0)
            self.assertEqual(data["operating_state"]["temp_c"], 35.0)
        except Exception as e:
            self.fail(f"HTTP request to /api/eis-laboratory with query params failed: {e}")

if __name__ == '__main__':
    unittest.main()
