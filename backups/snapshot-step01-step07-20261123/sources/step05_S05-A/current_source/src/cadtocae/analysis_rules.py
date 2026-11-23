"""Role-based A2 planning. No structure-type dispatch or script-text parsing."""
from __future__ import annotations

import math
from .analysis_inputs import normalize_inputs
from .analysis_plan import AnalysisPlan, PartitionRegion, SurfaceRegion, semantic_name


def resolve_role(instances, role, instance_id=None, connection_group=None):
    found = [item for item in instances
             if (item.get("canonical_role") or item.get("component_code")) == role
             and (instance_id is None or item.get("instance_name") == instance_id)
             and (connection_group is None or item.get("connection_group") == connection_group)]
    if len(found) != 1:
        raise ValueError("Unresolved/ambiguous role %s: %d candidates" % (role, len(found)))
    return found[0]


def build_analysis_plan(summary, inputs):
    data = normalize_inputs(inputs)
    info = data["Project_Info"]
    if summary.get("project_id") != info["project_id"] or summary.get("model_name") != info["project_id"]:
        raise ValueError("project_id/model_name mismatch")
    semantic_name(info["project_id"].upper().replace("-", "_"))
    instances = summary.get("instances", [])
    ids = [item.get("instance_name") for item in instances]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Invalid/duplicate instance_name")
    rows = [row for row in data["Partition_Region"] if row["enabled"]]
    if len(rows) != 1:
        raise ValueError("A2 supports one front-brace connection at a time")
    row = rows[0]
    if (row["partition_rule"], row["connection_id"], row["target_role"], row["reference_station"], row["region_id"]) != (
            "BEAM_LOCAL_PATCH", "BEAM_BRACE_FRONT", "INCLINED_BEAM", "C", "REGION_BEAM_BRACE_FRONT"):
        raise ValueError("Unsupported A2 rule; only BEAM_BRACE_FRONT at C is enabled")
    station = summary.get("assembly_points", {}).get("C")
    if not isinstance(station, (list, tuple)) or len(station) != 3 or any(
            isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in station):
        raise ValueError("Missing/invalid assembly station C")
    beam = resolve_role(instances, "INCLINED_BEAM", row.get("instance_id"), row.get("connection_group"))
    brace = resolve_role(instances, "BRACE_FRONT", row.get("brace_instance_id"))
    for item in (beam, brace):
        length = item.get("geometry_info", {}).get("length")
        if not isinstance(length, (int, float)) or isinstance(length, bool) or not math.isfinite(length) or length <= 0:
            raise ValueError("Missing/invalid Part length: " + item["instance_name"])
        if item.get("geometry_info", {}).get("section_kind") != "C_CHANNEL":
            raise ValueError("A2 currently supports shell C_CHANNEL geometry only")
        if not item.get("part_name"):
            raise ValueError("Missing Part reference")
        placement = item.get("placement", {})
        if "rotation_steps" not in placement or "translation" not in placement:
            raise ValueError("unsupported transform contract: incomplete placement")
        # Numerical contract validation; ordering is resolved against runtime geometry.
        from .analysis_geometry import placement_candidates
        placement_candidates(placement)
    if beam["part_name"] == brace["part_name"]:
        raise ValueError("Beam and brace cannot share the same Part in A2")
    if row["half_length_m"] * 2 >= beam["geometry_info"]["length"]:
        raise ValueError("Patch cannot fit within beam length")
    common = {"reference_station": "C", "station_global": list(station),
              "half_length_m": row["half_length_m"], "source_input": row["source_input"]}
    partitions = [PartitionRegion("PARTITION_BEAM_C_" + sign, beam["instance_name"], beam["part_name"],
                                 "BEAM_LOCAL_PATCH", dict(common, boundary=sign)) for sign in ("MINUS", "PLUS")]
    partitions.append(PartitionRegion("PARTITION_BRACE_FRONT_CONTACT", brace["instance_name"], brace["part_name"],
                                      "BEAM_PHYSICAL_PLANE", dict(common)))
    regions = [SurfaceRegion("REGION_BEAM_BRACE_FRONT", beam["instance_name"], beam["part_name"],
                             "BEAM_LOWER_FLANGE", dict(common, physical_contact="OUTER_SURFACE")),
               SurfaceRegion("REGION_BRACE_FRONT_BEAM", brace["instance_name"], brace["part_name"],
                             "BRACE_PLANE_INTERSECTION", dict(common, physical_contact="BEAM_OUTER_PLANE"))]
    plan = AnalysisPlan(dict(info, phase="A2", producer=summary.get("assembly_info", {})),
                        [dict(item, affected_instances=[i["instance_name"] for i in instances
                                                       if i["part_name"] == item["part_name"]]) for item in (beam, brace)],
                        partitions, regions)
    plan.validate()
    return plan
