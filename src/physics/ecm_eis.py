"""
Physics-Informed Virtual Battery & Simulated EIS Laboratory Module.
Implements a 1-RC Randles Equivalent Circuit Model (ECM) parameterized by SOC, Temperature, and SOH.
Generates multi-frequency impedance spectroscopy sweeps (Nyquist & Bode representations),
EIS Fingerprints, Reference comparisons, and EIS-derived diagnostic indicators.

NOTE: All generated spectra are explicitly flagged as SIMULATED_EIS, not measured.
Input comes from Smart fortwo CAN / derived operating state.
"""

from typing import Dict, List, Any, Optional
import math
import numpy as np


class VirtualBatteryECM:
    """
    1-RC Randles Equivalent Circuit Model for EV Li-ion Pack.
    Circuit: R0 + (Rct || Cdl)
    Impedance: Z(omega) = R0 + Rct / (1 + j * omega * Rct * Cdl)
    """

    def __init__(self, r0_base: float = 0.020, rct_base: float = 0.015, cdl_base: float = 2.0):
        self.r0_base = r0_base
        self.rct_base = rct_base
        self.cdl_base = cdl_base

    def calculate_r0(self, soc_norm: float, temp_c: float, soh_norm: float) -> float:
        """
        Ohmic resistance (electrolyte + tabs + bulk current collectors).
        Rises with degradation (1-SOH), cold temperatures (<25°C), and low SOC (<20%).
        """
        soh_clamped = max(0.40, min(1.0, float(soh_norm)))
        soc_clamped = max(0.0, min(1.0, float(soc_norm)))
        degradation_factor = 1.0 + (1.0 - soh_clamped) * 2.0
        temp_factor = 1.0 + max(0.0, (25.0 - temp_c)) * 0.015
        soc_factor = 1.0 + (1.0 - soc_clamped) * 0.15
        return float(self.r0_base * degradation_factor * temp_factor * soc_factor)

    def calculate_rct(self, soc_norm: float, temp_c: float, soh_norm: float) -> float:
        """
        Charge transfer resistance across the electrode/electrolyte interface (SEI layer).
        Highly sensitive to SEI thickening and lithium plating degradation.
        """
        soh_clamped = max(0.40, min(1.0, float(soh_norm)))
        degradation_factor = 1.0 + (1.0 - soh_clamped) * 4.0
        temp_factor = 1.0 + max(0.0, (25.0 - temp_c)) * 0.025
        return float(self.rct_base * degradation_factor * temp_factor)

    def calculate_cdl(self, soh_norm: float) -> float:
        """
        Electrochemical double-layer capacitance.
        Gradually decreases as active electrode surface area is lost to degradation.
        """
        soh_clamped = max(0.40, min(1.0, float(soh_norm)))
        return float(self.cdl_base * (0.70 + 0.30 * soh_clamped))

    def compute_impedance_spectrum(
        self,
        soc_norm: float,
        temp_c: float,
        soh_norm: float,
        f_min: float = 0.01,
        f_max: float = 10000.0,
        n_points: int = 60
    ) -> Dict[str, Any]:
        """
        Generates simulated logarithmic frequency sweep from f_min (0.01 Hz) to f_max (10 kHz).
        Returns full Nyquist and Bode spectrum datasets.
        """
        r0 = self.calculate_r0(soc_norm, temp_c, soh_norm)
        rct = self.calculate_rct(soc_norm, temp_c, soh_norm)
        cdl = self.calculate_cdl(soh_norm)

        freqs = np.logspace(np.log10(f_min), np.log10(f_max), n_points)
        omega = 2.0 * np.pi * freqs

        # Complex impedance: Z = R0 + Rct / (1 + j*omega*Rct*Cdl)
        denom = 1.0 + np.square(omega * rct * cdl)
        z_real = r0 + (rct / denom)
        z_imag = (omega * np.square(rct) * cdl) / denom

        magnitude = np.sqrt(np.square(z_real) + np.square(z_imag))
        phase_deg = -np.arctan2(z_imag, z_real) * (180.0 / np.pi)

        spectrum_points = []
        for f, zr, zi, zm, ph in zip(freqs, z_real, z_imag, magnitude, phase_deg):
            spectrum_points.append({
                "freq_hz": round(float(f), 4),
                "z_real_mohm": round(float(zr * 1000.0), 3),
                "z_imag_neg_mohm": round(float(zi * 1000.0), 3),
                "z_mag_mohm": round(float(zm * 1000.0), 3),
                "phase_deg": round(float(ph), 2)
            })

        return {
            "r0_ohm": round(r0, 6),
            "rct_ohm": round(rct, 6),
            "cdl_farad": round(cdl, 4),
            "z_lowfreq_ohm": round(float(magnitude[0]), 6),
            "phase_lowfreq_deg": round(float(phase_deg[0]), 2),
            "frequency_hz": freqs.tolist(),
            "z_real_ohm": z_real.tolist(),
            "z_imag_ohm": z_imag.tolist(),
            "magnitude_ohm": magnitude.tolist(),
            "phase_deg": phase_deg.tolist(),
            "spectrum_points": spectrum_points,
            "is_simulated": True,
            "data_category": "SIMULATED_EIS",
            "model_type": "Single-RC Randles ECM"
        }

    def extract_fingerprint(self, spectrum: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts key EIS Fingerprint diagnostic metrics from spectrum:
        - R0, Rct, Cdl
        - Characteristic relaxation frequency fc = 1 / (2*pi*Rct*Cdl)
        - Magnitude |Z| and phase at selected frequencies (0.1, 1, 10, 100, 1k, 10k Hz)
        """
        r0_ohm = spectrum["r0_ohm"]
        rct_ohm = spectrum["rct_ohm"]
        cdl_farad = spectrum["cdl_farad"]

        # Characteristic relaxation frequency
        fc_hz = 1.0 / (2.0 * math.pi * rct_ohm * cdl_farad) if (rct_ohm * cdl_farad) > 0 else 0.0

        freqs = np.array(spectrum["frequency_hz"])
        mags = np.array(spectrum["magnitude_ohm"])
        phases = np.array(spectrum["phase_deg"])

        target_freqs = [0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]
        selected_points = []

        for target in target_freqs:
            idx = int(np.argmin(np.abs(freqs - target)))
            actual_f = freqs[idx]
            mag_mohm = round(float(mags[idx] * 1000.0), 2)
            phase_deg = round(float(phases[idx]), 2)
            selected_points.append({
                "target_frequency_hz": target,
                "actual_frequency_hz": round(float(actual_f), 2),
                "freq_hz": round(float(actual_f), 2),
                "magnitude_mohm": mag_mohm,
                "z_mag_mohm": mag_mohm,
                "phase_deg": phase_deg
            })

        return {
            "r0_mohm": round(r0_ohm * 1000.0, 2),
            "rct_mohm": round(rct_ohm * 1000.0, 2),
            "cdl_farad": round(cdl_farad, 3),
            "characteristic_frequency_fc_hz": round(fc_hz, 2),
            "fc_hz": round(fc_hz, 2),
            "selected_frequency_points": selected_points,
            "selected_points": selected_points,
            "provenance": "MODEL-DERIVED / SIMULATED"
        }

    def evaluate_reference_spectrum(self, f_min: float = 0.01, f_max: float = 10000.0, n_points: int = 60) -> Dict[str, Any]:
        """
        Computes reference healthy model state spectrum (SOH=100%, SOC=80%, Temp=25°C).
        Reference R0 = 20.1 mΩ, Rct = 18.0 mΩ.
        """
        ref_spectrum = self.compute_impedance_spectrum(
            soc_norm=0.80,
            temp_c=25.0,
            soh_norm=1.00,
            f_min=f_min,
            f_max=f_max,
            n_points=n_points
        )
        ref_fingerprint = self.extract_fingerprint(ref_spectrum)
        return {
            "spectrum": ref_spectrum,
            "fingerprint": ref_fingerprint,
            "soh_pct": 100.0,
            "soc_pct": 80.0,
            "temp_c": 25.0,
            "label": "Defined Healthy Nominal Reference State"
        }

    def evaluate_laboratory_state(
        self,
        soc_norm: float = 0.80,
        temp_c: float = 25.3,
        soh_norm: float = 0.884,
        telemetry_meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Runs complete EIS Fingerprint & Impedance Intelligence Laboratory evaluation.
        Produces current spectrum, reference comparison, fingerprint, and health correlation indicators.
        """
        soc_pct = round(soc_norm * 100.0, 1)
        soh_pct = round(soh_norm * 100.0 if soh_norm <= 1.0 else soh_norm, 1)

        # Current spectrum & fingerprint
        current_spectrum_dict = self.compute_impedance_spectrum(soc_norm=soc_norm, temp_c=temp_c, soh_norm=soh_norm / 100.0 if soh_norm > 1.0 else soh_norm)
        current_fingerprint = self.extract_fingerprint(current_spectrum_dict)

        # Reference spectrum & fingerprint
        ref_data = self.evaluate_reference_spectrum()
        ref_fingerprint = ref_data["fingerprint"]
        ref_spectrum_dict = ref_data["spectrum"]

        # Fingerprint Deviation Calculations
        r0_curr = current_fingerprint["r0_mohm"]
        r0_ref = ref_fingerprint["r0_mohm"]
        r0_dev_pct = round(((r0_curr - r0_ref) / r0_ref) * 100.0, 1)

        rct_curr = current_fingerprint["rct_mohm"]
        rct_ref = ref_fingerprint["rct_mohm"]
        rct_dev_pct = round(((rct_curr - rct_ref) / rct_ref) * 100.0, 1)

        cdl_curr = current_fingerprint["cdl_farad"]
        cdl_ref = ref_fingerprint["cdl_farad"]
        cdl_dev_pct = round(((cdl_curr - cdl_ref) / cdl_ref) * 100.0, 1)

        fc_curr = current_fingerprint["fc_hz"]
        fc_ref = ref_fingerprint["fc_hz"]
        fc_dev_pct = round(((fc_curr - fc_ref) / fc_ref) * 100.0, 1)

        # Selected frequency deviations
        freq_deviations = []
        for curr_pt, ref_pt in zip(current_fingerprint["selected_frequency_points"], ref_fingerprint["selected_frequency_points"]):
            m_curr = curr_pt["magnitude_mohm"]
            m_ref = ref_pt["magnitude_mohm"]
            m_dev = round(((m_curr - m_ref) / m_ref) * 100.0, 1)
            freq_deviations.append({
                "frequency_hz": curr_pt["target_frequency_hz"],
                "reference_magnitude_mohm": m_ref,
                "current_magnitude_mohm": m_curr,
                "deviation_pct": m_dev
            })

        deviation_assessment = {
            "r0_deviation_pct": r0_dev_pct,
            "rct_deviation_pct": rct_dev_pct,
            "selected_frequency_deviations": freq_deviations,
            "label": "Model-based EIS fingerprint deviation",
            "scientific_disclaimer": "Model-based EIS fingerprint deviation represents mathematical 1-RC ECM state shifts relative to a defined 100% SOH reference. It is not an experimentally measured cell degradation value."
        }

        ref_comparison_list = [
            {"parameter": "Ohmic Resistance (R₀)", "reference_val": f"{r0_ref:.1f}", "current_val": f"{r0_curr:.1f}", "unit": "mΩ", "deviation_pct": r0_dev_pct},
            {"parameter": "Charge Transfer (Rct)", "reference_val": f"{rct_ref:.1f}", "current_val": f"{rct_curr:.1f}", "unit": "mΩ", "deviation_pct": rct_dev_pct},
            {"parameter": "Double-Layer Cap. (Cdl)", "reference_val": f"{cdl_ref:.2f}", "current_val": f"{cdl_curr:.2f}", "unit": "F", "deviation_pct": cdl_dev_pct},
            {"parameter": "Characteristic Freq (f_c)", "reference_val": f"{fc_ref:.2f}", "current_val": f"{fc_curr:.2f}", "unit": "Hz", "deviation_pct": fc_dev_pct}
        ]

        # EIS-Derived Diagnostic Indicators
        if r0_dev_pct > 25.0:
            r0_trend_label = f"ELEVATED (+{r0_dev_pct}% vs reference)"
        elif r0_dev_pct > 10.0:
            r0_trend_label = f"MODERATE (+{r0_dev_pct}% vs reference)"
        else:
            r0_trend_label = f"NOMINAL (+{r0_dev_pct}% vs reference)"

        if rct_dev_pct > 25.0:
            rct_trend_label = f"KINETIC SLOWING (+{rct_dev_pct}% vs reference)"
        else:
            rct_trend_label = f"STABLE KINETICS (+{rct_dev_pct}% vs reference)"

        diagnostic_indicators = {
            "r0_trend": r0_trend_label,
            "rct_trend": rct_trend_label,
            "impedance_magnitude_shift": f"+{r0_dev_pct:.1f}% low-frequency magnitude shift",
            "fingerprint_deviation_score": round((r0_dev_pct + rct_dev_pct) / 2.0, 1),
            "label": "EIS-derived diagnostic indicators"
        }

        health_indicators_list = [
            {
                "name": "Electrolyte & Ohmic Integrity (R₀)",
                "status": "GOOD" if abs(r0_dev_pct) < 15 else ("MODERATE" if abs(r0_dev_pct) < 30 else "ELEVATED"),
                "value": f"{r0_curr:.2f} mΩ ({r0_dev_pct:+.1f}% vs baseline)",
                "description": f"Baseline {r0_ref:.1f} mΩ at 100% SOH. Ohmic growth indicates electrolyte degradation."
            },
            {
                "name": "SEI & Charge Transfer Kinetics (Rct)",
                "status": "GOOD" if abs(rct_dev_pct) < 20 else ("MODERATE" if abs(rct_dev_pct) < 40 else "ELEVATED"),
                "value": f"{rct_curr:.2f} mΩ ({rct_dev_pct:+.1f}% vs baseline)",
                "description": f"Baseline {rct_ref:.1f} mΩ. Rct growth reflects interfacial charge transfer slowing & SEI thickening."
            },
            {
                "name": "Electrode Surface Area Loss (Cdl)",
                "status": "GOOD" if soh_pct >= 85 else ("MODERATE" if soh_pct >= 70 else "ELEVATED"),
                "value": f"{cdl_curr:.2f} F",
                "description": "Double-layer capacitance tracks active surface area available for electrochemical reactions."
            },
            {
                "name": "Characteristic Relaxation Frequency (f_c)",
                "status": "GOOD" if fc_curr > 2.5 else "MODERATE",
                "value": f"{fc_curr:.2f} Hz",
                "description": "Frequency where imaginary impedance reaches peak arc magnitude."
            }
        ]

        # Operating State Context
        operating_state = {
          "soc_pct": soc_pct,
          "temp_c": round(temp_c, 1),
          "soh_pct": soh_pct,
          "soh_source": "Model Estimate / CAN Input",
          "can_verification_status": "Smart fortwo CAN decoded parameters (SOC, Temp)",
          "cell_imbalance_v": round(float((telemetry_meta or {}).get("CellVoltageImbalance", 0.007)), 4)
        }

        return {
            "operating_state": operating_state,
            "spectrum": current_spectrum_dict["spectrum_points"],
            "spectrum_raw": current_spectrum_dict,
            "fingerprint": current_fingerprint,
            "reference": {
                "r0_mohm": ref_fingerprint["r0_mohm"],
                "rct_mohm": ref_fingerprint["rct_mohm"],
                "cdl_farad": ref_fingerprint["cdl_farad"],
                "fc_hz": ref_fingerprint["characteristic_frequency_fc_hz"],
                "selected_frequency_points": ref_fingerprint["selected_frequency_points"],
                "soh_pct": 100.0,
                "soc_pct": 80.0,
                "temp_c": 25.0
            },
            "reference_spectrum": ref_spectrum_dict["spectrum_points"],
            "deviation": deviation_assessment,
            "reference_comparison": ref_comparison_list,
            "diagnostic_indicators": diagnostic_indicators,
            "health_indicators": health_indicators_list,
            "provenance": {
                "eis_type": "SIMULATED",
                "model": "1-RC RANDLES ECM",
                "input": "SMART FORTWO CAN / DERIVED OPERATING STATE",
                "badges": {
                    "soc": "REAL CAN / DERIVED",
                    "temperature": "REAL CAN DATA",
                    "soh": "MODEL ESTIMATE",
                    "eis": "SIMULATED EIS"
                }
            }
        }
