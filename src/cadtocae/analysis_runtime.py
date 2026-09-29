"""Embedded A2 Abaqus executor. Python 2.7 compatible; geometry helpers prepended.

Only native dependent, planar shell C-channel geometry is enabled in this first
increment. Unsupported topology is rejected before any Part mutation.
"""
import json
import os
import traceback


def _s5_repository_text(value):
    """Strict UTF-8 bytes -> text; no stripping, case folding or hidden-char removal.

    Python 2 JSON unicode and Repository str keys compare as text, but the
    original Repository key must be retained for the actual lookup.
    """
    try:
        text_type = unicode
    except NameError:
        text_type = str
    if isinstance(value, text_type):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "strict")
    raise ValueError("Repository name must be text or UTF-8 bytes: %r" % (value,))


def _s5_repository_key(repository, expected_name, repository_label, allow_missing=False):
    """Return the ORIGINAL key; optional absence is only for existing-object policy."""
    available = list(repository.keys())
    expected = _s5_repository_text(expected_name)
    matches = [key for key in available if _s5_repository_text(key) == expected]
    if repository_label in ('Model', 'Part', 'Instance') or len(matches) != 1:
        print('Expected %s: %r' % (repository_label, expected_name))
        print('expected %s repr: %r' % (repository_label.lower(), expected_name))
        print('expected %s type: %s' % (repository_label.lower(), type(expected_name)))
        print('expected %s length: %s' % (repository_label.lower(), len(expected_name)))
        print('Available %ss:' % repository_label)
        for key in available:
            print('key repr: %r; type: %s; length: %s; expected == key: %s; normalized exact match: %s' % (key, type(key), len(key), expected_name == key, _s5_repository_text(key) == expected))
    if not matches and allow_missing:
        return None
    if len(matches) != 1:
        reason = ('Required existing %s not found' if not matches else 'Multiple normalized %s matches') % repository_label
        _runtime_values_65 = []
        for key in available:
            _runtime_values_65.append('- %r (%s)' % (key, type(key)))
        raise ValueError('%s\nExpected %s: %s\nExpected repr: %r\nAvailable %ss / Available key repr:\n%s' % (reason, repository_label, expected.encode('unicode_escape').decode('ascii'), expected_name, repository_label, '\n'.join(_runtime_values_65)))
    return matches[0]


def resolve_repository_item(repository, expected_name, repository_label):
    """Strict normalized exact match, indexing only with the original key."""
    actual_key = _s5_repository_key(repository, expected_name, repository_label)
    return repository[actual_key]


def _resolve_existing_model(mdb, expected_name):
    return resolve_repository_item(mdb.models, expected_name, "Model")


def _s5_points(container):
    return [vector(v.pointOn[0]) for v in container.vertices]


def _s5_polygon(part, face, tolerance):
    normal = unit(vector(face.getNormal()))
    points = [vector(part.vertices[i].pointOn[0]) for i in face.getVertices()]
    if len(points) < 3:
        raise ValueError('Unsupported curved/closed face')
    _runtime_values_61 = []
    for i in range(3):
        _runtime_total_62 = 0
        for p in points:
            _runtime_total_62 += p[i]
        _runtime_values_61.append(_runtime_total_62)
    center = scale(tuple(_runtime_values_61), 1.0 / len(points))
    u = unit(sub(points[0], center))
    v = unit(cross(normal, u))
    points.sort(key=lambda p: math.atan2(dot(sub(p, center), v), dot(sub(p, center), u)))
    _runtime_match_63 = False
    for p in points:
        if _runtime_match_63:
            break
        if abs(dot(sub(p, center), normal)) > tolerance:
            _runtime_match_63 = True
    if _runtime_match_63:
        raise ValueError('Unsupported nonplanar face')
    _runtime_total_64 = 0
    for i in range(len(points)):
        _runtime_total_64 += dot(cross(sub(points[i], center), sub(points[(i + 1) % len(points)], center)), normal)
    area = _runtime_total_64 / 2.0
    actual_area = float(face.getSize(printResults=False))
    if abs(abs(area) - actual_area) > max(tolerance * tolerance, actual_area * 1e-06):
        raise ValueError('Unsupported face holes/curvature/nonconvex topology')
    turns = [dot(cross(sub(points[(i + 1) % len(points)], points[i]), sub(points[(i + 2) % len(points)], points[(i + 1) % len(points)])), normal) for i in range(len(points))]
    if min(turns) < -tolerance * tolerance:
        raise ValueError('Unsupported nonconvex face')
    return points


