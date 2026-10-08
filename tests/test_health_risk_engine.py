"""
Unit tests for RE-TWIN Health & Risk Diagnostic & Prognostics Engine.
Verifies vitals, degradation analysis, anomaly intelligence, stress metrics,
EIS health indicators, RUL uncertainty, risk matrix, early warnings, provenance,
and strict separation from Second-Life Decision engine.
"""

import pytest
from src.core.battery_state import BatteryPackSpec
from src.twin.digital_twin_core import DigitalTwinEngine
from src.twin.health_risk_engine import HealthRiskEngine


@pytest.fixture
def twin_engine():
    spec = BatteryPackSpec()
    return DigitalTwinEngine(spec=spec)


def test_health_risk_engine_evaluation(twin_engine):
    telemetry = {
        "PackVoltage": 31.16,
        "PackCurrent": 1.9,
        "PackPower_W": 59.2,
        "SOC": 66.7,
        "TempMean": 25.3,
        "CellVoltageImbalance": 0.007,
        "Throughput_Ah": 124.0
    }

    res = twin_engine.evaluate_health_and_risk(telemetry, soh_override=0.884)

    # 1. Verify Vitals
    assert "vitals" in res
    vitals = res["vitals"]
    assert vitals["soh"]["value"] == 88.4
    assert vitals["soh"]["provenance"] == "MODEL ESTIMATE"
    assert vitals["soc"]["value"] == 66.7
    assert vitals["soc"]["provenance"] == "REAL CAN / DERIVED"
    assert vitals["temperature"]["value"] == 25.3
    assert vitals["temperature"]["provenance"] == "REAL CAN DATA"
    assert vitals["internal_resistance"]["provenance"] == "SIMULATED EIS"

    # 2. Verify Degradation Analysis & Dominant Pattern
    assert "degradation_analysis" in res
    deg = res["degradation_analysis"]
    assert "dominant_pattern" in deg
    assert "Resistance-associated" in deg["dominant_pattern"] or "Capacity fade" in deg["dominant_pattern"]
    assert "scientific_disclaimer" in deg

    # 3. Verify Anomaly Intelligence & Timeline
    assert "anomaly_intelligence" in res
    anom = res["anomaly_intelligence"]
    assert "index" in anom
    assert 0 <= anom["index"] <= 100
    assert "event_timeline" in anom
    assert isinstance(anom["event_timeline"], list)

    # 4. Verify Operating Stress
    assert "operating_stress" in res
    stress = res["operating_stress"]
    assert "overall_stress_index" in stress

    # 5. Verify EIS Health Correlations & Labeling
    assert "eis_health_indicators" in res
    eis = res["eis_health_indicators"]
    assert eis["eis_type"] == "SIMULATED EIS"
    assert eis["model_type"] == "1-RC RANDLES ECM"
    assert "health_explanation" in eis

    # 6. Verify RUL with Uncertainty & Health Confidence
    assert "rul_uncertainty" in res
    rul_unc = res["rul_uncertainty"]
    assert rul_unc["confidence_label"] == "MODEL ESTIMATE"
    assert "confidence_pct" in rul_unc

    assert "health_confidence" in res
    health_conf = res["health_confidence"]
    assert "limiting_reasons" in health_conf
    assert len(health_conf["limiting_reasons"]) > 0

    # 7. Verify Risk Matrix
    assert "risk_intelligence" in res
    risk = res["risk_intelligence"]
    assert "overall_risk" in risk
    assert "matrix_position" in risk
    assert "categories" in risk

    # 8. Verify Early Warnings & Diagnostic Actions
    assert "early_warnings" in res
    assert "diagnostic_actions" in res
    actions = res["diagnostic_actions"]
    assert len(actions) > 0
    # Ensure NO second-life application recommendations exist in Health & Risk
    for act in actions:
        assert "application" not in act["action"].lower() or "validate" in act["action"].lower()
        assert "second-life" not in act["action"].lower()
        assert "repurposing" not in act["action"].lower()

    # 9. Verify Provenance Badges Map
    assert "provenance" in res
    prov = res["provenance"]
    assert prov["soh"] == "MODEL ESTIMATE"
    assert prov["soc"] == "REAL CAN / DERIVED"
    assert prov["eis"] == "SIMULATED EIS"
    assert prov["temperature"] == "REAL CAN DATA"


def test_health_risk_missing_data_handling(twin_engine):
    # Pass minimal telemetry snapshot
    telemetry = {
        "PackVoltage": 32.0,
        "SOC": 80.0
    }
    res = twin_engine.evaluate_health_and_risk(telemetry)
    assert res["vitals"]["soh"]["value"] > 0
    assert res["degradation_rate"]["has_sufficient_history"] is False
    assert res["degradation_rate"]["message"] == "Insufficient historical data for reliable degradation-rate estimation."


def test_strict_module_separation_check(twin_engine):
    telemetry = {
        "PackVoltage": 31.16,
        "PackCurrent": 1.9,
        "SOC": 66.7,
        "TempMean": 25.3
    }
    res = twin_engine.evaluate_health_and_risk(telemetry)
    # Confirm Health & Risk dictionary contains NO second-life fields
    forbidden_keys = [
        "recommended_application",
        "suitability",
        "repurposing_score",
        "application_ranking",
        "tier_recommendation",
        "refurbishment_planning"
    ]
    for key in forbidden_keys:
        assert key not in res
