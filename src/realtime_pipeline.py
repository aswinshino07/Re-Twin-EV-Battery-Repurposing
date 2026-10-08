"""
Real-time RE-TWIN pipeline.

For every new CAN frame:
  1. Update the rolling battery state (incremental decode)
  2. On each PackState heartbeat, once the state is fully warmed up:
       a. Score SOH with the pre-trained model (real-time INFERENCE)
       b. Feed CAN state + that SOH estimate into the virtual battery
          -> a fresh simulated EIS point, live
       c. Fuse CAN features + EIS features + Capacity & RPS into one row
       d. Run the digital twin's risk/recommendation logic
  3. Emit the fused row: print it live and append it to a running CSV log

Run against the recorded log, replayed in real time:
    python src/train_soh_model.py                     # once, offline
    python src/realtime_pipeline.py --replay data/ev_pack_drive.csv --speed 20

Run against a real CAN interface instead:
    python src/realtime_pipeline.py --live-channel can0
"""

import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from realtime.can_stream import replay_csv_realtime, live_python_can
from realtime.state import BatteryStateTracker
from virtual_battery_model import simulate_eis
from digital_twin import (
    calculate_capacity,
    calculate_rul,
    calculate_repurposing_score,
    recommendation,
    DEFAULT_RATED_CAPACITY_AH,
    DEFAULT_NOMINAL_VOLTAGE_V
)

FEATURES = ["SOC", "TempMean", "CellVoltageImbalance", "PackVoltage", "PackCurrent", "PackPower_W", "Throughput_Ah"]
FAULTS = ["Fault_OverVoltage", "Fault_UnderVoltage", "Fault_OverTemp",
          "Fault_UnderTemp", "Fault_OverCurrent"]


_running_soh = None

def process_state(snap, model, rated_ah=DEFAULT_RATED_CAPACITY_AH, nominal_v=DEFAULT_NOMINAL_VOLTAGE_V):
    """One fused CAN+EIS+Digital Twin row, computed live from the current battery state."""
    global _running_soh
    X = pd.DataFrame([{k: (snap.get(k) or 0) for k in FEATURES}])
    raw_soh = float(model.predict(X)[0])
    raw_soh = max(0.70, min(0.98, raw_soh))

    # Low-pass filter to ensure SOH stays rock-solid and stable across live drive cycle frames
    if _running_soh is None:
        _running_soh = raw_soh
    else:
        _running_soh = 0.98 * _running_soh + 0.02 * raw_soh
    soh = _running_soh

    # Low frequency EIS simulation (0.01 Hz)
    eis = simulate_eis(soc=snap["SOC"] / 100.0, temp_c=snap["TempMean"], soh=soh, n_points=1)

    cap_ah, energy_kwh = calculate_capacity(soh, rated_ah, nominal_v)
    rul_cycles = calculate_rul(soh)
    risk = "HIGH" if any((snap.get(f) or 0) for f in FAULTS) else "NORMAL"
    cell_imb = snap.get("CellVoltageImbalance", 0.005) or 0.005
    temp_c = snap.get("TempMean", 25.0) or 25.0

    rps = calculate_repurposing_score(
        soh=soh,
        remaining_capacity_ah=cap_ah,
        rated_capacity_ah=rated_ah,
        risk=risk,
        cell_imbalance_v=cell_imb,
        temp_mean_c=temp_c
    )
    rec = recommendation(
        soh=soh,
        risk=risk,
        remaining_capacity_ah=cap_ah,
        rated_capacity_ah=rated_ah,
        cell_imbalance_v=cell_imb,
        temp_mean_c=temp_c
    )

    fused = {
        "timestamp": snap["timestamp"],
        "SOC": snap["SOC"],
        "PackVoltage": snap["PackVoltage"],
        "PackCurrent": snap["PackCurrent"],
        "CellVoltageImbalance": cell_imb,
        "TempMean": temp_c,
        "R0_ohm": eis["r0_ohm"],
        "Rct_ohm": eis["rct_ohm"],
        "Cdl_F": eis["cdl_farad"],
        "Z_lowfreq_ohm": float(eis["impedance_magnitude_ohm"][0]),
        "Phase_lowfreq_deg": float(eis["phase_deg"][0]),
        "SOH_used": soh,
        "SOH_source": "realtime_estimate",
        "RemainingCapacity_Ah": cap_ah,
        "RemainingEnergy_kWh": energy_kwh,
        "EstimatedRUL_Cycles": rul_cycles,
        "RepurposingScore_RPS": rps,
        "Risk": risk,
        "SecondLifeRecommendation": rec,
    }
    return fused


