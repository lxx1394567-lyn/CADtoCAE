# Standalone Python 2.7 compatible Part-local BEAM_BRACE_TIE executor.
import os
import math
import traceback


def is_numeric_triple(value):
    """Only a finite, float-convertible three-component sequence is valid."""
    try:
        string_types = (basestring,)
    except NameError:
        string_types = (str, bytes)
    if isinstance(value, string_types):
        return False
    try:
        if len(value) != 3:
            return False
        for i in range(3):
            number = float(value[i])
            if math.isnan(number) or math.isinf(number):
                return False
        return True
    except (TypeError, ValueError, IndexError, KeyError, OverflowError):
        return False


def point3(value):
    """Read coordinates, including CAE (point, direction) payloads."""
    has_point_on = hasattr(value, 'pointOn')
    raw = value.pointOn if has_point_on else value
    point = raw
    try:
        for depth in range(8):
            if is_numeric_triple(point):
                return (float(point[0]), float(point[1]), float(point[2]))
            if len(point) and is_numeric_triple(point[0]):
                first = point[0]
                return (float(first[0]), float(first[1]), float(first[2]))
            # Preserve the existing shell pointOn six-scalar coordinate/normal form.
            if has_point_on and len(point) == 6 and is_numeric_triple(point[:3]):
                return (float(point[0]), float(point[1]), float(point[2]))
            if len(point) != 1:
                break
            point = point[0]
    except (TypeError, ValueError, IndexError, KeyError, OverflowError):
        pass
    raise ValueError('Invalid Abaqus 3D coordinate: %r' % (raw,))


def vector3(value):
    """Normalize an explicit vector API result; never infer a pointOn normal."""
    vector = value
    try:
        for depth in range(8):
            if is_numeric_triple(vector):
                return (float(vector[0]), float(vector[1]), float(vector[2]))
            if len(vector) != 1:
                break
            vector = vector[0]
    except (TypeError, ValueError, IndexError, KeyError, OverflowError):
        pass
    raise ValueError('Invalid Abaqus 3D vector: %r' % (value,))


def abaqus_name(value):
    """ASCII repository key: byte str on Python 2, native str on Python 3."""
    if value is None:
        return ''
    try:
        unicode_type = unicode
    except NameError:
        unicode_type = None
    try:
        if unicode_type is not None and isinstance(value, unicode_type):
            return value.encode('ascii')
        if isinstance(value, bytes):
            decoded = value.decode('ascii')
            return value if unicode_type is not None else decoded
        if isinstance(value, str):
            value.encode('ascii')
            return value
    except UnicodeError:
        raise ValueError('Abaqus repository names must be ASCII: %r' % (value,))
    raise TypeError('Abaqus repository name must be text: %r' % (value,))


def text(value):
    try:
        cls = unicode
    except NameError:
        cls = str
    return value if isinstance(value, cls) else value.decode('utf-8')


def item(repo, name, optional=False):
    name = abaqus_name(name)
    keys = [k for k in repo.keys() if text(k) == text(name)]
    if not keys and optional:
        return None
    if len(keys) != 1:
        raise ValueError('Expected unique %r; available: %r' % (name, list(repo.keys())))
    return repo[abaqus_name(keys[0])]


def surface_key(assembly, value):
    """Resolve an existing Tie region by repository key, never object.name."""
    if isinstance(value, (tuple, list)):
        if not value:
            raise ValueError('Empty Tie region descriptor')
        name = abaqus_name(value[0])
        item(assembly.surfaces, name)
        return name
    matches = []
    for name in assembly.surfaces.keys():
        if assembly.surfaces[name] is value:
            matches.append(abaqus_name(name))
    if len(matches) != 1:
        raise ValueError('Cannot resolve unique Tie surface repository key')
    return matches[0]


def seq(array, ids):
    result = array[0:0]
    for i in ids:
        result = result+array[i:i+1]
    return result


def vertices(obj, face):
    return [point3(obj.vertices[i]) for i in face.getVertices()]


def dot(a, b):
    total = 0.0
    for x, y in zip(a, b):
        total += x * y
    return total


def sub(a, b):
    result = []
    for x, y in zip(a, b):
        result.append(x - y)
    return tuple(result)


def center(points):
    result = []
    for i in range(3):
        total = 0.0
        for p in points:
            total += p[i]
        result.append(total / len(points))
    return tuple(result)


