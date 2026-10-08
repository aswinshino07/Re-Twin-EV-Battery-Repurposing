import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.battery_state import BatteryPackSpec
from src.twin.digital_twin_core import DigitalTwinEngine

FAULTS = [
    "Fault_OverVoltage", "Fault_UnderVoltage", "Fault_OverTemp",
    "Fault_UnderTemp", "Fault_OverCurrent"
]

DEFAULT_RATED_CAPACITY_AH = 50.0
DEFAULT_NOMINAL_VOLTAGE_V = 32.0

DEFAULT_WEIGHTS = {
    "soh": 0.30,
    "capacity": 0.25,
    "rul": 0.15,
    "safety": 0.20,
    "cell_balance": 0.10
}


def calculate_capacity(soh: float, rated_capacity_ah: float = DEFAULT_RATED_CAPACITY_AH, nominal_voltage_v: float = DEFAULT_NOMINAL_VOLTAGE_V):
    soh_norm = max(0.0, min(1.0, float(soh)))
    c_remaining_ah = rated_capacity_ah * soh_norm
    e_remaining_kwh = (nominal_voltage_v * c_remaining_ah) / 1000.0
    return round(c_remaining_ah, 2), round(e_remaining_kwh, 3)


def calculate_rul(soh: float) -> int:
    soh_norm = float(soh)
    if soh_norm <= 0.60:
        return 0
    return max(0, int((soh_norm - 0.60) * 7500))


def calculate_repurposing_score(
    soh: float,
    remaining_capacity_ah: float,
    rated_capacity_ah: float = DEFAULT_RATED_CAPACITY_AH,
    risk: str = "NORMAL",
    cell_imbalance_v: float = 0.005,
    temp_mean_c: float = 25.0,
    weights: dict = None
) -> float:
    if weights is None:
        weights = DEFAULT_WEIGHTS
    soh_norm = float(soh)
    soh_score = max(0.0, min(100.0, (soh_norm - 0.50) / 0.50 * 100.0))
    cap_ratio = remaining_capacity_ah / rated_capacity_ah if rated_capacity_ah > 0 else 0
    cap_score = max(0.0, min(100.0, cap_ratio * 100.0))
    rul_score = max(0.0, min(100.0, (soh_norm - 0.60) / 0.35 * 100.0))
    safety_penalty = 0.0 if (risk == "HIGH" or temp_mean_c > 55.0 or cell_imbalance_v > 0.050) else 100.0
    imb_mv = abs(float(cell_imbalance_v)) * 1000.0
    cell_balance_score = max(0.0, min(100.0, 100.0 - (imb_mv / 25.0 * 100.0)))
    rps = (
        weights["soh"] * soh_score +
        weights["capacity"] * cap_score +
        weights["rul"] * rul_score +
        weights["safety"] * safety_penalty +
        weights["cell_balance"] * cell_balance_score
    )
    return round(float(rps), 1)


def recommendation(
    soh: float,
    risk: str = "NORMAL",
    remaining_capacity_ah: float = None,
    rated_capacity_ah: float = DEFAULT_RATED_CAPACITY_AH,
    cell_imbalance_v: float = 0.005,
    temp_mean_c: float = 25.0
) -> str:
    soh_val = float(soh)
    if remaining_capacity_ah is None:
        remaining_capacity_ah = rated_capacity_ah * soh_val

    if risk == "HIGH" or (temp_mean_c is not None and temp_mean_c > 55.0) or (cell_imbalance_v is not None and cell_imbalance_v > 0.050):
        return "Inspection / isolation"
    if soh_val >= 0.90 and remaining_capacity_ah >= (0.90 * rated_capacity_ah):
        return "High-demand stationary storage"
    if soh_val >= 0.80:
        return "Solar energy storage / peak shaving"
    if soh_val >= 0.70:
        return "Home backup / UPS / telecom backup"
    if soh_val >= 0.60:
        return "Low-power applications"
    return "Recycling / material recovery"


def main():
    ap = argparse.ArgumentParser(description="RE-TWIN Digital Twin & Second-Life Decision Engine")
    ap.add_argument("--input", default="output/fused_features.csv")
    ap.add_argument("--capacity-ah", type=float, default=DEFAULT_RATED_CAPACITY_AH)
    ap.add_argument("--voltage-v", type=float, default=DEFAULT_NOMINAL_VOLTAGE_V)
    ap.add_argument("--out", default="output/digital_twin.csv")
    args = ap.parse_args()

    spec = BatteryPackSpec(rated_capacity_ah=args.capacity_ah, nominal_voltage_v=args.voltage_v)
    twin = DigitalTwinEngine(spec=spec)

    df = pd.read_csv(args.input)
    soh_col = "SOH_used" if "SOH_used" in df.columns else "SOH_predicted_demo"

    fused_rows = []
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        res = twin.evaluate_state(row_dict, soh_override=row_dict.get(soh_col))
        fused_rows.append({
            "timestamp": res["timestamp"],
            "SOH_used": res["health_assessment"]["soh"],
            "RemainingCapacity_Ah": res["health_assessment"]["remaining_capacity_ah"],
            "RemainingEnergy_kWh": res["health_assessment"]["remaining_energy_kwh"],
            "EstimatedRUL_Cycles": res["health_assessment"]["estimated_rul_cycles"],
            "RepurposingScore_RPS": res["decision"]["repurposing_score_rps"],
            "Risk": res["safety_audit"]["status"],
            "SecondLifeRecommendation": res["decision"]["recommended_tier"]
        })

    out_df = pd.DataFrame(fused_rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out, index=False)

    print("=== RE-TWIN Digital Twin Engine Evaluation (First 10 Rows) ===")
    print(out_df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()

