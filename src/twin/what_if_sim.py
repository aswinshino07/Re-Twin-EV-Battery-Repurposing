"""
What-If Scenario Simulation Engine.
Simulates hypothetical battery operating environments (temperature, C-rate, target duty cycles)
and projects second-life degradation, RUL, and economic viability.
"""

from typing import Dict, Any, List
from src.core.battery_state import BatteryPackSpec, ApplicationTier, SafetyStatus
from src.twin.digital_twin_core import DigitalTwinEngine


class WhatIfSimulator:
    def __init__(self, twin_engine: DigitalTwinEngine = None):
        self.twin = twin_engine or DigitalTwinEngine()

    def simulate_scenario(
        self,
        base_soh: float = 0.88,
        ambient_temp_c: float = 25.0,
        c_rate: float = 0.5,
        target_application: str = "Solar Energy Storage",
        cycles_per_year: int = 365,
        project_years: int = 5
    ) -> Dict[str, Any]:
        """
        Simulates dynamic battery degradation trajectory under hypothetical operating conditions.
        """
        # 1. Calculate degradation acceleration factors
        # Thermal acceleration (Arrhenius-like penalty for high temperatures, electrolyte freeze at <10°C)
        if ambient_temp_c >= 25.0:
            thermal_penalty = 1.0 + ((ambient_temp_c - 25.0) / 20.0) * 0.40
        else:
            thermal_penalty = 1.0 + ((25.0 - ambient_temp_c) / 25.0) * 0.20

        # C-rate stress (Joule heating and mechanical electrode strain)
        c_rate_penalty = 1.0 + max(0.0, (c_rate - 0.5)) * 0.60

        # Composite yearly degradation rate (% SOH loss per 100 cycles)
        base_fade_per_100_cycles = 0.008  # 0.8% SOH per 100 gentle cycles
        effective_fade_rate = base_fade_per_100_cycles * thermal_penalty * c_rate_penalty

        # Project multi-year degradation trajectory
        yearly_projection = []
        current_soh = base_soh
        total_cycles = 0

        for year in range(1, project_years + 1):
            cycles_this_year = cycles_per_year
            total_cycles += cycles_this_year
            soh_loss = (cycles_this_year / 100.0) * effective_fade_rate
            current_soh = max(0.50, current_soh - soh_loss)

            cap_ah, energy_kwh = self.twin.capacity_calculator.calculate_usable_capacity_and_energy(current_soh)
            status, _ = self.twin.safety_checker.evaluate_safety({
                "TempMean": ambient_temp_c,
                "CellVoltageImbalance": 0.005 + (1.0 - current_soh) * 0.020
            })
            rps, _ = self.twin.rps_calculator.calculate_score(
                soh=current_soh,
                remaining_capacity_ah=cap_ah,
                safety_status=status,
                temp_mean_c=ambient_temp_c
            )
            tier, _ = self.twin.app_router.route_application(
                soh=current_soh,
                remaining_capacity_ah=cap_ah,
                safety_status=status,
                rps=rps,
                temp_mean_c=ambient_temp_c
            )

            yearly_projection.append({
                "year": year,
                "cumulative_cycles": total_cycles,
                "projected_soh_pct": round(current_soh * 100.0, 2),
                "usable_capacity_ah": cap_ah,
                "usable_energy_kwh": energy_kwh,
                "projected_rps": rps,
                "recommended_tier": tier.value,
                "is_usable": current_soh >= 0.60 and status != SafetyStatus.QUARANTINE
            })

        # Calculate estimated second-life economic residual value
        # Battery energy value: ~$120/kWh for second-life stationary storage
        nominal_kwh = yearly_projection[0]["usable_energy_kwh"]
        residual_value_usd = round(nominal_kwh * 120.0 * (base_soh / 1.0), 2)
        annual_energy_throughput_kwh = round(cycles_per_year * nominal_kwh * 0.90, 1)

        return {
            "parameters": {
                "base_soh": base_soh,
                "ambient_temp_c": ambient_temp_c,
                "c_rate": c_rate,
                "target_application": target_application,
                "cycles_per_year": cycles_per_year,
                "project_years": project_years
            },
            "stress_multipliers": {
                "thermal_acceleration": round(thermal_penalty, 2),
                "c_rate_acceleration": round(c_rate_penalty, 2),
                "effective_fade_per_100_cycles_pct": round(effective_fade_rate * 100.0, 3)
            },
            "economics": {
                "estimated_pack_residual_value_usd": residual_value_usd,
                "annual_throughput_kwh": annual_energy_throughput_kwh,
                "estimated_payback_years": round(residual_value_usd / (annual_energy_throughput_kwh * 0.12), 1)
            },
            "yearly_projection": yearly_projection
        }

    def simulate_battery_parameters(
        self,
        soh: float = 0.86,
        soc: float = 80.0,
        rated_capacity_ah: float = 50.0,
        remaining_capacity_ah: float = None,
        temperature_c: float = 28.0,
        cell_imbalance_v: float = 0.008,
        r0_ohm: float = 0.0255,
        rct_ohm: float = 0.0220,
        rul_cycles: int = None,
        fault_flags: Dict[str, bool] = None,
        safety_status: str = "NORMAL",
        dt_dt_c_per_min: float = 0.0
    ) -> Dict[str, Any]:
        """
        Interactive What-If Single State Battery Simulator.
        Instantly recalculates second-life suitability, repurposing score, safety risk,
        usable energy, and explainable decision rationale for user-adjusted parameters
        without modifying the underlying dataset.
        """
        soh_val = max(0.0, min(1.0, float(soh)))
        soc_val = max(0.0, min(100.0, float(soc)))
        rated_ah = float(rated_capacity_ah) if rated_capacity_ah > 0 else 50.0
        
        if remaining_capacity_ah is None or remaining_capacity_ah <= 0:
            rem_ah = round(rated_ah * soh_val, 2)
        else:
            rem_ah = float(remaining_capacity_ah)

        nom_v = self.twin.spec.nominal_voltage_v
        usable_energy_kwh = round((nom_v * rem_ah) / 1000.0, 3)

        if rul_cycles is None:
            rul_cycles = max(0, int((soh_val - 0.60) * 7500)) if soh_val > 0.60 else 0

        # Safety & Fault flags parsing
        faults_active = []
        if fault_flags:
            for k, v in fault_flags.items():
                if v:
                    faults_active.append(k.replace("Fault_", ""))

        # Determine safety status
        if faults_active or temperature_c > self.twin.spec.max_safe_temp_c or cell_imbalance_v > self.twin.spec.max_cell_imbalance_v or dt_dt_c_per_min >= 1.0:
            effective_status = SafetyStatus.QUARANTINE
            risk_label = "CRITICAL SAFETY INTERLOCK"
        elif safety_status == "QUARANTINE":
            effective_status = SafetyStatus.QUARANTINE
            risk_label = "CRITICAL SAFETY INTERLOCK"
        elif safety_status == "WARNING" or cell_imbalance_v > 0.025 or temperature_c > 45.0 or dt_dt_c_per_min >= 0.5:
            effective_status = SafetyStatus.WARNING
            risk_label = "MODERATE RISK / ATTENTION"
        else:
            effective_status = SafetyStatus.NORMAL
            risk_label = "LOW RISK / SAFE"

        # Construct BatteryCapability for RepurposingEngine
        from src.decision.repurposing_engine import BatteryCapability
        capability = BatteryCapability(
            soh=soh_val,
            remaining_capacity_ah=rem_ah,
            usable_energy_kwh=usable_energy_kwh,
            temperature_c=float(temperature_c),
            cell_imbalance_v=float(cell_imbalance_v),
            bms_fault_active=len(faults_active) > 0 or effective_status == SafetyStatus.QUARANTINE,
            bms_fault_details=faults_active,
            rul_cycles=rul_cycles,
            safety_status=effective_status,
            internal_resistance_mohm=r0_ohm * 1000.0 if r0_ohm < 1.0 else r0_ohm,
            nominal_voltage_v=nom_v,
            rated_capacity_ah=rated_ah,
            rated_energy_kwh=round((nom_v * rated_ah) / 1000.0, 3)
        )

        assessment = self.twin.repurposing_engine.evaluate_battery(capability)

        # Health Grade
        if soh_val >= 0.90:
            soh_grade = "Grade A+ (Pristine / Utility Grade)"
        elif soh_val >= 0.80:
            soh_grade = "Grade A (Good / Commercial Grade)"
        elif soh_val >= 0.70:
            soh_grade = "Grade B (Moderate / Residential Grade)"
        elif soh_val >= 0.60:
            soh_grade = "Grade C (Degraded / Low-Duty Grade)"
        else:
            soh_grade = "Grade D (End-of-Life / Recycling)"

        # Compute dynamic simulated EIS spectrum
        eis_spectrum = self.twin.ecm.compute_impedance_spectrum(
            soc_norm=soc_val / 100.0,
            temp_c=temperature_c,
            soh_norm=soh_val,
            n_points=35
        )

        return {
            "simulation_label": "WHAT-IF SIMULATION",
            "is_what_if": True,
            "original_dataset_modified": False,
            "inputs": {
                "soh": round(soh_val, 4),
                "soh_pct": round(soh_val * 100.0, 2),
                "soc_pct": round(soc_val, 1),
                "rated_capacity_ah": rated_ah,
                "remaining_capacity_ah": rem_ah,
                "temperature_c": round(temperature_c, 1),
                "cell_imbalance_v": round(cell_imbalance_v, 4),
                "cell_imbalance_mv": round(cell_imbalance_v * 1000.0, 1),
                "r0_mohm": round(r0_ohm * 1000.0 if r0_ohm < 1.0 else r0_ohm, 2),
                "rct_mohm": round(rct_ohm * 1000.0 if rct_ohm < 1.0 else rct_ohm, 2),
                "rul_cycles": rul_cycles,
                "fault_flags": fault_flags or {},
                "safety_status": effective_status.value
            },
            "health_status": {
                "soh_pct": round(soh_val * 100.0, 2),
                "soh_grade": soh_grade,
                "capacity_retention_pct": round((rem_ah / rated_ah) * 100.0, 1),
                "usable_energy_kwh": usable_energy_kwh
            },
            "safety_risk": {
                "risk_level": risk_label,
                "safety_status": effective_status.value,
                "is_safe": effective_status != SafetyStatus.QUARANTINE,
                "active_faults": faults_active,
                "safety_override_triggered": assessment.safety_override_triggered,
                "thermal_rate_critical": dt_dt_c_per_min >= 1.0
            },
            "decision": {
                "repurposing_score": assessment.repurposing_score,
                "score_breakdown": assessment.score_breakdown,
                "suitability_category": assessment.suitability_category.value,
                "recommended_application": assessment.recommended_application,
                "recommended_tier": assessment.recommended_tier,
                "is_suitable_for_second_life": assessment.is_suitable_for_second_life,
                "recommendation_summary": assessment.recommendation_summary,
                "reasons": assessment.reasons,
                "unsuitable_reasons": assessment.unsuitable_reasons,
                "application_evaluations": {
                    k: v.to_dict() for k, v in assessment.application_evaluations.items()
                },
                "all_warnings": assessment.all_warnings
            },
            "eis_spectrum": {
                "r0_mohm": round(eis_spectrum["r0_ohm"] * 1000.0, 2),
                "rct_mohm": round(eis_spectrum["rct_ohm"] * 1000.0, 2),
                "cdl_farad": round(eis_spectrum["cdl_farad"], 2),
                "frequency_hz": eis_spectrum["frequency_hz"],
                "z_real_ohm": eis_spectrum["z_real_ohm"],
                "z_imag_ohm": eis_spectrum["z_imag_ohm"],
                "magnitude_ohm": eis_spectrum["magnitude_ohm"],
                "phase_deg": eis_spectrum["phase_deg"]
            }
        }
