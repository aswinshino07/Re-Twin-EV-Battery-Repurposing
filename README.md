# RE-TWIN: Second-Life EV Battery Repurposing Platform
### *EIS-Fingerprint & Physics-Informed Digital Twin for Intelligent Repurposing Decisions*

---

## 1. Executive Summary & Core Value Proposition

When electric vehicles are retired, their battery packs typically retain **70% to 85% of their initial capacity**. Decommissioning these packs directly to shredders for recycling is economically wasteful and carbon-intensive. However, repurposing degraded packs without rigorous safety and electrochemical screening presents severe thermal runaway hazards.

**The Central Question RE-TWIN Solves:**
> *"Given the condition and remaining capability of a retired EV battery, what is the safest and most suitable second-life application for it?"*

**Core Product Value:**
**RE-TWIN converts raw battery CAN telemetry and operational condition data into an explainable, certified second-life reuse decision.**

---

## 2. Scientific Integrity & Data Classification

RE-TWIN enforces strict classification across every metric:

| Category | Description & Role in RE-TWIN |
| :--- | :--- |
| **1. Measured Data** | Physical laboratory test bench measurements (when connected to external cyclers). |
| **2. Recorded Telemetry** | Raw CAN frames (Voltage, Current, Cell Voltages 1–8, Module Temps 1–4, Fault bitflags). |
| **3. Derived Features** | Coulomb-integrated SOC, cumulative Ah throughput, cell imbalance ($\Delta V$), thermal spread. |
| **4. Simulated EIS** | Physics-informed 1-RC Randles equivalent circuit model ($R_0, R_{ct}, C_{dl}$, Nyquist & Bode). |
| **5. Estimated Values** | Usable capacity ($C_{\text{rem}}$ in Ah), usable energy ($E_{\text{rem}}$ in kWh), RUL cycles. |
| **6. AI Predictions** | Interpretable Linear Regression SOH estimation with transparent feature attribution. |
| **7. Recommendations** | Multi-criteria Repurposing Score (RPS: 0–100) and 6-Tier Second-Life Decision Engine. |

> [!IMPORTANT]
> **Scientific Scope:** The included CAN dataset is synthetic, and the EIS spectrum is model-simulated (not measured on a potentiostat). Simulated values and synthetic demo targets are explicitly flagged across all code, reports, and UI screens.

---

## 3. Product Architecture & 18 Core Modules

```
CAN DATA 
  → DBC DECODING (cantools / Pure-Python Fallback)
  → SYNCHRONIZED BATTERY STATE (Coulomb Counting + Aggregation)
  → HEALTH + SAFETY + EIS FEATURES (1-RC Randles ECM)
  → AI HEALTH ASSESSMENT (Interpretable Linear Regression)
  → REPURPOSING SCORE (Multi-Criteria RPS 0-100)
  → APPLICATION MATCHING (6-Tier Decision Hierarchy)
  → DIGITAL TWIN (Physical, Electrochemical & Economic State)
  → USER DASHBOARD (6-Tab Dark-Mode Control Center)
  → BATTERY REPORT & PASSPORT (EU Circular Economy Ready)
```

### Module Breakdown
1. **Battery Data Ingestion:** CSV logs, high-speed replay (1x–100x), live SocketCAN/PCAN/Vector hardware.
2. **CAN/DBC Decoder:** `ev_bms.dbc` decoder with pure-Python fallback.
3. **Battery State Reconstruction:** Synchronized temporal alignment and forward-fill.
4. **Feature Engineering:** Coulomb-counting SOC, charge throughput (Ah), cell divergence ($\Delta V$).
5. **Battery Health Assessment:** Thermal stress, C-rate stress, and ohmic degradation tracking.
6. **Capacity Estimation:** Remaining usable capacity ($Ah$) and energy ($kWh$).
7. **EIS Simulation Module:** 1-RC Randles ECM generating 50-point sweeps (0.01 Hz to 100 kHz).
8. **Anomaly & Safety Detection:** OverVoltage, UnderVoltage, OverTemp, UnderTemp, OverCurrent, and Quarantine interlock.
9. **SOH Prediction:** Interpretable Linear Regression with explicit feature weights.
10. **RUL Estimation:** Multi-profile cycle life projections (Gentle, Standard, Aggressive).
11. **Repurposing Score (RPS):** Weighted multi-criteria index (SOH, Capacity, RUL, Safety, Cell Balance).
12. **Application Suitability Engine:** 6-Tier decision router with commercial justification.
13. **Digital Twin Core:** Unified Python state object combining all telemetry, ECM, and decision parameters.
14. **What-If Scenario Simulator:** Interactive simulator for ambient temperatures ($0-50^\circ\text{C}$), C-rates, and multi-year degradation trajectories.
15. **Battery Passport:** EU Circular Economy Digital Battery Passport with avoided $\text{CO}_2\text{e}$ metrics.
16. **Assessment Report:** Standalone printable HTML Battery Health Certificate.
17. **Professional Web Dashboard:** Modern dark-mode UI with live charts, Nyquist/Bode plots, and telemetry tables.

