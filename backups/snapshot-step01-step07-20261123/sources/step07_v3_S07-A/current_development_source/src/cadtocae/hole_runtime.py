# Step06 v0.1 standalone Abaqus/CAE 2020 runtime, Python 2.7 compatible.
# Small repository/name/point helpers are prepended by the generator.
import json
import math
import os
import traceback


def s6_dot(a, b):
    value = 0.0
    for i in range(len(a)):
        value += a[i] * b[i]
    return value


def s6_capsule(sketch, width, total_length, direction, counterclockwise):
    """Closed capsule: two parallel lines and two semicircles, total tip-to-tip length."""
    radius = width / 2.0
    half_straight = (total_length - width) / 2.0
    if half_straight <= 1.e-12:
        sketch.CircleByCenterPerimeter(center=(0., 0.), point1=(radius, 0.))
        return
    ux, uy = direction
    vx, vy = -uy, ux
    left = (-half_straight * ux, -half_straight * uy)
    right = (half_straight * ux, half_straight * uy)
    lb = (left[0] - radius * vx, left[1] - radius * vy)
    rb = (right[0] - radius * vx, right[1] - radius * vy)
    rt = (right[0] + radius * vx, right[1] + radius * vy)
    lt = (left[0] + radius * vx, left[1] + radius * vy)
    sketch.Line(point1=lb, point2=rb)
    sketch.ArcByCenterEnds(center=right, point1=rb, point2=rt, direction=counterclockwise)
    sketch.Line(point1=rt, point2=lt)
    sketch.ArcByCenterEnds(center=left, point1=lt, point2=lb, direction=counterclockwise)


def s6_face(part, hole):
    center = list(hole['local_center_m'])
    axis = hole['local_axis']
    normal_index = 1 if axis == [0., 1., 0.] or axis == (0., 1., 0.) else 0
    center[normal_index] = 0.0
    # coordinates=XYZ returns a Face; positional nested tuples return a FaceArray.
    face = part.faces.findAt(coordinates=tuple(center), printWarning=False)
    normal = vector3(face.getNormal(point=tuple(center)))
    if abs(s6_dot(normal, axis) + 1.0) > 1.e-6:
        raise ValueError('Support outer face normal mismatch: ' + hole['driving_hole_id'])
    for index in face.getVertices():
        vertex = point3(part.vertices[index])
        if abs(vertex[normal_index]) > 1.e-7:
            raise ValueError('Hole sketch face is not the expected outer plane')
    return face, tuple(center)


def s6_volume(part):
    value = part.getVolume(cells=part.cells)
    if value <= 0.0 or math.isnan(value) or math.isinf(value):
        raise ValueError('Invalid support solid volume')
    return value


def s6_geometry_preflight(part, hole, removed_volume=0., existing=False):
    geometry = hole['source_geometry']
    if geometry['section_kind'] != 'ANGLE' or geometry['model_policy'] != 'SOLID' or not len(part.cells):
        raise ValueError('P01 requires a native SOLID ANGLE')
    a, b, t, length = geometry['leg_a_m'], geometry['leg_b_m'], geometry['t_m'], geometry['length_m']
    radius = geometry.get('inner_root_radius_m', 0.)
    points = []
    for vertex in part.vertices:
        points.append(point3(vertex))
    if not points:
        raise ValueError('Missing native support vertices')
    upper = (a, b, length)
    for dimension in range(3):
        values = []
        for point in points:
            values.append(point[dimension])
        if abs(min(values)) > 1.e-7 or abs(max(values) - upper[dimension]) > 1.e-7:
            raise ValueError('Actual Part extents do not match Step02 local geometry')
    expected = (t * (a + b - t) + radius * radius * (1. - math.pi / 4.)) * length
    if abs(s6_volume(part) - (expected - removed_volume)) > max(expected * 1.e-4, 1.e-12):
        raise ValueError('Actual Part volume differs from uncut angle; check dimensions/existing features')
    if not existing:
        s6_face(part, hole)


