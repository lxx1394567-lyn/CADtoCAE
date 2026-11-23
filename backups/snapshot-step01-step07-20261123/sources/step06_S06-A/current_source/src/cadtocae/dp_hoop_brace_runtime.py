"""DP geometry adapter and preservation checks; Python 2.7, no Part edits."""


def dp_region_name(region):
    return region.name if hasattr(region,'name') else region[0]


def validate_existing_purlin_connectors(model):
    from abaqusConstants import KINEMATIC, ON, OFF
    a=model.rootAssembly;section='STEP06_CONNECTOR_SECTION_PURLIN_BOLT'
    result=dict(status='PASS',support_purlin_count=4,support_beam_count=4,
                rp_count=16,coupling_count=16,wire_count=8,section=section,
                support_purlin_connections=[],support_beam_connections=[])
    try:
        validate_bolt_preset(model.sections[section])
        for group in ('P01','P02','P03','P04'):
            for family,names in (('support_purlin_connections',b1_names(group)),
                                 ('support_beam_connections',sb_names(group))):
                for key in ('rp_support','rp_purlin','wire','orientation'):
                    feature=a.features[str(names[key])]
                    if safe_suppressed(feature):raise ValueError('suppressed '+names[key])
                for key in ('rp_support','rp_purlin'):
                    rps=a.sets[str(names[key])].referencePoints
                    expected=a.referencePoints[a.features[str(names[key])].id]
                    if len(rps)!=1 or tuple(a.getCoordinates(entity=rps[0]))!=tuple(a.getCoordinates(entity=expected)):
                        raise ValueError('RP set mismatch: '+names[key])
                for key,rp in (('support_coupling','rp_support'),('purlin_coupling','rp_purlin')):
                    c=model.constraints[str(names[key])]
                    if (safe_suppressed(c) or c.couplingType!=KINEMATIC or
                        (c.u1,c.u2,c.u3,c.ur1,c.ur2,c.ur3)!=(ON,ON,ON,OFF,OFF,OFF)):
                        raise ValueError('KINEMATIC U123 required: '+names[key])
                    if dp_region_name(c.controlPoint)!=names[rp]:raise ValueError('Coupling RP mismatch')
                wire=str(names['wire']);edges=a.getFeatureEdges(name=wire)
                if len(edges)!=1 or [e.index for e in a.sets[wire].edges]!=[edges[0].index]:
                    raise ValueError('Wire edge mismatch: '+wire)
                assignments=[x for x in a.sectionAssignments if dp_region_name(x.region)==wire]
                if len(assignments)!=1 or assignments[0].sectionName!=section:
                    raise ValueError('Section assignment mismatch: '+wire)
                orientations=[x for x in a.connectorOrientations if dp_region_name(x.region)==wire]
                datum=a.datums[a.features[str(names['orientation'])].id]
                if len(orientations)!=1 or any([tuple(getattr(orientations[0].localCsys1,axis).direction)!=tuple(getattr(datum,axis).direction) for axis in ('axis1','axis2','axis3')]):
                    raise ValueError('Connector orientation mismatch: '+wire)
                entry=dict(names);entry.update(connection_group=group,status='SUCCESS',
                    validation_source='LIVE_CAE',connector_section=section)
                result[family].append(entry)
    except Exception as error:
        raise ValueError('PURLIN_CONNECTORS_REQUIRED: '+str(error))
    return result


def dp_hb_optional_audit(plan,report):
    import os
    live=report['purlin_prerequisite']
    families=('support_purlin_connections','support_beam_connections')
    for family in families:report[family]=live[family]
    path=plan.get('optional_audit_path',plan.get('purlin_report_path'))
    if not path or not os.path.isfile(path):
        report['purlin_report_audit_status']='MISSING'
        report['warnings'].append('PURLIN_REPORT_MISSING: validated from live CAE objects instead.')
        return
    try:
        with open(path) as handle:prior=json.load(handle)
        if prior.get('status')!='SUCCESS' or prior.get('project_id')!=plan['project_id']:
            raise ValueError('project_id/status mismatch')
        for family in families:
            entries=prior.get(family,[])
            if (sorted([r['connection_group'] for r in entries])!=['P01','P02','P03','P04'] or
                any([r.get('status')!='SUCCESS' for r in entries])):
                raise ValueError('family records mismatch: '+family)
        for family in families:report[family]=prior[family]
        report['purlin_report_audit_status']='PASS'
    except Exception as error:
        report['purlin_report_audit_status']='INVALID'
        report['warnings'].append('PURLIN_REPORT_INVALID: '+str(error)+'; validated from live CAE objects instead.')


