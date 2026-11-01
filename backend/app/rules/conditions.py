"""Pure attribute condition evaluation.

CRITICAL HONESTY RULE (AGENT_RULES 6b, docs/04 s2):
Unknown is a valid state.
A rule condition on an unknown attribute NEVER matches.
Never turn 'could not tell' into a positive result or an alert.
"""

from app.core.types import AttrValue, TrackAttributes
from app.rules.models import ConditionSpec


def eval_condition(cond: ConditionSpec, attr_val: AttrValue | None) -> bool:
    """Evaluate a single ConditionSpec against an AttrValue.
    
    If attr_val is None or attr_val.state != 'known', return FALSE immediately.
    """
    if attr_val is None:
        return False

    if attr_val.state != "known":
        # Hard rule: unknown never matches any condition, including ne / not_in
        return False

    val = attr_val.value
    target = cond.value
    op = cond.op

    if op == "eq":
        return val == target
    elif op == "ne":
        return val != target
    elif op == "in":
        return val in target
    elif op == "not_in":
        return val not in target
    elif op == "startswith":
        return str(val).startswith(str(target))

    return False


def eval_where(where: list[ConditionSpec], track_attrs: TrackAttributes | None) -> bool:
    """Evaluate all conditions in a 'where' clause (ANDed).
    
    If 'where' is empty, returns True.
    If 'where' has conditions and track_attrs is None, returns False.
    """
    if not where:
        return True

    if track_attrs is None:
        return False

    for cond in where:
        attr_val = track_attrs.attrs.get(cond.attr)
        if not eval_condition(cond, attr_val):
            return False

    return True
