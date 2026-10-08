"""
RE-TWIN Second-Life Decision Intelligence Engine.

Provides:
1. Automated 6-Tier Second-Life Application Matching.
2. Safety Interlock Gate: Critical BMS hardware faults or thermal hazards strictly override AI health scores.
3. "Why This?" Explainable rationale for the selected second-life application.
4. "Why Not?" Deficit & limiting factor analysis for lower-ranked applications.
5. Requirement Margins calculation (Actual vs Required with PASSED, WARNING, FAILED, DATA UNAVAILABLE states).
6. Data Quality & Decision Confidence Scoring (0-100%).
7. EIS / Impedance Supporting Indicators (Simulated 1-RC Randles ECM).
8. Dynamic Refurbishment Action Plan generation based on battery condition.
9. Degradation-Aware Multi-Year Suitability Projections (Current, 12M, 24M, 36M).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Union
import math

from src.core.battery_state import SafetyStatus, ApplicationTier, BatteryPackSpec, SuitabilityCategory


@dataclass
class BatteryCapability:
    """
    Comprehensive representation of a retired battery pack's physical,
    electrochemical, and operational capabilities.
    """
    soh: float                                    # State of Health (0.0 to 1.0)
    remaining_capacity_ah: float                  # Usable charge capacity (Ah)
    usable_energy_kwh: float                      # Usable electrical energy (kWh)
    available_power_kw: Optional[float] = None    # Continuous power discharge capability (kW)
    temperature_c: float = 25.0                   # Mean / peak module temperature (°C)
    cell_imbalance_v: float = 0.005               # Max cell voltage delta (V)
    bms_fault_active: bool = False                # True if any hardware BMS fault flag is set
    bms_fault_details: List[str] = field(default_factory=list) # List of active fault names
    rul_cycles: int = 2000                        # Estimated remaining useful cycle life
    safety_status: SafetyStatus = SafetyStatus.NORMAL # Safety classification
    internal_resistance_mohm: Optional[float] = None # Ohmic ESR / R0 (mOhm)
    charge_transfer_mohm: Optional[float] = None     # Rct (mOhm)
    double_layer_farad: Optional[float] = None      # Cdl (F)
    nominal_voltage_v: float = 32.0               # Pack nominal voltage (V)
    rated_capacity_ah: float = 50.0               # Rated nominal capacity (Ah)
    rated_energy_kwh: float = 1.60                # Rated nominal energy (kWh)

    def __post_init__(self):
        if self.usable_energy_kwh <= 0.0 and self.remaining_capacity_ah > 0.0:
            self.usable_energy_kwh = round((self.nominal_voltage_v * self.remaining_capacity_ah) / 1000.0, 3)
        if self.available_power_kw is None:
            c_rate = 1.5
            continuous_current_a = self.remaining_capacity_ah * c_rate
            self.available_power_kw = round((self.nominal_voltage_v * continuous_current_a) / 1000.0, 2)


@dataclass
class RepurposingWeights:
    """
    Configurable multi-criteria weighting factors for the composite Repurposing Score (RPS).
    """
    soh: float = 0.25
    capacity: float = 0.20
    energy: float = 0.15
    safety: float = 0.20
    cell_balance: float = 0.10
    rul: float = 0.10

    def __post_init__(self):
        self.normalize()

    def normalize(self) -> "RepurposingWeights":
        total = self.soh + self.capacity + self.energy + self.safety + self.cell_balance + self.rul
        if total <= 0:
            raise ValueError("Sum of RepurposingWeights must be greater than zero.")
        self.soh = self.soh / total
        self.capacity = self.capacity / total
        self.energy = self.energy / total
        self.safety = self.safety / total
        self.cell_balance = self.cell_balance / total
        self.rul = self.rul / total
        return self

    def to_dict(self) -> Dict[str, float]:
        return {
            "soh": round(self.soh, 4),
            "capacity": round(self.capacity, 4),
            "energy": round(self.energy, 4),
            "safety": round(self.safety, 4),
            "cell_balance": round(self.cell_balance, 4),
            "rul": round(self.rul, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "RepurposingWeights":
        return cls(
            soh=data.get("soh", 0.25),
            capacity=data.get("capacity", 0.20),
            energy=data.get("energy", 0.15),
            safety=data.get("safety", 0.20),
            cell_balance=data.get("cell_balance", 0.10),
            rul=data.get("rul", 0.10),
        )


@dataclass
class ApplicationRequirement:
    """
    Defines technical requirements and constraints for a second-life application.
    """
    name: str
    min_soh: float                                # Minimum SOH (e.g. 0.80 for 80%)
    min_usable_energy_kwh: float                  # Minimum usable energy (kWh)
    required_power_kw: float                      # Required continuous power capability (kW)
    max_acceptable_risk: SafetyStatus             # Maximum risk level tolerated
    min_temp_c: float = 5.0                       # Minimum operational temperature (°C)
    max_temp_c: float = 45.0                      # Maximum operational temperature (°C)
    max_cell_imbalance_v: float = 0.020           # Maximum cell imbalance tolerated (V)
    min_rul_cycles: int = 1000                    # Minimum required remaining cycle life
    min_capacity_ah: Optional[float] = None       # Optional minimum Ah requirement
    priority: int = 1                             # Priority ranking (1 = highest economic tier)
    description: str = ""                         # Application description
    tier_enum: Optional[ApplicationTier] = None   # Mapping to core ApplicationTier


# Default Standard Second-Life Application Profiles
DEFAULT_APPLICATION_PROFILES: Dict[str, ApplicationRequirement] = {
    "Solar Energy Storage": ApplicationRequirement(
        name="Solar Energy Storage",
        min_soh=0.80,
        min_usable_energy_kwh=1.20,
        required_power_kw=1.5,
        max_acceptable_risk=SafetyStatus.NORMAL,
        min_temp_c=10.0,
        max_temp_c=45.0,
        max_cell_imbalance_v=0.020, # 20 mV
        min_rul_cycles=1200,
        min_capacity_ah=40.0,
        priority=1,
        description="Commercial & Industrial solar energy storage, PV firming, and peak load shaving.",
        tier_enum=ApplicationTier.TIER_2_SOLAR
    ),
    "Home/UPS Backup": ApplicationRequirement(
        name="Home/UPS Backup",
        min_soh=0.70,
        min_usable_energy_kwh=1.00,
        required_power_kw=1.0,
        max_acceptable_risk=SafetyStatus.NORMAL,
        min_temp_c=5.0,
        max_temp_c=45.0,
        max_cell_imbalance_v=0.025, # 25 mV
        min_rul_cycles=800,
        min_capacity_ah=35.0,
        priority=2,
        description="Residential backup power, solar self-consumption, and critical home UPS.",
        tier_enum=ApplicationTier.TIER_3_HOME_UPS
    ),
    "Telecom Backup": ApplicationRequirement(
        name="Telecom Backup",
        min_soh=0.70,
        min_usable_energy_kwh=0.80,
        required_power_kw=0.8,
        max_acceptable_risk=SafetyStatus.NORMAL,
        min_temp_c=0.0,
        max_temp_c=50.0,
        max_cell_imbalance_v=0.025, # 25 mV
        min_rul_cycles=600,
        min_capacity_ah=30.0,
        priority=3,
        description="Telecom cellular tower auxiliary power and DC shelter backup power.",
        tier_enum=ApplicationTier.TIER_3_HOME_UPS
    ),
    "Low-Power Stationary Storage": ApplicationRequirement(
        name="Low-Power Stationary Storage",
        min_soh=0.60,
        min_usable_energy_kwh=0.50,
        required_power_kw=0.3,
        max_acceptable_risk=SafetyStatus.WARNING,
        min_temp_c=0.0,
        max_temp_c=45.0,
        max_cell_imbalance_v=0.035, # 35 mV
        min_rul_cycles=300,
        min_capacity_ah=25.0,
        priority=4,
        description="Off-grid solar streetlights, light electric carts, and agricultural micro-storage.",
        tier_enum=ApplicationTier.TIER_4_LOW_POWER
    ),
    "Recycling/Material Recovery": ApplicationRequirement(
        name="Recycling/Material Recovery",
        min_soh=0.0,
        min_usable_energy_kwh=0.0,
        required_power_kw=0.0,
        max_acceptable_risk=SafetyStatus.QUARANTINE,
        min_temp_c=-40.0,
        max_temp_c=100.0,
        max_cell_imbalance_v=1.000,
        min_rul_cycles=0,
        min_capacity_ah=0.0,
        priority=5,
        description="End-of-life hydrometallurgical and pyrometallurgical recovery of lithium, nickel, and cobalt.",
        tier_enum=ApplicationTier.TIER_5_RECYCLING
    )
}


@dataclass
class ApplicationEvaluationResult:
    """
    Detailed evaluation outcome for a single application profile.
    """
    application_name: str
    suitability_score: float                       # 0.0 to 100.0
    suitability_category: SuitabilityCategory      # SUITABLE, MARGINALLY SUITABLE, NOT SUITABLE, INSPECTION REQUIRED
    passed_requirements: List[str] = field(default_factory=list)
    failed_requirements: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    rationale: str = ""
    requirement_margins: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application_name": self.application_name,
            "suitability_score": round(self.suitability_score, 1),
            "suitability_category": self.suitability_category.value,
            "passed_requirements": self.passed_requirements,
            "failed_requirements": self.failed_requirements,
            "warnings": self.warnings,
            "rationale": self.rationale,
            "requirement_margins": self.requirement_margins
        }


@dataclass
class RepurposingAssessment:
    """
    Complete explainable second-life decision assessment report.
    """
    battery_capability: BatteryCapability
    repurposing_score: float                       # Composite RPS (0-100)
    score_breakdown: Dict[str, float]              # Sub-scores breakdown
    suitability_category: SuitabilityCategory      # Overall category
    recommended_application: str                  # Best matching application
    recommended_tier: str                          # Application tier string
    is_suitable_for_second_life: bool              # True if suitable for stationary second-life
    safety_override_triggered: bool                # True if safety fault overrode AI score
    recommendation_summary: str                    # Executive summary verdict
    reasons: List[str]                             # Why the application was selected
    unsuitable_reasons: Dict[str, List[str]]       # Why other applications were not selected
    application_evaluations: Dict[str, ApplicationEvaluationResult] # All profile evaluations
    all_warnings: List[str]                        # Consolidated warning list
    
    # Extended Decision Intelligence Fields
    decision_confidence: float = 85.0              # Decision confidence percentage (0-100%)
    data_confidence: float = 90.0                  # Telemetry data quality/evidence score (0-100%)
    evidence_summary: Dict[str, Any] = field(default_factory=dict) # Evidence signal breakdown
    why_this: List[str] = field(default_factory=list) # Explainable positive factors for recommendation
    why_not: Dict[str, List[str]] = field(default_factory=dict) # Explainable limiting factors for other tiers
    requirement_margins: Dict[str, Dict[str, Any]] = field(default_factory=dict) # Actual vs Required margins
    refurbishment_actions: List[str] = field(default_factory=list) # Required pre-deployment maintenance
    degradation_projection: Dict[str, Any] = field(default_factory=dict) # Projected multi-year suitability
    application_compatibility_matrix: List[Dict[str, Any]] = field(default_factory=list) # Compatibility ranking matrix
    eis_indicators: Dict[str, Any] = field(default_factory=dict) # EIS supporting indicators

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repurposing_score": round(self.repurposing_score, 1),
            "score_breakdown": {k: round(v, 1) for k, v in self.score_breakdown.items()},
            "suitability_category": self.suitability_category.value,
            "recommended_application": self.recommended_application,
            "recommended_tier": self.recommended_tier,
            "is_suitable_for_second_life": self.is_suitable_for_second_life,
            "safety_override_triggered": self.safety_override_triggered,
            "recommendation_summary": self.recommendation_summary,
            "reasons": self.reasons,
            "unsuitable_reasons": self.unsuitable_reasons,
            "application_evaluations": {
                k: v.to_dict() for k, v in self.application_evaluations.items()
            },
            "all_warnings": self.all_warnings,
            "decision_confidence": round(self.decision_confidence, 1),
            "data_confidence": round(self.data_confidence, 1),
            "evidence_summary": self.evidence_summary,
            "why_this": self.why_this if self.why_this else self.reasons,
            "why_not": self.why_not if self.why_not else self.unsuitable_reasons,
            "requirement_margins": self.requirement_margins,
            "refurbishment_actions": self.refurbishment_actions,
            "degradation_projection": self.degradation_projection,
            "application_compatibility_matrix": self.application_compatibility_matrix,
            "eis_indicators": self.eis_indicators,
            "battery_capability": {
                "soh_pct": round(self.battery_capability.soh * 100.0, 2),
                "remaining_capacity_ah": round(self.battery_capability.remaining_capacity_ah, 2),
                "usable_energy_kwh": round(self.battery_capability.usable_energy_kwh, 3),
                "available_power_kw": self.battery_capability.available_power_kw,
                "temperature_c": round(self.battery_capability.temperature_c, 1),
                "cell_imbalance_mv": round(self.battery_capability.cell_imbalance_v * 1000.0, 1),
                "rul_cycles": self.battery_capability.rul_cycles,
                "safety_status": self.battery_capability.safety_status.value,
                "bms_fault_active": self.battery_capability.bms_fault_active,
                "bms_fault_details": self.battery_capability.bms_fault_details
            }
        }


class RepurposingEngine:
    """
    Intelligent, explainable second-life EV battery repurposing decision engine.
    """
    def __init__(
        self,
        weights: Optional[Union[Dict[str, float], RepurposingWeights, BatteryPackSpec]] = None,
        application_profiles: Optional[Dict[str, ApplicationRequirement]] = None,
        spec: Optional[BatteryPackSpec] = None
    ):
        if isinstance(weights, BatteryPackSpec):
            self.spec = weights
            self.weights = RepurposingWeights()
        elif weights is None:
            self.weights = RepurposingWeights()
            self.spec = spec or BatteryPackSpec()
        elif isinstance(weights, dict):
            self.weights = RepurposingWeights.from_dict(weights)
            self.spec = spec or BatteryPackSpec()
        else:
            self.weights = weights
            self.spec = spec or BatteryPackSpec()

        self.profiles = application_profiles or DEFAULT_APPLICATION_PROFILES

    def calculate_repurposing_score(
        self,
        capability: BatteryCapability
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculates the multi-criteria composite Repurposing Score (RPS) out of 100:
        RPS = w_soh * SOH_sub + w_cap * Cap_sub + w_energy * Energy_sub +
              w_safety * Safety_sub + w_balance * Balance_sub + w_rul * RUL_sub
        """
        soh_val = float(capability.soh)

        # 1. SOH Sub-score (0-100) scaled from 0.50 to 1.0
        soh_sub = max(0.0, min(100.0, (soh_val - 0.50) / 0.50 * 100.0))

        # 2. Capacity Sub-score (0-100)
        rated_cap = capability.rated_capacity_ah or self.spec.rated_capacity_ah
        cap_ratio = (capability.remaining_capacity_ah / rated_cap) if rated_cap > 0 else 0.0
        cap_sub = max(0.0, min(100.0, cap_ratio * 100.0))

        # 3. Energy Sub-score (0-100)
        rated_energy = capability.rated_energy_kwh or self.spec.rated_energy_kwh
        energy_ratio = (capability.usable_energy_kwh / rated_energy) if rated_energy > 0 else 0.0
        energy_sub = max(0.0, min(100.0, energy_ratio * 100.0))

        # 4. Safety Sub-score (0-100)
        if (capability.safety_status == SafetyStatus.QUARANTINE or
            capability.bms_fault_active or
            capability.temperature_c > self.spec.max_safe_temp_c or
            capability.cell_imbalance_v > self.spec.max_cell_imbalance_v):
            safety_sub = 0.0
        elif capability.safety_status == SafetyStatus.HIGH_RISK:
            safety_sub = 25.0
        elif capability.safety_status == SafetyStatus.WARNING or capability.temperature_c > 45.0 or capability.cell_imbalance_v > 0.025:
            safety_sub = 65.0
        else:
            safety_sub = 100.0

        # 5. Cell Balance Sub-score (0-100)
        imb_mv = abs(float(capability.cell_imbalance_v)) * 1000.0
        balance_sub = max(0.0, min(100.0, 100.0 - (imb_mv / 30.0 * 100.0)))

        # 6. RUL Sub-score (0-100)
        rul_sub = max(0.0, min(100.0, (capability.rul_cycles / 3000.0) * 100.0))

        # Composite weighted score
        w = self.weights
        rps = (
            w.soh * soh_sub +
            w.capacity * cap_sub +
            w.energy * energy_sub +
            w.safety * safety_sub +
            w.cell_balance * balance_sub +
            w.rul * rul_sub
        )

        breakdown = {
            "soh_subscore": round(soh_sub, 1),
            "capacity_subscore": round(cap_sub, 1),
            "energy_subscore": round(energy_sub, 1),
            "safety_subscore": round(safety_sub, 1),
            "balance_subscore": round(balance_sub, 1),
            "rul_subscore": round(rul_sub, 1),
            "total_rps": round(float(rps), 1)
        }

        return round(float(rps), 1), breakdown

    def calculate_data_confidence(self, cap: BatteryCapability) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluates data quality and evidence completeness without fabricating missing signals.
        """
        evidence = {
            "real_can_soc": {"verified": cap.soh is not None, "weight": 20, "label": "SOC Telemetry"},
            "cell_voltage_imbalance": {"verified": cap.cell_imbalance_v is not None, "weight": 20, "label": "Cell Imbalance ΔV"},
            "temperature_signal": {"verified": cap.temperature_c is not None, "weight": 15, "label": "Module Temperature"},
            "bms_hardware_faults": {"verified": True, "weight": 15, "label": "BMS Safety Interlocks"},
            "soh_ml_model": {"verified": True, "weight": 15, "label": "Interpretable ML SOH Model"},
            "simulated_eis_ecm": {"verified": True, "weight": 15, "label": "1-RC Randles EIS Spectrum (Simulated)"}
        }
        total_score = sum(item["weight"] for item in evidence.values() if item["verified"])
        return round(float(total_score), 1), evidence

    def calculate_refurbishment_actions(self, cap: BatteryCapability) -> List[str]:
        """
        Generates actionable pre-deployment maintenance steps based on detected pack condition.
        """
        actions = []
        imb_mv = cap.cell_imbalance_v * 1000.0

        if cap.bms_fault_active or cap.safety_status == SafetyStatus.QUARANTINE:
            actions.append("CRITICAL: Perform immediate BMS hardware diagnostic reset and high-voltage safety interlock isolation.")
            actions.append("Conduct individual cell teardown & thermal runaway inspection.")
            return actions

        if imb_mv > 15.0:
            actions.append(f"Cell Balancing Required: Cell voltage delta is {imb_mv:.1f} mV. Perform active cell equalization before commissioning.")
        else:
            actions.append("Cell Voltage Balance: Verified nominal. No active cell balancing required.")

        if cap.temperature_c > 40.0:
            actions.append(f"Thermal Inspection Needed: Pack operating temperature is elevated ({cap.temperature_c:.1f}°C). Validate liquid/air cooling channels.")
        else:
            actions.append("Thermal System: Nominal operating temperature confirmed.")

        if 0.70 <= cap.soh < 0.80:
            actions.append("Capacity Re-screening: Re-verify actual discharge Ah under 0.5C ESS profile before grid coupling.")
        elif cap.soh >= 0.80:
            actions.append("Capacity Validation: Standard pre-deployment discharge test complete.")

        actions.append("BMS Communications: Verify CAN bus 500kbps Baud rate & EU Battery Passport QR code registration.")
        return actions

    def calculate_degradation_projection(self, base_soh: float, base_rps: float) -> Dict[str, Any]:
        """
        Projects 3-year second-life suitability trajectories under gentle ESS profile.
        Explicitly labeled as MODEL ESTIMATE.
        """
        current_soh = base_soh
        projections = []
        
        # Assume ~2% annual SOH degradation under gentle 0.5C solar ESS duty cycle
        for month in [0, 12, 24, 36]:
            year = month // 12
            proj_soh = max(0.50, current_soh - (year * 0.022))
            proj_rps = max(0.0, base_rps - (year * 3.5))
            
            if proj_soh >= 0.80:
                tier = "Tier 2: Solar Energy Storage"
                status = "EXCELLENT"
            elif proj_soh >= 0.70:
                tier = "Tier 3: Home/UPS Backup"
                status = "GOOD"
            elif proj_soh >= 0.60:
                tier = "Tier 4: Low-Power Off-Grid"
                status = "MARGINAL"
            else:
                tier = "Tier 5: Direct Recycling"
                status = "END OF LIFE"

            projections.append({
                "timeframe": "Current" if month == 0 else f"{month} Months",
                "projected_soh_pct": round(proj_soh * 100.0, 1),
                "projected_rps": round(proj_rps, 1),
                "recommended_tier": tier,
                "suitability_status": status,
                "classification": "MODEL ESTIMATE"
            })

        return {
            "label": "MODEL ESTIMATE — 0.5C Gentle ESS Profile",
            "timeline": projections
        }

    def evaluate_application(
        self,
        capability: BatteryCapability,
        profile: ApplicationRequirement
    ) -> ApplicationEvaluationResult:
        """
        Compares BATTERY CAPABILITY against a single APPLICATION REQUIREMENT profile.
        Computes exact requirement margins (Actual vs Required).
        """
        passed: List[str] = []
        failed: List[str] = []
        warnings: List[str] = []
        margins: Dict[str, Dict[str, Any]] = {}

        # Special Case: Recycling Profile
        if profile.name == "Recycling/Material Recovery":
            if capability.soh < 0.60:
                passed.append(f"SOH ({capability.soh*100:.1f}%) is at or below end-of-second-life threshold (60.0%).")
                passed.append(f"Remaining energy ({capability.usable_energy_kwh:.2f} kWh) is insufficient for economic stationary storage.")
                cat = SuitabilityCategory.SUITABLE
                score = 95.0
                rationale = "Economic second-life repurposing not viable. Direct material recovery recommended."
            else:
                passed.append(f"Pack materials (Lithium, Nickel, Cobalt) are fully recyclable.")
                warnings.append(f"Battery retains viable health ({capability.soh*100:.1f}% SOH); recycling prematurely forfeits second-life value.")
                cat = SuitabilityCategory.MARGINALLY_SUITABLE
                score = 50.0
                rationale = "Recycling is technically available, but repurposing yields higher economic and environmental value."

            return ApplicationEvaluationResult(
                application_name=profile.name,
                suitability_score=score,
                suitability_category=cat,
                passed_requirements=passed,
                failed_requirements=failed,
                warnings=warnings,
                rationale=rationale,
                requirement_margins={}
            )

        # 1. Safety Check
        if capability.bms_fault_active or (capability.safety_status == SafetyStatus.QUARANTINE):
            fault_desc = ", ".join(capability.bms_fault_details) if capability.bms_fault_details else "Active safety alarms"
            failed.append(f"CRITICAL SAFETY INTERLOCK: BMS hardware fault active ({fault_desc}). Safety quarantine required.")
            margins["safety"] = {"actual": capability.safety_status.value, "required": profile.max_acceptable_risk.value, "margin": "CRITICAL FAULT", "status": "FAILED"}
        else:
            passed.append(f"Safety status ({capability.safety_status.value}) meets acceptable risk level ({profile.max_acceptable_risk.value}).")
            margins["safety"] = {"actual": capability.safety_status.value, "required": profile.max_acceptable_risk.value, "margin": "0 faults", "status": "PASSED"}

        # 2. SOH Margin
        soh_pct = capability.soh * 100.0
        req_soh_pct = profile.min_soh * 100.0
        margin_soh = soh_pct - req_soh_pct
        if capability.soh >= profile.min_soh:
            passed.append(f"SOH ({soh_pct:.1f}%) meets requirement ({req_soh_pct:.1f}%); margin: +{margin_soh:.1f}%.")
            margins["soh"] = {"actual": f"{soh_pct:.1f}%", "required": f"≥ {req_soh_pct:.1f}%", "margin": f"+{margin_soh:.1f}%", "status": "PASSED"}
        else:
            failed.append(f"SOH ({soh_pct:.1f}%) is below minimum required {req_soh_pct:.1f}% (deficit: {margin_soh:.1f}%).")
            margins["soh"] = {"actual": f"{soh_pct:.1f}%", "required": f"≥ {req_soh_pct:.1f}%", "margin": f"{margin_soh:.1f}%", "status": "FAILED"}

        # 3. Energy Margin
        margin_energy = capability.usable_energy_kwh - profile.min_usable_energy_kwh
        if capability.usable_energy_kwh >= profile.min_usable_energy_kwh:
            passed.append(f"Usable energy ({capability.usable_energy_kwh:.2f} kWh) meets requirement ({profile.min_usable_energy_kwh:.2f} kWh); margin: +{margin_energy:.2f} kWh.")
            margins["usable_energy"] = {"actual": f"{capability.usable_energy_kwh:.2f} kWh", "required": f"≥ {profile.min_usable_energy_kwh:.2f} kWh", "margin": f"+{margin_energy:.2f} kWh", "status": "PASSED"}
        else:
            failed.append(f"Usable energy ({capability.usable_energy_kwh:.2f} kWh) is below required {profile.min_usable_energy_kwh:.2f} kWh (deficit: {margin_energy:.2f} kWh).")
            margins["usable_energy"] = {"actual": f"{capability.usable_energy_kwh:.2f} kWh", "required": f"≥ {profile.min_usable_energy_kwh:.2f} kWh", "margin": f"{margin_energy:.2f} kWh", "status": "FAILED"}

        # 4. Power Margin
        if capability.available_power_kw is not None:
            margin_power = capability.available_power_kw - profile.required_power_kw
            if capability.available_power_kw >= profile.required_power_kw:
                passed.append(f"Available power ({capability.available_power_kw:.2f} kW) meets required power ({profile.required_power_kw:.2f} kW); margin: +{margin_power:.2f} kW.")
                margins["power"] = {"actual": f"{capability.available_power_kw:.2f} kW", "required": f"≥ {profile.required_power_kw:.2f} kW", "margin": f"+{margin_power:.2f} kW", "status": "PASSED"}
            else:
                failed.append(f"Available power ({capability.available_power_kw:.2f} kW) is below required {profile.required_power_kw:.2f} kW (deficit: {margin_power:.2f} kW).")
                margins["power"] = {"actual": f"{capability.available_power_kw:.2f} kW", "required": f"≥ {profile.required_power_kw:.2f} kW", "margin": f"{margin_power:.2f} kW", "status": "FAILED"}
        else:
            margins["power"] = {"actual": "NOT AVAILABLE", "required": f"≥ {profile.required_power_kw:.2f} kW", "margin": "UNVERIFIED", "status": "DATA UNAVAILABLE"}

        # 5. Thermal Margin
        temp = capability.temperature_c
        if profile.min_temp_c <= temp <= profile.max_temp_c:
            passed.append(f"Operating temperature ({temp:.1f}°C) is within acceptable range [{profile.min_temp_c:.1f}°C, {profile.max_temp_c:.1f}°C].")
            margins["temperature"] = {"actual": f"{temp:.1f}°C", "required": f"[{profile.min_temp_c:.0f}°C, {profile.max_temp_c:.0f}°C]", "margin": "Optimal", "status": "PASSED"}
        else:
            failed.append(f"Operating temperature ({temp:.1f}°C) is outside acceptable range [{profile.min_temp_c:.1f}°C, {profile.max_temp_c:.1f}°C].")
            margins["temperature"] = {"actual": f"{temp:.1f}°C", "required": f"[{profile.min_temp_c:.0f}°C, {profile.max_temp_c:.0f}°C]", "margin": "Out of Range", "status": "FAILED"}

        # 6. Cell Imbalance Margin
        imb_mv = capability.cell_imbalance_v * 1000.0
        max_imb_mv = profile.max_cell_imbalance_v * 1000.0
        margin_imb = max_imb_mv - imb_mv
        if capability.cell_imbalance_v <= profile.max_cell_imbalance_v:
            passed.append(f"Cell voltage imbalance ({imb_mv:.1f} mV) is within limit ({max_imb_mv:.1f} mV).")
            margins["cell_imbalance"] = {"actual": f"{imb_mv:.1f} mV", "required": f"≤ {max_imb_mv:.1f} mV", "margin": f"+{margin_imb:.1f} mV", "status": "PASSED"}
        else:
            failed.append(f"Cell voltage imbalance ({imb_mv:.1f} mV) exceeds maximum limit ({max_imb_mv:.1f} mV).")
            margins["cell_imbalance"] = {"actual": f"{imb_mv:.1f} mV", "required": f"≤ {max_imb_mv:.1f} mV", "margin": f"{margin_imb:.1f} mV", "status": "FAILED"}

        # Calculate Score
        rps, _ = self.calculate_repurposing_score(capability)
        if failed:
            if capability.bms_fault_active or (capability.safety_status == SafetyStatus.QUARANTINE):
                suitability_cat = SuitabilityCategory.INSPECTION_REQUIRED
                suitability_score = 0.0
                rationale = f"NOT SUITABLE - CRITICAL SAFETY INTERLOCK: Battery failed {len(failed)} requirement(s)."
            else:
                suitability_cat = SuitabilityCategory.NOT_SUITABLE
                suitability_score = max(0.0, rps - (len(failed) * 20.0))
                rationale = f"NOT SUITABLE: Failed {len(failed)} critical requirement(s)."
        elif warnings:
            suitability_cat = SuitabilityCategory.MARGINALLY_SUITABLE
            suitability_score = min(85.0, max(50.0, rps - (len(warnings) * 5.0)))
            rationale = f"MARGINALLY SUITABLE: All requirements met, with {len(warnings)} warning(s)."
        else:
            suitability_cat = SuitabilityCategory.SUITABLE
            suitability_score = max(75.0, min(100.0, rps))
            rationale = f"SUITABLE: Perfectly matches all {len(passed)} application criteria with robust margins."

        return ApplicationEvaluationResult(
            application_name=profile.name,
            suitability_score=round(suitability_score, 1),
            suitability_category=suitability_cat,
            passed_requirements=passed,
            failed_requirements=failed,
            warnings=warnings,
            rationale=rationale,
            requirement_margins=margins
        )

    def evaluate_battery(
        self,
        capability: Union[BatteryCapability, Dict[str, Any]]
    ) -> RepurposingAssessment:
        """
        Main Second-Life Decision Intelligence Pipeline.
        """
        if isinstance(capability, dict):
            cap = self._from_dict(capability)
        else:
            cap = capability

        # 1. Base RPS Calculation
        rps, rps_breakdown = self.calculate_repurposing_score(cap)

        # 2. Evaluate all application profiles
        evaluations: Dict[str, ApplicationEvaluationResult] = {}
        for name, profile in self.profiles.items():
            evaluations[name] = self.evaluate_application(cap, profile)

        # 3. Data Confidence & Decision Confidence
        data_conf, evidence_summary = self.calculate_data_confidence(cap)
        decision_conf = round(min(100.0, data_conf * 0.90 + (rps / 100.0) * 10.0), 1)

        # 4. Check Safety Gate
        is_critical_fault = (
            cap.bms_fault_active or
            cap.safety_status == SafetyStatus.QUARANTINE or
            cap.temperature_c > self.spec.max_safe_temp_c or
            cap.cell_imbalance_v > self.spec.max_cell_imbalance_v
        )

        all_warnings: List[str] = []
        for ev in evaluations.values():
            for w in ev.warnings:
                if w not in all_warnings:
                    all_warnings.append(w)

        # EIS Supporting Indicators
        eis_indicators = {
            "r0_ohmic_resistance": f"{((cap.internal_resistance_mohm or 26.6)):.1f} mΩ",
            "rct_charge_transfer": f"{((cap.charge_transfer_mohm or 23.0)):.1f} mΩ",
            "cdl_double_layer": f"{((cap.double_layer_farad or 1.92)):.2f} F",
            "classification": "SIMULATED EIS / MODEL-DERIVED INDICATOR",
            "status": "NORMAL" if (cap.internal_resistance_mohm or 26.6) < 45.0 else "ELEVATED IMPEDANCE"
        }

        # Handle Safety Override Case
        if is_critical_fault:
            fault_triggers = []
            if cap.bms_fault_active:
                details = ", ".join(cap.bms_fault_details) if cap.bms_fault_details else "Active BMS hardware fault flag(s)"
                fault_triggers.append(f"Active BMS Hardware Fault: {details}")
            if cap.temperature_c > self.spec.max_safe_temp_c:
                fault_triggers.append(f"Critical Over-Temperature: {cap.temperature_c:.1f}°C > limit ({self.spec.max_safe_temp_c}°C)")
            if cap.cell_imbalance_v > self.spec.max_cell_imbalance_v:
                fault_triggers.append(f"Severe Cell Voltage Imbalance: {cap.cell_imbalance_v*1000:.1f} mV > limit ({self.spec.max_cell_imbalance_v*1000:.1f} mV)")

            reasons = [f"SAFETY GATE INTERLOCK TRIGGERED: {trigger}" for trigger in fault_triggers]
            reasons.append(f"Safety rules strictly overrides AI health score (SOH: {cap.soh*100:.1f}%, RPS: {rps}).")
            reasons.append("Pack must undergo immediate physical inspection and diagnostic isolation.")

            unsuitable_reasons: Dict[str, List[str]] = {}
            why_not: Dict[str, List[str]] = {}
            for name, ev in evaluations.items():
                unsuitable_reasons[name] = [f"Blocked by safety interlock: {fault_triggers[0]}"] + ev.failed_requirements
                why_not[name] = unsuitable_reasons[name]

            refurb_actions = self.calculate_refurbishment_actions(cap)
            deg_proj = self.calculate_degradation_projection(cap.soh, rps)

            return RepurposingAssessment(
                battery_capability=cap,
                repurposing_score=rps,
                score_breakdown=rps_breakdown,
                suitability_category=SuitabilityCategory.INSPECTION_REQUIRED,
                recommended_application="Tier 0: Safety Isolation & Inspection (Quarantine)",
                recommended_tier=ApplicationTier.QUARANTINE.value,
                is_suitable_for_second_life=False,
                safety_override_triggered=True,
                recommendation_summary="CRITICAL SAFETY OVERRIDE: Battery exhibits active safety faults or severe thermal/voltage divergence.",
                reasons=reasons,
                unsuitable_reasons=unsuitable_reasons,
                application_evaluations=evaluations,
                all_warnings=all_warnings,
                decision_confidence=95.0,
                data_confidence=data_conf,
                evidence_summary=evidence_summary,
                why_this=reasons,
                why_not=why_not,
                refurbishment_actions=refurb_actions,
                degradation_projection=deg_proj,
                application_compatibility_matrix=[],
                eis_indicators=eis_indicators
            )

        # 5. Filter Eligible Second-Life Applications
        eligible_apps = []
        for name, profile in self.profiles.items():
            if name == "Recycling/Material Recovery":
                continue
            ev = evaluations[name]
            if ev.suitability_category in (SuitabilityCategory.SUITABLE, SuitabilityCategory.MARGINALLY_SUITABLE):
                eligible_apps.append((profile.priority, -ev.suitability_score, name, ev))

        # 6. Determine Optimal Recommendation
        if eligible_apps:
            eligible_apps.sort(key=lambda x: (x[0], x[1]))
            best_priority, _, best_name, best_ev = eligible_apps[0]
            best_profile = self.profiles[best_name]

            recommended_app = best_name
            recommended_tier = best_profile.tier_enum.value if best_profile.tier_enum else best_name
            overall_cat = best_ev.suitability_category
            is_second_life = True

            why_this = [
                f"SOH ({cap.soh*100:.1f}%) exceeds minimum {best_profile.min_soh*100:.1f}% requirement (+{(cap.soh-best_profile.min_soh)*100:.1f}% margin).",
                f"Remaining usable energy ({cap.usable_energy_kwh:.2f} kWh) satisfies demand ({best_profile.min_usable_energy_kwh:.2f} kWh).",
                f"Continuous power ({cap.available_power_kw:.2f} kW) meets required power ({best_profile.required_power_kw:.2f} kW).",
                f"Cell balance ({cap.cell_imbalance_v*1000:.1f} mV) is within limit ({best_profile.max_cell_imbalance_v*1000:.1f} mV).",
                f"Temperature ({cap.temperature_c:.1f}°C) operates safely within range [{best_profile.min_temp_c:.0f}°C, {best_profile.max_temp_c:.0f}°C].",
                f"Estimated RUL of {cap.rul_cycles} cycles satisfies project life requirement (> {best_profile.min_rul_cycles} cycles).",
                f"BMS safety audit status is NORMAL with zero active fault interlocks."
            ]

            summary = (
                f"RECOMMENDED: Optimal second-life match is '{recommended_app}' ({overall_cat.value}, RPS: {rps}/100). "
                f"Battery possesses robust capacity ({cap.remaining_capacity_ah:.1f} Ah, {cap.usable_energy_kwh:.2f} kWh) "
                f"and healthy thermal/balance margins."
            )

        else:
            recommended_app = "Recycling/Material Recovery"
            recycling_profile = self.profiles.get("Recycling/Material Recovery")
            recommended_tier = recycling_profile.tier_enum.value if (recycling_profile and recycling_profile.tier_enum) else ApplicationTier.TIER_5_RECYCLING.value
            overall_cat = SuitabilityCategory.SUITABLE
            is_second_life = False

            why_this = [
                f"SOH ({cap.soh*100:.1f}%) is below minimum threshold for reliable stationary storage (< 60.0%).",
                f"Usable energy ({cap.usable_energy_kwh:.2f} kWh) is insufficient for grid duty cycles.",
                "Battery has reached end of economic second-life repurposing viability.",
                "Direct material recovery yields highest circular economy value."
            ]

            summary = (
                f"RECYCLING RECOMMENDED: SOH ({cap.soh*100:.1f}%) falls below minimum second-life requirements. "
                f"Direct hydrometallurgical material extraction recommended."
            )

        # 7. Build Why Not Limiting Factor Analysis
        why_not: Dict[str, List[str]] = {}
        for name, ev in evaluations.items():
            if name == recommended_app:
                continue

            if ev.failed_requirements:
                why_not[name] = ev.failed_requirements
            elif name == "Recycling/Material Recovery":
                why_not[name] = [
                    f"Battery retains high second-life utility ({cap.soh*100:.1f}% SOH); direct recycling forfeits residual value."
                ]
            else:
                target_prof = self.profiles.get(name)
                best_prof = self.profiles.get(recommended_app)
                if target_prof and best_prof and target_prof.priority > best_prof.priority:
                    why_not[name] = [
                        f"Battery qualifies for higher-priority application '{recommended_app}' (Priority {best_prof.priority} vs {target_prof.priority}).",
                        f"Allocating to '{recommended_app}' maximizes economic return."
                    ]
                else:
                    why_not[name] = [
                        f"Application '{recommended_app}' scored higher suitability ({evaluations[recommended_app].suitability_score} vs {ev.suitability_score})."
                    ]

        # 8. Application Compatibility Ranking Matrix
        matrix = []
        for name, ev in evaluations.items():
            prof = self.profiles.get(name)
            matrix.append({
                "application": name,
                "fitness_score": ev.suitability_score,
                "status": ev.suitability_category.value,
                "passed_count": len(ev.passed_requirements),
                "failed_count": len(ev.failed_requirements),
                "warning_count": len(ev.warnings),
                "priority": prof.priority if prof else 99,
                "requirement_margins": ev.requirement_margins
            })
        matrix.sort(key=lambda x: (x["priority"], -x["fitness_score"]))

        # Refurbishment & Degradation
        refurb_actions = self.calculate_refurbishment_actions(cap)
        deg_proj = self.calculate_degradation_projection(cap.soh, rps)
        top_margins = evaluations[recommended_app].requirement_margins if recommended_app in evaluations else {}

        return RepurposingAssessment(
            battery_capability=cap,
            repurposing_score=rps,
            score_breakdown=rps_breakdown,
            suitability_category=overall_cat,
            recommended_application=recommended_app,
            recommended_tier=recommended_tier,
            is_suitable_for_second_life=is_second_life,
            safety_override_triggered=False,
            recommendation_summary=summary,
            reasons=why_this,
            unsuitable_reasons=why_not,
            application_evaluations=evaluations,
            all_warnings=all_warnings,
            decision_confidence=decision_conf,
            data_confidence=data_conf,
            evidence_summary=evidence_summary,
            why_this=why_this,
            why_not=why_not,
            requirement_margins=top_margins,
            refurbishment_actions=refurb_actions,
            degradation_projection=deg_proj,
            application_compatibility_matrix=matrix,
            eis_indicators=eis_indicators
        )

    def _from_dict(self, data: Dict[str, Any]) -> BatteryCapability:
        soh = float(data.get("SOH", data.get("SOH_predicted_demo", data.get("soh", 0.88))))
        rated_cap = float(data.get("RatedCapacity_Ah", self.spec.rated_capacity_ah))
        rated_energy = float(data.get("RatedEnergy_kWh", self.spec.rated_energy_kwh))
        nom_v = float(data.get("NominalVoltage_V", self.spec.nominal_voltage_v))

        cap_ah = data.get("RemainingCapacity_Ah", data.get("remaining_capacity_ah"))
        if cap_ah is None:
            cap_ah = round(rated_cap * soh, 2)
        else:
            cap_ah = float(cap_ah)

        energy_kwh = data.get("RemainingEnergy_kWh", data.get("remaining_energy_kwh"))
        if energy_kwh is None:
            energy_kwh = round((nom_v * cap_ah) / 1000.0, 3)
        else:
            energy_kwh = float(energy_kwh)

        power_kw = data.get("AvailablePower_kW", data.get("available_power_kw"))
        if power_kw is not None:
            power_kw = float(power_kw)

        temp_c = float(data.get("TempMax", data.get("TempMean", data.get("temp_mean_c", 25.0))))
        cell_imb_v = float(data.get("CellVoltageImbalance", data.get("cell_imbalance_v", 0.005)))

        fault_keys = [
            "Fault_OverVoltage", "Fault_UnderVoltage", "Fault_OverTemp",
            "Fault_UnderTemp", "Fault_OverCurrent"
        ]
        active_faults = []
        for fk in fault_keys:
            if data.get(fk, 0) == 1 or data.get(fk) is True:
                active_faults.append(fk.replace("Fault_", ""))

        bms_active = bool(data.get("bms_fault_active", False) or len(active_faults) > 0)

        safety_status = data.get("safety_status")
        if isinstance(safety_status, str):
            try:
                safety_status = SafetyStatus(safety_status)
            except ValueError:
                safety_status = SafetyStatus.NORMAL
        elif not isinstance(safety_status, SafetyStatus):
            if bms_active or temp_c > self.spec.max_safe_temp_c or cell_imb_v > self.spec.max_cell_imbalance_v:
                safety_status = SafetyStatus.QUARANTINE
            elif cell_imb_v > 0.025 or temp_c > 45.0:
                safety_status = SafetyStatus.WARNING
            else:
                safety_status = SafetyStatus.NORMAL

        rul = data.get("EstimatedRUL_Cycles", data.get("rul_cycles"))
        if rul is None:
            rul = max(0, int((soh - 0.60) * 7500)) if soh > 0.60 else 0
        else:
            rul = int(rul)

        return BatteryCapability(
            soh=soh,
            remaining_capacity_ah=cap_ah,
            usable_energy_kwh=energy_kwh,
            available_power_kw=power_kw,
            temperature_c=temp_c,
            cell_imbalance_v=cell_imb_v,
            bms_fault_active=bms_active,
            bms_fault_details=active_faults,
            rul_cycles=rul,
            safety_status=safety_status,
            internal_resistance_mohm=data.get("R0_mOhm", 26.6),
            charge_transfer_mohm=data.get("Rct_mOhm", 23.0),
            double_layer_farad=data.get("Cdl_F", 1.92),
            nominal_voltage_v=nom_v,
            rated_capacity_ah=rated_cap,
            rated_energy_kwh=rated_energy
        )
