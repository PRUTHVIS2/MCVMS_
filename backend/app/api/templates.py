"""Rule templates, attribute catalogue, and presets API.

docs/04_ZONES_AND_RULES.md, docs/08_API_AND_UI.md:
- GET /api/v1/rule-templates: templates, catalogue, presets, and shape applicability.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import require_admin
from app.models.user import UserOut
from app.rules.models import (
    VALID_OPS,
    VALID_SEVERITIES,
)

router = APIRouter(tags=["templates"])


class TemplateInfo(BaseModel):
    template: str
    name: str
    description: str
    allowed_shapes: list[str]
    required_params: list[str]
    optional_params: list[str]


class AttributeInfo(BaseModel):
    attr: str
    type: str
    description: str
    allowed_ops: list[str]
    values: list[Any] | None = None


class RulePresetsResponse(BaseModel):
    templates: list[TemplateInfo]
    catalogue: dict[str, list[AttributeInfo]]
    operators: list[str]
    severities: list[str]
    presets: dict[str, dict[str, Any]]


TEMPLATES_LIST = [
    TemplateInfo(
        template="presence",
        name="Zone Presence",
        description="Fires when condition holds continuously for min_seconds while the subject is inside a polygon zone.",
        allowed_shapes=["polygon"],
        required_params=[],
        optional_params=["min_seconds"]
    ),
    TemplateInfo(
        template="dwell",
        name="Zone Dwell Time",
        description="Fires when subject stays in a polygon zone longer than dwell_seconds. Timer resets after reset_after_s outside.",
        allowed_shapes=["polygon"],
        required_params=["dwell_seconds"],
        optional_params=["reset_after_s"]
    ),
    TemplateInfo(
        template="line_crossing",
        name="Line Crossing",
        description="Fires when subject foot point crosses a line in configured direction with conditions satisfied at crossing tick.",
        allowed_shapes=["line"],
        required_params=[],
        optional_params=[]
    ),
    TemplateInfo(
        template="count_threshold",
        name="Count Threshold",
        description="Fires when at least count distinct tracks matching conditions are in the zone simultaneously for min_seconds.",
        allowed_shapes=["polygon"],
        required_params=["count"],
        optional_params=["min_seconds"]
    )
]

CATALOGUE = {
    "vehicle": [
        AttributeInfo(
            attr="category",
            type="string",
            description="Detected vehicle category",
            allowed_ops=["eq", "ne", "in", "not_in"],
            values=["two_wheeler", "auto_rickshaw", "car", "bus", "truck"]
        ),
        AttributeInfo(
            attr="heavy",
            type="boolean",
            description="Derived flag indicating heavy vehicle (bus, truck)",
            allowed_ops=["eq", "ne"],
            values=[True, False]
        ),
        AttributeInfo(
            attr="colour",
            type="string",
            description="Dominant vehicle colour from HSV classifier",
            allowed_ops=["eq", "ne", "in", "not_in"],
            values=["black", "white", "grey_silver", "red", "orange_yellow", "green", "blue", "brown"]
        ),
        AttributeInfo(
            attr="body_type",
            type="string",
            description="Body type if classifier enabled",
            allowed_ops=["eq", "ne", "in", "not_in"],
            values=["hatchback", "sedan", "suv", "van", "pickup"]
        ),
        AttributeInfo(
            attr="plate",
            type="string",
            description="Normalised license plate text",
            allowed_ops=["eq", "ne", "in", "not_in", "startswith"]
        ),
        AttributeInfo(
            attr="registry_status",
            type="string",
            description="Registry match status",
            allowed_ops=["eq", "ne"],
            values=["registered", "unregistered"]
        ),
        AttributeInfo(
            attr="registry_kind",
            type="string",
            description="Registry classification kind",
            allowed_ops=["eq", "ne", "in", "not_in"],
            values=["staff", "student", "visitor", "service", "other"]
        ),
        AttributeInfo(
            attr="vehicle_id",
            type="integer",
            description="Persistent linked vehicle ID",
            allowed_ops=["eq", "ne", "in", "not_in"]
        )
    ],
    "person": [
        AttributeInfo(
            attr="id_state",
            type="string",
            description="ID card wearing state (unknown never matches conditions)",
            allowed_ops=["eq", "ne"],
            values=["wearing", "not_wearing"]
        )
    ]
}

PRESETS = {
    "heavy_vehicle": {
        "name": "No heavy vehicles during restricted hours",
        "subject": {
            "kind": "vehicle",
            "where": [{"attr": "heavy", "op": "eq", "value": True}],
            "min_box_px": 80
        },
        "trigger": {
            "template": "presence",
            "min_seconds": 2.0
        },
        "confirm": {
            "n_of_m": [4, 5],
            "min_confidence": 0.6
        },
        "schedule": {
            "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
            "from": "09:00",
            "to": "17:00",
            "timezone": "Asia/Kolkata"
        },
        "response": {
            "severity": "critical",
            "pre_roll_s": 15.0,
            "hold_s": 20.0,
            "max_clip_min": 15.0,
            "cooldown_s": 300.0,
            "alert_ttl_min": 240.0,
            "escalation": []
        }
    },
    "any_vehicle": {
        "name": "Any vehicle entered zone",
        "subject": {
            "kind": "vehicle",
            "where": []
        },
        "trigger": {
            "template": "presence",
            "min_seconds": 0.0
        },
        "confirm": {
            "n_of_m": [3, 5],
            "min_confidence": 0.5
        },
        "response": {
            "severity": "medium",
            "pre_roll_s": 10.0,
            "hold_s": 15.0,
            "cooldown_s": 60.0,
            "alert_ttl_min": 60.0,
            "escalation": []
        }
    },
    "unregistered_vehicle": {
        "name": "Unregistered vehicle in zone",
        "subject": {
            "kind": "vehicle",
            "where": [{"attr": "registry_status", "op": "eq", "value": "unregistered"}]
        },
        "trigger": {
            "template": "presence",
            "min_seconds": 2.0
        },
        "confirm": {
            "n_of_m": [4, 5],
            "min_confidence": 0.6
        },
        "response": {
            "severity": "medium",
            "cooldown_s": 300.0,
            "alert_ttl_min": 120.0,
            "escalation": []
        }
    },
    "vehicle_dwell": {
        "name": "Vehicle stays too long",
        "subject": {
            "kind": "vehicle",
            "where": []
        },
        "trigger": {
            "template": "dwell",
            "dwell_seconds": 300.0,
            "reset_after_s": 2.0
        },
        "confirm": {
            "n_of_m": [4, 5],
            "min_confidence": 0.5
        },
        "response": {
            "severity": "medium",
            "cooldown_s": 300.0,
            "alert_ttl_min": 120.0,
            "escalation": []
        }
    },
    "vehicle_count": {
        "name": "Vehicle count above threshold",
        "subject": {
            "kind": "vehicle",
            "where": []
        },
        "trigger": {
            "template": "count_threshold",
            "count": 5,
            "min_seconds": 5.0
        },
        "confirm": {
            "n_of_m": [4, 5],
            "min_confidence": 0.5
        },
        "response": {
            "severity": "medium",
            "cooldown_s": 300.0,
            "alert_ttl_min": 120.0,
            "escalation": []
        }
    },
    "line_crossing": {
        "name": "Vehicle crosses line",
        "subject": {
            "kind": "vehicle",
            "where": []
        },
        "trigger": {
            "template": "line_crossing"
        },
        "confirm": {
            "n_of_m": [2, 3],
            "min_confidence": 0.5
        },
        "response": {
            "severity": "low",
            "cooldown_s": 30.0,
            "alert_ttl_min": 60.0,
            "escalation": []
        }
    },
    "person_no_id": {
        "name": "Person without visible ID card",
        "subject": {
            "kind": "person",
            "where": [{"attr": "id_state", "op": "eq", "value": "not_wearing"}],
            "min_box_px": 150.0
        },
        "trigger": {
            "template": "presence",
            "min_seconds": 1.0
        },
        "confirm": {
            "n_of_m": [4, 5],
            "min_confidence": 0.6
        },
        "response": {
            "severity": "low",
            "cooldown_s": 60.0,
            "alert_ttl_min": 120.0,
            "escalation": [
                {"if_count_in_window": {"n": 5, "window_min": 10}, "severity": "medium"}
            ]
        }
    }
}


@router.get("/rule-templates", response_model=RulePresetsResponse)
def get_rule_templates(
    current_user: Annotated[UserOut, Depends(require_admin)]
):
    return RulePresetsResponse(
        templates=TEMPLATES_LIST,
        catalogue=CATALOGUE,
        operators=sorted(VALID_OPS),
        severities=sorted(VALID_SEVERITIES),
        presets=PRESETS
    )
