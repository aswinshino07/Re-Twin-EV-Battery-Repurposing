"""
RE-TWIN Dashboard & Real-Time Intelligence Server.
Provides:
  1. Static file serving (HTML, CSS, JS, CSVs, icons)
  2. REST API endpoints for live What-If simulation and Battery Passport
  3. Real-time telemetry streaming endpoint for the web dashboard.
"""

import http.server
import socketserver
import urllib.parse
import json
import webbrowser
import os
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR
sys.path.insert(0, str(PROJECT_DIR))

from src.core.battery_state import BatteryPackSpec
from src.twin.digital_twin_core import DigitalTwinEngine
from src.twin.what_if_sim import WhatIfSimulator
from src.twin.passport_generator import BatteryPassportGenerator

PORT = 8050
spec = BatteryPackSpec()
twin = DigitalTwinEngine(spec=spec, model_path=str(PROJECT_DIR / "models" / "soh_linear_regression.joblib"))
what_if_sim = WhatIfSimulator(twin)
passport_gen = BatteryPassportGenerator(spec, twin)


class RetwinHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_DIR), **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip('/')
        query = urllib.parse.parse_qs(parsed.query)

        # Redirect root to dashboard.html
        if path in ("/", "/dashboard", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/dashboard.html")
            self.end_headers()
            return

        # API: What-If Simulation (Single Battery Parameter Sandbox)
        if path == "/api/simulate-battery":
            try:
                soh = float(query.get("soh", [0.86])[0])
                soc = float(query.get("soc", [80.0])[0])
                rated_ah = float(query.get("rated_ah", [50.0])[0])
                rem_ah = float(query.get("rem_ah", [0])[0]) if "rem_ah" in query and float(query.get("rem_ah", [0])[0]) > 0 else None
                temp = float(query.get("temp", [28.0])[0])
                imb_mv = float(query.get("imb_mv", [8.0])[0])
                r0_mohm = float(query.get("r0", [25.5])[0])
                rct_mohm = float(query.get("rct", [22.0])[0])
                rul = int(query.get("rul", [0])[0]) if "rul" in query and int(query.get("rul", [0])[0]) > 0 else None
                safety = query.get("safety", ["NORMAL"])[0]
                fault_flags = {
                    "Fault_OverVoltage": query.get("fault_ov", ["0"])[0] in ("1", "true", "True"),
                    "Fault_UnderVoltage": query.get("fault_uv", ["0"])[0] in ("1", "true", "True"),
                    "Fault_OverTemp": query.get("fault_ot", ["0"])[0] in ("1", "true", "True"),
                    "Fault_UnderTemp": query.get("fault_ut", ["0"])[0] in ("1", "true", "True"),
                    "Fault_OverCurrent": query.get("fault_oc", ["0"])[0] in ("1", "true", "True"),
                }
                res = what_if_sim.simulate_battery_parameters(
                    soh=soh,
                    soc=soc,
                    rated_capacity_ah=rated_ah,
                    remaining_capacity_ah=rem_ah,
                    temperature_c=temp,
                    cell_imbalance_v=imb_mv / 1000.0,
                    r0_ohm=r0_mohm / 1000.0,
                    rct_ohm=rct_mohm / 1000.0,
                    rul_cycles=rul,
                    fault_flags=fault_flags,
                    safety_status=safety
                )
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # API: What-If Simulation (Multi-Year Trajectory)
        if path == "/api/what-if":
            try:
                base_soh = float(query.get("soh", [0.88])[0])
                temp = float(query.get("temp", [25.0])[0])
                c_rate = float(query.get("crate", [0.5])[0])
                app = query.get("app", ["Solar Energy Storage"])[0]
                years = int(query.get("years", [5])[0])
                res = what_if_sim.simulate_scenario(
                    base_soh=base_soh,
                    ambient_temp_c=temp,
                    c_rate=c_rate,
                    target_application=app,
                    project_years=years
                )
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # API: Explainable AI SOH Feature Influences
        if path == "/api/soh-attribution":
            try:
                telemetry = {
                    "PackVoltage": float(query.get("v", [32.10])[0]),
                    "PackCurrent": float(query.get("i", [12.5])[0]),
                    "PackPower_W": float(query.get("p", [401.2])[0]),
                    "SOC": float(query.get("soc", [80.0])[0]),
                    "TempMean": float(query.get("temp", [25.0])[0]),
                    "CellVoltageImbalance": float(query.get("imb", [0.006])[0]),
                    "Throughput_Ah": float(query.get("tp", [124.0])[0])
                }
                attribution_res = twin.soh_predictor.get_feature_influences(telemetry)
                self._send_json(attribution_res)
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # API: Battery Diagnostic & Prognostic Intelligence Center
        if path in ("/api/health-risk", "/api/health"):
            try:
                soh_val = float(query.get("soh", [0.884])[0])
                telemetry = {
                    "PackVoltage": float(query.get("v", [31.16])[0]),
                    "PackCurrent": float(query.get("i", [1.9])[0]),
                    "PackPower_W": float(query.get("p", [59.2])[0]),
                    "SOC": float(query.get("soc", [66.7])[0]),
                    "TempMean": float(query.get("temp", [25.3])[0]),
                    "CellVoltageImbalance": float(query.get("imb", [0.007])[0]),
                    "Throughput_Ah": float(query.get("tp", [124.0])[0])
                }
                res = twin.evaluate_health_and_risk(telemetry, soh_override=soh_val)
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # API: EIS Fingerprint & Impedance Intelligence Laboratory
        if path in ("/api/eis", "/api/eis-laboratory"):
            try:
                soh_val = float(query.get("soh", [0.884])[0])
                soc_val = float(query.get("soc", [80.0])[0]) / 100.0 if float(query.get("soc", [80.0])[0]) > 1.0 else float(query.get("soc", [0.80])[0])
                temp_val = float(query.get("temp", [25.3])[0])
                f_min = float(query.get("f_min", [0.01])[0])
                f_max = float(query.get("f_max", [10000.0])[0])
                
                lab_res = twin.ecm.evaluate_laboratory_state(
                    soc_norm=soc_val,
                    temp_c=temp_val,
                    soh_norm=soh_val / 100.0 if soh_val > 1.0 else soh_val
                )
                self._send_json(lab_res)
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # API: Second-Life Decision Intelligence Engine
        if path == "/api/second-life-decision":
            try:
                soh = float(query.get("soh", [0.865])[0])
                temp = float(query.get("temp", [25.3])[0])
                imb_mv = float(query.get("imb", [7.0])[0])
                telemetry = {
                    "SOH": soh,
                    "TempMean": temp,
                    "CellVoltageImbalance": imb_mv / 1000.0,
                    "PackVoltage": float(query.get("v", [31.16])[0]),
                    "PackCurrent": float(query.get("i", [1.9])[0]),
                    "SOC": float(query.get("soc", [66.7])[0])
                }
                assessment = twin.repurposing_engine.evaluate_battery(telemetry)
                self._send_json(assessment.to_dict())
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # API: Battery Passport
        if path == "/api/passport":
            try:
                eval_res = twin.evaluate_state({
                    "PackVoltage": 32.10,
                    "PackCurrent": 12.5,
                    "PackPower_W": 401.2,
                    "SOC": 82.5,
                    "TempMean": 26.2,
                    "CellVoltageImbalance": 0.006,
                    "Throughput_Ah": 124.0
                })
                passport = passport_gen.generate_passport(eval_res)
                self._send_json(passport)
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # API: Standalone Certificate HTML
        if path == "/api/certificate":
            try:
                eval_res = twin.evaluate_state({
                    "PackVoltage": 32.10,
                    "PackCurrent": 12.5,
                    "PackPower_W": 401.2,
                    "SOC": 82.5,
                    "TempMean": 26.2,
                    "CellVoltageImbalance": 0.006,
                    "Throughput_Ah": 124.0
                })
                cert_html = passport_gen.generate_html_certificate(eval_res)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(cert_html.encode("utf-8"))
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # API: Multi-Pack Battery Comparison
        if path in ("/api/compare-packs", "/api/compare"):
            try:
                # Generate evaluations for 3 sample pack condition profiles
                p1_spec = BatteryPackSpec(pack_id="BAT-8S-50AH-001")
                p2_spec = BatteryPackSpec(pack_id="BAT-8S-50AH-002 (Aged)")
                p3_spec = BatteryPackSpec(pack_id="BAT-8S-50AH-003 (Cell Fault)")

                eval1 = twin.evaluate_state({"PackVoltage": 32.1, "PackCurrent": 12.5, "SOC": 82.5, "TempMean": 26.2, "CellVoltageImbalance": 0.006}, soh_override=0.88)
                eval2 = twin.evaluate_state({"PackVoltage": 30.5, "PackCurrent": 15.0, "SOC": 65.0, "TempMean": 34.0, "CellVoltageImbalance": 0.018}, soh_override=0.74)
                eval3 = twin.evaluate_state({"PackVoltage": 28.2, "PackCurrent": 5.0, "SOC": 45.0, "TempMean": 58.0, "CellVoltageImbalance": 0.062, "Fault_OverTemp": 1}, soh_override=0.62)

                eval1["pack_id"] = p1_spec.pack_id
                eval2["pack_id"] = p2_spec.pack_id
                eval3["pack_id"] = p3_spec.pack_id

                comp_res = twin.compare_packs([eval1, eval2, eval3])
                self._send_json(comp_res)
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # API: Real-time latest telemetry frame (with in-memory fallback cache)
        if path == "/api/latest-frame":
            try:
                realtime_log = PROJECT_DIR / "output" / "realtime_fused_log.csv"
                if not realtime_log.exists():
                    realtime_log = PROJECT_DIR / "output" / "digital_twin.csv"

                if realtime_log.exists():
                    import pandas as pd
                    df = pd.read_csv(realtime_log)
                    latest = df.iloc[-1].to_dict() if len(df) > 0 else {}
                    self._send_json({"latest_frame": latest, "total_frames": len(df)})
                else:
                    self._send_json({"latest_frame": None, "total_frames": 0})
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # Default fallback to static file server
        super().do_GET()

    def _send_json(self, data: dict, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    os.chdir(str(PROJECT_DIR))
    url = f"http://localhost:{PORT}/dashboard.html"
    print("=" * 80)
    print("  RE-TWIN — Intelligent Second-Life EV Battery Repurposing Platform")
    print(f"  Serving Directory: {PROJECT_DIR}")
    print(f"  Dashboard URL:     {url}")
    print(f"  REST API:          http://localhost:{PORT}/api/what-if | /api/passport")
    print("=" * 80)

    try:
        import threading
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    except Exception:
        pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), RetwinHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down RE-TWIN server.")
            httpd.server_close()


if __name__ == "__main__":
    main()
