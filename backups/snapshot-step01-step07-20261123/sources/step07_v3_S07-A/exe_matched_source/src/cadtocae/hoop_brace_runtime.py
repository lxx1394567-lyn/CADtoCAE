"""Python 2.7 HOOP A / Brace start-web connector runtime. No part edits."""


def hb_names(side):
    return dict(hoop_rp='STEP06_RP_HOOP_'+side,brace_rp='STEP06_RP_BRACE_'+side,
        hoop_region='STEP06_REGION_HOOP_'+side+'_HOLE',brace_web50_region='STEP06_REGION_BRACE_'+side+'_WEB50',
        hoop_coupling='STEP06_COUPLING_HOOP_'+side,brace_coupling='STEP06_COUPLING_BRACE_'+side,
        wire='STEP06_WIRE_HOOP_BRACE_'+side+'_BOLT',orientation='STEP06_CSYS_HOOP_BRACE_'+side+'_BOLT')


def hb_web(model, instance, placement):
    part=model.parts[str(instance.partName)]
    if len(part.cells):raise ValueError('BRACE_WEB50_REQUIRES_SHELL')
    selected=[];web_y=[]
    for face in part.faces:
        points=[point3(part.vertices[i]) for i in face.getVertices()]
        if not points or any([abs(p[0])>1.e-6 for p in points]):continue
        web_y.extend([p[1] for p in points])
        if min([p[2] for p in points])>=-1.e-6 and max([p[2] for p in points])<=.050001:
            selected.append(face)
    if not selected:raise ValueError('BRACE_START_50MM_WEB_MISSING: Step05 partition required')
    expected=(max(web_y)-min(web_y))*.05
    faces=instance.faces[0:0];seen=[];area=0.
    for face in selected:
        center=step04_local_point_to_global(point3(face.getCentroid()),placement)
        hit=instance.faces.findAt((tuple(center),),printWarning=False)
        if not hasattr(hit,'getSize'):
            if len(hit)!=1:raise ValueError('BRACE_WEB50_AMBIGUOUS')
            hit=hit[0]
        if hit.index in seen:raise ValueError('BRACE_WEB50_DUPLICATE')
        for i in hit.getVertices():
            local=step04_global_point_to_local(point3(instance.vertices[i]),placement)
            if abs(local[0])>1.e-6 or local[2]<-1.e-6 or local[2]>.050001:
                raise ValueError('BRACE_WEB50_GEOMETRY_MISMATCH')
        normal=unit(hit.getNormal(point=tuple(center)))
        expected_normal=step04_local_vector_to_global((1.,0.,0.),placement)
        if abs(dot(normal,expected_normal))<.999999:raise ValueError('BRACE_WEB50_NORMAL_MISMATCH')
        seen.append(hit.index);faces+=instance.faces[hit.index:hit.index+1]
        area+=hit.getSize(printResults=False)
    if expected<=0. or abs(area-expected)>max(1.e-10,expected*1.e-4):
        raise ValueError('BRACE_WEB50_AREA_INCOMPLETE')
    return faces,dict(semantic='BRACE_START_50MM_WEB',station_m=[0.,.05],face_keys=seen,area=area,expected_area=expected)


def hb_geometry(model,c):
    from abaqusConstants import ON
    a=model.rootAssembly
    for key,part_key in (('hoop_instance','hoop_part'),('brace_instance','brace_part')):
        if c[key] not in a.instances.keys():raise ValueError('INSTANCE_MISSING: '+c[key])
        instance=a.instances[str(c[key])]
        if instance.partName!=c[part_key] or instance.dependent!=ON:raise ValueError('INSTANCE_PART_MISMATCH')
    delta=sub(c['brace_rp_global'],c['hoop_rp_global'])
    if norm(sub(delta,(0.,-.005,0.)))>1.e-9 or abs(c['hoop_thickness']-.005)>1.e-9:
        raise ValueError('HOOP_BRACE_RP_SPACING_MISMATCH')
    if norm(cross(unit(c['bolt_axis']),(0.,1.,0.)))>1.e-6:raise ValueError('HOOP_BOLT_AXIS_NOT_GLOBAL_Y')
    frame=b1_frame(dict(rp_support=c['hoop_rp_global'],rp_purlin=c['brace_rp_global'],
                       bolt_axis=c['bolt_axis'],slot_major_axis=c['brace_axis']))
    major=frame['connector_local_2']
    wall,evidence=b1_resolve(a.instances[str(c['hoop_instance'])],c['hoop_rp_global'],
        dict(slot_major_axis=major,bolt_axis=c['bolt_axis'],width_m=.016,total_length_m=.016,thickness_m=.005),True)
    web,check=hb_web(model,a.instances[str(c['brace_instance'])],c['brace_placement'])
    return frame,wall,web,evidence,check


