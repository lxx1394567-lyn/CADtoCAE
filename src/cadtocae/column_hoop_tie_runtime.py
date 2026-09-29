# Standalone embedded Abaqus 2020 code. Frozen column utilities supply shell sides.


def cht_radial(point, member):
    delta = cct_sub(point,member['origin'])
    z = cct_dot(delta,member['axis_direction'])
    axis = member['axis_direction']
    return (delta[0]-axis[0]*z,delta[1]-axis[1]*z,delta[2]-axis[2]*z)


def cht_bounds(instance, axis, faces=None):
    indices = []
    if faces is None:
        indices = range(len(instance.vertices))
    else:
        for face in faces:
            for i in face.getVertices():
                if i not in indices:
                    indices.append(i)
    if not indices:
        raise ValueError('HOOP axial boundary vertices missing')
    low, high = None, None
    for i in indices:
        z = cct_dot(point3(instance.vertices[i]),axis)
        if low is None or z < low: low = z
        if high is None or z > high: high = z
    return [low,high]


def cht_center(faces):
    sx, sy, sz = 0., 0., 0.
    area = 0.
    for face in faces:
        size = float(face.getSize(printResults=False))
        raw = face.getCentroid()
        try:
            point = point3(raw)
        except ValueError:
            print('HOOP centroid face index = %s; getCentroid raw repr = %r' % (face.index, raw))
            raise
        if math.isnan(size) or math.isinf(size) or size < 0.:
            raise ValueError('Invalid HOOP face area')
        sx += size*point[0]
        sy += size*point[1]
        sz += size*point[2]
        area += size
    if area <= 1.e-12: raise ValueError('Empty HOOP contact region')
    return point3((sx/area,sy/area,sz/area))


def cht_inner(instance, half, column, overlap):
    ids = []
    r = half['inner_radius_m']
    axis = column['axis_direction']
    diagnostics = 0
    for face in instance.faces:
        try:
            point = point3(face)
        except ValueError:
            print('HOOP_%s candidate face index = %s; pointOn raw repr = %r' % (half['label'],face.index,face.pointOn))
            raise
        radial = cht_radial(point,column)
        size = math.sqrt(cct_dot(radial,radial))
        if abs(size-r) > 1.e-6: continue
        raw_normal = face.getNormal(point=point)
        if diagnostics < 3:
            print('HOOP_%s candidate face: index = %s; pointOn raw repr = %r; normalized coordinate = %r; area = %s; radius = %s' %
                (half['label'],face.index,face.pointOn,point,float(face.getSize(printResults=False)),size))
            print('HOOP_%s candidate getCentroid raw repr = %r' % (half['label'],face.getCentroid()))
            print('HOOP_%s candidate getNormal = %r' % (half['label'],raw_normal))
            diagnostics += 1
        n = cct_unit(vector3(raw_normal))
        if cct_dot(n,radial)/size > -1.+1.e-5: continue
        curvature = face.getCurvature(point=point)
        curv = sorted([abs(curvature['curvature1']),abs(curvature['curvature2'])])
        if curv[0] > 1.e-6 or abs(curv[1]-1./r) > 1.e-5/r: continue
        bounds = cht_bounds(instance,axis,[face])
        if bounds[1]-bounds[0] <= 1.e-6: continue
        if bounds[0] < overlap[0]-1.e-6 or bounds[1] > overlap[1]+1.e-6:
            raise ValueError('HOOP inner face extends outside overlap; existing HOOP boundaries required (no HOOP modification)')
        ids.append(face.index)
    if not ids: raise ValueError('No unique cylindrical HOOP inner contact surface')
    faces = seq(instance.faces,ids)
    bounds = cht_bounds(instance,axis,faces)
    cct_same_interval(bounds,bounds,overlap)
    return ids,cht_center(faces)


def cht_pair_geometry(a,b,column):
    da = cct_unit(cht_radial(a,column))
    db = cct_unit(cht_radial(b,column))
    if cct_dot(da,db) > -1.+1.e-5:
        raise ValueError('HOOP A/B inner surfaces are not opposite half-hoops')
    return da


def cht_local_normal(part,instance,column,normal):
    # One actual corresponding radial vertex supplies the cross-section basis.
    # No reconstructed global pose or guessed global cutting plane.
    for i in range(len(part.vertices)):
        local = point3(part.vertices[i])
        radius = math.sqrt(local[0]*local[0]+local[1]*local[1])
        if radius < 1.e-12: continue
        u = cct_unit(cht_radial(point3(instance.vertices[i]),column))
        axis = column['axis_direction']
        v = (axis[1]*u[2]-axis[2]*u[1],axis[2]*u[0]-axis[0]*u[2],axis[0]*u[1]-axis[1]*u[0])
        x,y = local[0]/radius,local[1]/radius
        a,b = cct_dot(normal,u),cct_dot(normal,v)
        return cct_unit((a*x-b*y,a*y+b*x,0.))
    raise ValueError('Column radial vertex correspondence missing')


