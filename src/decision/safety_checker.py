"""
Anomaly, Fault & Safety Detection Module.
Evaluates hardware BMS fault flags and dynamic operational stress thresholds.
Enforces a hard Safety Quarantine Override if critical anomalies are detected.
"""

from typing import Dict, Any, Tuple, List
from src.core.battery_state import SafetyStatus, BatteryPackSpec

FAULT_SIGNALS = [
    "Fault_OverVoltage",
    "Fault_UnderVoltage",
    "Fault_OverTemp",
    "Fault_UnderTemp",
    "Fault_OverCurrent"
]


class SafetyChecker:
    def __init__(self, spec: BatteryPackSpec = None):
        self.spec = spec or BatteryPackSpec()

    def evaluate_safety(self, state_dict: Dict[str, Any]) -> Tuple[SafetyStatus, List[str]]:
        """
        Evaluates active safety state and generates diagnostic alarm list.
        """
        alarms = []

        # 1. BMS Hardware Bitfield Faults
        for fault in FAULT_SIGNALS:
            if state_dict.get(fault, 0) == 1:
                alarms.append(f"HARDWARE_FAULT: {fault.replace('Fault_', '')}")

        # 2. Dynamic Thermal Thresholds
        temp_mean = float(state_dict.get("TempMean", 25.0) or 25.0)
        temp_max = float(state_dict.get("TempMax", temp_mean) or temp_mean)
        temp_min = float(state_dict.get("TempMin", temp_mean) or temp_mean)

        if temp_max > self.spec.max_safe_temp_c:
            alarms.append(f"CRITICAL_OVERTEMP: Max Temp {temp_max:.1f}°C exceeds safe limit ({self.spec.max_safe_temp_c}°C)")
        elif temp_max > 45.0:
            alarms.append(f"THERMAL_WARNING: Elevated module temperature ({temp_max:.1f}°C)")

        if temp_min < self.spec.min_safe_temp_c:
            alarms.append(f"UNDERTEMP_WARNING: Low module temperature ({temp_min:.1f}°C)")

        # 3. Dynamic Cell Imbalance (Delta V)
        imbalance_v = float(state_dict.get("CellVoltageImbalance", 0.005) or 0.005)
        imbalance_mv = abs(imbalance_v) * 1000.0

        if imbalance_v > self.spec.max_cell_imbalance_v:
            alarms.append(f"SEVERE_CELL_IMBALANCE: {imbalance_mv:.1f} mV divergence exceeds critical safety limit (50 mV)")
        elif imbalance_mv > 25.0:
            alarms.append(f"CELL_IMBALANCE_WARNING: Moderate cell divergence ({imbalance_mv:.1f} mV)")

        # 4. Pack Voltage Range
        pack_v = float(state_dict.get("PackVoltage", 32.0) or 32.0)
        if pack_v > self.spec.max_voltage_v:
            alarms.append(f"PACK_OVERVOLTAGE: {pack_v:.2f}V exceeds limit ({self.spec.max_voltage_v}V)")
        elif pack_v < self.spec.min_voltage_v:
            alarms.append(f"PACK_UNDERVOLTAGE: {pack_v:.2f}V is below cutoff ({self.spec.min_voltage_v}V)")

        # Determine Safety Classification
        if any(a.startswith("HARDWARE_FAULT") or a.startswith("CRITICAL") or a.startswith("SEVERE") for a in alarms):
            status = SafetyStatus.QUARANTINE
        elif alarms:
            status = SafetyStatus.WARNING
        else:
            status = SafetyStatus.NORMAL

        return status, alarms