def hb_existing(model):
    a=model.rootAssembly
    constraints={}
    for name in model.constraints.keys():
        obj=model.constraints[name];values=[]
        for field in ('couplingType','u1','u2','u3','ur1','ur2','ur3','suppressed','controlPoint','surface'):
            values.append(str(getattr(obj,field,None)))
        constraints[name]=values
    rps={}
    for key in a.referencePoints.keys():rps[str(key)]=tuple(a.getCoordinates(entity=a.referencePoints[key]))
    wire_frames={}
    for name in a.features.keys():
        if name.startswith('STEP06_WIRE_'):
            wire_frames[name]=[e.getSize(printResults=False) for e in a.getFeatureEdges(name=name)]
        if name.startswith('STEP06_CSYS_'):
            datum=a.datums[a.features[name].id]
            wire_frames[name]=[tuple(datum.axis1.direction),tuple(datum.axis2.direction),tuple(datum.axis3.direction)]
    return dict(constraints=constraints,rps=rps,parts=b1_snapshot(model),wire_frames=wire_frames)


def hb_preserved(model,before):
    after=hb_existing(model)
    for category in ('constraints','rps','parts','wire_frames'):
        for key,value in before[category].items():
            if after[category].get(key)!=value:raise ValueError('EXISTING_MODEL_REGRESSION: '+key)
    validate_bolt_preset(model.sections['STEP06_CONNECTOR_SECTION_PURLIN_BOLT'])


