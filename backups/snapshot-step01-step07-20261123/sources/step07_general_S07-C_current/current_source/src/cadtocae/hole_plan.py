"""Pure Step06 driving/derived hole plans. No CAE operations or guessed intersections."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
import math
from pathlib import Path
import tempfile

from .analysis_geometry import placement_candidates, transform, matvec, add, sub, scale, unit, cross
from .hole_transforms import step04_validate_anchors, step04_local_point_to_global, step04_local_vector_to_global
from .hole_inputs import HoleLocationRow, positive_number, read_hole_inputs
from .workbook import export_abaqus_json

TOLERANCE_M = 1.e-9
SURFACES = {"PURLIN_LOCAL": "PURLIN_LOCAL_WEB", "INCLINED_BEAM": "INCLINED_BEAM_TOP_FLANGE"}


@dataclass(frozen=True)
class SharedPartInfo:
    part_name: str
    instance_names: tuple[str, ...]
    shared_part: bool
    requires_instance_isolation: bool
    hole_pattern_identical: bool | None = None
    execution_policy: str = "TARGET_SURFACE_PENDING_RUNTIME"


@dataclass(frozen=True)
class DrivingHoleSpec:
    driving_hole_id: str
    project_id: str
    connection_group: str
    hole_id: str
    source_role: str
    source_instance: str
    source_part: str
    connection_target_role: str
    leg: str
    distance_from_angle_corner_m: float
    distance_from_end_m: float
    end_reference: str
    hole_diameter_m: float | None
    local_center_m: tuple[float, float, float]
    local_axis: tuple[float, float, float]
    enabled: bool
    validation_status: str
    source_row: int
    shared_part_info: SharedPartInfo
    corner_reference: str = "ANGLE_OUTER_PLANES_THEORETICAL_INTERSECTION"
    center_reference: str = "LEG_MID_THICKNESS"
    axis_convention: str = "UNDIRECTED_HOLE_AXIS"
    hole_type: str = "ROUND"
    width_m: float = 0.
    total_length_m: float = 0.
    major_axis: str | None = None
    local_major_axis: tuple[float, float, float] | None = None
    source_geometry: dict = field(default_factory=dict)
    source_file: str = ""
    source_sheet: str = ""


@dataclass(frozen=True)
class DerivedHoleSpec:
    derived_hole_id: str
    source_driving_hole_id: str
    project_id: str
    connection_group: str
    target_role: str
    target_instance: str
    target_part: str
    derivation_method: str
    global_source_center_m: tuple[float, float, float] | None
    global_axis: tuple[float, float, float] | None
    target_local_center_m: None
    target_local_axis: None
    hole_diameter_m: float | None
    target_surface_role: str
    validation_status: str
    source_pose_status: str
    target_pose_status: str
    shared_part_info: SharedPartInfo
    hole_type: str = "ROUND"
    width_m: float = 0.
    total_length_m: float = 0.
    major_axis: str | None = None


@dataclass(frozen=True)
class HolePlan:
    project_id: str
    driving_holes: tuple[DrivingHoleSpec, ...]
    derived_holes: tuple[DerivedHoleSpec, ...]
    disabled_hole_ids: tuple[str, ...]
    validation_status: str = "INPUT_VALIDATED_RUNTIME_REQUIRED"
    schema_version: str = "step06-hole-setup-v0.1"
    benchmark_scope: str = "P01"
    shared_part_policy: str = "IDENTICAL_PATTERN_MODIFY_ONCE"
    part_executions: tuple[dict, ...] = ()

    def to_dict(self):
        return asdict(self)


def _one(items, label):
    if len(items) != 1:
        raise ValueError("Expected unique %s; found %d" % (label, len(items)))
    return items[0]


def _role(instance):
    return instance.get("canonical_role") or instance.get("component_code")


def _instances(summary):
    members = summary.get("instances")
    if not isinstance(members, list) or not members:
        raise ValueError("assembly_summary.instances required")
    names = set()
    for member in members:
        for key in ("instance_name", "part_name", "component_code"):
            if not isinstance(member.get(key), str) or not member[key].strip():
                raise ValueError("Missing instance " + key)
        if member["instance_name"] in names:
            raise ValueError("Duplicate instance_name")
        names.add(member["instance_name"])
    return members


def _shared(member, members):
    names = tuple(sorted(m["instance_name"] for m in members if m["part_name"] == member["part_name"]))
    return SharedPartInfo(member["part_name"], names, len(names) > 1, len(names) > 1)


def _pattern(rows, component):
    """Compare physical Part-local cuts, not row/group IDs or Assembly placement."""
    result = []
    for row in sorted(rows, key=lambda r:r.hole_id):
        center, axis = _local_hole(row, component)
        if not row.enabled:
            continue
        width = row.hole_diameter_mm / 1000.
        major = (0., 0., 1.) if row.slot_major_axis == "PART_LENGTH" else ((1., 0., 0.) if axis[1] else (0., 1., 0.))
        result.append(dict(hole_id=row.hole_id, hole_type=row.hole_type, width_m=width,
                           total_length_m=row.slot_total_length_mm/1000. if row.hole_type == "SLOT" else width,
                           local_center_m=center, local_axis=axis,
                           local_major_axis=major if row.hole_type == "SLOT" else None))
    return result


def _part_executions(members, rows, components):
    executions = []
    for source in members:
        if _role(source) != "PURLIN_SUPPORT" or source.get("connection_group") != "P01":
            continue
        standard_rows = [r for r in rows if r.connection_group == "P01"]
        if not standard_rows:
            continue
        component = _component(source, components)
        standard = _pattern(standard_rows, component)
        references = sorted((m for m in members if m['part_name'] == source['part_name']), key=lambda m:m['instance_name'])
        evidence, reasons = [], []
        for member in references:
            group = member.get('connection_group')
            explicit = [r for r in rows if r.connection_group == group]
            # Engineering rule: unlisted support instances on this Part inherit P01's standard pattern.
            selected = explicit if explicit else standard_rows
            candidate = _component(member, components) if _role(member) == 'PURLIN_SUPPORT' else None
            geometry_matches = candidate == component and member.get('geometry_info') == source.get('geometry_info')
            pattern = _pattern(selected, candidate) if candidate else []
            if _role(member) != 'PURLIN_SUPPORT' or not geometry_matches:
                reasons.append(member['instance_name'] + ': role/geometry evidence mismatch')
            if pattern != standard:
                reasons.append(member['instance_name'] + ': different Part-local hole pattern')
            evidence.append(dict(instance_name=member['instance_name'], canonical_role=_role(member),
                                 source_part=member['part_name'], geometry_matches=geometry_matches,
                                 pattern_source='EXPLICIT_GROUP' if explicit else 'P01_STANDARD_INHERITED',
                                 connection_group=group, hole_pattern=pattern))
        identical = not reasons
        pattern_conflict = any(e['geometry_matches'] and e['canonical_role'] == 'PURLIN_SUPPORT'
                               and e['hole_pattern'] != standard for e in evidence)
        policy = ('PART_ISOLATION_REQUIRED' if pattern_conflict else 'PART_EVIDENCE_REVIEW_REQUIRED') if reasons else (
            'MODIFY_SHARED_PART_ONCE' if len(references) > 1 else 'MODIFY_PART_ONCE')
        executions.append(dict(source_part=source['part_name'], shared_part=len(references)>1,
                               referencing_instances=[m['instance_name'] for m in references],
                               expected_affected_instances=[m['instance_name'] for m in references],
                               hole_pattern_identical=identical, requires_instance_isolation=pattern_conflict,
                               execution_policy=policy, standard_hole_pattern=standard,
                               instance_patterns=evidence, blocking_reasons=reasons))
    return tuple(executions)


def _component(member, components):
    component = _one([c for c in components if c.get("part_name") == member["part_name"]
                      and c.get("component_code") == member["component_code"]],
                     "normalized component " + member["part_name"])
    length = positive_number(component.get("length_m"), "component length_m")
    reported = positive_number((member.get("geometry_info") or {}).get("length"), "summary geometry length")
    if abs(length - reported) > TOLERANCE_M:
        raise ValueError("Workbook/summary length mismatch: " + member["part_name"])
    return component


def _local_hole(row, component):
    if component.get("section_kind") != "ANGLE" or component.get("model_policy") != "SOLID":
        raise ValueError("Phase 1 requires a Step02 SOLID ANGLE support")
    params = component.get("section_params_m") or {}
    a, b, thickness = [positive_number(params.get(k), k) for k in ("leg_a_m", "leg_b_m", "t_m")]
    radius = params.get("inner_root_radius_m", 0.)
    if isinstance(radius, bool) or not isinstance(radius, (float, int)) or not math.isfinite(radius) or radius < 0:
        raise ValueError("Invalid inner_root_radius_m")
    if min(a, b) <= thickness + radius or abs(a - b) <= TOLERANCE_M:
        raise ValueError("Invalid/ambiguous LONG_LEG and SHORT_LEG geometry")
    # Step02 a extends along +X, b along +Y, extrusion along +Z.
    along_x = (row.leg == "LONG_LEG") == (a > b)
    leg_length = a if along_x else b
    length = positive_number(component.get("length_m"), "length_m")
    distance = row.distance_from_angle_corner_mm / 1000.
    end = row.distance_from_end_mm / 1000.
    hole_radius = row.hole_diameter_mm / 2000.
    major_half = row.slot_total_length_mm / 2000. if row.hole_type == "SLOT" else hole_radius
    radial_half = major_half if row.slot_major_axis == "LEG_DIRECTION" else hole_radius
    length_half = major_half if row.slot_major_axis == "PART_LENGTH" else hole_radius
    z = end if row.end_reference == "START" else length - end
    # Geometric containment only: no code-prescribed structural edge distance.
    if distance - radial_half <= thickness + radius + TOLERANCE_M:
        raise ValueError("Hole overlaps angle root/fillet exclusion region")
    if distance + radial_half >= leg_length - TOLERANCE_M:
        raise ValueError("Hole exceeds leg/free-edge clearance")
    if min(z, length - z) <= length_half + TOLERANCE_M:
        raise ValueError("Hole exceeds support length/end-edge clearance")
    center = (distance, thickness / 2., z) if along_x else (thickness / 2., distance, z)
    axis = (0., 1., 0.) if along_x else (1., 0., 0.)
    return center, axis


def _unique_pose(member):
    placement = member.get("placement")
    if not isinstance(placement, dict):
        raise ValueError("Missing placement: " + member["instance_name"])
    candidates = placement_candidates(placement)
    first = candidates[0]
    for pose in candidates:
        numbers = list(pose["translation"]) + [v for row in pose["rotation"] for v in row]
        if not all(math.isfinite(x) for x in numbers):
            raise ValueError("Non-finite placement")
        for basis in ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.)):
            if max(abs(x-y) for x, y in zip(transform(first, basis), transform(pose, basis))) > TOLERANCE_M:
                return None
    return first


def build_hole_plan(summary, rows: list[HoleLocationRow], components):
    """Resolve P01-P04 patterns; execute the P01 source Part once, including identical references.

    Target surface names express intent only. No face intersection is performed.
    """
    project = summary.get("project_id")
    if not isinstance(project, str) or not project or summary.get("model_name") != project:
        raise ValueError("assembly_summary project_id/model_name mismatch")
    if not rows or any(r.project_id != project for r in rows):
        raise ValueError("Matching project required")
    for group in sorted({r.connection_group for r in rows}):
        selected = [r for r in rows if r.connection_group == group]
        if len(selected) != 2 or {r.hole_id for r in selected} != {"PS_TO_PURLIN", "PS_TO_BEAM"}:
            raise ValueError(group + " requires the two distinct driving rows")
    members = _instances(summary)
    driving, derived, disabled = [], [], []
    for row in sorted(rows, key=lambda r: (r.connection_group, r.hole_id)):
        group = row.connection_group
        source = _one([m for m in members if _role(m) == "PURLIN_SUPPORT" and m.get("connection_group") == group],
                      group + " PURLIN_SUPPORT")
        component = _component(source, components)
        center, axis = _local_hole(row, component)
        driving_id = "STEP06_DRIVING_" + group + "_" + row.hole_id
        if not row.enabled:
            disabled.append(driving_id)
            continue
        target = _one([m for m in members if _role(m) == row.connection_target
                       and (row.connection_target == "INCLINED_BEAM" or m.get("connection_group") == group)],
                      "target " + row.connection_target)
        target_component = _component(target, components)
        if target_component.get("section_kind") != "C_CHANNEL" or target_component.get("model_policy") != "SHELL":
            raise ValueError("Phase 1 target requires C_CHANNEL SHELL")
        source_pose, target_pose = _unique_pose(source), _unique_pose(target)
        width = row.hole_diameter_mm / 1000.
        total_length = row.slot_total_length_mm / 1000. if row.hole_type == "SLOT" else width
        major = (0., 0., 1.) if row.slot_major_axis == "PART_LENGTH" else ((1., 0., 0.) if axis[1] else (0., 1., 0.))
        geometry = dict(component["section_params_m"], length_m=component["length_m"],
                        section_kind=component["section_kind"], model_policy=component["model_policy"])
        driving.append(DrivingHoleSpec(
            driving_id, project, group, row.hole_id, "PURLIN_SUPPORT", source["instance_name"], source["part_name"],
            row.connection_target, row.leg, row.distance_from_angle_corner_mm / 1000.,
            row.distance_from_end_mm / 1000., row.end_reference, width if row.hole_type == "ROUND" else None,
            center, axis, True, "GEOMETRY_PREFLIGHT_PASSED_RUNTIME_REQUIRED", row.source_row, _shared(source, members),
            hole_type=row.hole_type, width_m=width, total_length_m=total_length,
            major_axis=row.slot_major_axis, local_major_axis=major if row.hole_type == "SLOT" else None,
            source_geometry=geometry, source_file=row.source_file, source_sheet=row.source_sheet))
        suffix = "PURLIN" if row.connection_target == "PURLIN_LOCAL" else "BEAM"
        derived.append(DerivedHoleSpec(
            "STEP06_DERIVED_" + group + "_" + suffix + "_FROM_SUPPORT", driving_id, project, group,
            row.connection_target, target["instance_name"], target["part_name"], "AXIS_SURFACE_INTERSECTION",
            tuple(transform(source_pose, center)) if source_pose else None,
            tuple(matvec(source_pose["rotation"], axis)) if source_pose else None,
            None, None, width if row.hole_type == "ROUND" else None, SURFACES[row.connection_target],
            "TARGET_SURFACE_PENDING_RUNTIME",
            "SUMMARY_TRANSFORM_UNAMBIGUOUS_RUNTIME_UNVERIFIED" if source_pose else "POSE_PENDING_RUNTIME",
            "SUMMARY_TRANSFORM_UNAMBIGUOUS_RUNTIME_UNVERIFIED" if target_pose else "POSE_PENDING_RUNTIME",
            _shared(target, members), row.hole_type, width, total_length, row.slot_major_axis))
    executions = _part_executions(members, rows, components)
    by_part = {e['source_part']:e for e in executions}
    for i, hole in enumerate(driving):
        if hole.source_part in by_part:
            e = by_part[hole.source_part]
            driving[i] = replace(hole, shared_part_info=SharedPartInfo(
                hole.source_part, tuple(e['referencing_instances']), e['shared_part'],
                e['requires_instance_isolation'], e['hole_pattern_identical'], e['execution_policy']))
    return HolePlan(project, tuple(driving), tuple(derived), tuple(disabled), part_executions=executions)


def load_hole_plan(components_path, summary_path, hole_input_path):
    """Consume stable data only. The temporary normalized component JSON is private."""
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8-sig"))
    with tempfile.TemporaryDirectory(prefix="step06_components_") as directory:
        normalized = export_abaqus_json(components_path, Path(directory) / "components.json", selection="complete")
        components = json.loads(normalized.read_text(encoding="utf-8"))["components"]
    return build_hole_plan(summary, read_hole_inputs(hole_input_path), components)


def _step04_summary_anchors(summary, member, component, components):
    """Independent assembly anchors; never manufacture expected points from placement itself."""
    if member.get('transform_anchors'):
        return member['transform_anchors']
    if member.get('local_anchor') is not None and member.get('global_anchor') is not None:
        return [dict(name=member.get('global_anchor_name','assembly_anchor'),
                     local_point=member['local_anchor'], expected_global=member['global_anchor'])]
    points = summary.get('assembly_points') or {}
    role = _role(member)
    if role in ('INCLINED_BEAM', 'BRACE_FRONT', 'BRACE_REAR'):
        names = {'INCLINED_BEAM': ('G_global','F','C','E'),
                 'BRACE_FRONT': ('B','C'), 'BRACE_REAR': ('D','E')}[role]
        if names[0] not in points or names[1] not in points:
            return []
        origin = points[names[0]]
        tangent = unit(sub(points[names[1]], origin))
        anchors = []
        for name in names:
            if name in points:
                delta = sub(points[name], origin)
                station = sum(delta[i]*tangent[i] for i in range(3))
                anchors.append(dict(name=name+' / C_CHANNEL_WEB_MIDPOINT',
                    local_point=[0.,component['section_params_m']['h_m']/2.,station],
                    expected_global=points[name]))
        return anchors
    group = member.get('connection_group')
    station = 'P'+str(int(group[1:])) if group in ('P01','P02','P03','P04') else None
    if role not in ('PURLIN_SUPPORT','PURLIN_LOCAL') or station not in points or 'G_global' not in points or 'F' not in points:
        return []
    # Same explicit section-reference rules as Step04; all global anchors come from summary points.
    from .main_frame_assembly import _beam_top_surface_offset, _beam_section_center_offset, PURLIN_BEAM_GAP_M
    beam = _one([c for c in components if c.get('component_code') == 'INCLINED_BEAM'], 'beam anchor component')
    tangent = unit(sub(points['F'], points['G_global']))
    normal = unit(cross(tangent, (0.,1.,0.)))
    if normal[2] < 0.:
        normal = scale(normal,-1.)
    offset = _beam_top_surface_offset(beam)
    if role == 'PURLIN_LOCAL':
        offset += PURLIN_BEAM_GAP_M + component['section_params_m']['t_m']/2.
    expected = add(add(points[station],(0.,_beam_section_center_offset(beam),0.)),scale(normal,offset))
    return [dict(name=station+' / '+role+' Step04 section reference',
                 local_point=[0.,0.,component['length_m']/2.], expected_global=expected)]


def build_step06_a_plan(summary, rows, components):
    """Expand the shared standard to every present P01-P04 support, without copying XYZ to targets."""
    members = _instances(summary)
    standard = [r for r in rows if r.connection_group == 'P01']
    source = _one([m for m in members if _role(m) == 'PURLIN_SUPPORT' and m.get('connection_group') == 'P01'], 'P01 support')
    expanded = list(rows)
    inherited = []
    for member in members:
        if _role(member) != 'PURLIN_SUPPORT':
            continue
        group = member.get('connection_group')
        if group not in ('P01','P02','P03','P04'):
            raise ValueError('Step06-A supports P01-P04 groups only')
        if member['part_name'] != source['part_name']:
            raise ValueError('Step06-A currently requires one standard support Part')
        if not any(r.connection_group == group for r in rows):
            expanded.extend(replace(r, connection_group=group) for r in standard)
            inherited.append(group)
    plan = build_hole_plan(summary, expanded, components).to_dict()
    for group in {m.get('connection_group') for m in members if _role(m) == 'PURLIN_SUPPORT'}:
        if len([h for h in plan['driving_holes'] if h['connection_group'] == group]) != 2:
            raise ValueError('Step06-A requires both enabled driving holes in ' + group)
    plan.update(schema_version='step06-hole-setup-v0.2', benchmark_scope='P01-P04',
                runtime_mode='STEP06_A', inherited_standard_groups=sorted(inherited))
    required = {h['source_instance'] for h in plan['driving_holes']} | {h['target_instance'] for h in plan['derived_holes']}
    plan['instances'] = []
    for member in members:
        if member['instance_name'] in required:
            component = _component(member, components)
            plan['instances'].append(dict(member, component_geometry=component,
                transform_anchors=_step04_summary_anchors(summary, member, component, components)))
    validation = dict(contract='PRE_TRANSLATION_ROTATIONS_THEN_TRANSLATION_THEN_POST_TRANSLATION_ROTATIONS', status='PASSED', instances=[], errors=[])
    for member in plan['instances']:
        checks = []
        state = 'PASSED'
        try:
            step04_validate_anchors(member['placement'], member['transform_anchors'], results=checks)
        except (ValueError, KeyError, TypeError) as exc:
            state = 'NEEDS_REVIEW'
            validation['status'] = 'NEEDS_REVIEW'
            validation['errors'].append(member['instance_name']+': '+str(exc))
        validation['instances'].append(dict(instance_name=member['instance_name'], status=state, anchors=checks))
    plan['summary_transform_validation'] = validation
    metadata = {m['instance_name']:m for m in plan['instances']}
    source_holes = {h['driving_hole_id']:h for h in plan['driving_holes']}
    for h in plan['derived_holes']:
        h['validation_status'] = 'TARGET_SURFACE_PENDING_RUNTIME'
        source = source_holes[h['source_driving_hole_id']]
        placement = metadata[source['source_instance']]['placement']
        h['global_source_center_m'] = step04_local_point_to_global(source['local_center_m'], placement)
        h['global_axis'] = step04_local_vector_to_global(source['local_axis'], placement)
        h['global_major_axis'] = step04_local_vector_to_global(source['local_major_axis'], placement) if source['local_major_axis'] else None
        h['source_pose_status'] = h['target_pose_status'] = 'SUMMARY_PRE_TRANSLATION_ROTATIONS_THEN_TRANSLATION_THEN_POST_TRANSLATION_ROTATIONS_ANCHOR_CHECK_REQUIRED'
    return plan