def _s5_shell_section(model, part, face):
    assignments = [a for a in part.sectionAssignments if not getattr(a, "suppressed", False)
                   and face.index in [f.index for f in a.region.faces]]
    if len(assignments) != 1:
        raise ValueError("Shell face requires one unambiguous section assignment")
    assignment = assignments[0]
    section = resolve_repository_item(model.sections, assignment.sectionName, "Section")
    if str(getattr(assignment, "thicknessAssignment", "")) != "FROM_SECTION":
        raise ValueError("Unsupported geometry-based shell thickness")
    if str(getattr(section, "thicknessType", "")) != "UNIFORM":
        raise ValueError("Only uniform homogeneous shell thickness supported")
    return float(section.thickness), str(assignment.offsetType), float(assignment.offset)


def _s5_pose(part, instance, metadata, tolerance):
    if str(instance.dependent) != 'ON' or instance.partName != metadata['part_name']:
        raise ValueError('A2 requires the expected dependent native Part instance')
    if len(part.cells) or not len(part.faces):
        raise ValueError('A2 supports shell faces only, not solid/orphan geometry')
    if len(part.faces) != len(instance.faces) or len(part.edges) != len(instance.edges):
        raise ValueError('unsupported transform contract: Part/Instance topology differs')
    local, world = (_s5_points(part), _s5_points(instance))
    pose = fit_pose(local, world, tolerance)
    for face, placed in zip(part.faces, instance.faces):
        if tuple(face.getVertices()) != tuple(placed.getVertices()):
            raise ValueError('unsupported transform contract: face correspondence')
        if norm(sub(matvec(pose['rotation'], vector(face.getNormal())), vector(placed.getNormal()))) > 1e-05:
            raise ValueError('unsupported transform contract: face normal mismatch')
    pose['matching_translation_insertions'] = verify_pose_contract(pose, metadata['placement'], local, tolerance)
    pose['source'] = 'dependent_vertex_rigid_fit_all_vertices_and_face_normals_verified'
    length = metadata['geometry_info']['length']
    _runtime_values_56 = None
    for p in local:
        _runtime_value_57 = p[2]
        if _runtime_values_56 is None or _runtime_value_57 < _runtime_values_56:
            _runtime_values_56 = _runtime_value_57
    if _runtime_values_56 is None:
        raise ValueError('min() arg is an empty sequence')
    _runtime_condition_58 = abs(_runtime_values_56) > tolerance
    if not _runtime_condition_58:
        _runtime_values_59 = None
        for p in local:
            _runtime_value_60 = p[2]
            if _runtime_values_59 is None or _runtime_value_60 > _runtime_values_59:
                _runtime_values_59 = _runtime_value_60
        if _runtime_values_59 is None:
            raise ValueError('max() arg is an empty sequence')
        _runtime_condition_58 = abs(_runtime_values_59 - length) > tolerance
    if _runtime_condition_58:
        raise ValueError('Part local length/origin does not match summary')
    return pose


def _s5_real_geometry(model, part, metadata, tolerance):
    """Compare actual C-channel geometry/sections to the normalized REAL workbook."""
    expected = metadata.get('component_geometry')
    if expected is None:
        raise ValueError('missing real component geometry: ' + part.name)
    if expected['model_policy'] != 'SHELL' or expected['section_kind'] != 'C_CHANNEL':
        raise ValueError('Real component geometry type mismatch: ' + part.name)
    params = expected['section_params_m']
    h, b, lip = (params['h_m'], params['b_m'], params['lip_m'])
    profile = [(b, lip, 0.0), (b, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, h, 0.0), (b, h, 0.0), (b, h - lip, 0.0)]
    points = _s5_points(part)
    flat = [(p[0], p[1], 0.0) for p in points]

    def on_segment(p, a, end):
        direction = sub(end, a)
        fraction = dot(sub(p, a), direction) / dot(direction, direction)
        nearest = add(a, scale(direction, max(0.0, min(1.0, fraction))))
        return norm(sub(p, nearest)) <= tolerance
    _runtime_match_52 = False
    for p in flat:
        if _runtime_match_52:
            break
        _runtime_match_53 = False
        for a, end in zip(profile[:-1], profile[1:]):
            if _runtime_match_53:
                break
            if on_segment(p, a, end):
                _runtime_match_53 = True
        if not _runtime_match_53:
            _runtime_match_52 = True
    if _runtime_match_52:
        raise ValueError('Real workbook/Part section dimensions mismatch: ' + part.name)
    _runtime_match_54 = False
    for corner in profile:
        if _runtime_match_54:
            break
        _runtime_match_55 = False
        for p in flat:
            if _runtime_match_55:
                break
            if norm(sub(corner, p)) <= tolerance:
                _runtime_match_55 = True
        if not _runtime_match_55:
            _runtime_match_54 = True
    if _runtime_match_54:
        raise ValueError('Real Part missing C-channel profile corners: ' + part.name)
    for face in part.faces:
        thickness, _offset_type, _offset = _s5_shell_section(model, part, face)
        if abs(thickness - expected['thickness_m']) > tolerance:
            raise ValueError('Real workbook/Part thickness mismatch: ' + part.name)