---

## 4. 6-Tier Second-Life Decision Architecture

| Tier | SOH Threshold | Usable Capacity (50Ah Pack) | Recommended Second-Life Application |
| :--- | :--- | :--- | :--- |
| **Tier 1** | $\ge 90\%$ | $\ge 45.0\text{ Ah}$ | High-demand stationary storage (grid peak shaving, fast frequency regulation) |
| **Tier 2** | $80\% - 90\%$ | $40.0 - 45.0\text{ Ah}$ | Solar & commercial storage (C&I peak shaving, EV charging buffer) |
| **Tier 3** | $70\% - 80\%$ | $35.0 - 40.0\text{ Ah}$ | Home backup / UPS / telecom tower backup power |
| **Tier 4** | $60\% - 70\%$ | $30.0 - 35.0\text{ Ah}$ | Low-power off-grid applications (light utility EVs, solar streetlights) |
| **Tier 5** | $< 60\%$ | $< 30.0\text{ Ah}$ | Direct recycling & material recovery (Lithium, Nickel, Cobalt extraction) |
| **Tier 0** | Any SOH | Any Capacity | **Safety Isolation & Inspection (Quarantine)** |

---

## 5. Quick Start & Execution Guide

### 1. Installation
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Run Complete Batch Assessment Pipeline
```bash
python src/main.py
```
*Outputs generated in `output/`:*
- `decoded_frames.csv`: Decoded raw CAN signals
- `battery_features.csv`: Synchronized time-step states with Coulomb counting
- `predictions.csv`: Operational features with SOH estimates
- `simulated_eis.csv`: 50-point simulated EIS spectra
- `digital_twin.csv` / `fused_features.csv`: Full Digital Twin evaluation
- `battery_passport_report.html`: Exportable Digital Battery Passport

### 3. Run What-If Scenario Simulation
```bash
python src/main.py --what-if
```

### 5. Launch Interactive Web Dashboard & REST API
```bash
python serve_dashboard.py
```
Open your browser at **`http://localhost:8050/dashboard.html`**.

### 6. Real-Time Streaming Mode
```bash
# Replay recorded drive cycle at 20x speed:
python src/realtime_pipeline.py --replay data/ev_pack_drive.csv --speed 20

# Or connect to a real CAN hardware interface:
python src/realtime_pipeline.py --live-channel can0
```

---

## 6. Project Structure

```
RE-TWIN/
├── data/
│   ├── ev_bms.dbc                    # DBC CAN database definition
│   ├── ev_pack_drive.csv             # Synthetic drive-cycle CAN log
│   ├── sample_pack_b.csv             # Moderate aging pack sample
│   └── sample_pack_c_fault.csv       # Fault-injected pack sample
├── models/
│   └── soh_linear_regression.joblib  # Trained interpretable ML model
├── output/                           # Generated evaluation logs & reports
├── src/
│   ├── core/                         # State contracts, decoder & feature engine
│   ├── physics/                      # 1-RC Randles ECM & simulated EIS
│   ├── ml/                           # Interpretable Linear Regression predictor
│   ├── decision/                     # Safety audit, RPS, capacity & tier router
│   ├── twin/                         # Digital Twin core, What-If & Passport
│   ├── realtime/                     # Live CAN streaming & rolling tracker
│   └── main.py                       # Master CLI entrypoint
├── dashboard.html                    # 6-Tab Enterprise Web Dashboard
├── serve_dashboard.py                # Local web & REST API server
├── run_simulation.py                 # Real-time simulation launcher
└── requirements.txt                  # Dependencies
```

## Real Smart fortwo CAN Dataset

The project also includes a source-grounded real-vehicle CAN dataset under `data/smart_fortwo/`. The supplied source README documents CAN access through the OBD port and confirms an SOC decoder for CAN ID `0x2D5`, plus charging-current-limit diagnostic examples for IDs `0x483`, `0x512`, and `0x61A`.

`src/smart_fortwo_can_decoder.py` intentionally decodes only these documented signals. It does not guess pack voltage, pack current, cell voltages, temperatures, SOH, or RUL from undocumented IDs. See `data/smart_fortwo/SMART_FORTWO_SIGNAL_MAP.md` for the exact scope and limitations.
