# Python 2.7 compatible; shares only the frozen executor's utility functions.


def cct_box(obj):
    box = obj.faces.getBoundingBox()
    return box['low'], box['high']


def cct_verify(part, instance, member, ON):
    if len(part.cells) or not len(part.faces) or instance.dependent != ON:
        raise ValueError('COLUMN_COLUMN_TIE requires native dependent PIPE shell')
    if text(instance.partName) != text(member['part_name']):
        raise ValueError('Column instance references wrong Part')
    low, high = cct_box(part)
    r, length = member['radius_m'], member['length_m']
    for a, b in zip(low+high, (-r,-r,0.,r,r,length)):
        if abs(a-b) > 1.e-6:
            raise ValueError('Column Part differs from PIPE local Z geometry')
    axis = cct_unit(member['axis_direction'])
    ilow, ihigh = cct_box(instance)
    origin = []
    for i in range(3):
        # A full cylinder is centrally symmetric, including after rotation.
        center = (ilow[i]+ihigh[i])/2.
        origin.append(center-axis[i]*length/2.)
        extent = abs(axis[i])*length/2.+r*math.sqrt(max(0.,1.-axis[i]*axis[i]))
        if abs(ihigh[i]-center-extent) > 1.e-6 or abs(origin[i]-member['origin'][i]) > 1.e-6:
            raise ValueError('Column runtime placement differs from summary')
    if len(part.vertices) != len(instance.vertices) or not len(part.vertices):
        raise ValueError('Column Part/Instance vertex correspondence missing')
    for i in range(len(part.vertices)):
        local = point3(part.vertices[i])
        world = point3(instance.vertices[i])
        delta = cct_sub(world,origin)
        station = cct_dot(delta,axis)
        radial = (delta[0]-axis[0]*station,delta[1]-axis[1]*station,delta[2]-axis[2]*station)
        if abs(station-local[2]) > 1.e-6 or abs(math.sqrt(cct_dot(radial,radial))-r) > 1.e-6:
            raise ValueError('Column runtime axis differs from summary')
    return dict(member,origin=origin,axis_direction=axis)


def cct_partition(part, station, XYPLANE, report):
    low, high = cct_box(part)
    if abs(station-low[2]) < 1.e-6 or abs(station-high[2]) < 1.e-6:
        return
    name = abaqus_name('STEP05_CCT_Z_%d' % int(round(station*1.e6)))
    crossing, below, above = False, False, False
    for face in part.faces:
        box = part.faces[face.index:face.index+1].getBoundingBox()
        lo, hi = box['low'][2], box['high'][2]
        if lo < station-1.e-6 and hi > station+1.e-6:
            crossing = True
        if abs(hi-station) < 1.e-6:
            below = True
        if abs(lo-station) < 1.e-6:
            above = True
    if not crossing:
        if not below or not above:
            raise ValueError('Column partition boundary missing')
        report['reused'].append(part.name+':'+name)
        return
    if item(part.features, name, True) is not None or item(part.features, name+'_PLANE', True) is not None:
        raise ValueError('Conflicting column partition '+name)
    if len(part.elements):
        part.deleteMesh()
        report['mesh_removed'].append(part.name)
    report['remesh_required_parts'].append(part.name)
    datum = part.DatumPlaneByPrincipalPlane(principalPlane=XYPLANE, offset=station)
    datum_id = datum.id
    part.features.changeKey(fromName=abaqus_name(datum.name), toName=abaqus_name(name+'_PLANE'))
    feature = part.PartitionFaceByDatumPlane(datumPlane=part.datums[datum_id], faces=part.faces[:])
    part.features.changeKey(fromName=abaqus_name(feature.name), toName=name)
    # Validate circular boundaries using face bounds; a circular edge may have one vertex.
    below, above = False, False
    for face in part.faces:
        box = part.faces[face.index:face.index+1].getBoundingBox()
        lo, hi = box['low'][2], box['high'][2]
        if lo < station-1.e-6 and hi > station+1.e-6:
            raise ValueError('Column partition did not split face')
        if abs(hi-station) < 1.e-6:
            below = True
        if abs(lo-station) < 1.e-6:
            above = True
    if not below or not above:
        raise ValueError('Column partition boundary missing')
    report['partitions'].append(dict(part=part.name, station=station, name=name))