def _s5_print(label, value):
    # JSON escaping keeps Python 2 CAE consoles safe for non-ASCII project paths.
    print("%s = %s" % (label, json.dumps(value, ensure_ascii=True)))


def _s5_edges_on_plane(part, point, normal, tolerance):
    result = []
    for edge in part.edges:
        vertices = [vector(part.vertices[i].pointOn[0]) for i in edge.getVertices()]
        if len(vertices) != 2:
            continue
        if abs(norm(sub(vertices[0], vertices[1])) - edge.getSize(printResults=False)) > tolerance:
            continue
        _runtime_match_51 = True
        for p in vertices + [vector(edge.pointOn[0])]:
            if not _runtime_match_51:
                break
            if not abs(dot(sub(p, point), normal)) <= tolerance:
                _runtime_match_51 = False
        if _runtime_match_51:
            result.append(edge.index)
    return result


def _s5_sequence(array, indices):
    if not indices:
        raise ValueError("Empty geometric region")
    result = array[indices[0]:indices[0]+1]
    for index in indices[1:]:
        result = result + array[index:index+1]
    return result


def _s5_station(part, pose, station_global, tolerance, report):
    expected = inverse_point(pose, station_global)[2]
    name = 'SET_BEAM_SEC_C'
    if _s5_repository_key(part.sets, name, 'Set', allow_missing=True) is None:
        report['warnings'].append('SET_BEAM_SEC_C absent; using verified summary C projection; no C partition created')
        return expected
    region = resolve_repository_item(part.sets, name, 'Set')
    if len(region.faces) or not len(region.edges):
        raise ValueError('SET_BEAM_SEC_C is not an edge section')
    expected_edges = set(_s5_edges_on_plane(part, (0.0, 0.0, expected), (0.0, 0.0, 1.0), tolerance))
    _runtime_values_50 = []
    for edge in region.edges:
        _runtime_values_50.append(edge.index)
    actual = set(_runtime_values_50)
    if not expected_edges or actual != expected_edges:
        raise ValueError('SET_BEAM_SEC_C does not cover the correct complete C station')
    report['existing_objects_reused'].append(name)
    return expected


