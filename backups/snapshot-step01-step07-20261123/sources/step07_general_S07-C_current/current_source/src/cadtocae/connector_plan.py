"""Step06 future connector intent only. No wire, section, behavior or CAE objects."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .hole_plan import HolePlan

PROPERTY_FAMILIES = ("PURLIN_BOLT", "HOOP_BOLT")


@dataclass(frozen=True)
class ConnectorIntent:
    connector_id: str
    source_driving_hole_id: str
    target_derived_hole_id: str
    connector_property: str = "PURLIN_BOLT"
    behavior_status: str = "NOT_CALIBRATED"
    validation_status: str = "HOLE_GEOMETRY_PENDING_RUNTIME"


@dataclass(frozen=True)
class ConnectorPlan:
    hole_plan: HolePlan
    connections: tuple[ConnectorIntent, ...]
    phase: str = "INPUT_AND_PLAN_ONLY"

    def to_dict(self):
        return asdict(self)


def build_connector_plan(holes: HolePlan):
    connections = []
    used = set()
    for driving in holes.driving_holes:
        targets = [h for h in holes.derived_holes if h.source_driving_hole_id == driving.driving_hole_id]
        if len(targets) != 1:
            raise ValueError("Each driving hole requires exactly one derived hole")
        target = targets[0]
        if (target.project_id, target.connection_group, target.target_role, target.hole_diameter_m) != (
                driving.project_id, driving.connection_group, driving.connection_target_role, driving.hole_diameter_m):
            raise ValueError("Driving/derived hole contract mismatch")
        name = "STEP06_CONNECTOR_" + driving.connection_group + "_" + driving.hole_id
        if name in used:
            raise ValueError("Duplicate connector semantic ID")
        used.add(name)
        connections.append(ConnectorIntent(name, driving.driving_hole_id, target.derived_hole_id))
    if len(connections) != len(holes.derived_holes):
        raise ValueError("Orphan derived hole")
    return ConnectorPlan(holes, tuple(connections))
