"""Serializable analysis objects; Abaqus objects never enter the plan."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any


def semantic_name(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", value):
        raise ValueError("Invalid semantic id: %r" % value)
    name = value if value.startswith("STEP05_") else "STEP05_" + value
    if len(name) > 80:
        raise ValueError("Semantic name exceeds 80 characters")
    return name


@dataclass
class AnalysisObject:
    semantic_id: str
    target_instance: str
    target_part: str
    source_rule: str
    parameters: dict[str, Any]
    validation_status: str = "RUNTIME_REQUIRED"


@dataclass
class PartitionRegion(AnalysisObject):
    pass


@dataclass
class SurfaceRegion(AnalysisObject):
    pass


@dataclass
class TieConnection:
    semantic_id: str
    master_region: str
    slave_region: str
    adjust: str = "DEFAULT"
    position_tolerance: str = "DEFAULT"


@dataclass
class ReferencePoint(AnalysisObject):
    pass


@dataclass
class CouplingConnection:
    semantic_id: str
    control_rp: str
    target_region: str
    coupling_type: str = "DISTRIBUTING"
    dofs: tuple[bool, ...] = (True, True, True, True, True, True)


@dataclass
class AnalysisPlan:
    project: dict[str, Any]
    instances: list[dict[str, Any]]
    partitions: list[PartitionRegion]
    regions: list[SurfaceRegion]
    ties: list[TieConnection] = field(default_factory=list)
    reference_points: list[ReferencePoint] = field(default_factory=list)
    couplings: list[CouplingConnection] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=lambda: {
        "status": "INPUT_VALIDATED_RUNTIME_REQUIRED", "errors": [], "warnings": []})
    future_defaults: dict[str, Any] = field(default_factory=lambda: {
        "tie": {"master_slave_policy": "PROGRAM_SELECTED_IN_A3", "adjust": "DEFAULT", "position_tolerance": "DEFAULT"},
        "coupling": {"coupling_type": "DISTRIBUTING", "dofs": [True, True, True, True, True, True]},
        "enabled": False})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        if self.ties or self.reference_points or self.couplings:
            raise ValueError("A2 enables partitions and regions only")
        names = [semantic_name(obj.semantic_id) for obj in self.partitions + self.regions]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate semantic object name")
        if len(self.regions) != 2 or len(self.partitions) != 3:
            raise ValueError("A2 requires exactly one beam/front-brace connection")