def cht_mesh(part,report):
    if len(part.elements):
        part.deleteMesh()
        if part.name not in report['mesh_removed']: report['mesh_removed'].append(part.name)
    if part.name not in report['remesh_required_parts']: report['remesh_required_parts'].append(part.name)


def cht_rename(part,feature,name):
    part.features.changeKey(fromName=abaqus_name(feature.name),toName=abaqus_name(name))


def cht_axial_cut(part,station,XYPLANE,report):
    low,high = cct_box(part)
    if abs(station-low[2]) < 1.e-6 or abs(station-high[2]) < 1.e-6: return
    crossing = False
    for face in part.faces:
        b = part.faces[face.index:face.index+1].getBoundingBox()
        if b['low'][2] < station-1.e-6 and b['high'][2] > station+1.e-6: crossing = True
    if not crossing:
        # Frozen helper verifies an already existing complete circular boundary.
        cct_partition(part,station,XYPLANE,report)
        return
    name = abaqus_name('STEP05_CHT_Z_%d' % int(round(station*1.e6)))
    if item(part.features,name,True) is not None: raise ValueError('Conflicting hoop axial partition')
    cht_mesh(part,report)
    datum = part.DatumPlaneByPrincipalPlane(principalPlane=XYPLANE,offset=station)
    index = datum.id
    cht_rename(part,datum,name+'_PLANE')
    cut = part.PartitionFaceByDatumPlane(datumPlane=part.datums[index],faces=part.faces[:])
    cht_rename(part,cut,name)
    cct_partition(part,station,XYPLANE,report)
    report['partitions'].append(dict(part=part.name,station=station,name=name))


def cht_band_ids(part,interval):
    ids = []
    for face in part.faces:
        box = part.faces[face.index:face.index+1].getBoundingBox()
        if box['low'][2] >= interval[0]-1.e-6 and box['high'][2] <= interval[1]+1.e-6:
            ids.append(face.index)
    if not ids: raise ValueError('Empty column hoop band')
    return ids


def cht_half_cut(part,instance,column,normal,report):
    name = abaqus_name('STEP05_CHT_HALF_SPLIT')
    if column.get('partition_namespace'):
        name = abaqus_name(name+'_'+column['partition_namespace'])
    if item(part.features,name,True) is not None:
        report['reused'].append(name)
        return
    local = cht_local_normal(part,instance,column,normal)
    z = (column['interval'][0]+column['interval'][1])/2.
    coords = [(0.,0.,z),(0.,0.,z+1.),(-local[1],local[0],z)]
    datums = []
    cht_mesh(part,report)
    for i in range(3):
        point = part.DatumPointByCoordinate(coords=coords[i])
        index = point.id
        cht_rename(part,point,name+'_P%d' % (i+1))
        datums.append(part.datums[index])
    plane = part.DatumPlaneByThreePoints(point1=datums[0],point2=datums[1],point3=datums[2])
    index = plane.id
    cht_rename(part,plane,name+'_PLANE')
    faces = seq(part.faces,cht_band_ids(part,column['interval']))
    cut = part.PartitionFaceByDatumPlane(datumPlane=part.datums[index],faces=faces)
    cht_rename(part,cut,name)
    report['partitions'].append(dict(part=part.name,name=name,local_normal=local,global_normal=normal))


def cht_disjoint(a,b,whole):
    if set(a).intersection(set(b)):
        raise ValueError('COLUMN_HOOP_TIE column master regions overlap')
    if not a or not b or set(a).union(set(b)) != set(whole):
        raise ValueError('COLUMN_HOOP_TIE half-regions do not cover the complete column band')


def cht_halves(instance,ids,column,normal,hoop_centers):
    halves = [[],[]]
    area = [0.,0.]
    for i in ids:
        face = instance.faces[i]
        positive,negative = False,False
        for v in face.getVertices():
            s = cct_dot(cht_radial(point3(instance.vertices[v]),column),normal)
            if s > 1.e-6: positive = True
            if s < -1.e-6: negative = True
        if positive and negative: raise ValueError('Column face crosses half-hoop split plane')
        s = cct_dot(cht_radial(point3(face.getCentroid()),column),normal)
        if abs(s) <= 1.e-6: raise ValueError('Ambiguous column half representative point')
        side = 0 if s > 0 else 1
        halves[side].append(i)
        area[side] += float(face.getSize(printResults=False))
    cht_disjoint(halves[0],halves[1],ids)
    if abs(area[0]-area[1]) > max(1.e-12,(area[0]+area[1])*1.e-5):
        raise ValueError('Column regions are not two complete half-cylinders')
    paired = [None,None]
    for group in halves:
        center = cht_center(seq(instance.faces,group))
        distances = []
        for point in hoop_centers:
            d = cct_sub(center,point)
            distances.append(math.sqrt(cct_dot(d,d)))
        if abs(distances[0]-distances[1]) <= 1.e-6: raise ValueError('Ambiguous HOOP A/B nearest pairing')
        target = 0 if distances[0] < distances[1] else 1
        if paired[target] is not None: raise ValueError('HOOP A/B pairing is not one-to-one')
        paired[target] = group
    return paired


