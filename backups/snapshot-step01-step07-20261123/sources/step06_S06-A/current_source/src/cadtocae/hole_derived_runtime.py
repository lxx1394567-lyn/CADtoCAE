# Step06-A narrow derived-hole runtime. Embedded with pure geometry helpers.
S6A_TOL = 1.e-6


def s6a_pose(part, instance, metadata, diagnostics=None):
    from abaqusConstants import ON
    if instance.partName != part.name or instance.dependent != ON:
        raise ValueError('Expected dependent instance: ' + metadata['instance_name'])
    checks = []
    if diagnostics is not None:
        diagnostics[metadata['instance_name']] = dict(source='assembly_summary',
            contract='PRE_TRANSLATION_ROTATIONS_THEN_TRANSLATION_THEN_POST_TRANSLATION_ROTATIONS', anchors=checks)
    step04_validate_anchors(metadata['placement'], metadata.get('transform_anchors'), S6A_TOL, checks)
    return metadata['placement']


def s6a_references(assembly, part, expected):
    from abaqusConstants import ON
    names = []
    repositories = [assembly.instances]
    if hasattr(assembly, 'allInstances'):
        repositories.append(assembly.allInstances)
    for repository in repositories:
        for name in repository.keys():
            instance = repository[name]
            if instance.partName == part.name:
                if instance.dependent != ON:
                    raise ValueError('Independent target reference: ' + str(name))
                if name not in names:
                    names.append(name)
    if sorted(names) != sorted(expected):
        raise ValueError('PART_REFERENCE_REVIEW_REQUIRED: ' + part.name)
    return sorted(names)


def s6a_area(part):
    result = 0.
    for face in part.faces:
        result += face.getSize(printResults=False)
    return result


def s6a_plane_areas(part, geometry):
    # Areas of all five channel surfaces: protect web/lower flange/lips explicitly.
    result = [0., 0., 0., 0., 0.]
    p = geometry['section_params_m']
    for face in part.faces:
        points = []
        for i in face.getVertices():
            points.append(point3(part.vertices[i]))
        matched = []
        for index, axis, coordinate in ((0,0,0.), (1,1,0.), (2,1,p['h_m']), (3,0,p['b_m'])):
            valid = bool(points)
            for q in points:
                if abs(q[axis]-coordinate) > S6A_TOL:
                    valid = False
            if valid:
                if index == 3:
                    index = 3 if point3(face)[1] < p['h_m']/2. else 4
                matched.append(index)
        if len(matched) != 1:
            raise ValueError('Nonplanar/unrecognized C-channel surface')
        result[matched[0]] += face.getSize(printResults=False)
    return result


def s6a_shell_geometry(part, geometry):
    if geometry['model_policy'] != 'SHELL' or geometry['section_kind'] != 'C_CHANNEL' or len(part.cells) or not len(part.faces):
        raise ValueError('Derived holes require native SHELL C_CHANNEL')
    params = geometry['section_params_m']
    sizes = (params['b_m'], params['h_m'], geometry['length_m'])
    points = []
    for v in part.vertices:
        points.append(point3(v))
    for axis in range(3):
        values = []
        for p in points:
            values.append(p[axis])
        if not values or abs(min(values)) > S6A_TOL or abs(max(values)-sizes[axis]) > S6A_TOL:
            raise ValueError('Target C-channel extents/origin mismatch: ' + part.name)
    expected = (params['h_m']+2.*params['b_m']+2.*params['lip_m'])*geometry['length_m']
    if abs(s6a_area(part)-expected) > max(expected*1.e-5, 1.e-10):
        raise ValueError('Target C-channel area differs from uncut profile: ' + part.name)
    s6a_plane_areas(part, geometry)


