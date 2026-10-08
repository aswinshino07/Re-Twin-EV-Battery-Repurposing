"""
Offline training step for real-time SOH inference.

Trains the same demonstration Linear Regression as soh_model.py, but
PERSISTS the fitted model (joblib) so realtime_pipeline.py can load it
once at startup and do fast inference per incoming CAN frame -- retraining
a LinearRegression on every single incoming frame isn't meaningful (one
new point barely moves a batch-fit line) or fast enough for a live loop.

Run this once, and again whenever you have a meaningfully larger/updated
battery_features.csv you want the model refreshed on. Then run
realtime_pipeline.py to serve it live.
"""

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

FEATURES = ["SOC", "TempMean", "CellVoltageImbalance", "PackVoltage", "PackCurrent", "PackPower_W", "Throughput_Ah"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="output/battery_features.csv")
    ap.add_argument("--out", default="models/soh_linear_regression.joblib")
    args = ap.parse_args()

    df = pd.read_csv(args.input).copy()

    # Strictly data-dependent SOH derived from physical degradation mechanisms:
    # 1. Cumulative Coulomb charge throughput (loss proportional to cycled Ah)
    # 2. Cell voltage imbalance (loss from cell divergence / weak cells)
    # 3. Thermal aging stress (exposure above optimal 25°C baseline)
    # 4. State of Charge operating point
    throughput = df["Throughput_Ah"].fillna(0) if "Throughput_Ah" in df.columns else (df["PackCurrent"].abs() * 0.1 / 3600.0).cumsum()
    imbalance = df["CellVoltageImbalance"].fillna(0.005)
    temp = df["TempMean"].fillna(25.0)
    soc = df["SOC"].fillna(80.0)

    df["SOH_reference_demo"] = (
        0.8860
        - 0.0020 * throughput
        - 0.12 * imbalance.clip(lower=0)
        - 0.0004 * (temp - 25.0).clip(lower=0)
        - 0.0005 * (1.0 - soc / 100.0)
    ).clip(0.70, 0.98)

    avail_features = [f for f in FEATURES if f in df.columns]
    X = df[avail_features].replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0)
    y = df["SOH_reference_demo"]

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
    model = LinearRegression().fit(Xtr, ytr)
    pred = model.predict(Xte)

    print(f"Test MAE: {mean_absolute_error(yte, pred):.6f}")
    print(f"Test R2:  {r2_score(yte, pred):.6f}")
    print("WARNING: synthetic demonstration SOH target; replace with measured/reference SOH.")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.out)
    print(f"\nModel saved to {args.out}")


if __name__ == "__main__":
    main()
