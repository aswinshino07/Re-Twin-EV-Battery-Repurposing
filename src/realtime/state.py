"""
Maintains the latest known value of every BMS signal as CAN frames arrive
one at a time, mirroring feature_engineering's synchronized state logic
(latest value per signal, forward-filled) but updated incrementally.
Equipped with full cantools support and pure-Python DBC bitshift fallback.
"""

from pathlib import Path
import sys

# Ensure core packages are accessible
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.decoder import CANDecoder

SIGNALS = [
    "PackVoltage", "PackCurrent", "SOC",
    "Cell1", "Cell2", "Cell3", "Cell4",
    "Cell5", "Cell6", "Cell7", "Cell8",
    "Temp1", "Temp2", "Temp3", "Temp4",
    "Fault_OverVoltage", "Fault_UnderVoltage", "Fault_OverTemp",
    "Fault_UnderTemp", "Fault_OverCurrent",
    "Contactor_Closed", "Balancing_Active",
]


class BatteryStateTracker:
    def __init__(self, dbc_path, q_nominal_ah=50.0):
        self.decoder = CANDecoder(dbc_path)
        self.state = {k: None for k in SIGNALS}
        self.last_timestamp = None
        self.q_nominal_ah = q_nominal_ah
        self.initial_soc = None
        self.coulomb_soc = None
        self.cumulative_ah = 0.0
        self.net_ah_discharged = 0.0

    def update(self, timestamp, arb_id, data):
        """
        Decode one frame and merge its signals into the running state.
        Returns the message name (e.g. 'BMS_PackState'), or None.
        """
        msg_name, signals = self.decoder.decode_frame(arb_id, data)
        if not signals:
            return None

        if "SOC" in signals and signals["SOC"] is not None:
            raw_soc = float(signals["SOC"])
            signals["SOC_raw"] = raw_soc
            if self.initial_soc is None:
                self.initial_soc = raw_soc
                self.coulomb_soc = raw_soc
            signals["SOC"] = round(self.coulomb_soc if self.coulomb_soc is not None else raw_soc, 2)

        if "PackCurrent" in signals and signals["PackCurrent"] is not None and self.last_timestamp is not None:
            dt = max(0.0, timestamp - self.last_timestamp)
            current = float(signals["PackCurrent"])
            self.cumulative_ah += abs(current) * dt / 3600.0
            self.net_ah_discharged += current * dt / 3600.0
            if self.initial_soc is not None:
                self.coulomb_soc = max(0.0, min(100.0, self.initial_soc - (self.net_ah_discharged / self.q_nominal_ah) * 100.0))
                self.state["SOC"] = round(self.coulomb_soc, 2)

        self.state.update(signals)
        self.last_timestamp = timestamp
        return msg_name

    def is_ready(self):
        """True once every tracked signal has been seen at least once."""
        return all(v is not None for v in self.state.values())

    def snapshot(self):
        """Current synchronized state, plus derived features."""
        s = dict(self.state)
        s["timestamp"] = self.last_timestamp
        s["Throughput_Ah"] = round(self.cumulative_ah, 4)

        cells = [s[f"Cell{i}"] for i in range(1, 9) if s.get(f"Cell{i}") is not None]
        temps = [s[f"Temp{i}"] for i in range(1, 5) if s.get(f"Temp{i}") is not None]

        if cells:
            s["CellVoltageMin"] = min(cells)
            s["CellVoltageMax"] = max(cells)
            s["CellVoltageMean"] = sum(cells) / len(cells)
            s["CellVoltageImbalance"] = s["CellVoltageMax"] - s["CellVoltageMin"]
        if temps:
            s["TempMin"] = min(temps)
            s["TempMax"] = max(temps)
            s["TempMean"] = sum(temps) / len(temps)
            s["TempSpread"] = s["TempMax"] - s["TempMin"]
        if s.get("PackVoltage") is not None and s.get("PackCurrent") is not None:
            s["PackPower_W"] = s["PackVoltage"] * s["PackCurrent"]

        return s