def _s5_flange(model, part, pose, low, high, tolerance):
    points = _s5_points(part)
    _runtime_values_27 = None
    for p in points:
        _runtime_value_28 = p[1]
        if _runtime_values_27 is None or _runtime_value_28 < _runtime_values_27:
            _runtime_values_27 = _runtime_value_28
    if _runtime_values_27 is None:
        raise ValueError('min() arg is an empty sequence')
    _runtime_values_29 = None
    for p in points:
        _runtime_value_30 = p[1]
        if _runtime_values_29 is None or _runtime_value_30 > _runtime_values_29:
            _runtime_values_29 = _runtime_value_30
    if _runtime_values_29 is None:
        raise ValueError('max() arg is an empty sequence')
    ymin, ymax = (_runtime_values_27, _runtime_values_29)
    _runtime_values_31 = None
    for p in points:
        _runtime_value_32 = p[0]
        if _runtime_values_31 is None or _runtime_value_32 < _runtime_values_31:
            _runtime_values_31 = _runtime_value_32
    if _runtime_values_31 is None:
        raise ValueError('min() arg is an empty sequence')
    _runtime_values_33 = None
    for p in points:
        _runtime_value_34 = p[0]
        if _runtime_values_33 is None or _runtime_value_34 > _runtime_values_33:
            _runtime_values_33 = _runtime_value_34
    if _runtime_values_33 is None:
        raise ValueError('max() arg is an empty sequence')
    xmin, xmax = (_runtime_values_31, _runtime_values_33)
    yaxis = matvec(pose['rotation'], (0.0, 1.0, 0.0))
    vertical = dot(yaxis, (0.0, 0.0, 1.0))
    if abs(vertical) < 0.0001 or ymax - ymin <= tolerance or xmax - xmin <= tolerance:
        raise ValueError('Cannot uniquely determine lower flange physical side')
    outward = (0.0, -1.0 if vertical > 0 else 1.0, 0.0)
    y = ymin if vertical > 0 else ymax
    candidates, records, intervals = ([], [], [])
    for face in part.faces:
        polygon = _s5_polygon(part, face, tolerance)
        _runtime_match_35 = True
        for p in polygon:
            if not _runtime_match_35:
                break
            if not abs(p[1] - y) <= tolerance:
                _runtime_match_35 = False
        if not _runtime_match_35:
            continue
        _runtime_values_36 = None
        for p in polygon:
            _runtime_value_37 = p[2]
            if _runtime_values_36 is None or _runtime_value_37 > _runtime_values_36:
                _runtime_values_36 = _runtime_value_37
        if _runtime_values_36 is None:
            raise ValueError('max() arg is an empty sequence')
        _runtime_condition_38 = _runtime_values_36 <= low + tolerance
        if not _runtime_condition_38:
            _runtime_values_39 = None
            for p in polygon:
                _runtime_value_40 = p[2]
                if _runtime_values_39 is None or _runtime_value_40 < _runtime_values_39:
                    _runtime_values_39 = _runtime_value_40
            if _runtime_values_39 is None:
                raise ValueError('min() arg is an empty sequence')
            _runtime_condition_38 = _runtime_values_39 >= high - tolerance
        if _runtime_condition_38:
            continue
        _runtime_values_41 = None
        for p in polygon:
            _runtime_value_42 = p[0]
            if _runtime_values_41 is None or _runtime_value_42 < _runtime_values_41:
                _runtime_values_41 = _runtime_value_42
        if _runtime_values_41 is None:
            raise ValueError('min() arg is an empty sequence')
        _runtime_condition_43 = abs(_runtime_values_41 - xmin) > tolerance
        if not _runtime_condition_43:
            _runtime_values_44 = None
            for p in polygon:
                _runtime_value_45 = p[0]
                if _runtime_values_44 is None or _runtime_value_45 > _runtime_values_44:
                    _runtime_values_44 = _runtime_value_45
            if _runtime_values_44 is None:
                raise ValueError('max() arg is an empty sequence')
            _runtime_condition_43 = abs(_runtime_values_44 - xmax) > tolerance
        if not _runtime_condition_43:
            _runtime_condition_43 = len(polygon) != 4
        if _runtime_condition_43:
            raise ValueError('Unsupported partial-width/nonrectangular flange patch')
        _runtime_values_46 = None
        for p in polygon:
            _runtime_value_47 = p[2]
            if _runtime_values_46 is None or _runtime_value_47 < _runtime_values_46:
                _runtime_values_46 = _runtime_value_47
        if _runtime_values_46 is None:
            raise ValueError('min() arg is an empty sequence')
        _runtime_values_48 = None
        for p in polygon:
            _runtime_value_49 = p[2]
            if _runtime_values_48 is None or _runtime_value_49 > _runtime_values_48:
                _runtime_values_48 = _runtime_value_49
        if _runtime_values_48 is None:
            raise ValueError('max() arg is an empty sequence')
        intervals.append((max(low, _runtime_values_46), min(high, _runtime_values_48)))
        thickness, offset_type, offset = _s5_shell_section(model, part, face)
        physical = shell_outer_plane(polygon[0], vector(face.getNormal()), outward, thickness, offset_type, offset)
        candidates.append(face.index)
        records.append(physical)
    if not candidates:
        raise ValueError('No lower flange patch candidate')
    cursor = low
    for start, end in sorted(intervals):
        if abs(start - cursor) > tolerance:
            raise ValueError('Gap/overlap in beam flange patch')
        cursor = end
    if abs(cursor - high) > tolerance:
        raise ValueError('Incomplete beam flange patch')
    first = records[0]
    for record in records[1:]:
        if record['physical_side'] != first['physical_side'] or abs(record['point'][1] - first['point'][1]) > tolerance or abs(record['thickness_m'] - first['thickness_m']) > tolerance:
            raise ValueError('Ambiguous flange side/offset/thickness')
    result = dict(first, geometric_y=y, x_bounds=[xmin, xmax], face_indices=candidates)
    result['point_global'] = transform(pose, first['point'])
    result['normal_global'] = matvec(pose['rotation'], first['normal'])
    return result


