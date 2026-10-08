"""
Feature Engineering & Battery State Reconstruction Module.
Extracts synchronized operational features, Coulomb-counting SOC, cell voltage imbalance,
thermal spread, and cumulative Ah charge throughput.
"""

from typing import List, Optional
import numpy as np
import pandas as pd
from .battery_state import BatteryPackSpec

SIGNALS = [
    "PackVoltage", "PackCurrent", "SOC",
    "Cell1", "Cell2", "Cell3", "Cell4",
    "Cell5", "Cell6", "Cell7", "Cell8",
    "Temp1", "Temp2", "Temp3", "Temp4",
    "Fault_OverVoltage", "Fault_UnderVoltage", "Fault_OverTemp",
    "Fault_UnderTemp", "Fault_OverCurrent",
    "Contactor_Closed", "Balancing_Active"
]


class FeatureEngine:
    def __init__(self, spec: Optional[BatteryPackSpec] = None):
        self.spec = spec or BatteryPackSpec()

    def engineer_features(self, decoded_df: pd.DataFrame) -> pd.DataFrame:
        """
        Processes decoded asynchronous frames into synchronized time-step features.
        """
        df = decoded_df.sort_values(["timestamp", "arbitration_id"]).copy()
        available = [c for c in SIGNALS if c in df.columns]

        # 1. Synchronized state per timestamp: latest non-null value per timestamp + forward fill
        state = (
            df.groupby("timestamp", sort=True)[available]
              .agg(lambda s: s.dropna().iloc[-1] if s.notna().any() else np.nan)
              .ffill()
              .bfill()
              .reset_index()
        )

        # 2. Cell voltage stats & imbalance (mV and V)
        cells = [f"Cell{i}" for i in range(1, 9) if f"Cell{i}" in state.columns]
        if cells:
            state["CellVoltageMin"] = state[cells].min(axis=1)
            state["CellVoltageMax"] = state[cells].max(axis=1)
            state["CellVoltageMean"] = state[cells].mean(axis=1)
            state["CellVoltageImbalance"] = (state["CellVoltageMax"] - state["CellVoltageMin"]).round(4)
            state["CellVoltageImbalance_mV"] = (state["CellVoltageImbalance"] * 1000.0).round(1)

        # 3. Temperature stats & thermal spread
        temps = [f"Temp{i}" for i in range(1, 5) if f"Temp{i}" in state.columns]
        if temps:
            state["TempMin"] = state[temps].min(axis=1)
            state["TempMax"] = state[temps].max(axis=1)
            state["TempMean"] = state[temps].mean(axis=1).round(2)
            state["TempSpread"] = (state["TempMax"] - state["TempMin"]).round(2)

        # 4. Coulomb-counting State of Charge (SOC) Integration
        if "SOC" in state.columns:
            state["SOC_raw"] = state["SOC"]
            if "PackCurrent" in state.columns and "timestamp" in state.columns:
                dt_s = state["timestamp"].diff().fillna(0).clip(lower=0)
                q_nominal_ah = self.spec.rated_capacity_ah
                cum_net_ah = (state["PackCurrent"] * dt_s / 3600.0).cumsum()
                soc_0 = state["SOC_raw"].dropna().iloc[0] if state["SOC_raw"].notna().any() else 80.0
                state["SOC"] = (soc_0 - (cum_net_ah / q_nominal_ah) * 100.0).clip(0.0, 100.0).round(2)
            else:
                state["SOC"] = state["SOC_raw"].ewm(span=25, adjust=False).mean().round(2)

        # 5. Pack Power & C-Rate
        if "PackVoltage" in state.columns and "PackCurrent" in state.columns:
            state["PackPower_W"] = (state["PackVoltage"] * state["PackCurrent"]).round(1)
            state["PackPower_kW"] = (state["PackPower_W"] / 1000.0).round(3)
            state["CRate"] = (state["PackCurrent"].abs() / self.spec.rated_capacity_ah).round(2)

        # 6. Cumulative Electrical Charge Throughput (Ah)
        if "PackCurrent" in state.columns and "timestamp" in state.columns:
            dt_s = state["timestamp"].diff().fillna(0).clip(lower=0)
            state["Throughput_Ah"] = (state["PackCurrent"].abs() * dt_s / 3600.0).cumsum().round(4)
        else:
            state["Throughput_Ah"] = 0.0

        return state
