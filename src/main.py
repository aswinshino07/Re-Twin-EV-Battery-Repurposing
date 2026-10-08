"""
RE-TWIN Master Pipeline & Product Entrypoint.
Orchestrates:
  1. CAN/DBC Decoding
  2. Synchronized State Reconstruction & Feature Engineering
  3. AI SOH Estimation (Interpretable Linear Regression)
  4. Physics-Informed 1-RC ECM & Simulated EIS Generation
  5. Feature Fusion & Safety Audit
  6. Capacity, RUL, Repurposing Score (RPS) & 6-Tier Second-Life Recommendation
  7. Digital Battery Passport & Assessment Certificate Export
"""

import argparse
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.battery_state import BatteryPackSpec
from src.core.decoder import CANDecoder
from src.core.feature_engine import FeatureEngine
from src.twin.digital_twin_core import DigitalTwinEngine
from src.twin.what_if_sim import WhatIfSimulator
from src.twin.passport_generator import BatteryPassportGenerator


def run_pipeline(
    csv_path: str = "data/ev_pack_drive.csv",
    dbc_path: str = "data/ev_bms.dbc",
    model_path: str = "models/soh_linear_regression.joblib",
    out_dir: str = "output"
):
    csv_file = ROOT / csv_path if not Path(csv_path).is_absolute() else Path(csv_path)
    dbc_file = ROOT / dbc_path if not Path(dbc_path).is_absolute() else Path(dbc_path)
    out_folder = ROOT / out_dir if not Path(out_dir).is_absolute() else Path(out_dir)
    model_file = ROOT / model_path if not Path(model_path).is_absolute() else Path(model_path)
    out_folder.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("  RE-TWIN — EIS-Fingerprint & Physics-Informed Digital Twin")
    print("  Intelligent Second-Life EV Battery Repurposing Platform")
    print("=" * 80)

    # 1. CAN Ingestion & DBC Decoding
    print("\n[1/7] Ingesting and Decoding CAN Frames against DBC...")
    decoder = CANDecoder(str(dbc_file))
    raw_df = pd.read_csv(csv_file)
    decoded_df, skipped = decoder.decode_dataframe(raw_df)
    decoded_out = out_folder / "decoded_frames.csv"
    decoded_df.to_csv(decoded_out, index=False)
    print(f"      Decoded {len(decoded_df)} valid frames ({skipped} skipped). Saved to {decoded_out.name}")

    # 2. Synchronized State Reconstruction & Feature Engineering
    print("\n[2/7] Reconstructing Synchronized Battery State & Extracting Features...")
    spec = BatteryPackSpec()
    feature_engine = FeatureEngine(spec)
    features_df = feature_engine.engineer_features(decoded_df)
    feat_out = out_folder / "battery_features.csv"
    features_df.to_csv(feat_out, index=False)
    print(f"      Reconstructed {len(features_df)} synchronized states with Coulomb counting. Saved to {feat_out.name}")

    # 3. Initialize Digital Twin Core
    print("\n[3/7] Initializing Digital Twin & Interpretable ML SOH Predictor...")
    twin = DigitalTwinEngine(spec=spec, model_path=str(model_file))
    if twin.soh_predictor.model is None:
        print("      [INFO] Training initial baseline SOH regression model...")
        twin.soh_predictor.train_on_features(features_df)
        twin.soh_predictor.save(model_file)

    # 4. Predict SOH & Generate Predictions CSV
    soh_series = twin.soh_predictor.predict_dataframe(features_df)
    features_df["SOH_predicted_demo"] = soh_series
    pred_out = out_folder / "predictions.csv"
    features_df.to_csv(pred_out, index=False)
    print(f"      Generated SOH predictions (Mean SOH: {soh_series.mean()*100:.1f}%). Saved to {pred_out.name}")

    # 5. Physics-Informed Simulated EIS Generation
    print("\n[4/7] Generating Physics-Informed EIS Impedance Sweeps (0.01 Hz - 100 kHz)...")
    eis_records = []
    for _, row in features_df.iterrows():
        soh_val = float(row["SOH_predicted_demo"])
        soc_val = float(row["SOC"]) / 100.0
        temp_val = float(row["TempMean"])
        spectrum = twin.ecm.compute_impedance_spectrum(soc_norm=soc_val, temp_c=temp_val, soh_norm=soh_val, n_points=50)
        for i, freq in enumerate(spectrum["frequency_hz"]):
            eis_records.append({
                "timestamp": row["timestamp"],
                "SOC_pct": row["SOC"],
                "TempMean_C": row["TempMean"],
                "SOH_used": soh_val,
                "frequency_hz": freq,
                "impedance_magnitude_ohm": spectrum["magnitude_ohm"][i],
                "phase_deg": spectrum["phase_deg"][i],
                "R0_ohm": spectrum["r0_ohm"],
                "Rct_ohm": spectrum["rct_ohm"],
                "Cdl_F": spectrum["cdl_farad"],
                "EIS_label": "SIMULATED_EIS"
            })
    eis_df = pd.DataFrame(eis_records)
    eis_out = out_folder / "simulated_eis.csv"
    eis_df.to_csv(eis_out, index=False)
    print(f"      Generated {len(eis_df)} EIS frequency points across {len(features_df)} timesteps. Saved to {eis_out.name}")

    # 6. Feature Fusion & Master Digital Twin Decision Evaluation
    print("\n[5/7] Executing Feature Fusion & 6-Tier Repurposing Decision Engine...")
    digital_twin_rows = []
    fused_rows = []

    for _, row in features_df.iterrows():
        row_dict = row.to_dict()
        res = twin.evaluate_state(row_dict, soh_override=row_dict["SOH_predicted_demo"])

        # Fused table row
        fused_rows.append({
            "timestamp": res["timestamp"],
            "SOC": res["telemetry"]["soc_pct"],
            "PackVoltage": res["telemetry"]["voltage_v"],
            "PackCurrent": res["telemetry"]["current_a"],
            "CellVoltageImbalance": row_dict.get("CellVoltageImbalance", 0.005),
            "TempMean": res["telemetry"]["temp_mean_c"],
            "R0_ohm": res["electrochemical_eis"]["r0_mohm"] / 1000.0,
            "Rct_ohm": res["electrochemical_eis"]["rct_mohm"] / 1000.0,
            "Cdl_F": res["electrochemical_eis"]["cdl_f"],
            "Z_lowfreq_ohm": res["electrochemical_eis"]["z_lowfreq_mohm"] / 1000.0,
            "Phase_lowfreq_deg": res["electrochemical_eis"]["phase_lowfreq_deg"],
            "SOH_used": res["health_assessment"]["soh"],
            "SOH_source": res["health_assessment"]["soh_source"],
            "RemainingCapacity_Ah": res["health_assessment"]["remaining_capacity_ah"],
            "RemainingEnergy_kWh": res["health_assessment"]["remaining_energy_kwh"],
            "EstimatedRUL_Cycles": res["health_assessment"]["estimated_rul_cycles"],
            "RepurposingScore_RPS": res["decision"]["repurposing_score_rps"],
            "Risk": res["safety_audit"]["status"],
            "SecondLifeRecommendation": res["decision"]["recommended_tier"]
        })

    fused_df = pd.DataFrame(fused_rows)
    fused_out = out_folder / "fused_features.csv"
    twin_out = out_folder / "digital_twin.csv"
    fused_df.to_csv(fused_out, index=False)
    fused_df.to_csv(twin_out, index=False)
    print(f"      Evaluated {len(fused_df)} Digital Twin states. Saved to {twin_out.name}")

    # 6. Generate Digital Battery Passport & Assessment Certificate
    print("\n[6/7] Generating Circular Economy Digital Battery Passport...")
    passport_gen = BatteryPassportGenerator(spec, twin)
    latest_eval = twin.evaluate_state(features_df.iloc[-1].to_dict(), soh_override=features_df.iloc[-1]["SOH_predicted_demo"])
    passport_data = passport_gen.generate_passport(latest_eval)
    cert_html = passport_gen.generate_html_certificate(latest_eval)

    cert_out = out_folder / "battery_passport_report.html"
    with open(cert_out, "w", encoding="utf-8") as f:
        f.write(cert_html)
    print(f"      Generated Assessment Certificate. Saved to {cert_out.name}")

    # 7. Execute Multi-Pack Battery Comparison
    print("\n[7/7] Running Multi-Pack Battery Comparison Engine...")
    p2_eval = twin.evaluate_state(features_df.iloc[-1].to_dict(), soh_override=0.74)
    p2_eval["pack_id"] = "BAT-8S-50AH-002 (Aged)"
    p3_eval = twin.evaluate_state(features_df.iloc[-1].to_dict(), soh_override=0.62)
    p3_eval["pack_id"] = "BAT-8S-50AH-003 (Faulted)"
    p3_eval["safety_audit"]["status"] = "QUARANTINE"
    p3_eval["safety_audit"]["is_safe"] = False

    comp_summary = twin.compare_packs([latest_eval, p2_eval, p3_eval])
    print(f"      Compared {comp_summary['pack_count']} battery packs. Top Pack: {comp_summary['benchmark_summary']['top_performing_pack']}")

    # Summary Report
    print("\n" + "=" * 80)
    print("  FINAL RE-TWIN BATTERY ASSESSMENT REPORT")
    print("  Question: Given battery condition, what is the safest & most suitable second-life use?")
    print("=" * 80)
    print(f"  * Battery Pack ID:               {spec.pack_id}")
    print(f"  * State of Health (SOH):          {latest_eval['health_assessment']['soh_pct']}% ({latest_eval['health_assessment']['soh_grade']}) [AI Predicted]")
    print(f"  * Remaining Usable Capacity:      {latest_eval['health_assessment']['remaining_capacity_ah']} Ah / {spec.rated_capacity_ah} Ah rated [Estimated]")
    print(f"  * Remaining Usable Energy:        {latest_eval['health_assessment']['remaining_energy_kwh']} kWh [Estimated]")
    print(f"  * Repurposing Score (RPS):        {latest_eval['decision']['repurposing_score_rps']} / 100 [Recommendation]")
    print(f"  * Projected Second-Life RUL:      ~{latest_eval['health_assessment']['estimated_rul_cycles']} Cycles (Gentle: {latest_eval['health_assessment']['rul_profiles']['gentle_cycles']} cyc) [Estimated]")
    print(f"  * Ohmic Resistance (R0):          {latest_eval['electrochemical_eis']['r0_mohm']} mOhm (Simulated EIS - 1-RC Randles ECM)")
    print(f"  * Safety Audit Status:            {latest_eval['safety_audit']['status']} [Interlock Audit]")
    print(f"  * RECOMMENDED APPLICATION:        {latest_eval['decision']['recommended_tier']} [Recommendation]")
    print(f"  * Rationale:                      {latest_eval['decision']['rationale']}")
    print(f"  * GHG Emissions Avoided:          {passport_data['circular_economy_impact']['ghg_avoided_kg_co2e']} kg CO2e")
    print("=" * 80)