def _s5_brace_segments(model, part, pose, beam_pose, flange, low, high, tolerance):
    point = inverse_point(pose, flange['point_global'])
    normal = matvec(transpose(pose['rotation']), flange['normal_global'])
    segments, section_records = ([], [])
    if abs(normal[2]) < 1e-05:
        raise ValueError('Contact plane is parallel to brace length axis')
    all_points = _s5_points(part)
    _runtime_values_18 = None
    for p in all_points:
        _runtime_value_19 = p[2]
        if _runtime_values_18 is None or _runtime_value_19 > _runtime_values_18:
            _runtime_values_18 = _runtime_value_19
    if _runtime_values_18 is None:
        raise ValueError('max() arg is an empty sequence')
    length = _runtime_values_18
    hits = []
    for face in part.faces:
        polygon = _s5_polygon(part, face, tolerance)
        intersection = plane_intersection(polygon, point, normal, tolerance)
        if not intersection:
            continue
        projected = [inverse_point(beam_pose, transform(pose, p)) for p in intersection]
        _runtime_match_20 = True
        for p in projected:
            if not _runtime_match_20:
                break
            if not (low - tolerance <= p[2] <= high + tolerance and flange['x_bounds'][0] - tolerance <= p[0] <= flange['x_bounds'][1] + tolerance):
                _runtime_match_20 = False
        if not _runtime_match_20:
            raise ValueError('Brace intersection extends outside finite beam patch; additional region rule required')
        thickness, offset_type, offset = _s5_shell_section(model, part, face)
        shell_outer_plane(polygon[0], vector(face.getNormal()), vector(face.getNormal()), thickness, offset_type, offset)
        section_records.append({'face_index': face.index, 'thickness_m': thickness, 'offset_type': offset_type, 'offset_fraction': offset, 'positive_normal_local': list(face.getNormal())})
        _runtime_match_21 = False
        for old in segments:
            if _runtime_match_21:
                break
            _runtime_match_22 = True
            for p in intersection:
                if not _runtime_match_22:
                    break
                _runtime_match_23 = False
                for q in old:
                    if _runtime_match_23:
                        break
                    if norm(sub(p, q)) <= tolerance:
                        _runtime_match_23 = True
                if not _runtime_match_23:
                    _runtime_match_22 = False
            if _runtime_match_22:
                _runtime_match_21 = True
        if not _runtime_match_21:
            segments.append(intersection)
        _runtime_values_24 = []
        for p in intersection:
            _runtime_values_24.append(p[2])
        hits.extend(_runtime_values_24)
    if not segments:
        raise ValueError('Contact plane does not intersect brace geometry; no material extension/removal allowed')
    if min(hits) <= length / 2.0 <= max(hits):
        raise ValueError('Brace end region cannot be uniquely identified')
    pending, connected = (list(segments[1:]), list(segments[0]))
    while pending:
        _runtime_values_25 = []
        for s in pending:
            _runtime_match_26 = False
            for a in s:
                if _runtime_match_26:
                    break
                for b in connected:
                    if _runtime_match_26:
                        break
                    if norm(sub(a, b)) <= tolerance:
                        _runtime_match_26 = True
            if _runtime_match_26:
                _runtime_values_25.append(s)
        linked = _runtime_values_25
        if not linked:
            raise ValueError('Disconnected brace intersection; ambiguous region')
        for segment in linked:
            pending.remove(segment)
            connected.extend(segment)
    return {'point_local': point, 'normal_local': normal, 'segments_local': segments, 'end': 'TOP' if min(hits) > length / 2.0 else 'BOTTOM', 'adjacent_shell_sections': section_records, 'physical_side': 'EDGE_ON_BEAM_PHYSICAL_OUTER_PLANE', 'offset_interpretation': 'intersection of brace reference shell geometry with beam physical outer plane; edge is not a shell face side'}


def _s5_partition_needed(part, point, normal, tolerance):
    for face in part.faces:
        distances = [dot(sub(p, point), normal) for p in _s5_polygon(part, face, tolerance)]
        if min(distances) < -tolerance and max(distances) > tolerance:
            return True
    if not _s5_edges_on_plane(part, point, normal, tolerance):
        raise ValueError("Partition plane neither crosses geometry nor matches existing edges")
    return False


def _s5_partition(part, name, point, normal, needed, tolerance, report):
    if not needed:
        report["existing_objects_reused"].append(name + ":verified_geometric_boundary")
        return
    datum_name = name + "_PLANE"
    # Abaqus DatumPlaneByPointNormal requires datum objects, not numeric vectors.
    # Three stable construction datum points also work in CAE 2020.
    helper = min(((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)), key=lambda axis: abs(dot(axis, normal)))
    u = unit(cross(normal, helper))
    v = unit(cross(normal, u))
    datum_points = []
    for index, coords in enumerate((point, add(point, u), add(point, v))):
        feature = part.DatumPointByCoordinate(coords=tuple(coords))
        datum_points.append(part.datums[feature.id])
        stable = datum_name + "_P%d" % index
        part.features.changeKey(fromName=feature.name, toName=stable)
        report["semantic_mapping"][stable] = {"part": part.name, "name": stable}
    datum = part.DatumPlaneByThreePoints(point1=datum_points[0], point2=datum_points[1], point3=datum_points[2])
    datum_id = datum.id
    part.features.changeKey(fromName=datum.name, toName=datum_name)
    report["semantic_mapping"][datum_name] = {"part": part.name, "name": datum_name}
    feature = part.PartitionFaceByDatumPlane(datumPlane=part.datums[datum_id], faces=part.faces[:])
    part.features.changeKey(fromName=feature.name, toName=name)
    if _s5_partition_needed(part, point, normal, tolerance):
        raise ValueError("Partition did not establish complete boundary: " + name)
    report["partitions"].append({"name": name, "part": part.name, "point_local": point, "normal_local": normal})