def execute_hoop_brace(plan,mdb,report_path):
    from abaqusConstants import ON,OFF,KINEMATIC,WHOLE_SURFACE,UNIFORM,CARTESIAN,IMPRINT
    report=dict(project_id=plan['project_id'],status='FAILED',hoop_brace_connections=[],errors=[],warnings=[])
    report.update(bolt_preset_metadata())
    before=None
    try:
        if not plan['project_id'].startswith('SP_SC_ANG18_') or plan['brace_hoop_half']!='A':raise ValueError('HOOP_BRACE_SCOPE')
        if [c['side'] for c in plan['connections']]!=['FRONT','REAR']:raise ValueError('Expected Front/Rear')
        model=resolve_step06_model(mdb,plan['project_id']);a=model.rootAssembly
        validate_bolt_preset(model.sections['STEP06_CONNECTOR_SECTION_PURLIN_BOLT'])
        if not any([n.startswith('STEP05_') for n in model.constraints.keys()]):raise ValueError('STEP05_REQUIRED')
        for group in ('P01','P02','P03','P04'):
            for names in (b1_names(group),sb_names(group)):
                for key in ('rp_support','rp_purlin','wire','orientation'):
                    if names[key] not in a.features.keys():raise ValueError('PURLIN_CONNECTORS_REQUIRED: '+names[key])
                for key in ('support_coupling','purlin_coupling'):
                    if names[key] not in model.constraints.keys():raise ValueError('PURLIN_CONNECTORS_REQUIRED')
        section_name=str(plan['connector_section'])
        if section_name in model.sections.keys():raise ValueError('EXISTING_HOOP_BOLT_SECTION')
        prepared=[]
        for c in plan['connections']:
            expected_hole='HOOP_LEFT' if c['side']=='FRONT' else 'HOOP_RIGHT'
            if c['hoop_instance']!='HOOP_01_A' or c['hoop_hole_id']!=expected_hole:raise ValueError('HOOP_HALF_MAPPING_MISMATCH')
            names=hb_names(c['side'])
            for name in names.values():
                for repo in (a.features,a.sets,a.surfaces,model.constraints):
                    if name in repo.keys():raise ValueError('EXISTING_HOOP_BRACE_OBJECT: '+name)
            prepared.append(hb_geometry(model,c))
        old=hb_existing(model);before=bg_state(model)
        model.ConnectorSection(name=section_name,translationalType=CARTESIAN)
        apply_bolt_preset(model.sections[section_name])
        for c,context in zip(plan['connections'],prepared):
            frame,wall,web,wall_check,web_check=context;names=hb_names(c['side']);rps=[]
            for side,faces in (('hoop',wall),('brace',web)):
                name=str(names[side+'_rp']);feature=a.ReferencePoint(point=tuple(c[side+'_rp_global']))
                a.features.changeKey(fromName=str(feature.name),toName=name)
                rp=a.referencePoints[feature.id];rps.append(rp);control=a.Set(name=name,referencePoints=(rp,))
                region=str(names['hoop_region' if side=='hoop' else 'brace_web50_region'])
                surface=a.Surface(name=region,side1Faces=faces)
                model.Coupling(name=str(names[side+'_coupling']),controlPoint=control,surface=surface,
                    influenceRadius=WHOLE_SURFACE,couplingType=KINEMATIC,adjust=OFF,localCsys=None,
                    u1=ON,u2=ON,u3=ON,ur1=OFF,ur2=OFF,ur3=OFF,weightingMethod=UNIFORM)
            wire=a.WirePolyLine(points=((rps[0],rps[1]),),mergeType=IMPRINT,meshable=OFF)
            name=str(names['wire']);a.features.changeKey(fromName=str(wire.name),toName=name)
            edges=a.getFeatureEdges(name=name)
            if len(edges)!=1 or abs(edges[0].getSize(printResults=False)-.005)>1.e-6:raise ValueError('HOOP_WIRE_LENGTH_MISMATCH')
            region=a.Set(name=name,edges=edges);a.SectionAssignment(region=region,sectionName=section_name)
            cs=a.DatumCsysByThreePoints(name=str(names['orientation']),coordSysType=CARTESIAN,
                origin=tuple(c['hoop_rp_global']),point1=add(c['hoop_rp_global'],frame['connector_local_1']),
                point2=add(c['hoop_rp_global'],frame['connector_local_2']))
            a.ConnectorOrientation(region=region,localCsys1=a.datums[cs.id],orient2sameAs1=ON)
            entry=dict(c);entry.update(names);entry.update(local_1=frame['connector_local_1'],local_2=frame['connector_local_2'],
                local_3=frame['connector_local_3'],connector_section=section_name,hoop_geometry=wall_check,brace_geometry=web_check,status='SUCCESS')
            report['hoop_brace_connections'].append(entry)
        a.regenerate()
        for c in plan['connections']:hb_geometry(model,c)
        hb_preserved(model,old)
        after=bg_state(model)
        if (len(after['rps'])-len(before['rps'])!=4 or len(after['constraints'])-len(before['constraints'])!=4
            or after['assignments']-before['assignments']!=2 or after['orientations']-before['orientations']!=2
            or len(after['sections'])-len(before['sections'])!=1):raise ValueError('HOOP_OBJECT_COUNT_MISMATCH')
        report.update(status='SUCCESS',created_rps=4,created_couplings=4,created_wires=2,created_connectors=2,
                      created_sections=1,created_orientations=2,existing_model_regression='PASS')
    except Exception as error:
        report['errors'].append(str(error))
        if before is not None:
            try:
                bg_rollback(model,before);report['rollback_status']='PASS'
                for row in report['hoop_brace_connections']:row['status']='ROLLED_BACK'
            except Exception as rollback_error:
                report['rollback_status']='FAILED';report['errors'].append(str(rollback_error))
        raise
    finally:
        with open(report_path,'w') as handle:json.dump(report,handle,indent=2,ensure_ascii=True,allow_nan=False)
    return report