def cht_write(path,report):
    with open(path) as handle: combined = json.load(handle)
    if report.get('report_key'):
        combined.setdefault('column_hoop_groups',{})[report['report_key']] = report
    else:
        combined['column_hoop_tie'] = report
    combined['overall_status'] = 'SUCCESS' if report['status'] == 'SUCCESS' else report['status']
    combined['remesh_required'] = combined.get('remesh_required',False) or bool(report['remesh_required_parts'])
    with open(path,'w') as handle: json.dump(combined,handle,ensure_ascii=True,indent=2)


def prepare_hoop(plan,mdb,path,fingerprint,previous,XYPLANE,ON,prepared_parts=None,report_key=None):
    report = dict(rule_id='COLUMN_HOOP_TIE',fingerprint=fingerprint,status='PREFLIGHT',partitions=[],reused=[],
        mesh_removed=[],remesh_required_parts=[],semantic_mapping={},connections=[],errors=[],material_removed=False)
    if report_key: report['report_key'] = report_key
    try:
        rule = plan['column_hoop_tie']
        model = item(mdb.models,plan['model_name'])
        a = model.rootAssembly
        col = rule['column']
        p,inst = item(model.parts,col['part_name']),item(a.instances,col['instance_name'])
        col = cct_verify(p,inst,col,ON)
        users = 0
        for other in a.instances.values():
            if text(other.partName) == text(p.name): users += 1
        if users != 1: raise ValueError('Unexpected shared column Part')
        verified = previous and previous.get('fingerprint') == fingerprint and previous.get('status') == 'SUCCESS'
        in_current_batch = prepared_parts is not None and col['part_name'] in prepared_parts
        if item(model.constraints,'STEP05_TIE_COLUMN_UP_DOWN',True) is not None and not verified:
            raise ValueError('Reopen clean Step02 + Step04 model: hoop partitions must precede column Tie creation')
        for key in p.features.keys():
            if text(key).startswith('STEP05_CHT_') and not in_current_batch and not verified:
                raise ValueError('Existing hoop geometry lacks matching successful report; conflict policy FAIL')
        print('COLUMN_HOOP_TIE column = %s; hoop group = %s' % (col['instance_name'],rule['group_id']))
        axis = col['axis_direction']
        start = cct_dot(col['origin'],axis)
        column_range = [start,start+col['length_m']]
        bands,hoops = [],[]
        for half in rule['halves']:
            h = item(a.instances,half['instance_name'])
            hp = item(model.parts,half['part_name'])
            if text(h.partName) != text(half['part_name']) or not len(hp.cells): raise ValueError('Expected HOOP solid instance')
            band = cht_bounds(h,axis)
            if abs((band[1]-band[0])-half['width_m']) > 1.e-6: raise ValueError('HOOP width/axis differs from components')
            bands.append(band)
            hoops.append(h)
            print('HOOP_%s = %s; axial band = %s' % (half['label'],half['instance_name'],band))
        if abs(bands[0][0]-bands[1][0]) > 1.e-6 or abs(bands[0][1]-bands[1][1]) > 1.e-6:
            raise ValueError('HOOP A/B axial bands differ')
        overlap = [max(column_range[0],bands[0][0]),min(column_range[1],bands[0][1])]
        if overlap[1]-overlap[0] <= 1.e-6: raise ValueError('COLUMN_HOOP_TIE has no valid axial overlap')
        col['interval'] = [overlap[0]-start,overlap[1]-start]
        centers = []
        for h,half in zip(hoops,rule['halves']): centers.append(cht_inner(h,half,col,overlap)[1])
        normal = cht_pair_geometry(centers[0],centers[1],col)
        report.update(column=col['instance_name'],group_id=rule['group_id'],column_range=column_range,
            hoop_band=bands[0],actual_overlap=overlap,overlap_length=overlap[1]-overlap[0],local_overlap=col['interval'])
        print('column range = %s; hoop band = %s; actual overlap = %s; overlap length = %s' % (column_range,bands[0],overlap,overlap[1]-overlap[0]))
        print('COLUMN_DOWN local overlap = %s' % col['interval'])
        for station in col['interval']: cht_axial_cut(p,station,XYPLANE,report)
        a.regenerate()
        cht_half_cut(p,item(a.instances,col['instance_name']),col,normal,report)
        a.regenerate()
        print('column partitions = %s' % report['partitions'])
        report['status'] = 'GEOMETRY_READY'
        if prepared_parts is not None: prepared_parts.add(col['part_name'])
        if previous:
            for name in previous.get('remesh_required_parts',[]):
                if name == p.name and not len(p.elements) and name not in report['remesh_required_parts']: report['remesh_required_parts'].append(name)
        return dict(rule=rule,column=col,normal=normal,overlap=overlap,report=report,model=model,path=path)
    except Exception as exc:
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        raise
    finally:
        cht_write(path,report)


