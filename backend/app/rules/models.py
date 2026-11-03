"""Pydantic validation models for zones and registered actions.

Validates the full rule specification per docs/04 s5 and docs/03.
Fail fast on schema or logic mismatches.
"""

import datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.geometry import validate_polygon

# Valid attributes catalogue per docs/04 s2
VEHICLE_ATTRIBUTES = {
    "category", "heavy", "colour", "body_type",
    "plate", "registry_status", "registry_kind", "vehicle_id"
}
PERSON_ATTRIBUTES = {"id_state"}
ALL_ATTRIBUTES = VEHICLE_ATTRIBUTES | PERSON_ATTRIBUTES

VALID_OPS = {"eq", "ne", "in", "not_in", "startswith"}
VALID_TEMPLATES = {"presence", "dwell", "line_crossing", "count_threshold"}
VALID_SEVERITIES = {"low", "medium", "critical"}


class ConditionSpec(BaseModel):
    """Single condition on a track attribute."""
    attr: str
    op: str
    value: Any

    @field_validator("attr")
    @classmethod
    def validate_attr(cls, v: str) -> str:
        if v not in ALL_ATTRIBUTES:
            raise ValueError(f"Unknown attribute '{v}'. Allowed: {sorted(ALL_ATTRIBUTES)}")
        return v

    @field_validator("op")
    @classmethod
    def validate_op(cls, v: str) -> str:
        if v not in VALID_OPS:
            raise ValueError(f"Unknown operator '{v}'. Allowed: {sorted(VALID_OPS)}")
        return v

    @model_validator(mode="after")
    def validate_op_value_compatibility(self) -> "ConditionSpec":
        if self.op in ("in", "not_in") and not isinstance(self.value, (list, tuple, set)):
            raise ValueError(f"Operator '{self.op}' requires a list/tuple value, got {type(self.value)}")
        if self.op == "startswith" and not isinstance(self.value, str):
            raise ValueError(f"Operator 'startswith' requires a string value, got {type(self.value)}")
        return self


class SubjectSpec(BaseModel):
    """Subject definition for a rule."""
    kind: Literal["vehicle", "person"]
    where: list[ConditionSpec] = Field(default_factory=list)
    min_box_px: float | None = None

    @model_validator(mode="after")
    def validate_attribute_subject_kind(self) -> "SubjectSpec":
        allowed = VEHICLE_ATTRIBUTES if self.kind == "vehicle" else PERSON_ATTRIBUTES
        for c in self.where:
            if c.attr not in allowed:
                raise ValueError(
                    f"Attribute '{c.attr}' is not applicable to subject kind '{self.kind}'. "
                    f"Allowed for {self.kind}: {sorted(allowed)}"
                )
        return self


class TriggerSpec(BaseModel):
    """Trigger template configuration."""
    template: Literal["presence", "dwell", "line_crossing", "count_threshold"]
    min_seconds: float = 0.0
    dwell_seconds: float | None = None
    reset_after_s: float = 2.0
    count: int | None = None

    @model_validator(mode="after")
    def validate_template_params(self) -> "TriggerSpec":
        if self.template == "dwell":
            if self.dwell_seconds is None or self.dwell_seconds <= 0:
                raise ValueError("Trigger template 'dwell' requires 'dwell_seconds' > 0")
        elif self.template == "count_threshold" and (self.count is None or self.count <= 0):
            raise ValueError("Trigger template 'count_threshold' requires 'count' > 0")
        return self


class ConfirmSpec(BaseModel):
    """Rolling confirmation window configuration."""
    n_of_m: list[int] = Field(default_factory=lambda: [4, 5])
    min_confidence: float = 0.6

    @field_validator("n_of_m")
    @classmethod
    def validate_n_of_m(cls, v: list[int]) -> list[int]:
        if len(v) != 2:
            raise ValueError("n_of_m must be a list of two integers [n, m]")
        n, m = v
        if n <= 0 or m <= 0 or n > m:
            raise ValueError(f"Invalid n_of_m [{n}, {m}]: require 0 < n <= m")
        return v


VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleSpec(BaseModel):
    """Schedule specification for when the rule is armed."""
    days: list[str] = Field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
    from_time: str | None = Field(default=None, alias="from")
    to_time: str | None = Field(default=None, alias="to")
    timezone: str = "Asia/Kolkata"

    model_config = {"populate_by_name": True}

    @field_validator("days")
    @classmethod
    def validate_days(cls, v: list[str]) -> list[str]:
        for d in v:
            if d.lower() not in VALID_DAYS:
                raise ValueError(f"Invalid day '{d}'. Allowed: {sorted(VALID_DAYS)}")
        return [d.lower() for d in v]

    @field_validator("from_time", "to_time")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        if v is not None and not TIME_PATTERN.match(v):
            raise ValueError(f"Time '{v}' must be in HH:MM format (00:00 - 23:59)")
        return v