def run_what_if_demo():
    print("=" * 80)
    print("  RE-TWIN What-If Scenario Simulation Demo")
    print("=" * 80)
    sim = WhatIfSimulator()
    res = sim.simulate_scenario(base_soh=0.88, ambient_temp_c=35.0, c_rate=1.0, project_years=4)
    print(f"Scenario: 35°C Ambient, 1.0C Cycling, 365 cyc/year")
    print(f"Thermal Acceleration: {res['stress_multipliers']['thermal_acceleration']}x | C-Rate Acceleration: {res['stress_multipliers']['c_rate_acceleration']}x")
    for y in res["yearly_projection"]:
        print(f"  Year {y['year']}: SOH={y['projected_soh_pct']}% | Usable Cap={y['usable_capacity_ah']} Ah | RPS={y['projected_rps']} | {y['recommended_tier']}")


def main():
    parser = argparse.ArgumentParser(description="RE-TWIN Second-Life Battery Repurposing Platform")
    parser.add_argument("--csv", default="data/ev_pack_drive.csv")
    parser.add_argument("--dbc", default="data/ev_bms.dbc")
    parser.add_argument("--model", default="models/soh_linear_regression.joblib")
    parser.add_argument("--out", default="output")
    parser.add_argument("--what-if", action="store_true", help="Run What-If scenario demo")
    args = parser.parse_args()

    if args.what_if:
        run_what_if_demo()
    else:
        run_pipeline(args.csv, args.dbc, args.model, args.out)


if __name__ == "__main__":
    main()
