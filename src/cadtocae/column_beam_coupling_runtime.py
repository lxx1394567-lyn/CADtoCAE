"""CAE 2020 geometry edges -> Surface -> two distributing Couplings."""


def cpl_distance(a,b):
    delta = cct_sub(point3(a),point3(b))
    return math.sqrt(cct_dot(delta,delta))


def cpl_station_edges(part,station):
    ids = []
    for edge in part.edges:
        points = [point3(edge)]
        for index in edge.getVertices():
            points.append(point3(part.vertices[index]))
        valid = True
        for point in points:
            if abs(point[2]-station) > 1.e-6: valid = False
        if valid and float(edge.getSize(printResults=False)) > 1.e-12:
            ids.append(int(edge.index))
    return ids


def cpl_f_edges(part,instance,rule):
    ids = cpl_station_edges(part,rule['f_station_m'])
    existing = item(getattr(part,'sets',{}),rule['source_set'],True)
    inherited = item(getattr(instance,'sets',{}),rule['source_set'],True)
    reused = existing is not None or inherited is not None
    for region in (existing,inherited):
        if region is None: continue
        stored = []
        for edge in region.edges: stored.append(int(edge.index))
        if not stored or sorted(set(stored)) != sorted(ids):
            raise ValueError('SET_BEAM_SEC_F differs from complete F section edges')
    return ids,reused


def cpl_report(path,report):
    combined = {}
    if os.path.isfile(path):
        with open(path) as handle: combined = json.load(handle)
    combined['column_beam_coupling'] = report
    combined['overall_status'] = report['status']
    combined['remesh_required'] = combined.get('remesh_required',False) or bool(report['remesh_required_parts'])
    with open(path,'w') as handle: json.dump(combined,handle,ensure_ascii=True,indent=2)


def prepare_coupling_geometry(plan,mdb,path,XYPLANE,ON):
    rule = plan['column_beam_coupling']
    report = dict(status='PREPARING',errors=[],mesh_removed=[],remesh_required_parts=[],partitions=[],
        semantic_mapping={},targets=[],couplings=[],material_removed=False)
    model = item(mdb.models,plan['model_name'])
    a = model.rootAssembly
    try:
        for member in (rule['column'],rule['beam']):
            part = item(model.parts,member['part_name'])
            inst = item(a.instances,member['instance_name'])
            if text(inst.partName) != text(member['part_name']) or inst.dependent != ON or len(part.cells):
                raise ValueError('Expected dependent shell coupling member')
            owners = 0
            for other in a.instances.values():
                if text(other.partName) == text(member['part_name']): owners += 1
            if owners != 1: raise ValueError('Shared coupling Part')
        up = rule['column']
        cct_verify(item(model.parts,up['part_name']),item(a.instances,up['instance_name']),up,ON)
        bp = item(model.parts,rule['beam']['part_name'])
        bi = item(a.instances,rule['beam']['instance_name'])
        ids,reused = cpl_f_edges(bp,bi,rule)
        if not ids:
            if len(model.constraints):
                raise ValueError('Missing F section: reopen clean Step02 + Step04 model before partitioning')
            name = abaqus_name('STEP05_CPL_BEAM_F_PARTITION')
            if item(bp.features,name,True) is not None:
                raise ValueError('Existing F partition does not contain valid section edges')
            if len(bp.elements):
                bp.deleteMesh()
                report['mesh_removed'].append(rule['beam']['part_name'])
            report['remesh_required_parts'].append(rule['beam']['part_name'])
            datum = bp.DatumPlaneByPrincipalPlane(principalPlane=XYPLANE,offset=rule['f_station_m'])
            bp.features.changeKey(fromName=abaqus_name(datum.name),toName=abaqus_name(name+'_PLANE'))
            feature = bp.PartitionFaceByDatumPlane(datumPlane=bp.datums[datum.id],faces=bp.faces[:])
            bp.features.changeKey(fromName=abaqus_name(feature.name),toName=name)
            a.regenerate()
            ids,reused = cpl_f_edges(bp,item(a.instances,rule['beam']['instance_name']),rule)
            if not ids: raise ValueError('F partition produced no section edges')
            report['partitions'].append(dict(part=rule['beam']['part_name'],station=rule['f_station_m'],name=name))
        report['reused_step04_f_set'] = reused
        return dict(rule=rule,model=model,report=report,path=path)
    except Exception as exc:
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        cpl_report(path,report)
        raise