def s6a_intersection(hole, source_pose, target_pose, geometry, surface):
    source_global = step04_local_point_to_global(hole['local_center_m'], source_pose)
    global_axis = step04_local_vector_to_global(hole['local_axis'], source_pose)
    major = hole.get('local_major_axis')
    if major is None:
        major = (0.,0.,1.)
    global_major = step04_local_vector_to_global(major, source_pose)
    q = step04_global_point_to_local(source_global, target_pose)
    axis = step04_global_vector_to_local(global_axis, target_pose)
    direction = step04_global_vector_to_local(global_major, target_pose)
    normal_axis = 0 if surface == 'PURLIN_LOCAL_WEB' else 1
    coordinate = 0. if normal_axis == 0 else geometry['section_params_m']['h_m']
    if abs(axis[normal_axis]) < 1.-1.e-6 or abs(direction[normal_axis]) > 1.e-6:
        raise ValueError('Hole axis/major axis incompatible with target ' + surface)
    distance = (coordinate-q[normal_axis])/axis[normal_axis]
    center = add(q, scale(axis, distance))
    intersection = step04_local_point_to_global(center, target_pose)
    if norm(cross(sub(intersection, source_global), global_axis)) > S6A_TOL:
        raise ValueError('Derived hole is not coaxial')
    return dict(source_global_center=source_global, global_hole_axis=global_axis,
                global_major_axis=global_major, intersection_global=intersection,
                local_center=center, local_axis=axis, local_major_axis=direction,
                target_surface=surface, normal_axis=normal_axis, plane_coordinate=coordinate,
                width_m=hole['width_m'], total_length_m=hole['total_length_m'], hole_type=hole['hole_type'])


def s6a_target_face(part, result, check_outline=False):
    center = result['local_center']
    face = part.faces.findAt(coordinates=tuple(center), printWarning=False)
    axis, coordinate = result['normal_axis'], result['plane_coordinate']
    normal = unit(vector3(face.getNormal(point=tuple(center))))
    if abs(normal[axis]) < 1.-1.e-6:
        raise ValueError('Target is not the requested web/top flange plane')
    points = []
    for i in face.getVertices():
        p = point3(part.vertices[i])
        if abs(p[axis]-coordinate) > S6A_TOL:
            raise ValueError('Target face crosses the semantic surface')
        points.append(p)
    if check_outline:
        # Narrow support: a complete slot must fit inside one rectangular planar patch.
        if len(points) != 4 or len(face.getEdges()) != 4:
            raise ValueError('Target must be one uncut rectangular web/flange patch')
        rectangle_area = 1.
        for dimension in range(3):
            if dimension == axis:
                continue
            values = []
            for p in points:
                values.append(p[dimension])
            low, high = min(values), max(values)
            half = result['width_m']/2. + (result['total_length_m']-result['width_m'])/2.*abs(result['local_major_axis'][dimension])
            if center[dimension]-half <= low+S6A_TOL or center[dimension]+half >= high-S6A_TOL:
                raise ValueError('Slot exceeds target web/top flange or partition edge')
            rectangle_area *= high-low
        if abs(face.getSize(printResults=False)-rectangle_area) > max(rectangle_area*1.e-5, 1.e-10):
            raise ValueError('Target face is not a complete rectangular patch')
    return face


def s6a_same_pattern(a, b):
    for key in ('width_m', 'total_length_m'):
        if abs(a[key]-b[key]) > S6A_TOL:
            return False
    if a['hole_type'] != b['hole_type'] or norm(sub(a['local_center'], b['local_center'])) > S6A_TOL:
        return False
    for key in ('local_axis','local_major_axis'):
        if abs(dot(a[key],b[key])) < 1.-1.e-6:
            return False
    return True


