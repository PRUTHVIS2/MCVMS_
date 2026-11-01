"""Pure rules package.

Exports: RuleEngine, CompiledRule, CompiledZone, RulesConfig, Decision.
Models: RegisteredActionSpec, ZoneSpec, SubjectSpec, TriggerSpec, etc.
"""

from app.rules.conditions import eval_condition, eval_where
from app.rules.engine import CompiledRule, CompiledZone, Decision, RuleEngine, RulesConfig
from app.rules.escalation import pick_severity
from app.rules.models import (
    ConfirmSpec,
    EscalationRow,
    ExemptionsSpec,
    RegisteredActionSpec,
    ResponseSpec,
    ScheduleSpec,
    SubjectSpec,
    TriggerSpec,
    ValidSpec,
    ZoneSpec,
    validate_rule_zone_compatibility,
)
from app.rules.schedule import is_in_schedule, is_in_valid_dates, is_rule_armed

__all__ = [
    "CompiledRule",
    "CompiledZone",
    "ConfirmSpec",
    "Decision",
    "EscalationRow",
    "ExemptionsSpec",
    "RegisteredActionSpec",
    "ResponseSpec",
    "RuleEngine",
    "RulesConfig",
    "ScheduleSpec",
    "SubjectSpec",
    "TriggerSpec",
    "ValidSpec",
    "ZoneSpec",
    "eval_condition",
    "eval_where",
    "is_in_schedule",
    "is_in_valid_dates",
    "is_rule_armed",
    "pick_severity",
    "validate_rule_zone_compatibility",
]