def _s5_set(part, name, kind, indices, report):
    if _s5_repository_key(part.sets, name, 'Set', allow_missing=True) is not None:
        existing = getattr(resolve_repository_item(part.sets, name, 'Set'), kind)
        _runtime_values_17 = []
        for x in existing:
            _runtime_values_17.append(x.index)
        if set(_runtime_values_17) != set(indices):
            raise ValueError('Existing region differs: ' + name)
        report['existing_objects_reused'].append(name)
    else:
        part.Set(name=name, **{kind: _s5_sequence(getattr(part, kind), indices)})
    report['sets'].append({'name': name, 'part': part.name, 'kind': kind})


def _s5_surface(part, name, indices, side, report):
    if _s5_repository_key(part.surfaces, name, 'Surface', allow_missing=True) is not None:
        surface = resolve_repository_item(part.surfaces, name, 'Surface')
        _runtime_values_14 = []
        for face in surface.faces:
            _runtime_values_14.append(face.index)
        if set(_runtime_values_14) != set(indices):
            raise ValueError('Existing surface differs: ' + name)
        _runtime_condition_15 = not hasattr(surface, 'sides')
        if not _runtime_condition_15:
            _runtime_match_16 = False
            for x in surface.sides:
                if _runtime_match_16:
                    break
                if str(x) != side:
                    _runtime_match_16 = True
            _runtime_condition_15 = _runtime_match_16
        if _runtime_condition_15:
            raise ValueError('Existing surface side cannot be verified: ' + name)
        report['existing_objects_reused'].append(name)
    else:
        part.Surface(name=name, **{'side1Faces' if side == 'SIDE1' else 'side2Faces': _s5_sequence(part.faces, indices)})
    report['surfaces'].append({'name': name, 'part': part.name, 'physical_side': side})


