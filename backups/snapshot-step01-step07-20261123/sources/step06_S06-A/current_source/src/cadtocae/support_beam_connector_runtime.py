"""Python 2.7 family adapter; uses the unchanged Purlin execution function."""
import types


def sb_names(group):
    names=b1_names(group)
    for key,value in list(names.items()):
        if key=='connector_section':continue
        if key=='wire':names[key]='STEP06_WIRE_'+group+'_SUPPORT_BEAM_BOLT'
        elif key=='orientation':names[key]='STEP06_CSYS_'+group+'_SUPPORT_BEAM_BOLT'
        else:names[key]=value.replace('_SUPPORT','_SUPPORT_BEAM').replace('_PURLIN','_BEAM')
    return names


def sb_execute_one(plan,mdb,context):
    # Bind only the name provider in a private function namespace. The validated
    # executor's bytecode, APIs and original globals are never changed.
    original=execute_connector_b1
    code=original.__code__ if hasattr(original,'__code__') else original.func_code
    environment=dict(original.__globals__ if hasattr(original,'__globals__') else original.func_globals)
    environment['b1_names']=sb_names
    bound=types.FunctionType(code,environment)
    return bound(plan,mdb,None,context,True)


def sb_prior_snapshot(model,records):
    a=model.rootAssembly; result=[]
    for record in records:
        names=b1_names(record['connection_group']); data={}
        for key in ('rp_support','rp_purlin'):
            name=str(names[key]); rp=a.sets[name].referencePoints[0]
            coordinate=tuple(a.getCoordinates(entity=rp))
            if norm(sub(coordinate,record[key]))>1.e-6:raise ValueError('Existing Purlin RP differs from SUCCESS report')
            data[key]=(a.features[name].id,coordinate)
        for key in ('support_coupling','purlin_coupling'):
            obj=model.constraints[str(names[key])]
            values=[]
            for field in ('couplingType','u1','u2','u3','ur1','ur2','ur3','weightingMethod','suppressed'):
                values.append(str(getattr(obj,field)))
            data[key]=values
        for key in ('wire','orientation'):
            data[key]=a.features[str(names[key])].id
        data['wire_lengths']=[e.getSize(printResults=False) for e in a.getFeatureEdges(name=str(names['wire']))]
        datum=a.datums[a.features[str(names['orientation'])].id]
        data['axes']=[tuple(datum.axis1.direction),tuple(datum.axis2.direction),tuple(datum.axis3.direction)]
        result.append(data)
    # Existing assignments/orientations are never modified; preserve their bindings.
    return result


def sb_unique(regions):
    seen=[]
    for region in regions:
        key=sorted([edge.index for edge in region])
        if not key or key in seen:
            raise ValueError('BEAM_HOLE_REGION_DUPLICATE')
        for previous in seen:
            if set(key).intersection(previous):raise ValueError('BEAM_HOLE_REGION_DUPLICATE: overlap')
        seen.append(key)
    return seen


def sb_preflight(plan,mdb):
    from abaqusConstants import ON, CARTESIAN, NONE
    items=plan['connections']
    if [p['connection_group'] for p in items]!=['P01','P02','P03','P04']:raise ValueError('Expected P01-P04')
    model=resolve_step06_model(mdb,plan['project_id']);a=model.rootAssembly
    for name in ['INCLINED_BEAM_01'] + ['PURLIN_SUPPORT_'+g[1:] for g in ('P01','P02','P03','P04')]:
        if name not in a.instances.keys():
            raise ValueError('STEP06_A_REQUIRED: INSTANCE_MISSING: target model missing instance '+name)
    section=model.sections['STEP06_CONNECTOR_SECTION_PURLIN_BOLT']
    validate_bolt_preset(section)
    prior=sb_prior_snapshot(model,plan['support_purlin_connections'])
    contexts=[];beam_regions=[]
    for p in items:
        group=p['connection_group']
        if (p['source_instance']!='PURLIN_SUPPORT_'+group[1:] or p['target_instance']!='INCLINED_BEAM_01'
                or p['target_surface']!='INCLINED_BEAM_TOP_FLANGE' or p['support_hole_id']!='PS_TO_BEAM'):raise ValueError('SUPPORT_BEAM scope mismatch')
        connector_profile(p)
        names=sb_names(group)
        for key,name in names.items():
            if key=='connector_section':continue
            for repo in (a.features,a.sets,a.surfaces,model.constraints):
                if name in repo.keys():raise ValueError('EXISTING_STEP06_B_OBJECT: Existing SUPPORT_BEAM object: '+name)
        frame=b1_frame(p)
        axes=[frame['connector_local_1'],frame['connector_local_2'],frame['connector_local_3']]
        if abs(dot(axes[0],axes[1]))>1.e-10 or dot(cross(axes[0],axes[1]),axes[2])<1.-1.e-10:raise ValueError('Invalid frame')
        regions=[];evidence=[]
        for side,solid in (('source',True),('target',False)):
            instance=a.instances[str(p[side+'_instance'])]
            if instance.partName!=p[side+'_part'] or instance.dependent!=ON:raise ValueError('Instance/Part mismatch')
            center=p['rp_support'] if solid else p['rp_purlin']
            try:
                region,check=b1_resolve(instance,center,p,solid)
            except Exception as error:
                raise ValueError('STEP06_A_REQUIRED: HOLE_REGION_MISSING: '+str(error))
            regions.append(region);evidence.append(check)
        beam_regions.append(regions[1]);contexts.append((model,frame,regions,evidence))
    return contexts,sb_unique(beam_regions),prior