def s6a_support_existing(part, holes, previous):
    # Existing driving holes may be continued only with successful, matching runtime evidence.
    proof = previous.get('support_validation') or previous.get('support') or previous
    if proof.get('status') != 'SUCCESS':
        raise ValueError('Existing support holes require their successful Step06 report')
    records = proof.get('created_hole_details', [])
    removed = 0.
    for hole in holes:
        name = 'STEP06_HOLE_' + hole['hole_id']
        matches = []
        for r in records:
            if r['name'] == name and r['part'] == part.name:
                matches.append(r)
        if len(matches) != 1 or name not in part.features:
            raise ValueError('Existing support hole evidence/features incomplete')
        r = matches[0]
        for key in ('width_m','total_length_m','hole_type','local_center_m','local_axis','local_major_axis'):
            if r.get(key) != hole.get(key):
                raise ValueError('Existing support hole pattern differs from input')
        removed += (math.pi*hole['width_m']**2/4.+hole['width_m']*(hole['total_length_m']-hole['width_m']))*hole['source_geometry']['t_m']
    allowed = []
    for hole in holes:
        allowed.extend(['STEP06_HOLE_'+hole['hole_id'], 'STEP06_AXIS_'+hole['hole_id']])
    for key in part.features.keys():
        if str(key).startswith('STEP06_') and key not in allowed:
            raise ValueError('Unexpected/partial Step06 support feature')
    s6_geometry_preflight(part, holes[0], removed_volume=removed, existing=True)
    return proof


def s6a_shell_cut(model, part, result, geometry, report):
    from abaqusConstants import ZAXIS, SIDE1, RIGHT, COUNTERCLOCKWISE
    name = result['feature_name']
    face = s6a_target_face(part, result)
    before = s6a_plane_areas(part, geometry)
    datum = part.DatumAxisByPrincipalAxis(principalAxis=ZAXIS)
    report['model_modified'] = True
    axis_name = name+'_AXIS'
    part.features.changeKey(fromName=abaqus_name(datum.name), toName=abaqus_name(axis_name))
    report['created_auxiliary_features'].append(axis_name)
    up = part.datums[datum.id]
    matrix = part.MakeSketchTransform(sketchPlane=face, sketchUpEdge=up, sketchPlaneSide=SIDE1,
                                     sketchOrientation=RIGHT, origin=tuple(result['local_center'])).matrix()
    if len(matrix) != 12 or norm(sub(matrix[9:12], result['local_center'])) > S6A_TOL:
        raise ValueError('Derived sketch transform origin mismatch')
    uv = (dot(result['local_major_axis'], matrix[0:3]), dot(result['local_major_axis'], matrix[3:6]))
    if abs(s6_dot(uv,uv)-1.) > 1.e-6:
        raise ValueError('Derived slot direction not in sketch plane')
    sketch_name = name+'_SKETCH'
    sketch = model.ConstrainedSketch(name=abaqus_name(sketch_name), sheetSize=1., transform=matrix)
    s6_capsule(sketch, result['width_m'], result['total_length_m'], uv, COUNTERCLOCKWISE)
    partition = part.PartitionFaceBySketch(faces=(face,), sketch=sketch, sketchUpEdge=up, sketchOrientation=RIGHT)
    partition_name = name+'_OUTLINE'
    part.features.changeKey(fromName=abaqus_name(partition.name), toName=abaqus_name(partition_name))
    report['created_auxiliary_features'].append(partition_name)
    inside = s6a_target_face(part, result)
    expected = math.pi*result['width_m']**2/4.+result['width_m']*(result['total_length_m']-result['width_m'])
    if abs(inside.getSize(printResults=False)-expected) > max(expected*1.e-4, 1.e-10):
        raise ValueError('Partition did not isolate exactly the slot interior; no face removed')
    feature = part.RemoveFaces(faceList=(inside,))
    part.features.changeKey(fromName=abaqus_name(feature.name), toName=abaqus_name(name))
    result['created_feature'] = name
    report['created_derived_features'].append(name)
    after = s6a_plane_areas(part, geometry)
    target_index = 0 if result['target_surface'] == 'PURLIN_LOCAL_WEB' else 2
    for i in range(5):
        expected_delta = expected if i == target_index else 0.
        if abs(before[i]-after[i]-expected_delta) > max(expected*1.e-4, 1.e-10):
            raise ValueError('Shell area change outside intended slot; inspect partial model')
    result['removed_area_m2'] = before[target_index]-after[target_index]
    del model.sketches[abaqus_name(sketch_name)]


