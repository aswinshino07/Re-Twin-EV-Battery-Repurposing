
import numpy as np

def ohmic_resistance(soc, temp_c, soh):
    r0_base = 0.020
    degradation_factor = 1 + (1 - soh) * 2.0
    temp_factor = 1 + max(0.0, (25 - temp_c)) * 0.01
    soc_factor = 1 + (1 - soc) * 0.15
    return r0_base * degradation_factor * temp_factor * soc_factor

def charge_transfer_resistance(soc, temp_c, soh):
    rct_base = 0.015
    degradation_factor = 1 + (1 - soh) * 4.0
    temp_factor = 1 + max(0.0, (25 - temp_c)) * 0.02
    return rct_base * degradation_factor * temp_factor

def double_layer_capacitance(soh):
    return 2.0 * (0.7 + 0.3 * soh)

def impedance(freq_hz, r0, rct, cdl):
    omega = 2 * np.pi * freq_hz
    z_rc = rct / (1 + 1j * omega * rct * cdl)
    return r0 + z_rc

def simulate_eis(soc, temp_c, soh, f_min=0.01, f_max=1e5, n_points=50):
    freqs = np.logspace(np.log10(f_min), np.log10(f_max), n_points)
    r0 = ohmic_resistance(soc, temp_c, soh)
    rct = charge_transfer_resistance(soc, temp_c, soh)
    cdl = double_layer_capacitance(soh)
    z = impedance(freqs, r0, rct, cdl)
    return {
        "frequency_hz": freqs,
        "impedance_magnitude_ohm": np.abs(z),
        "phase_deg": np.angle(z, deg=True),
        "r0_ohm": r0,
        "rct_ohm": rct,
        "cdl_farad": cdl,
        "label": "SIMULATED_EIS",
    }