def execute_support_beam(plan,mdb,report_path):
    with open(report_path) as handle:report=json.load(handle)
    previous=report.get('support_purlin_connections',report.get('connections',[]))
    if (report.get('project_id')!=plan['project_id'] or
            json.dumps(previous,sort_keys=True)!=json.dumps(plan['support_purlin_connections'],sort_keys=True)):
        raise ValueError('Purlin SUCCESS report changed; regenerate SUPPORT_BEAM script')
    report['support_purlin_connections']=previous
    report.update(bolt_preset_metadata())
    report.update(support_purlin_created=4,support_beam_expected=4,support_beam_created=0,
                  support_beam_connections=[],support_beam_errors=[],support_beam_status='FAILED')
    before=None
    try:
        contexts,keys,prior=sb_preflight(plan,mdb)
        model=contexts[0][0];before=bg_state(model)
        for p,context,key in zip(plan['connections'],contexts,keys):
            r=sb_execute_one(p,mdb,context);names=sb_names(p['connection_group'])
            r.update(support_instance=p['source_instance'],beam_instance=p['target_instance'],
                support_rp=names['rp_support'],beam_rp=names['rp_purlin'],support_rp_global=p['rp_support'],
                beam_rp_global=p['rp_purlin'],beam_region=r['purlin_region'],beam_coupling=r['purlin_coupling'],
                beam_edge_geometry_keys=key,rp_distance=r['rp_distance_m'],coaxial_error=r['coaxial_error_m'],
                local_1=r['connector_local_1'],local_2=r['connector_local_2'],local_3=r['connector_local_3'])
            report['support_beam_connections'].append(r)
        after=bg_state(model)
        if (len(after['rps'])-len(before['rps'])!=8 or len(after['constraints'])-len(before['constraints'])!=8
                or after['assignments']-before['assignments']!=4 or after['orientations']-before['orientations']!=4
                or after['sections']!=before['sections']):raise ValueError('Unexpected object counts')
        if sb_prior_snapshot(model,previous)!=prior:raise ValueError('Existing Purlin connector regression')
        report.update(status='SUCCESS',support_beam_status='SUCCESS',support_beam_created=4,
            support_beam_new_rps=8,support_beam_new_couplings=8,support_beam_new_wires=4,
            support_beam_new_sections=0,step06_total_rps=16,step06_total_couplings=16,step06_total_wires=8,
            step06_total_sections=1,purlin_regression_status='PASS',beam_region_uniqueness='PASS')
    except Exception as exc:
        report['support_beam_errors'].append(str(exc));report['status']='FAILED'
        if before is not None:
            try:
                bg_rollback(model,before);report['support_beam_rollback']='PASS'
                for r in report['support_beam_connections']:r['status']='ROLLED_BACK'
            except Exception as error:
                report['support_beam_rollback']='FAILED';report['support_beam_errors'].append(str(error))
        raise
    finally:
        with open(report_path,'w') as handle:json.dump(report,handle,indent=2,ensure_ascii=True,allow_nan=False)
    return report