def execute_analysis(plan, mdb, report_path, fingerprint):
    """Write a report on success AND failure. Preflight precedes mesh/geometry edits."""
    report = {'project_id': plan['project']['project_id'], 'model_name': plan['project']['project_id'], 'phase': 'A2', 'status': 'PREFLIGHT', 'plan_fingerprint': fingerprint, 'reference_station': 'C', 'patch_half_length_m': plan['regions'][0]['parameters']['half_length_m'], 'partitions': [], 'surfaces': [], 'sets': [], 'reference_points': [], 'tie_connections': [], 'coupling_connections': [], 'tie_created': False, 'beam_part': None, 'brace_part': None, 'beam_region': None, 'brace_region': None, 'partition_locations': [], 'existing_objects_reused': [], 'mesh_removed': False, 'mesh_removed_parts': [], 'remesh_required': False, 'remesh_required_parts': [], 'warnings': [], 'errors': [], 'semantic_mapping': {}, 'material_removed': False, 'modified_parts': []}
    real = plan['project'].get('mode') == 'REAL_CASE'
    try:
        if plan['ties'] or plan['reference_points'] or plan['couplings']:
            raise ValueError('A2 accepts geometry regions only')
        if real:
            print('STEP05 REAL CASE')
            for label, value in (('project_id', plan['project']['project_id']), ('model_name', plan['project'].get('model_name')), ('beam instance', plan['instances'][0]['instance_name']), ('brace instance', plan['instances'][1]['instance_name']), ('beam part', plan['instances'][0]['part_name']), ('brace part', plan['instances'][1]['part_name']), ('C global', plan['real_case']['C_global']), ('beam region name', 'STEP05_REGION_BEAM_BRACE_FRONT'), ('brace region name', 'STEP05_REGION_BRACE_FRONT_BEAM')):
                _s5_print(label, value)
            if plan['project'].get('model_name') != plan['project']['project_id']:
                raise ValueError('Real model_name/project_id mismatch')
        name = plan['project']['project_id']
        model = _resolve_existing_model(mdb, name)
        print('Resolved Model: %r' % _s5_repository_key(mdb.models, name, 'Model'))
        assembly = model.rootAssembly
        tolerance = plan['project']['geometry_tolerance_m']
        beam_meta, brace_meta = plan['instances']
        resolved_parts, resolved_instances = ([], [])
        for item in (beam_meta, brace_meta):
            part_key = _s5_repository_key(model.parts, item['part_name'], 'Part')
            instance_key = _s5_repository_key(assembly.instances, item['instance_name'], 'Instance')
            resolved_parts.append(model.parts[part_key])
            resolved_instances.append(assembly.instances[instance_key])
            print('Resolved Parts: %s -> %r' % (item['component_code'], part_key))
            print('Resolved Instances: %s -> %r' % (item['instance_name'], instance_key))
        beam, brace = resolved_parts
        beam_instance, brace_instance = resolved_instances
        print('STEP05 repository preflight passed')
        report['beam_part'], report['brace_part'] = (beam.name, brace.name)
        previous = None
        if os.path.isfile(report_path):
            with open(report_path, 'r') as handle:
                previous = json.load(handle)
        existing = [key for part in (beam, brace) for repo in (part.features, part.sets, part.surfaces) for key in repo.keys() if _s5_repository_text(key).startswith('STEP05_')]
        if existing and (not previous or previous.get('status') != 'SUCCESS' or previous.get('plan_fingerprint') != fingerprint):
            raise ValueError('STEP05 objects already exist without matching successful report; conflict policy FAIL')
        for meta, part in ((beam_meta, beam), (brace_meta, brace)):
            _runtime_values_1 = []
            for i in assembly.instances.values():
                if i.partName == part.name:
                    _runtime_values_1.append(i.name)
            users = sorted(_runtime_values_1)
            if users != sorted(meta['affected_instances']):
                raise ValueError('Actual shared Part references differ from summary: ' + part.name)
        _runtime_values_2 = {}
        for item in plan['instances']:
            _runtime_values_2[item['part_name']] = item['affected_instances']
        report['affected_instances'] = _runtime_values_2
        beam_pose = _s5_pose(beam, beam_instance, beam_meta, tolerance)
        brace_pose = _s5_pose(brace, brace_instance, brace_meta, tolerance)
        report['pose_verification'] = {'beam': beam_pose, 'brace': brace_pose}
        if real:
            _s5_real_geometry(model, beam, beam_meta, tolerance)
            _s5_real_geometry(model, brace, brace_meta, tolerance)
            _runtime_values_3 = {}
            for item in (beam_meta, brace_meta):
                _runtime_values_3[item['part_name']] = item['component_geometry']
            report['real_component_geometry'] = _runtime_values_3
        center = _s5_station(beam, beam_pose, plan['regions'][0]['parameters']['station_global'], tolerance, report)
        if real and abs(center - plan['real_case']['C_beam_local_station_m']) > tolerance:
            raise ValueError('Runtime C station disagrees with real coordinate workbook')
        low, high = patch_limits(center, report['patch_half_length_m'], beam_meta['geometry_info']['length'], tolerance)
        report['partition_locations'] = [low, high]
        report['station_local_m'] = center
        flange = _s5_flange(model, beam, beam_pose, low, high, tolerance)
        brace_info = _s5_brace_segments(model, brace, brace_pose, beam_pose, flange, low, high, tolerance)
        if real:
            _s5_print('C local station', center)
            _s5_print('patch range', [low, high])
            _s5_print('beam physical side', flange['physical_side'])
        operations = [(beam, 'STEP05_PARTITION_BEAM_C_MINUS', (0.0, 0.0, low), (0.0, 0.0, 1.0)), (beam, 'STEP05_PARTITION_BEAM_C_PLUS', (0.0, 0.0, high), (0.0, 0.0, 1.0)), (brace, 'STEP05_PARTITION_BRACE_FRONT_CONTACT', brace_info['point_local'], brace_info['normal_local'])]
        needs = [_s5_partition_needed(part, p, n, tolerance) for part, name, p, n in operations]
        if existing and any(needs):
            raise ValueError('Previously successful geometry has changed; refusing implicit replacement')
        if previous and previous.get('status') == 'SUCCESS':
            for part in (beam, brace):
                if part.name in previous.get('remesh_required_parts', []) and (not len(part.elements)):
                    report['remesh_required_parts'].append(part.name)
                    report['remesh_required'] = True
        _runtime_values_4 = {}
        for part in (beam, brace):
            _runtime_total_5 = 0
            for f in part.faces:
                _runtime_total_5 += f.getSize(printResults=False)
            _runtime_values_4[part.name] = _runtime_total_5
        area_before = _runtime_values_4
        report['status'] = 'EXECUTING'
        for part in (beam, brace):
            _runtime_match_6 = False
            for needed, (target, _, _, _) in zip(needs, operations):
                if _runtime_match_6:
                    break
                if needed and target is part:
                    _runtime_match_6 = True
            if _runtime_match_6:
                if part.name not in report['remesh_required_parts']:
                    report['remesh_required_parts'].append(part.name)
                report['remesh_required'] = True
                if len(part.elements):
                    part.deleteMesh()
                    report['mesh_removed'] = True
                    report['mesh_removed_parts'].append(part.name)
        for needed, (part, name, p, n) in zip(needs, operations):
            if needed and part.name not in report['modified_parts']:
                report['modified_parts'].append(part.name)
            _s5_partition(part, name, p, n, needed, tolerance, report)
            report['semantic_mapping'][name] = {'part': part.name, 'feature_name': _s5_repository_key(part.features, name, 'Feature', allow_missing=True), 'point_local': p, 'normal_local': n, 'resolution': 'CREATED' if needed else 'VERIFIED_EXISTING_BOUNDARY'}
        assembly.regenerate()
        flange = _s5_flange(model, beam, beam_pose, low, high, tolerance)
        for index in flange['face_indices']:
            points = _s5_polygon(beam, beam.faces[index], tolerance)
            _runtime_match_7 = False
            for p in points:
                if _runtime_match_7:
                    break
                if p[2] < low - tolerance or p[2] > high + tolerance:
                    _runtime_match_7 = True
            if _runtime_match_7:
                raise ValueError('Beam region extends beyond patch boundaries')
        expected_area = (high - low) * (flange['x_bounds'][1] - flange['x_bounds'][0])
        _runtime_total_8 = 0
        for i in flange['face_indices']:
            _runtime_total_8 += beam.faces[i].getSize(printResults=False)
        selected_area = _runtime_total_8
        if abs(selected_area - expected_area) > max(tolerance * tolerance, expected_area * 1e-05):
            raise ValueError('Beam patch is incomplete or ambiguous')
        brace_edges = _s5_edges_on_plane(brace, brace_info['point_local'], brace_info['normal_local'], tolerance)
        _runtime_total_9 = 0
        for s in brace_info['segments_local']:
            _runtime_total_9 += norm(sub(s[0], s[1]))
        expected_length = _runtime_total_9
        _runtime_total_10 = 0
        for i in brace_edges:
            _runtime_total_10 += brace.edges[i].getSize(printResults=False)
        actual_length = _runtime_total_10
        if not brace_edges or abs(expected_length - actual_length) > tolerance * max(1, len(brace_edges)):
            raise ValueError('Brace region does not match preflight intersection')
        _s5_set(beam, 'STEP05_REGION_BEAM_BRACE_FRONT', 'faces', flange['face_indices'], report)
        _s5_surface(beam, 'STEP05_SURF_BEAM_BRACE_FRONT', flange['face_indices'], flange['physical_side'], report)
        _s5_set(brace, 'STEP05_REGION_BRACE_FRONT_BEAM', 'edges', brace_edges, report)
        if real:
            for name, value in (('STEP05_C_MINUS_80', low), ('STEP05_C_PLUS_80', high)):
                edges = _s5_edges_on_plane(beam, (0.0, 0.0, value), (0.0, 0.0, 1.0), tolerance)
                _s5_set(beam, name, 'edges', edges, report)
        report['warnings'].append('Brace region is an interior shell intersection edge Set; no material removed and no interaction surface assumed')
        report['beam_region'] = dict(flange, geometric_region_type='FACE', name='STEP05_REGION_BEAM_BRACE_FRONT')
        report['brace_region'] = dict(brace_info, geometric_region_type='EDGE', name='STEP05_REGION_BRACE_FRONT_BEAM', edge_indices=brace_edges)
        for record in report['sets'] + report['surfaces']:
            report['semantic_mapping'][record['name']] = record
        for part in (beam, brace):
            _runtime_total_11 = 0
            for f in part.faces:
                _runtime_total_11 += f.getSize(printResults=False)
            after = _runtime_total_11
            if abs(after - area_before[part.name]) > max(tolerance * tolerance, area_before[part.name] * 1e-06):
                raise ValueError('Unexpected shell area change after partition')
        report['shell_area_before'] = area_before
        _runtime_values_12 = {}
        for part in (beam, brace):
            _runtime_total_13 = 0
            for f in part.faces:
                _runtime_total_13 += f.getSize(printResults=False)
            _runtime_values_12[part.name] = _runtime_total_13
        report['shell_area_after'] = _runtime_values_12
        assembly.regenerate()
        report['status'] = 'SUCCESS'
        return report
    except Exception as exc:
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        if real:
            _s5_print('mesh removed', report['mesh_removed'])
            _s5_print('remesh required', report['remesh_required'])
            print('Tie created = False\nCoupling created = False\nMaterial removed = False')
        parent = os.path.dirname(os.path.abspath(report_path))
        if not os.path.isdir(parent):
            os.makedirs(parent)
        with open(report_path, 'w') as handle:
            json.dump(report, handle, indent=2, ensure_ascii=True, allow_nan=False)
