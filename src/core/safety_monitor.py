"""
Advanced Predictive Safety Monitor Module.
Computes:
1. Dynamic thermal rate-of-rise: dT/dt = Delta T / Delta t (°C/min) with configurable thresholds.
2. Rest-period self-discharge rate: dV/dt = Delta V / Delta t (mV/hr) during verified zero-load intervals.
3. Hard safety interlocks that strictly enforce QUARANTINE / ISOLATION.
"""

from typing import Dict, List, Any, Optional, Tuple
from collections import deque
from src.core.battery_state import SafetyStatus


class AdvancedSafetyMonitor:
    """
    Predictive and operational safety analyzer for EV battery packs.
    """

    def __init__(
        self,
        dt_warning_threshold_c_per_min: float = 0.50,
        dt_critical_threshold_c_per_min: float = 1.00,
        dv_abnormal_decay_mv_per_hr: float = 15.0,
        window_size_samples: int = 30
    ):
        self.dt_warning_thresh = dt_warning_threshold_c_per_min
        self.dt_critical_thresh = dt_critical_threshold_c_per_min
        self.dv_abnormal_thresh = dv_abnormal_decay_mv_per_hr
        self.window_size = window_size_samples
        
        # Rolling historical buffers for rate calculations
        self.time_history = deque(maxlen=window_size_samples)
        self.temp_history = deque(maxlen=window_size_samples)
        self.voltage_history = deque(maxlen=window_size_samples)
        self.current_history = deque(maxlen=window_size_samples)

    def push_sample(self, timestamp_s: float, temp_c: float, voltage_v: float, current_a: float):
        """Pushes a live sample to the rolling history."""
        self.time_history.append(float(timestamp_s))
        self.temp_history.append(float(temp_c))
        self.voltage_history.append(float(voltage_v))
        self.current_history.append(float(current_a))

    def compute_thermal_rate(self) -> Dict[str, Any]:
        """
        Calculates dT/dt = Delta T / Delta t in °C/min.
        NOTE: dT/dt thresholds are configurable prototype safety assumptions.
        """
        if len(self.time_history) < 3:
            return {
                "dt_dt_c_per_min": 0.0,
                "status": "NORMAL",
                "label": "THERMAL RATE STABLE",
                "description": "Insufficient samples for dynamic rate computation."
            }

        delta_t_sec = self.time_history[-1] - self.time_history[0]
        if delta_t_sec <= 0.001:
            return {
                "dt_dt_c_per_min": 0.0,
                "status": "NORMAL",
                "label": "THERMAL RATE STABLE",
                "description": "Zero time elapsed."
            }

        delta_temp_c = self.temp_history[-1] - self.temp_history[0]
        rate_c_per_min = (delta_temp_c / delta_t_sec) * 60.0
        rate_rounded = round(float(rate_c_per_min), 3)

        current_temp = self.temp_history[-1]

        if rate_rounded >= self.dt_critical_thresh or (current_temp > 50.0 and rate_rounded >= self.dt_warning_thresh):
            status = "CRITICAL"
            label = "CRITICAL THERMAL ESCALATION"
            desc = f"Rapid heating detected ({rate_rounded:+.2f} °C/min). Active thermal escalation."
        elif rate_rounded >= self.dt_warning_thresh:
            status = "WARNING"
            label = "ELEVATED THERMAL RATE"
            desc = f"Elevated temperature increase ({rate_rounded:+.2f} °C/min). Requires cooling audit."
        elif rate_rounded <= -self.dt_critical_thresh:
            status = "NORMAL"
            label = "ACTIVE PACK COOLING"
            desc = f"Battery is cooling down ({rate_rounded:+.2f} °C/min)."
        else:
            status = "NORMAL"
            label = "THERMAL RATE NORMAL"
            desc = f"Temperature trajectory is stable ({rate_rounded:+.2f} °C/min)."

        return {
            "dt_dt_c_per_min": rate_rounded,
            "status": status,
            "label": label,
            "description": desc,
            "thresholds": {
                "warning_c_per_min": self.dt_warning_thresh,
                "critical_c_per_min": self.dt_critical_thresh
            }
        }

    def compute_self_discharge(self) -> Dict[str, Any]:
        """
        Calculates dV/dt during verified rest intervals (|I| < 0.05 A).
        Avoids confusing load-induced IR drop with self-discharge.
        """
        if len(self.current_history) < 10:
            return {
                "status": "INSUFFICIENT_DATA",
                "dv_dt_mv_per_hr": None,
                "label": "INSUFFICIENT REST-PERIOD DATA",
                "description": "Insufficient rest-period data for self-discharge assessment."
            }

        # Check if all recent samples are in near-zero load (<0.05 A)
        recent_currents = list(self.current_history)
        is_resting = all(abs(i) < 0.05 for i in recent_currents)

        if not is_resting:
            return {
                "status": "ACTIVE_LOAD",
                "dv_dt_mv_per_hr": None,
                "label": "ACTIVE LOAD / DISCHARGE",
                "description": "Active current flow detected. Self-discharge assessment requires steady rest state."
            }

        delta_t_sec = self.time_history[-1] - self.time_history[0]
        if delta_t_sec < 5.0:  # Minimum 5s rest interval
            return {
                "status": "INSUFFICIENT_DATA",
                "dv_dt_mv_per_hr": None,
                "label": "INSUFFICIENT REST DURATION",
                "description": "Insufficient rest-period data for self-discharge assessment."
            }

        delta_v_volts = self.voltage_history[-1] - self.voltage_history[0]
        # Decay rate in mV per hour (positive means loss of voltage)
        decay_mv_per_hr = (-delta_v_volts * 1000.0 / delta_t_sec) * 3600.0
        decay_rounded = round(float(decay_mv_per_hr), 2)

        if decay_rounded > self.dv_abnormal_thresh:
            status = "ABNORMAL_SELF_DISCHARGE"
            label = "ABNORMAL SELF-DISCHARGE (MICRO-SHORT RISK)"
            desc = f"Elevated open-circuit voltage decay ({decay_rounded:.1f} mV/hr). Possible internal short circuit."
        elif decay_rounded > 5.0:
            status = "ELEVATED_SELF_DISCHARGE"
            label = "ELEVATED SELF-DISCHARGE"
            desc = f"Moderate voltage decay ({decay_rounded:.1f} mV/hr) observed during rest."
        else:
            status = "NORMAL_SELF_DISCHARGE"
            label = "NORMAL SELF-DISCHARGE"
            desc = f"Voltage retention is stable ({decay_rounded:.1f} mV/hr) during rest."

        return {
            "status": status,
            "dv_dt_mv_per_hr": decay_rounded,
            "label": label,
            "description": desc
        }

    def evaluate_comprehensive_safety(
        self,
        telemetry: Dict[str, Any],
        max_safe_temp_c: float = 55.0,
        max_cell_imbalance_v: float = 0.050
    ) -> Tuple[SafetyStatus, List[str], Dict[str, Any]]:
        """
        Executes unified safety audit combining BMS flags, thermal rates, and self-discharge.
        """
        temp = float(telemetry.get("TempMean", 25.0))
        imbalance_v = float(telemetry.get("CellVoltageImbalance", 0.005))
        ts = float(telemetry.get("timestamp", len(self.time_history) * 0.1))
        v_pack = float(telemetry.get("PackVoltage", 32.0))
        i_pack = float(telemetry.get("PackCurrent", 0.0))

        self.push_sample(ts, temp, v_pack, i_pack)
        thermal_res = self.compute_thermal_rate()
        self_discharge_res = self.compute_self_discharge()

        alarms = []
        
        # 1. Hardware BMS fault flags
        bms_fault_keys = [
            ("Fault_OverTemp", "BMS Hardware Over-Temperature Fault"),
            ("Fault_UnderTemp", "BMS Hardware Under-Temperature Fault"),
            ("Fault_OverVoltage", "BMS Hardware Over-Voltage Fault"),
            ("Fault_UnderVoltage", "BMS Hardware Under-Voltage Fault"),
            ("Fault_OverCurrent", "BMS Hardware Over-Current Fault"),
        ]
        for key, name in bms_fault_keys:
            if telemetry.get(key, 0) == 1:
                alarms.append(name)

        # 2. Temperature limits
        if temp > max_safe_temp_c:
            alarms.append(f"Pack Temperature ({temp:.1f} °C) exceeds hard safety threshold ({max_safe_temp_c} °C)")

        # 3. Dynamic thermal rate critical
        if thermal_res["status"] == "CRITICAL":
            alarms.append(f"Thermal Rate Alert: {thermal_res['description']}")

        # 4. Severe cell imbalance
        if imbalance_v > max_cell_imbalance_v:
            alarms.append(f"Cell Voltage Imbalance ({imbalance_v*1000:.1f} mV) exceeds hard limit ({max_cell_imbalance_v*1000} mV)")

        # 5. Abnormal self-discharge
        if self_discharge_res["status"] == "ABNORMAL_SELF_DISCHARGE":
            alarms.append(f"Self-Discharge Alert: {self_discharge_res['description']}")

        # Overall Status
        if len(alarms) > 0:
            status = SafetyStatus.QUARANTINE
        elif temp > 45.0 or imbalance_v > 0.025 or thermal_res["status"] == "WARNING":
            status = SafetyStatus.WARNING
        else:
            status = SafetyStatus.NORMAL

        diagnostics = {
            "thermal_rate": thermal_res,
            "self_discharge": self_discharge_res,
            "active_alarms": alarms,
            "safety_status": status.value,
            "safety_override_active": status == SafetyStatus.QUARANTINE
        }

        return status, alarms, diagnostics