def normal(face):
    n = vector3(face.getNormal())
    length = math.sqrt(dot(n, n))
    if length < 1e-12:
        raise ValueError('Invalid face normal')
    result = []
    for v in n:
        result.append(v / length)
    return tuple(result)


def crosses(part, station):
    for face in part.faces:
        below, above = False, False
        for point in vertices(part, face):
            if point[2] < station - 1.e-6:
                below = True
            if point[2] > station + 1.e-6:
                above = True
        if below and above:
            return True
    return False


def boundary_exists(part, station):
    for edge in part.edges:
        ids = edge.getVertices()
        if len(ids) != 2:
            continue
        on_plane = True
        for i in ids:
            if abs(point3(part.vertices[i])[2] - station) >= 1.e-6:
                on_plane = False
                break
        if on_plane:
            return True
    return False


def partition(part, station, XYPLANE, report):
    name = abaqus_name('STEP05_BBT_Z_%d' % int(round(station*1.e6)))
    if not crosses(part, station):
        if not boundary_exists(part, station):
            raise ValueError('No complete partition or existing boundary at %s' % station)
        report['reused'].append(part.name+':'+name)
        return
    if item(part.features, name, True) is not None or item(part.features, name+'_PLANE', True) is not None:
        raise ValueError('Conflicting partition feature '+name)
    if len(part.elements):
        part.deleteMesh()
        report['mesh_removed'].append(part.name)
    if part.name not in report['remesh_required_parts']:
        report['remesh_required_parts'].append(part.name)
    datum = part.DatumPlaneByPrincipalPlane(principalPlane=XYPLANE, offset=station)
    datum_id = datum.id
    part.features.changeKey(fromName=abaqus_name(datum.name), toName=abaqus_name(name+'_PLANE'))
    feature = part.PartitionFaceByDatumPlane(datumPlane=part.datums[datum_id], faces=part.faces[:])
    part.features.changeKey(fromName=abaqus_name(feature.name), toName=abaqus_name(name))
    if crosses(part, station) or not boundary_exists(part, station):
        raise ValueError('Partition failed at %s' % station)
    report['partitions'].append(dict(part=part.name, station=station, name=name))


def zone_faces(part, interval, web=False):
    selected = []
    for f in part.faces:
        points = vertices(part, f)
        if not points:
            continue
        accepted = True
        for point in points:
            if not interval[0]-1.e-6 <= point[2] <= interval[1]+1.e-6:
                accepted = False
                break
            if web and abs(point[0]) >= 1.e-6:
                accepted = False
                break
        if not accepted:
            continue
        selected.append(f.index)
    if not selected:
        raise ValueError('Empty %s region in %r' % ('web' if web else 'brace end', interval))
    return selected


def contact_faces(beam_instance, beam_ids, brace_instance, candidates):
    bf = beam_instance.faces[beam_ids[0]]
    n = normal(bf)
    bp = vertices(beam_instance,bf)[0]
    beam_points = [p for i in beam_ids for p in vertices(beam_instance,beam_instance.faces[i])]
    for i in beam_ids:
        if abs(dot(normal(beam_instance.faces[i]),n)) < 1.-1.e-6:
            raise ValueError('Beam web patch normals disagree')
    # Direct comparisons of already assembled faces; no transform reconstruction.
    scores = []
    for i in candidates:
        f = brace_instance.faces[i]
        if abs(dot(normal(f),n)) < 1.-1.e-5:
            continue
        points = vertices(brace_instance,f)
        gap = abs(dot(sub(center(points),bp),n))
        # Tangential center separation breaks equal-plane-distance ties.
        delta = sub(center(points),center(beam_points))
        lateral = math.sqrt(max(0.,dot(delta,delta)-dot(delta,n)**2))
        scores.append((gap,lateral,i))
    if not scores:
        raise ValueError('No brace end face parallel to beam web')
    scores.sort()
    nearest = [s for s in scores if abs(s[0]-scores[0][0]) < 1.e-6]
    nearest.sort(key=lambda s:s[1])
    if len(nearest)>1 and abs(nearest[0][1]-nearest[1][1]) < 1.e-6:
        raise ValueError('Ambiguous brace contact faces')
    return [nearest[0][2]], nearest[0][0], nearest[0][1]