ROOT = Path(__file__).resolve().parents[1]

def resolve_path(p, default_relative=None):
    if p is None:
        return None
    path = Path(p)
    if path.exists():
        return path
    if (ROOT / path).exists():
        return ROOT / path
    if default_relative and (ROOT / default_relative).exists():
        return ROOT / default_relative
    return ROOT / path


def main():
    ap = argparse.ArgumentParser(description="RE-TWIN Real-Time CAN Pipeline")
    ap.add_argument("--dbc", default="data/ev_bms.dbc")
    ap.add_argument("--model", default="models/soh_linear_regression.joblib")
    ap.add_argument("--replay", default="data/ev_pack_drive.csv",
                     help="CSV log to replay in real time (ignored if --live-channel is set)")
    ap.add_argument("--live-channel", default=None,
                     help="Use a real CAN interface (e.g. PCAN_USBBUS1 on Windows, can0 on Linux)")
    ap.add_argument("--bustype", default="socketcan")
    ap.add_argument("--speed", type=float, default=20.0, help="Replay speed multiplier")
    ap.add_argument("--capacity-ah", type=float, default=DEFAULT_RATED_CAPACITY_AH, help="Rated battery pack capacity (Ah)")
    ap.add_argument("--voltage-v", type=float, default=DEFAULT_NOMINAL_VOLTAGE_V, help="Nominal pack voltage (V)")
    ap.add_argument("--out", default="output/realtime_fused_log.csv")
    args = ap.parse_args()

    model_path = resolve_path(args.model)
    dbc_path = resolve_path(args.dbc)
    replay_path = resolve_path(args.replay)
    out_path = resolve_path(args.out)

    if not model_path.exists():
        print(f"[INFO] Model {model_path} not found. Training model offline first...")
        feat_path = resolve_path("output/battery_features.csv")
        if not feat_path.exists():
            import subprocess
            subprocess.run([sys.executable, str(ROOT / "src" / "main.py")], check=True)
        import train_soh_model
        train_soh_model.main()

    model = joblib.load(model_path)
    tracker = BatteryStateTracker(dbc_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        try:
            out_path.unlink()  # start each run with a fresh live log
        except Exception:
            pass
    header_written = False

    source = (
        live_python_can(args.live_channel, args.bustype)
        if args.live_channel
        else replay_csv_realtime(replay_path, speed=args.speed)
    )

    print(f"{'timestamp':>10} {'SOC%':>6} {'V':>6} {'I':>6} | "
          f"{'SOH':>6} {'Cap_Ah':>7} {'RPS':>5} {'RUL':>5} | {'Risk':6} recommendation")
    print("-" * 105)

    for t, arb_id, data in source:
        msg_name = tracker.update(t, arb_id, data)
        if msg_name != "BMS_PackState" or not tracker.is_ready():
            continue  # PackState is the heartbeat that drives one fused update per arrival

        snap = tracker.snapshot()
        fused = process_state(snap, model, rated_ah=args.capacity_ah, nominal_v=args.voltage_v)

        print(f"{fused['timestamp']:10.1f} {snap['SOC']:6.1f} {snap['PackVoltage']:6.2f} "
              f"{snap['PackCurrent']:6.1f} | "
              f"{fused['SOH_used']:6.3f} {fused['RemainingCapacity_Ah']:7.2f} "
              f"{fused['RepurposingScore_RPS']:5.1f} {fused['EstimatedRUL_Cycles']:5d} | "
              f"{fused['Risk']:6} {fused['SecondLifeRecommendation']}")

        pd.DataFrame([fused]).to_csv(out_path, mode="a", header=not header_written, index=False)
        header_written = True


if __name__ == "__main__":
    main()