def cpl_edge_surface(a,target,edges):
    set_name = abaqus_name(target['region'])
    surface_name = abaqus_name(target['surface'])
    old = item(a.sets,set_name,True)
    if old is not None and signature(old.edges) != signature(edges): raise ValueError('Conflicting coupling edge Set '+set_name)
    old_surface = item(a.surfaces,surface_name,True)
    if old_surface is not None:
        if signature(old_surface.edges) != signature(edges): raise ValueError('Conflicting coupling edge Surface '+surface_name)
        for side in getattr(old_surface,'sides',()):
            if str(side) != 'SIDE1': raise ValueError('Conflicting coupling edge side')
    if old is None: a.Set(name=set_name,edges=edges)
    if old_surface is None: a.Surface(name=surface_name,side1Edges=edges)
    return item(a.surfaces,surface_name)


def cpl_set_key(repo,value):
    if isinstance(value,(tuple,list)):
        name = abaqus_name(value[0])
        item(repo,name)
        return name
    matches = []
    for key in repo.keys():
        if repo[key] is value: matches.append(abaqus_name(key))
    if len(matches) != 1: raise ValueError('Ambiguous coupling control point Set')
    return matches[0]


def execute_coupling(context,ON,OFF,DISTRIBUTING,WHOLE_SURFACE,UNIFORM):
    rule,model,report = context['rule'],context['model'],context['report']
    a = model.rootAssembly
    try:
        print('RP / COUPLING VALIDATION')
        up,beam = rule['column'],rule['beam']
        cp,ci = item(model.parts,up['part_name']),item(a.instances,up['instance_name'])
        verified = cct_verify(cp,ci,up,ON)
        origin,axis = verified['origin'],verified['axis_direction']
        rp_point = (origin[0]+axis[0]*up['length_m'],origin[1]+axis[1]*up['length_m'],origin[2]+axis[2]*up['length_m'])
        if cpl_distance(rp_point,rule['rp_coordinate']) > 1.e-6: raise ValueError('RP/column top mismatch')
        top_ids = cpl_station_edges(cp,up['length_m'])
        if not top_ids: raise ValueError('No COLUMN_UP top ring geometry edges')
        circumference = 0.
        for index in top_ids:
            edge = ci.edges[index]
            if tuple(edge.getVertices()) != tuple(cp.edges[index].getVertices()): raise ValueError('Column edge correspondence changed')
            radial = cct_sub(point3(edge),rp_point)
            if abs(cct_dot(radial,axis))>1.e-6 or abs(math.sqrt(cct_dot(radial,radial))-up['radius_m'])>1.e-6:
                raise ValueError('Top ring does not agree with RP/PIPE geometry')
            circumference += float(edge.getSize(printResults=False))
        if abs(circumference-2.*math.pi*up['radius_m'])>1.e-6:
            raise ValueError('Incomplete COLUMN_UP top ring')
        bp,bi = item(model.parts,beam['part_name']),item(a.instances,beam['instance_name'])
        f_ids,reused = cpl_f_edges(bp,bi,rule)
        if not f_ids: raise ValueError('Missing F section edges after geometry regeneration')
        for index in f_ids:
            edge = bi.edges[index]
            if tuple(edge.getVertices()) != tuple(bp.edges[index].getVertices()): raise ValueError('Beam edge correspondence changed')
            points = [point3(edge)]
            for vertex_id in edge.getVertices(): points.append(point3(bi.vertices[vertex_id]))
            for point in points:
                if abs(cct_dot(cct_sub(point,rule['f_point']),beam['axis_direction']))>1.e-6:
                    raise ValueError('Beam F edge is outside global F station plane')
        selections = [seq(ci.edges,top_ids),seq(bi.edges,f_ids)]
        if set(signature(selections[0])) & set(signature(selections[1])):
            raise ValueError('Coupling targets must be distinct geometry regions')
        surfaces = []
        for target,edges in zip(rule['targets'],selections):
            surfaces.append(cpl_edge_surface(a,target,edges))
            report['targets'].append(dict(instance=target['instance_name'],region=target['region'],surface=target['surface'],target_type='EDGE',selected_ids=[]))
            for edge in edges: report['targets'][-1]['selected_ids'].append(int(edge.index))
            print(json.dumps(report['targets'][-1],sort_keys=True))
        rp_name = abaqus_name(rule['rp_name'])
        feature = item(a.features,rp_name,True)
        created = feature is None
        if feature is None:
            if item(a.sets,rp_name,True) is not None: raise ValueError('RP Set exists without semantic RP feature')
            feature = a.ReferencePoint(point=rp_point)
            a.features.changeKey(fromName=abaqus_name(feature.name),toName=rp_name)
        rp_id = feature.id
        rp = a.referencePoints[rp_id]
        if cpl_distance(a.getCoordinates(entity=rp),rp_point)>1.e-6: raise ValueError('Conflicting RP position '+rp_name)
        old = item(a.sets,rp_name,True)
        if old is None: a.Set(name=rp_name,referencePoints=(rp,))
        else:
            if len(old.referencePoints)!=1 or old.referencePoints[0] is not rp:
                raise ValueError('Conflicting RP control Set')
        control = item(a.sets,rp_name)
        report['reference_point'] = dict(semantic_name=rp_name,actual_id=rp_id,coordinate=list(rp_point),created=created)
        report['semantic_mapping'][rp_name] = rp_id
        report['reused_step04_f_set'] = reused
        print('RP_COLUMN_UP coordinate = %s; actual ID = %s' % (rp_point,rp_id))
        print('BEAM F point = %s; SET_BEAM_SEC_F reused = %s' % (rule['f_point'],reused))
        for target,surface in zip(rule['targets'],surfaces):
            name = abaqus_name(target['coupling'])
            old = item(model.constraints,name,True)
            params = dict(influenceRadius=WHOLE_SURFACE,couplingType=DISTRIBUTING,adjust=OFF,
                localCsys=None,u1=ON,u2=ON,u3=ON,ur1=ON,ur2=ON,ur3=ON,weightingMethod=UNIFORM)
            if old is not None:
                if surface_key(a,old.surface)!=target['surface'] or cpl_set_key(a.sets,old.controlPoint)!=rp_name or getattr(old,'suppressed',False):
                    raise ValueError('Conflicting Coupling regions '+name)
                for key in params:
                    if getattr(old,key)!=params[key]: raise ValueError('Conflicting Coupling parameter '+name+':'+key)
        # Check both definitions before creating either Coupling.
        for target,surface in zip(rule['targets'],surfaces):
            name = abaqus_name(target['coupling'])
            old = item(model.constraints,name,True)
            if old is None: model.Coupling(name=name,controlPoint=control,surface=surface,**params)
            report['couplings'].append(dict(name=name,type='DISTRIBUTING',control_point=rp_name,surface=target['surface'],created=old is None,dofs=['U1','U2','U3','UR1','UR2','UR3']))
            print('%s type = DISTRIBUTING; DOF = U1 U2 U3 UR1 UR2 UR3' % name)
        print('same RP = True')
        a.regenerate()
        report['same_rp'] = True
        report['status'] = 'SUCCESS'
        return report
    except Exception as exc:
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        raise
    finally:
        cpl_report(context['path'],report)