class ValidSpec(BaseModel):
    """Calendar validity date range (inclusive)."""
    from_date: str | None = None  # YYYY-MM-DD
    until_date: str | None = None # YYYY-MM-DD

    @field_validator("from_date", "until_date")
    @classmethod
    def validate_date_format(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                datetime.date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Date '{v}' must be in YYYY-MM-DD format") from None
        return v

    @model_validator(mode="after")
    def validate_date_order(self) -> "ValidSpec":
        if self.from_date and self.until_date:
            d_from = datetime.date.fromisoformat(self.from_date)
            d_until = datetime.date.fromisoformat(self.until_date)
            if d_from > d_until:
                raise ValueError(f"from_date '{self.from_date}' cannot be after until_date '{self.until_date}'")
        return self


class ExemptionsSpec(BaseModel):
    """Calendar exemption references."""
    calendar_ids: list[str] = Field(default_factory=list)
    note: str | None = ""


class EscalationRow(BaseModel):
    """Escalation rule by event count in time window."""
    if_count_in_window: dict[str, Any]  # e.g. {"n": 5, "window_min": 10}
    severity: Literal["low", "medium", "critical"]

    @model_validator(mode="after")
    def validate_count_window(self) -> "EscalationRow":
        w = self.if_count_in_window
        if "n" not in w or "window_min" not in w:
            raise ValueError("if_count_in_window requires 'n' and 'window_min'")
        if w["n"] <= 0 or w["window_min"] <= 0:
            raise ValueError("'n' and 'window_min' must be positive")
        return self


class ResponseSpec(BaseModel):
    """Response configuration when rule triggers."""
    severity: Literal["low", "medium", "critical"] = "medium"
    pre_roll_s: float = 15.0
    hold_s: float = 20.0
    max_clip_min: float = 15.0
    cooldown_s: float = 300.0
    alert_ttl_min: float = 240.0
    escalation: list[EscalationRow] = Field(default_factory=list)


class RegisteredActionSpec(BaseModel):
    """Full registered action specification."""
    name: str
    subject: SubjectSpec
    trigger: TriggerSpec
    confirm: ConfirmSpec = Field(default_factory=ConfirmSpec)
    schedule: ScheduleSpec | None = None
    valid: ValidSpec | None = None
    exemptions: ExemptionsSpec | None = None
    response: ResponseSpec = Field(default_factory=ResponseSpec)

    model_config = {"populate_by_name": True}


class ZoneSpec(BaseModel):
    """Zone specification."""
    id: str | None = None
    camera_id: str | None = None
    name: str
    kind: Literal["normal", "special"]
    shape: Literal["polygon", "line"]
    points: list[list[float]]  # list of [x, y] coordinates
    direction: Literal["in", "out", "both"] | None = None
    is_read_area: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def validate_zone_shape_and_points(self) -> "ZoneSpec":
        pts = self.points
        for p in pts:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                raise ValueError(f"Each point must have exactly 2 coordinates [x, y], got {p}")
            if not (isinstance(p[0], (int, float)) and isinstance(p[1], (int, float))):
                raise TypeError(f"Coordinates must be numeric, got {p}")
        if self.shape == "polygon":
            if len(pts) < 3 or len(pts) > 20:
                raise ValueError(f"Polygon must have between 3 and 20 points, got {len(pts)}")
            tuple_pts = [(float(p[0]), float(p[1])) for p in pts]
            is_valid, reason = validate_polygon(tuple_pts)
            if not is_valid:
                raise ValueError(f"Invalid polygon geometry: {reason}")
        elif self.shape == "line":
            if len(pts) != 2:
                raise ValueError(f"Line must have exactly 2 points, got {len(pts)}")
            if self.direction is None:
                self.direction = "in"
        return self


def validate_rule_zone_compatibility(rule: RegisteredActionSpec, zone: ZoneSpec) -> None:
    """Validate that the rule template is compatible with the zone shape and kind."""
    if zone.kind == "normal":
        raise ValueError("Cannot register an action on a 'normal' zone. Actions require a 'special' zone.")
    if rule.trigger.template == "line_crossing" and zone.shape != "line":
        raise ValueError(f"Trigger template 'line_crossing' requires a 'line' zone, got '{zone.shape}'")
    if rule.trigger.template in ("presence", "dwell", "count_threshold") and zone.shape != "polygon":
        raise ValueError(f"Trigger template '{rule.trigger.template}' requires a 'polygon' zone, got '{zone.shape}'")