def dp_hb_names(side):
    names=hb_names(side)
    names.update(hoop_surface='STEP06_SURF_HOOP_'+side+'_HOLE',
                 brace_surface='STEP06_SURF_BRACE_'+side+'_WEB50')
    return names


def dp_patch_distance(position,c):
    p=step04_global_point_to_local(position,c['brace_placement'])
    return math.sqrt(p[0]**2+(p[1]-max(0.,min(c['brace_web_height_m'],p[1])))**2+
                     (p[2]-max(0.,min(.05,p[2])))**2)


def dp_hb_geometry(model,c):
    from abaqusConstants import ON
    a=model.rootAssembly
    for key,pk in (('hoop_instance','hoop_part'),('brace_instance','brace_part')):
        if c[key] not in a.instances.keys():raise ValueError('INSTANCE_MISSING: '+c[key])
        i=a.instances[str(c[key])]
        if i.partName!=c[pk] or i.dependent!=ON:raise ValueError('INSTANCE_PART_MISMATCH')
    delta=sub(c['brace_rp_global'],c['hoop_rp_global']);thickness=c['hoop_thickness_m']
    if thickness<=0. or abs(norm(delta)-thickness)>1.e-6:raise ValueError('HOOP_BRACE_RP_SPACING_MISMATCH')
    frame=b1_frame(dict(rp_support=c['hoop_rp_global'],rp_purlin=c['brace_rp_global'],
                       bolt_axis=c['bolt_axis'],slot_major_axis=c['brace_axis']))
    wall,evidence=b1_resolve(a.instances[str(c['hoop_instance'])],c['hoop_rp_global'],
        dict(slot_major_axis=c['hole_major_axis'],bolt_axis=c['bolt_axis'],hole_type=c['hole_type'],
             width_m=c['width_m'],total_length_m=c['total_length_m'],thickness_m=thickness),True)
    web,check=hb_web(model,a.instances[str(c['brace_instance'])],c['brace_placement'])
    if abs(check['area']-.05*c['brace_web_height_m'])>max(1.e-10,check['area']*1.e-4):
        raise ValueError('BRACE_WEB50_AREA_INCOMPLETE')
    other=sub(c['hoop_rp_global'],delta)
    chosen_distance=dp_patch_distance(c['brace_rp_global'],c);other_distance=dp_patch_distance(other,c)
    if other_distance-chosen_distance<=1.e-6:raise ValueError('DP_BRACE_RP_SIDE_AMBIGUOUS')
    evidence['side_distance_m']=chosen_distance
    evidence['opposite_side_distance_m']=other_distance
    return frame,wall,web,evidence,check


def dp_hb_existing(model):
    a=model.rootAssembly;result=dict(step05=integrated_step05_state(model),parts=b1_snapshot(model),bolts=[])
    validate_bolt_preset(model.sections['STEP06_CONNECTOR_SECTION_PURLIN_BOLT'])
    for group in ('P01','P02','P03','P04'):
        for names in (b1_names(group),sb_names(group)):
            item={}
            for key in ('rp_support','rp_purlin'):
                name=str(names[key]);rp=a.sets[name].referencePoints[0]
                item[key]=(a.features[name].id,tuple(a.getCoordinates(entity=rp)))
            for key in ('support_coupling','purlin_coupling'):
                obj=model.constraints[str(names[key])]
                item[key]=[str(getattr(obj,k)) for k in ('couplingType','u1','u2','u3','ur1','ur2','ur3','weightingMethod')]
                item[key].append(safe_suppressed(obj))
                item[key].extend([str(obj.controlPoint),str(obj.surface)])
            item['wire']=(a.features[str(names['wire'])].id,
                          [e.getSize(printResults=False) for e in a.getFeatureEdges(name=str(names['wire']))])
            datum=a.datums[a.features[str(names['orientation'])].id]
            item['frame']=(a.features[str(names['orientation'])].id,tuple(datum.axis1.direction),
                           tuple(datum.axis2.direction),tuple(datum.axis3.direction))
            result['bolts'].append(item)
    # Only the original assignment/orientation prefixes are compared after appending.
    result['assignments']=[(str(x.region),x.sectionName) for x in a.sectionAssignments]
    result['orientations']=[str(x) for x in a.connectorOrientations]
    return result


def dp_hb_preserved(model,before):
    after=dp_hb_existing(model)
    for key in ('step05','parts','bolts'):
        if before[key]!=after[key]:raise ValueError('EXISTING_MODEL_REGRESSION: '+key)
    for key in ('assignments','orientations'):
        if before[key]!=after[key][:len(before[key])]:raise ValueError('EXISTING_MODEL_REGRESSION: '+key)