def cct_faces(part, instance, member, common_axis):
    ids, sides = [], []
    area = 0.0
    radius = member['radius_m']
    origin = member['origin']
    axis = member['axis_direction']
    interval = member['interval']
    selected_low, selected_high = None, None
    if len(part.faces) != len(instance.faces):
        raise ValueError('Column Part/Instance face correspondence differs')
    for local_face in part.faces:
        box = part.faces[local_face.index:local_face.index+1].getBoundingBox()
        lo, hi = box['low'][2], box['high'][2]
        if lo < interval[0]-1.e-6 or hi > interval[1]+1.e-6 or hi-lo <= 1.e-6:
            continue
        face = instance.faces[local_face.index]
        if tuple(face.getVertices()) != tuple(local_face.getVertices()):
            raise ValueError('Column Part/Instance face correspondence differs')
        point = point3(face)
        delta = cct_sub(point,origin)
        station = cct_dot(delta,axis)
        radial = (delta[0]-axis[0]*station,delta[1]-axis[1]*station,delta[2]-axis[2]*station)
        radial_length = math.sqrt(dot(radial, radial))
        if abs(radial_length-radius) > 1.e-6:
            continue
        curvature = face.getCurvature(point=point)
        values = sorted([abs(curvature['curvature1']), abs(curvature['curvature2'])])
        if values[0] > 1.e-6 or abs(values[1]-1./radius) > 1.e-5/radius:
            continue
        n = vector3(face.getNormal(point=point))
        nlength = math.sqrt(dot(n,n))
        if nlength <= 1.e-12:
            raise ValueError('Cannot resolve column physical shell side')
        alignment = dot(n,radial)/(nlength*radial_length)
        if abs(abs(alignment)-1.) > 1.e-5:
            raise ValueError('Cannot resolve column physical shell side')
        outer = 'SIDE1' if alignment > 0 else 'SIDE2'
        side = outer if member['physical_side'] == 'OUTER' else ('SIDE2' if outer == 'SIDE1' else 'SIDE1')
        ids.append(face.index)
        sides.append(side)
        area += float(face.getSize(printResults=False))
        vertices = face.getVertices()
        if not vertices:
            raise ValueError('Column selected face has no axial boundary vertices')
        for index in vertices:
            axial = cct_dot(point3(instance.vertices[index]),common_axis)
            if selected_low is None or axial < selected_low:
                selected_low = axial
            if selected_high is None or axial > selected_high:
                selected_high = axial
    if not ids:
        raise ValueError('No cylindrical shell faces in column overlap')
    for side in sides:
        if side != sides[0]:
            raise ValueError('Cannot uniquely resolve column physical shell side')
    expected = 2.*math.pi*radius*(interval[1]-interval[0])
    if abs(area-expected) > max(1.e-12,expected*1.e-5):
        raise ValueError('Column cylindrical overlap incomplete')
    return seq(instance.faces, ids), sides[0], ids, [selected_low,selected_high]