def cht_solid_region(a,name,faces,report):
    set_name = abaqus_name(name)
    surf_name = abaqus_name(set_name.replace('REGION_','SURF_'))
    old = item(a.sets,set_name,True)
    if old is None: a.Set(name=set_name,faces=faces)
    elif signature(old.faces) != signature(faces): raise ValueError('Conflicting hoop Set')
    old = item(a.surfaces,surf_name,True)
    if old is None: a.Surface(name=surf_name,side1Faces=faces)
    else:
        if signature(old.faces) != signature(faces): raise ValueError('Conflicting hoop Surface')
        for side in getattr(old,'sides',[]):
            if str(side) != 'SIDE1': raise ValueError('Conflicting hoop Surface orientation')
    report['semantic_mapping'][name] = surf_name
    return item(a.surfaces,surf_name)


def execute_hoop(context,ON,COMPUTED, tie_batch=None):
    report,model = context['report'],context['model']
    try:
        a = model.rootAssembly
        column,rule = context['column'],context['rule']
        p,inst = item(model.parts,column['part_name']),item(a.instances,column['instance_name'])
        faces,side,ids,interval = cct_faces(p,inst,column,column['axis_direction'])
        cct_same_interval(interval,interval,context['overlap'])
        hoop_ids,centers,hoops = [],[],[]
        for half in rule['halves']:
            h = item(a.instances,half['instance_name'])
            hids,center = cht_inner(h,half,column,context['overlap'])
            hoop_ids.append(hids)
            centers.append(center)
            hoops.append(h)
        groups = cht_halves(inst,ids,column,context['normal'],centers)
        cht_disjoint(groups[0],groups[1],ids)
        print('COLUMN_DOWN OUTER = %s' % side)
        report['column_shell_side'] = side
        for i in range(2):
            half = rule['halves'][i]
            master = region(a,half['column_region'],seq(inst.faces,groups[i]),side,report)
            slave = cht_solid_region(a,half['hoop_region'],seq(hoops[i].faces,hoop_ids[i]),report)
            master_surface_name = abaqus_name(half['column_region'].replace('REGION_', 'SURF_'))
            slave_surface_name = abaqus_name(half['hoop_region'].replace('REGION_', 'SURF_'))
            tie_name = abaqus_name(half['tie'])
            if tie_batch is not None:
                tie_batch.stage(model, master_surface_name=master_surface_name, slave_surface_name=slave_surface_name, master_instance=column['instance_name'], slave_instance=half['instance_name'], name=tie_name, master=master, slave=slave, positionToleranceMethod=COMPUTED, adjust=ON, tieRotations=ON, thickness=ON)
            old = item(model.constraints,tie_name,True)
            created = old is None
            if created:
                if tie_batch is None:
                    model.Tie(name=tie_name,master=master,slave=slave,positionToleranceMethod=COMPUTED,adjust=ON,tieRotations=ON,thickness=ON)
            else:
                if surface_key(a, old.master) != master_surface_name or surface_key(a, old.slave) != slave_surface_name or old.positionToleranceMethod != COMPUTED or old.adjust != ON or old.tieRotations != ON or old.thickness != ON or getattr(old,'suppressed',False) or str(getattr(old,'constraintEnforcement','SOLVER_DEFAULT')) != 'SOLVER_DEFAULT' or str(getattr(old,'constraintRatioMethod','DEFAULT')) != 'DEFAULT':
                    raise ValueError('Conflicting HOOP Tie '+tie_name)
                report['reused'].append(tie_name)
            record = dict(tie=tie_name,master=column['instance_name'],slave=half['instance_name'],master_physical_side='OUTER',slave_physical_side='INNER',hoop_inner_radius=half['inner_radius_m'],
                hoop_face_ids=hoop_ids[i],column_face_ids=groups[i],created=created and tie_batch is None)
            report['connections'].append(record)
            if half.get('component_mapping'):
                record['component_mapping'] = half['component_mapping']
            print(json.dumps(record,sort_keys=True))
        a.regenerate()
        report['status'] = 'SUCCESS' if tie_batch is None else 'PENDING_TIE_PREFLIGHT'
        return report
    except Exception as exc:
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        raise
    finally:
        print('COLUMN_HOOP_TIE Material removed = False')
        cht_write(context['path'],report)
