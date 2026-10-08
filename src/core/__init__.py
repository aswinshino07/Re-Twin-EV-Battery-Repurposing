"""
Core modules for RE-TWIN: State definitions, CAN/DBC decoder, and Feature Engine.
"""

from .battery_state import (
    DataCategory,
    SafetyStatus,
    ApplicationTier,
    BatteryPackSpec,
    BatteryStateSnapshot,
    ElectrochemicalState,
    HealthDecisionState,
)