def execute_column(plan, mdb, report_path, fingerprint, previous, XYPLANE, ON, COMPUTED, tie_batch=None):
    with open(report_path) as handle:
        combined = json.load(handle)
    report = dict(rule_id='COLUMN_COLUMN_TIE', fingerprint=fingerprint, status='PREFLIGHT',
                  partitions=[], reused=[], mesh_removed=[], remesh_required_parts=[],
                  semantic_mapping={}, errors=[], material_removed=False, tie_created=False)
    combined['column_column_tie'] = report
    try:
        print('COLUMN_COLUMN_TIE')
        model = item(mdb.models, plan['model_name'])
        a = model.rootAssembly
        rule = plan['column_column_tie']
        members = rule['members']
        objects, positions = [], []
        for member in members:
            p = item(model.parts, member['part_name'])
            inst = item(a.instances, member['instance_name'])
            count = 0
            for other in a.instances.values():
                if text(other.partName) == text(member['part_name']):
                    count += 1
            if count != 1:
                raise ValueError('Unexpected shared column Part')
            positions.append(cct_verify(p, inst, member, ON))
            objects.append((p,inst))
            print('%s part = %s; length = %s m' % (member['role'],member['part_name'],member['length_m']))
            for key in p.features.keys():
                if text(key).startswith('STEP05_CCT_'):
                    if not previous or previous.get('fingerprint') != fingerprint or previous.get('status') != 'SUCCESS':
                        raise ValueError('Existing column geometry lacks matching successful report; conflict policy FAIL')
        # Cheap actual geometry check before touching column mesh or geometry.
        layout = cct_axial_layout(positions,rule['tolerance_m'])
        report['ranges'] = layout
        for label in ('common_axis','upper_global_range','lower_global_range','actual_overlap','overlap_length'):
            print('%s = %s' % (label.replace('_',' '),layout[label]))
        for i in range(2):
            member = positions[i]
            interval = layout['local_overlaps'][i]
            cct_same_interval(interval,members[i]['interval'],members[i]['interval'],rule['tolerance_m'])
            member['interval'] = interval
            print('%s local overlap = %s; partitions = %s' % (member['role'],interval,layout['partitions'][i]))
            for station in layout['partitions'][i]:
                cct_partition(objects[i][0],station,XYPLANE,report)
        a.regenerate()
        selections = []
        for i in range(2):
            member = positions[i]
            inst = item(a.instances,member['instance_name'])
            selection = cct_faces(objects[i][0],inst,member,layout['common_axis'])
            selections.append(selection)
            print('%s selected global range = %s' % (member['role'],selection[3]))
        cct_same_interval(selections[0][3],selections[1][3],layout['actual_overlap'],rule['tolerance_m'])
        report['ranges']['selected_upper_range'] = selections[0][3]
        report['ranges']['selected_lower_range'] = selections[1][3]
        surfaces = []
        for member, selection in zip(positions,selections):
            faces, side, ids, selected_range = selection
            surfaces.append(region(a,member['region'],faces,side,report))
            report[member['role']] = dict(physical_side=member['physical_side'],shell_side=side,face_ids=ids)
            print('%s %s = %s' % (member['role'],member['physical_side'],side))
        master_surface_name = abaqus_name(positions[1]['region'].replace('REGION_', 'SURF_'))
        slave_surface_name = abaqus_name(positions[0]['region'].replace('REGION_', 'SURF_'))
        tie_name = abaqus_name(rule['tie'])
        if tie_batch is not None:
            tie_batch.stage(model, master_surface_name=master_surface_name, slave_surface_name=slave_surface_name, master_instance=rule['master'], slave_instance=rule['slave'], name=tie_name, master=surfaces[1], slave=surfaces[0], positionToleranceMethod=COMPUTED, adjust=ON, tieRotations=ON, thickness=ON)
        old = item(model.constraints,tie_name,True)
        if old is None:
            if tie_batch is None:
                model.Tie(name=tie_name,master=surfaces[1],slave=surfaces[0],positionToleranceMethod=COMPUTED,adjust=ON,tieRotations=ON,thickness=ON)
            report['tie_created'] = tie_batch is None
        else:
            if surface_key(a, old.master) != master_surface_name or surface_key(a, old.slave) != slave_surface_name or old.positionToleranceMethod != COMPUTED or old.adjust != ON or old.tieRotations != ON or old.thickness != ON or getattr(old,'suppressed',False) or str(getattr(old,'constraintEnforcement','SOLVER_DEFAULT')) != 'SOLVER_DEFAULT' or str(getattr(old,'constraintRatioMethod','DEFAULT')) != 'DEFAULT':
                raise ValueError('Conflicting column Tie '+tie_name)
            report['reused'].append(tie_name)
        report['tie_present'] = tie_batch is None or old is not None
        report['master'],report['slave'],report['tie'] = rule['master'],rule['slave'],rule['tie']
        if previous:
            for p, inst in objects:
                if p.name in previous.get('remesh_required_parts',[]) and not len(p.elements) and p.name not in report['remesh_required_parts']:
                    report['remesh_required_parts'].append(p.name)
        print('master = %s; slave = %s; Tie = %s; Tie created = %s' % (rule['master'],rule['slave'],tie_name,report['tie_created']))
        a.regenerate()
        report['status'] = 'SUCCESS' if tie_batch is None else 'PENDING_TIE_PREFLIGHT'
        combined['overall_status'] = 'SUCCESS'
        return report
    except Exception as exc:
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        report['traceback'] = traceback.format_exc()
        combined['overall_status'] = 'FAILED'
        print('COLUMN_COLUMN_TIE Tie created = False: %s' % exc)
        raise
    finally:
        report['remesh_required'] = bool(report['remesh_required_parts'])
        # Keep the frozen beam report/fingerprint intact; expose aggregate mesh status.
        combined['remesh_required'] = combined['remesh_required'] or report['remesh_required']
        print('COLUMN_COLUMN_TIE Material removed = False')
        with open(report_path,'w') as handle:
            json.dump(combined,handle,ensure_ascii=True,indent=2)