def execute_hole_setup(plan, mdb, report_path, fingerprint, preflight_only=False, write_report=True, report_state=None):
    """Validate the P01 Part's complete reference set and pattern before editing once."""
    report = dict(project_id=plan['project_id'], benchmark_scope='P01', status='PREFLIGHT',
                  plan_fingerprint=fingerprint, shared_part_policy='IDENTICAL_PATTERN_MODIFY_ONCE',
                  affected_instances=[], skipped_groups=[], created_holes=0, created_hole_details=[], created_auxiliary_features=[],
                  shared_part=False, referencing_instances=[], hole_pattern_identical=False,
                  requires_instance_isolation=False, execution_policy='PREFLIGHT', expected_affected_instances=[],
                  mesh_removed=False, remesh_required=False,
                  mesh_elements_before=None, mesh_nodes_before=None,
                  inherited_groups=[],
                  derived_holes_executed=False, model_modified=False, errors=[], warnings=[])
    if report_state is not None:
        report_state.update(report)
        report = report_state
    try:
        from abaqusConstants import ON, OFF, SIDE1, RIGHT, ZAXIS, COUNTERCLOCKWISE
        if plan.get('schema_version') != 'step06-hole-setup-v0.1' or plan.get('benchmark_scope') != 'P01':
            raise ValueError('Unsupported Step06 plan/scope')
        holes = []
        for hole in plan['driving_holes']:
            if hole['connection_group'] == 'P01' and hole['enabled']:
                holes.append(hole)
            elif hole['connection_group'] not in report['skipped_groups']:
                report['skipped_groups'].append(hole['connection_group'])
        if not holes:
            raise ValueError('No enabled P01 driving holes')
        policies = plan.get('part_executions', [])
        if len(policies) != 1:
            raise ValueError('Exactly one P01 Part execution policy required; regenerate Step06 plan')
        policy = policies[0]
        for hole in holes:
            if hole['source_part'] != policy['source_part']:
                raise ValueError('Exactly one P01 source Part required')
        for key in ('shared_part', 'referencing_instances', 'hole_pattern_identical',
                    'requires_instance_isolation', 'execution_policy', 'expected_affected_instances'):
            report[key] = policy[key]
        if policy['execution_policy'] not in ('MODIFY_SHARED_PART_ONCE', 'MODIFY_PART_ONCE'):
            raise ValueError(policy['execution_policy'] + ': ' + '; '.join(policy['blocking_reasons']))
        pattern = []
        for hole in sorted(holes, key=lambda item:item['hole_id']):
            item = {}
            for key in ('hole_id', 'hole_type', 'width_m', 'total_length_m', 'local_center_m', 'local_axis', 'local_major_axis'):
                item[key] = hole[key]
            pattern.append(item)
        if pattern != policy['standard_hole_pattern']:
            raise ValueError('Part-local execution pattern differs from policy; regenerate Step06 plan')
        evidence_names = []
        for evidence in policy['instance_patterns']:
            evidence_names.append(evidence['instance_name'])
            group = evidence.get('connection_group')
            if group and group != 'P01' and group not in report['inherited_groups']:
                report['inherited_groups'].append(group)
                if group in report['skipped_groups']:
                    report['skipped_groups'].remove(group)
            if evidence['canonical_role'] != 'PURLIN_SUPPORT' or evidence['source_part'] != policy['source_part'] or not evidence['geometry_matches']:
                raise ValueError('PART_EVIDENCE_REVIEW_REQUIRED: role/geometry mismatch')
            if evidence['hole_pattern'] != pattern:
                report['hole_pattern_identical'] = False
                report['requires_instance_isolation'] = True
                report['execution_policy'] = 'PART_ISOLATION_REQUIRED'
                raise ValueError('PART_ISOLATION_REQUIRED: different Part-local hole pattern')
        if sorted(evidence_names) != sorted(policy['expected_affected_instances']) or len(set(evidence_names)) != len(evidence_names):
            raise ValueError('Incomplete instance pattern evidence')
        model = resolve_repository_item(mdb.models, plan['project_id'], 'Model')
        assembly = model.rootAssembly
        prepared = []
        feature_names = []
        for hole in holes:
            feature_name = 'STEP06_HOLE_' + hole['hole_id']
            if feature_name in feature_names:
                raise ValueError('Duplicate P01 hole ID')
            feature_names.append(feature_name)
            part = resolve_repository_item(model.parts, hole['source_part'], 'Part')
            instance = resolve_repository_item(assembly.instances, hole['source_instance'], 'Instance')
            if instance.partName != part.name or instance.dependent != ON:
                raise ValueError('P01 instance must be dependent on the expected Part')
            actual_instances = []
            repositories = [assembly.instances]
            if hasattr(assembly, 'allInstances'):
                repositories.append(assembly.allInstances)
            for repository in repositories:
                for key in repository.keys():
                    other = repository[key]
                    if other.partName == part.name and key not in actual_instances:
                        actual_instances.append(key)
                        if other.dependent != ON:
                            raise ValueError('Expected dependent support instance: ' + str(key))
            actual_instances.sort()
            report['affected_instances'] = actual_instances
            report['referencing_instances'] = actual_instances
            report['shared_part'] = len(actual_instances) > 1
            if actual_instances != sorted(policy['expected_affected_instances']):
                raise ValueError('PART_REFERENCE_REVIEW_REQUIRED: actual references differ from verified pattern evidence')
            for key in assembly.features.keys():
                if assembly.features[key].isSuppressed():
                    raise ValueError('Suppressed assembly features prevent a complete shared-Part audit; review before cutting')
            for key in part.features.keys():
                if str(key).startswith('STEP06_'):
                    raise ValueError('Existing STEP06 features: rerun refused; inspect existing model/report')
            for key in model.sketches.keys():
                if str(key).startswith('STEP06_'):
                    raise ValueError('Existing STEP06 sketch: inspect prior partial operation')
            if hole['hole_type'] not in ('ROUND', 'SLOT'):
                raise ValueError('Unsupported hole type')
            s6_geometry_preflight(part, hole)
            prepared.append((part, hole, feature_name))
        if preflight_only:
            report['status'] = 'PREFLIGHT_PASSED'
            return report
        report['status'] = 'EXECUTING'
        part = prepared[0][0]
        report['mesh_elements_before'] = len(part.elements)
        report['mesh_nodes_before'] = len(part.nodes)
        if len(part.nodes) or len(part.elements):
            # Entire native target Part only; all geometry and policy checks already passed.
            report['model_modified'] = True
            report['remesh_required'] = True
            part.deleteMesh()
            report['mesh_removed'] = not len(part.nodes) and not len(part.elements)
            if not report['mesh_removed']:
                raise ValueError('Target mesh remains after deleteMesh; no cuts attempted')
        for part, hole, feature_name in prepared:
            face, origin = s6_face(part, hole)
            axis_feature = part.DatumAxisByPrincipalAxis(principalAxis=ZAXIS)
            report['model_modified'] = True
            axis_name = 'STEP06_AXIS_' + hole['hole_id']
            part.features.changeKey(fromName=abaqus_name(axis_feature.name), toName=abaqus_name(axis_name))
            report['created_auxiliary_features'].append(axis_name)
            up_axis = part.datums[axis_feature.id]
            matrix = part.MakeSketchTransform(sketchPlane=face, sketchUpEdge=up_axis,
                                              sketchPlaneSide=SIDE1, sketchOrientation=RIGHT, origin=origin).matrix()
            # Abaqus Transform.matrix: 4 rows x 3 (local U, V, N, translation).
            if len(matrix) != 12:
                raise ValueError('Unexpected sketch transform matrix')
            for i in range(3):
                if abs(matrix[9+i] - origin[i]) > 1.e-7:
                    raise ValueError('Sketch origin transform mismatch')
            sketch_name = 'STEP06_SKETCH_' + hole['hole_id']
            sketch = model.ConstrainedSketch(name=abaqus_name(sketch_name), sheetSize=1., transform=matrix)
            width = hole['width_m']
            total_length = hole['total_length_m']
            if hole['hole_type'] == 'ROUND':
                sketch.CircleByCenterPerimeter(center=(0., 0.), point1=(width/2., 0.))
            else:
                direction = hole['local_major_axis']
                uv = (s6_dot(direction, matrix[0:3]), s6_dot(direction, matrix[3:6]))
                if abs(s6_dot(uv, uv) - 1.) > 1.e-6:
                    raise ValueError('Slot major axis does not lie in sketch plane')
                s6_capsule(sketch, width, total_length, uv, COUNTERCLOCKWISE)
            before = s6_volume(part)
            feature = part.CutExtrude(sketchPlane=face, sketchPlaneSide=SIDE1, sketchUpEdge=up_axis,
                                      sketchOrientation=RIGHT, sketch=sketch, flipExtrudeDirection=OFF)
            part.features.changeKey(fromName=abaqus_name(feature.name), toName=abaqus_name(feature_name))
            after = s6_volume(part)
            removed = (math.pi*width*width/4. + width*(total_length-width))*hole['source_geometry']['t_m']
            record = dict(name=feature_name, part=part.name, instance=hole['source_instance'],
                          hole_type=hole['hole_type'], width_m=width, total_length_m=total_length,
                          local_center_m=hole['local_center_m'], local_axis=hole['local_axis'],
                          local_major_axis=hole.get('local_major_axis'), removed_volume_m3=before-after)
            report['created_hole_details'].append(record)
            report['created_holes'] = len(report['created_hole_details'])
            if abs(before-after-removed) > max(removed*1.e-4, 1.e-12):
                raise ValueError('Cut volume mismatch; inspect partial model. No automatic retry/rollback.')
            del model.sketches[abaqus_name(sketch_name)]
        assembly.regenerate()
        report['status'] = 'SUCCESS'
        report['warnings'].append('PURLIN_LOCAL/INCLINED_BEAM holes remain TARGET_SURFACE_PENDING_RUNTIME')
        return report
    except Exception as exc:
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        if write_report:
            with open(report_path, 'w') as handle:
                json.dump(report, handle, indent=2, ensure_ascii=True, allow_nan=False)