def execute_step06_a(plan, mdb, report_path, fingerprint):
    report = dict(project_id=plan['project_id'], benchmark_scope='P01-P04', status='PREFLIGHT',
                  plan_fingerprint=fingerprint, model_modified=False, errors=[],
                  purlin_local=[], inclined_beam=[], created_derived_features=[], created_auxiliary_features=[],
                  mesh_removed_parts=[], remesh_required_parts=[], mesh_before={}, support={},
                  derived_holes_executed=False, created_holes=0)
    report['transform_checks'] = {}
    try:
        if plan.get('schema_version') != 'step06-hole-setup-v0.2':
            raise ValueError('Unsupported Step06-A schema')
        previous = {}
        if os.path.isfile(report_path):
            with open(report_path) as handle:
                previous = json.load(handle)
        proof = previous.get('support_validation') or previous.get('support') or previous
        if proof.get('status') == 'SUCCESS' and proof.get('project_id') == plan['project_id']:
            # Preserve successful driving evidence even if a target pose fails before reuse checks.
            report['support_validation'] = proof
        model = resolve_repository_item(mdb.models, plan['project_id'], 'Model')
        assembly = model.rootAssembly
        for feature in assembly.features.values():
            if feature.isSuppressed():
                raise ValueError('Suppressed assembly feature prevents full reference audit')
        for key in model.sketches.keys():
            if str(key).startswith('STEP06_'):
                raise ValueError('Existing partial Step06 sketch')
        metadata, parts, poses = {}, {}, {}
        for member in plan['instances']:
            name = member['instance_name']
            metadata[name] = member
            part = resolve_repository_item(model.parts, member['part_name'], 'Part')
            instance = resolve_repository_item(assembly.instances, name, 'Instance')
            parts[part.name] = part
            poses[name] = s6a_pose(part, instance, member, report['transform_checks'])
        support_holes = []
        for hole in plan['driving_holes']:
            if hole['connection_group'] == 'P01':
                support_holes.append(hole)
        if len(support_holes) != 2:
            raise ValueError('Step06-A requires both enabled standard driving holes')
        support_part = parts[support_holes[0]['source_part']]
        policy = plan['part_executions'][0]
        if policy['execution_policy'] not in ('MODIFY_PART_ONCE','MODIFY_SHARED_PART_ONCE'):
            raise ValueError(policy['execution_policy'])
        s6a_references(assembly, support_part, policy['expected_affected_instances'])
        existing = False
        for key in support_part.features.keys():
            if str(key).startswith('STEP06_'):
                existing = True
        subplan = dict(plan)
        subplan.update(schema_version='step06-hole-setup-v0.1', benchmark_scope='P01')
        if existing:
            report['support_validation'] = s6a_support_existing(support_part, support_holes, previous)
            report['support'] = dict(status='REUSED_VERIFIED', created_holes=0)
        else:
            execute_hole_setup(subplan, mdb, report_path, fingerprint, preflight_only=True, write_report=False)
        source_by_id = {}
        for h in plan['driving_holes']:
            source_by_id[h['driving_hole_id']] = h
        checked_parts, by_target = {}, {}
        for derived in plan['derived_holes']:
            hole = source_by_id[derived['source_driving_hole_id']]
            target = metadata[derived['target_instance']]
            part = parts[target['part_name']]
            geometry = target['component_geometry']
            if part.name not in checked_parts:
                for key in part.features.keys():
                    if str(key).startswith('STEP06_'):
                        raise ValueError('Existing derived Step06 features; reopen model before derived execution')
                s6a_shell_geometry(part, geometry)
                checked_parts[part.name] = geometry
            r = s6a_intersection(hole, poses[hole['source_instance']], poses[derived['target_instance']], geometry, derived['target_surface_role'])
            r.update(connection_group=hole['connection_group'], source_instance=hole['source_instance'],
                     target_instance=derived['target_instance'], target_part=part.name)
            role = derived['target_role']
            r['feature_name'] = 'STEP06_HOLE_PURLIN_FROM_SUPPORT' if role == 'PURLIN_LOCAL' else 'STEP06_HOLE_BEAM_'+hole['connection_group']+'_FROM_SUPPORT'
            report['purlin_local' if role == 'PURLIN_LOCAL' else 'inclined_beam'].append(r)
            s6a_target_face(part, r, check_outline=True)
            by_target.setdefault(part.name, []).append(r)
        operations = []
        for part_name in sorted(by_target):
            results = by_target[part_name]
            expected = []
            for result in results:
                if result['target_instance'] not in expected:
                    expected.append(result['target_instance'])
            s6a_references(assembly, parts[part_name], expected)
            if results[0]['target_surface'] == 'PURLIN_LOCAL_WEB':
                identical = True
                for result in results:
                    if not s6a_same_pattern(results[0],result):
                        identical = False
                for result in results:
                    result.update(hole_pattern_identical=identical,
                                  execution_policy=('MODIFY_SHARED_PART_ONCE' if len(expected)>1 else 'MODIFY_PART_ONCE') if identical else 'PART_ISOLATION_REQUIRED')
                if not identical:
                    raise ValueError('PART_ISOLATION_REQUIRED: PURLIN_LOCAL derived patterns differ')
                operations.append(results[0])
            else:
                if len(expected) != 1:
                    raise ValueError('Beam derived holes require one target instance')
                for i in range(len(results)):
                    for j in range(i):
                        if norm(sub(results[i]['local_center'],results[j]['local_center'])) <= (results[i]['total_length_m']+results[j]['total_length_m'])/2.+S6A_TOL:
                            raise ValueError('Beam slot envelopes overlap')
                operations.extend(results)
        operations.sort(key=lambda r:(0 if r['target_surface']=='PURLIN_LOCAL_WEB' else 1,r['connection_group']))
        report['status'] = 'EXECUTING'
        if not existing:
            execute_hole_setup(subplan, mdb, report_path, fingerprint, write_report=False, report_state=report['support'])
            report['model_modified'] = True
            report['support_validation'] = report['support']
            if report['support']['mesh_removed']:
                report['mesh_removed_parts'].append(support_part.name)
                report['remesh_required_parts'].append(support_part.name)
        for part_name in sorted(checked_parts):
            part = parts[part_name]
            report['mesh_before'][part_name] = dict(nodes=len(part.nodes), elements=len(part.elements))
            if len(part.nodes) or len(part.elements):
                report['model_modified'] = True
                report['remesh_required_parts'].append(part_name)
                part.deleteMesh()
                if len(part.nodes) or len(part.elements):
                    raise ValueError('Target mesh remains after deleteMesh')
                report['mesh_removed_parts'].append(part_name)
        for result in operations:
            s6a_shell_cut(model, parts[result['target_part']], result, checked_parts[result['target_part']], report)
        assembly.regenerate()
        for result in report['purlin_local']:
            result['created_feature'] = 'STEP06_HOLE_PURLIN_FROM_SUPPORT'
        report.update(status='SUCCESS', derived_holes_executed=True,
                      created_holes=report['support'].get('created_holes',0)+len(report['created_derived_features']))
        return report
    except Exception as exc:
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        report['traceback'] = traceback.format_exc()
        if report['support'].get('model_modified'):
            report['model_modified'] = True
        raise
    finally:
        report['created_holes'] = report['support'].get('created_holes',0)+len(report['created_derived_features'])
        with open(report_path, 'w') as handle:
            json.dump(report, handle, indent=2, ensure_ascii=True, allow_nan=False)