def signature(faces):
    result = []
    for f in faces:
        result.append((text(f.instanceName), f.index))
    return sorted(result)


def region(assembly, name, faces, side, report):
    set_name = abaqus_name(name)
    existing = item(assembly.sets, set_name, True)
    if existing is None:
        assembly.Set(name=set_name, faces=faces)
    elif signature(existing.faces) != signature(faces):
        raise ValueError('Conflicting Set ' + name)
    surf_name = abaqus_name(set_name.replace('REGION_', 'SURF_'))
    existing = item(assembly.surfaces, surf_name, True)
    if existing is None:
        assembly.Surface(name=surf_name, **{'side1Faces' if side == 'SIDE1' else 'side2Faces': faces})
    else:
        if signature(existing.faces) != signature(faces) or not hasattr(existing, 'sides'):
            raise ValueError('Conflicting Surface ' + surf_name)
        for existing_side in existing.sides:
            if str(existing_side) != side:
                raise ValueError('Conflicting Surface ' + surf_name)
    report['semantic_mapping'][name] = surf_name
    return item(assembly.surfaces, surf_name)


def execute(plan, mdb, report_path, fingerprint, XYPLANE, ON, COMPUTED, tie_batch=None):
    report = dict(project_id=plan['project_id'], model_name=plan['model_name'], rule_id='BEAM_BRACE_TIE', fingerprint=fingerprint, status='PREFLIGHT', partitions=[], connections=[], mesh_removed=[], remesh_required_parts=[], remesh_required=False, reused=[], semantic_mapping={}, warnings=[], errors=[], material_removed=False, tie_created=False)
    try:
        model = item(mdb.models, plan['model_name'])
        a = model.rootAssembly
        parts, instances, metadata = ({}, {}, {})
        previous = None
        if os.path.isfile(report_path):
            with open(report_path) as handle:
                previous = json.load(handle)
        for m in plan['instances']:
            p = item(model.parts, m['part_name'])
            inst = item(a.instances, m['instance_name'])
            if inst.dependent != ON:
                raise ValueError('Part-local rule requires a fresh Step04 dependent instance: ' + m['instance_name'] + '; reopen Step02/Step04 model, not the previous Extend Face experiment')
            if len(p.cells) or not len(p.faces):
                raise ValueError('Expected native shell C_CHANNEL Part')
            if text(inst.partName) != text(m['part_name']):
                raise ValueError('Instance references wrong Part')
            users = [i for i in a.instances.values() if text(i.partName) == text(p.name)]
            if len(users) != 1:
                raise ValueError('Unexpected shared Part references')
            length = m['component_geometry']['length_m']
            z = [point3(v)[2] for v in p.vertices]
            if abs(min(z)) > 1e-06 or abs(max(z) - length) > 1e-06:
                raise ValueError('Part length differs from components input')
            section = m['component_geometry']['section_params_m']
            for axis, dimension in ((0, 'b_m'), (1, 'h_m')):
                coords = [point3(v)[axis] for v in p.vertices]
                if abs(min(coords)) > 1e-06 or abs(max(coords) - section[dimension]) > 1e-06:
                    raise ValueError('Part section differs from Step02 C_CHANNEL convention')
            parts[m['part_name']], instances[m['instance_name']], metadata[m['part_name']] = (p, inst, m)
        if not plan['config']['enabled']:
            report['status'] = 'DISABLED'
            return report
        existing = [k for p in parts.values() for k in p.features.keys() if text(k).startswith('STEP05_BBT_')]
        if existing and (not previous or previous.get('fingerprint') != fingerprint or previous.get('status') != 'SUCCESS'):
            raise ValueError('Existing BEAM_BRACE_TIE geometry lacks matching successful report; conflict policy FAIL')
        for name, stations in plan['partitions'].items():
            for station in sorted(set(stations)):
                partition(parts[name], station, XYPLANE, report)
        a.regenerate()
        resolved = []
        for c in plan['connections']:
            bp, rp = (parts[c['beam_part']], parts[c['brace_part']])
            bi, ri = (item(a.instances, c['beam']), item(a.instances, c['brace']))
            for p, i in ((bp, bi), (rp, ri)):
                if len(p.faces) != len(i.faces):
                    raise ValueError('Part/Instance face correspondence differs')
                for face in p.faces:
                    if tuple(face.getVertices()) != tuple(i.faces[face.index].getVertices()):
                        raise ValueError('Part/Instance face correspondence differs')
            beam_ids = zone_faces(bp, c['beam_range'], web=True)
            expected = (c['beam_range'][1] - c['beam_range'][0]) * metadata[bp.name]['component_geometry']['section_params_m']['h_m']
            actual = 0.0
            for i in beam_ids:
                actual += float(bp.faces[i].getSize(printResults=False))
            if abs(actual - expected) > max(1e-12, expected * 1e-06):
                raise ValueError('Beam web patch area incomplete')
            brace_ids, gap, lateral = contact_faces(bi, beam_ids, ri, zone_faces(rp, c['brace_range']))
            resolved.append((c, bi, ri, beam_ids, brace_ids, gap, lateral))
        for c, bi, ri, bids, rids, gap, lateral in resolved:
            config = plan['config']
            beam_surf = region(a, c['beam_region'], seq(bi.faces, bids), config['beam_shell_side'], report)
            brace_surf = region(a, c['brace_region'], seq(ri.faces, rids), config['brace_shell_side'], report)
            master_surface_name = abaqus_name(c['brace_region'].replace('REGION_', 'SURF_'))
            slave_surface_name = abaqus_name(c['beam_region'].replace('REGION_', 'SURF_'))
            tie_name = abaqus_name(c['tie'])
            if tie_batch is not None:
                tie_batch.stage(model, master_surface_name=master_surface_name, slave_surface_name=slave_surface_name, master_instance=c['brace'], slave_instance=c['beam'], name=tie_name, master=brace_surf, slave=beam_surf, positionToleranceMethod=COMPUTED, adjust=ON, tieRotations=ON, thickness=ON)
            old = item(model.constraints, tie_name, True)
            if old is None:
                if tie_batch is None:
                    model.Tie(name=tie_name, master=brace_surf, slave=beam_surf, positionToleranceMethod=COMPUTED, adjust=ON, tieRotations=ON, thickness=ON)
                report['tie_created'] = tie_batch is None
            else:

                if surface_key(a, old.master) != master_surface_name or surface_key(a, old.slave) != slave_surface_name or old.positionToleranceMethod != COMPUTED or (old.adjust != ON) or (old.tieRotations != ON) or (old.thickness != ON) or getattr(old, 'suppressed', False) or (str(getattr(old, 'constraintEnforcement', 'SOLVER_DEFAULT')) != 'SOLVER_DEFAULT') or (str(getattr(old, 'constraintRatioMethod', 'DEFAULT')) != 'DEFAULT'):
                    raise ValueError('Conflicting Tie ' + c['tie'])
                report['reused'].append(c['tie'])
            record = dict(c, beam_faces=bids, brace_faces=rids, normal_gap_m=gap, tangential_center_distance_m=lateral, beam_side=config['beam_shell_side'], brace_side=config['brace_shell_side'], tie_present=tie_batch is None or old is not None)
            report['connections'].append(record)
            print('BEAM_BRACE_TIE %s' % c['id'].replace('BEAM_BRACE_', ''))
            print(json.dumps(record, ensure_ascii=True, sort_keys=True))
            print('master = %s; slave = %s; Tie stage = %s' % (c['brace'], c['beam'], report['connections'][-1]['tie_present']))
        for name, p in parts.items():
            if previous and name in previous.get('remesh_required_parts', []) and (not len(p.elements)) and (name not in report['remesh_required_parts']):
                report['remesh_required_parts'].append(name)
        a.regenerate()
        report['status'] = 'SUCCESS' if tie_batch is None else 'PENDING_TIE_PREFLIGHT'
        return report
    except Exception as exc:
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        report['remesh_required'] = bool(report['remesh_required_parts'])
        print('Material removed = False; remesh_required = %s' % report['remesh_required'])
        with open(report_path, 'w') as handle:
            json.dump(report, handle, ensure_ascii=True, indent=2)


if __name__ == '__main__':
    from abaqus import mdb
    from abaqusConstants import XYPLANE, ON, COMPUTED
    import assembly
    import interaction
    import mesh
    execute(PLAN,mdb,REPORT,FINGERPRINT,XYPLANE,ON,COMPUTED)
