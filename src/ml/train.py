"""
Offline training pipeline for RE-TWIN SOH Model.
Trains interpretable Linear Regression on battery features and serializes to models/soh_linear_regression.joblib.
"""

from pathlib import Path
import sys
import pandas as pd

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.core.decoder import CANDecoder
from src.core.feature_engine import FeatureEngine
from src.ml.soh_predictor import SOHPredictor


def train():
    data_csv = ROOT / "data" / "ev_pack_drive.csv"
    dbc_file = ROOT / "data" / "ev_bms.dbc"
    model_file = ROOT / "models" / "soh_linear_regression.joblib"
    features_out = ROOT / "output" / "battery_features.csv"

    print("=" * 70)
    print("  RE-TWIN: Offline SOH Model Training")
    print("=" * 70)

    # 1. Decode & extract features if not already saved
    if not features_out.exists():
        print(f"[INFO] Decoding {data_csv.name}...")
        raw_df = pd.read_csv(data_csv)
        decoder = CANDecoder(str(dbc_file))
        decoded_df, _ = decoder.decode_dataframe(raw_df)
        engine = FeatureEngine()
        feat_df = engine.engineer_features(decoded_df)
        features_out.parent.mkdir(parents=True, exist_ok=True)
        feat_df.to_csv(features_out, index=False)
    else:
        feat_df = pd.read_csv(features_out)

    # 2. Train SOH predictor
    predictor = SOHPredictor()
    metrics = predictor.train_on_features(feat_df)
    predictor.save(model_file)

    print(f"[SUCCESS] Model trained & saved to: {model_file.relative_to(ROOT)}")
    print(f"  - Test MAE:  {metrics['mae']:.5f}")
    print(f"  - Test RMSE: {metrics['rmse']:.5f}")
    print(f"  - Test R2:   {metrics['r2']:.5f}")
    print("\n* NOTE: Target is physics-inspired synthetic demonstration data. *")


if __name__ == "__main__":
    train()
