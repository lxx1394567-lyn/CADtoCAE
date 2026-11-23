# -*- coding: utf-8 -*-
"""Step05 only: geometry-derived upper flange tractions, no database lifecycle."""

def l5_config(c):
    path=c.get('load_config_path')
    if not path:raise ValueError('LOAD_INPUT_PENDING_USER_DATA')
    with open(str(path),'rb') as f:raw=f.read()
    if hashlib.sha256(raw).hexdigest()!=c['load_config_sha256']:raise ValueError('LOAD_CONFIG_CHANGED: regenerate PY from workbook')
    d=json.loads(raw)
    if d.get('schema')=='step07-v3-d1':return v3_validate_config(d,c)
    if d['project_id']!=c['project_id'] or d['case_id']!=c.get('expected_case_id') or d['job_id']!=c.get('expected_job_id') or d['model_id']!=c.get('expected_model_id'):raise ValueError('LOAD_PROJECT_JOB_MISMATCH')
    if d['engineering_status'] not in ('SIMPLIFIED_TIE_BENCHMARK_PENDING_REVIEW','DEMO_ONLY') or d['create_step']!='STEP07_LOADING' or d['load_direction'] not in ('SIGNED_PANEL_NORMAL','WIND_NORMAL_DEAD_SNOW_VERTICAL'):raise ValueError('UNVALIDATED_LOAD_MODE')
    if sorted([x['id'] for x in d['components']])!=['COMBINED']:raise ValueError('LOAD_COMPONENT_MISMATCH')
    if abs(sum([x['q_N_per_m'] for x in d['components']])-d['q_N_per_m'])>1.e-7:raise ValueError('LOAD_SCALAR_COMBINATION_MISMATCH')
    for x in d['components']:
        if x['q_N_per_m']==0 or math.isnan(x['q_N_per_m']) or math.isinf(x['q_N_per_m']):raise ValueError('INVALID_LOAD_VALUE')
        if x['direction']!='PANEL_INWARD_NORMAL':raise ValueError('LOAD_COMPONENT_DIRECTION_MISMATCH')
    if d['q_N_per_m']*(1 if d['case_id']=='POS' else -1)<=0:raise ValueError('CASE_SIGN_MISMATCH')
    layout_total=d['cantilever_left_m']+sum(d['support_spacing_m'])+d['cantilever_right_m']
    if abs(layout_total-d['purlin_length_m'])>1.e-8 or abs(sum(d['tributary_lengths_m'])-layout_total)>1.e-8 or d['support_count']!=len(d['support_spacing_m'])+1:raise ValueError('INVALID_TRIBUTARY_LAYOUT')
    if abs(d['total_force_N']-d['q_N_per_m']*d['tributary_length_m'])>1.e-7:raise ValueError('TRIBUTARY_FORCE_MISMATCH')
    if d['load_direction']=='WIND_NORMAL_DEAD_SNOW_VERTICAL':
        if d['case_id']!='POS' or d['structure_type']!='SP_DC' or not d.get('vector_components'):raise ValueError('VECTOR_CASE_INVALID')
        if sorted([x['id'] for x in d['vector_components']])!=['DEAD','SNOW','WIND']:raise ValueError('VECTOR_COMPONENTS_INVALID')
        if abs(sum([x['q_N_per_m'] for x in d['vector_components']])-d['q_N_per_m'])>1.e-7:raise ValueError('VECTOR_SUM_INVALID')
        for x in d['vector_components']:
            if not 0<x['q_N_per_m']<float('inf') or x['direction']!=('PANEL_INWARD_NORMAL' if x['id']=='WIND' else 'GLOBAL_DOWN'):raise ValueError('VECTOR_DIRECTION_INVALID')
    return d

def l5_resultant(d,target):
    components=d.get('vector_components',d['components'])
    vector=[0.,0.,0.]
    for x in components:
        direction=target['wind_direction'] if x['direction']=='PANEL_INWARD_NORMAL' else [0.,0.,-1.]
        for k in range(3):vector[k]+=x['q_N_per_m']*d['tributary_length_m']*direction[k]
    norm=math.sqrt(sum([v*v for v in vector]))
    if not norm>0:raise ValueError('ZERO_RESULTANT')
    return vector,norm,[v/norm for v in vector]

def l5_regions(m,c,d):
    rows=[x for x in c['assembly_summary']['instances'] if x['canonical_role']=='PURLIN_LOCAL']
    if sorted([x['instance_name'] for x in rows])!=sorted(d['applied_instances']) or not rows:raise ValueError('LOAD_PURLIN_IDENTITY_MISMATCH')
    targets=[];tol=2.e-6
    for row in rows:
        name=str(row['instance_name']);i=m.rootAssembly.instances[name];p=m.parts[i.partName]
        if row['geometry_info']['section_kind']!='C_CHANNEL' or len(p.cells) or not len(i.elements):raise ValueError('LOAD_REQUIRES_MESHED_C_CHANNEL_SHELL: '+name)
        if len(p.sectionAssignments)!=1:raise ValueError('AMBIGUOUS_PURLIN_SECTION')
        section=p.sectionAssignments[0];thickness=m.sections[section.sectionName].thickness
        if abs(section.offset)>tol or thickness<=0:raise ValueError('UNVALIDATED_SHELL_OFFSET_OR_THICKNESS')
        points=[v.pointOn[0] for v in p.vertices];lower=[min([v[k] for v in points]) for k in range(3)];upper=[max([v[k] for v in points]) for k in range(3)]
        length=upper[2]-lower[2];width=upper[0]-lower[0]
        if abs(length-d['local_model_length_m'][name])>tol or abs(length-row['geometry_info']['length'])>tol:raise ValueError('ACTUAL_LOAD_LENGTH_MISMATCH: '+name)
        if length<=0 or width<=0:raise ValueError('LOCAL_LENGTH_OR_WIDTH_INVALID')
        outward=step04_local_vector_to_global((0.,1.,0.),row['placement']);axis=step04_local_vector_to_global((0.,0.,1.),row['placement'])
        if outward[2]<0 or abs(math.degrees(math.acos(max(-1.,min(1.,outward[2]))))-d['angle_deg'])>1.e-4:raise ValueError('PANEL_NORMAL_ANGLE_MISMATCH')
        ids=[];sides=[];area=0.;global_points=[]
        for f in p.faces:
            vertices=[p.vertices[k].pointOn[0] for k in f.getVertices()]
            if not vertices or any([abs(v[1]-upper[1])>tol for v in vertices]):continue
            n=f.getNormal(point=f.pointOn[0])
            if abs(abs(n[1])-1.)>1.e-6:raise ValueError('UPPER_FLANGE_NOT_PLANAR')
            if not len(f.getElements()):raise ValueError('UNMESHED_LOAD_FACE')
            ids.append(f.index);sides.append(1 if n[1]>0 else 2);area+=f.getSize(printResults=False)
            for v in vertices:global_points.append(step04_local_point_to_global(v,row['placement']))
            actual=i.faces[f.index].getNormal(point=i.faces[f.index].pointOn[0]);predicted=step04_local_vector_to_global(n,row['placement'])
            if sum([(actual[k]-predicted[k])**2 for k in range(3)])>1.e-10:raise ValueError('ACTUAL_FLANGE_NORMAL_MISMATCH')
        if not ids or len(set(sides))!=1 or abs(area-width*length)>2.e-8:raise ValueError('INCOMPLETE_OR_PERFORATED_UPPER_FLANGE: '+name)
        overlaps=[]
        for key,obj in m.constraints.items():
            for field in ('master','slave','surface'):
                value=getattr(obj,field,None)
                if value is None:continue
                region=m3_region(m.rootAssembly,value)
                if any([f.instanceName==name and f.index in ids for f in region.faces]):overlaps.append(key+':'+field)
        if overlaps:raise ValueError('LOAD_FACE_CONNECTION_OVERLAP_REQUIRES_REVIEW: '+str(overlaps))
        targets.append(dict(instance=name,part=p.name,group=row['connection_group'],faces=ids,side=sides[0],area_m2=area,width_m=width,length_m=length,axial_direction=axis,outward_normal=outward,wind_direction=[-x for x in outward],shell_thickness_m=thickness,shell_offset_m=section.offset,bbox_global_m=[[min([v[k] for v in global_points]) for k in range(3)],[max([v[k] for v in global_points]) for k in range(3)]],connection_face_overlaps=overlaps))
    return targets

def l5_clean_snapshot(db,c,loads,surfaces):
    snap=m3_snapshot(db,c);d=snap['models'][str(c['project_id'])]
    for name in loads:
        if name in d['loads']:d['loads'].remove(name)
    for name in surfaces:
        d['assembly_surfaces'].pop(name,None)
        if name in d['connections']['surfaces']:d['connections']['surfaces'].remove(name)
    return snap


def l5_prefix(d):
    return 'STEP07_LOAD_'+str(d['job_id'])+'_'+str(d['case_id'])+'_'

def l5_exclusive_preflight(m):
    if len(m.loads):raise ValueError('RESTORE_COMMON_BASE_MODEL: existing loads '+str(list(m.loads.keys()))+'; these loads were NOT deleted. Inspect Load Manager in STEP07_LOADING (not Initial/STEP07_PRELOAD). To use another case, manually reopen the saved UNLOADED stage04 base. No POS/NEG stacking or automatic deletion.')

def l5_user_feedback(m,d,r):
    r['requested_case']=str(d['case_id'])
    r['load_display_step']='STEP07_LOADING'
    r['existing_load_names']=sorted([str(n) for n in m.loads.keys()])
    r['inspection_instructions']='Load module: select STEP07_LOADING, then open Load Manager. Loads are inactive in Initial and STEP07_PRELOAD. POS and NEG require separate unloaded base models.'
    print('STEP07-05 requested '+str(d['case_id'])+'; existing load count='+str(len(m.loads)))
    print(r['inspection_instructions'])

def l5_apply(db,c,r):
    from abaqusConstants import GENERAL,UNIFORM,OFF,ON
    m=db.models[str(c['project_id'])];a=m.rootAssembly;d=l5_config(c)
    if d.get('schema')=='step07-v3-d1':return v3_apply(db,c,r)
    l5_user_feedback(m,d,r)
    l5_exclusive_preflight(m)
    targets=l5_regions(m,c,d)
    if any([n.startswith('STEP07_LOAD_') for n in a.surfaces.keys()]):raise ValueError('PARTIAL_LOAD_SURFACE_EXISTS')
    # Recheck live mesh without changing it or creating quality Sets.
    quality={};warnings=0
    for pn,meta in m3_parts(m,c).items():
        p=m.parts[pn]
        if not len(p.elements) or p.getUnmeshedRegions() is not None:raise ValueError('UNMESHED_PART_BEFORE_LOAD: '+pn)
        q=m3_quality(p,c);quality[pn]=q
        warnings+=len(set(q['analysis'].get('warningElements',[])+q['aspect_ratio'].get('failedElements',[])+q['shape_factor'].get('failedElements',[])))
    r['mesh_status']='REVIEW_REQUIRED' if warnings else 'NOT_INDEPENDENTLY_ACCEPTED';r['mesh_warning_unique_part_elements']=warnings
    r['load_configuration']=d;r['loading_regions']=targets;r['quality_checks']=quality
    before_full=m3_snapshot(db,c);before=l5_clean_snapshot(db,c,[],[]);digests={}
    for pn,p in m.parts.items():digests[pn]=m3_mesh_digest(p)
    made=[];surfaces=[];r['created_loads']=made;r['created_load_surfaces']=surfaces;r['loads']=[];r['engineering_status']=d['engineering_status'];r['existing_loads_deleted']=False
    r['load_mutation_started']=True
    try:
        total=[0.,0.,0.]
        for target in targets:
            i=a.instances[str(target['instance'])];faces=i.faces[0:0]
            for index in target['faces']:faces=faces+i.faces[index:index+1]
            surf=l5_prefix(d)+str(target['group'])+'_UPPER'
            if surf not in a.surfaces:
                a.Surface(name=surf,**({'side1Faces':faces} if target['side']==1 else {'side2Faces':faces}));surfaces.append(surf)
            force=[0.,0.,0.];target['surface']=surf;target['loads']=[]
            for component in d['components']:
                theoretical,resultant,direction=l5_resultant(d,target)
                magnitude=resultant/target['area_m2'];name=l5_prefix(d)+str(target['group'])+'_'+str(component['id'])
                obj=m.SurfaceTraction(name=name,createStepName='STEP07_LOADING',region=a.surfaces[surf],magnitude=magnitude,traction=GENERAL,distributionType=UNIFORM,directionVector=((0.,0.,0.),tuple(direction)),follower=OFF,resultant=ON,localCsys=None)
                made.append(name);target['loads'].append(name)
                if obj.suppressed or str(obj.traction)!='GENERAL' or str(obj.distributionType)!='UNIFORM' or str(obj.follower)!='OFF' or str(obj.resultant)!='ON' or obj.localCsys is not None:raise ValueError('CREATED_TRACTION_TYPE_MISMATCH')
                state=m.steps['STEP07_LOADING'].loadStates[name]
                if str(obj.region[0])!=surf or abs(state.magnitude-magnitude)>1.e-7:raise ValueError('CREATED_TRACTION_REGION_OR_MAGNITUDE_MISMATCH')
                raw_vector=obj.directionVector
                if len(raw_vector)==3 and isinstance(raw_vector[0],(int,float)):vector=list(raw_vector)
                elif len(raw_vector)==2:vector=[raw_vector[1][k]-raw_vector[0][k] for k in range(3)]
                else:raise ValueError('UNKNOWN_ABAQUS_TRACTION_DIRECTION_FORMAT')
                if any([abs(vector[k]-direction[k])>1.e-9 for k in range(3)]):raise ValueError('CREATED_TRACTION_DIRECTION_MISMATCH')
                prior_states={}
                for prior_step in ('Initial','STEP07_PRELOAD'):
                    try:
                        prior_state=m.steps[prior_step].loadStates[name]
                        prior_status=str(prior_state.status)
                    except Exception as exc:
                        message=str(exc)
                        if prior_step=='Initial' and isinstance(exc,KeyError) and message=="'Initial'":prior_states[prior_step]='NO_INITIAL_LOAD_STATE_IN_ABAQUS_2020'
                        elif prior_step=='STEP07_PRELOAD' and 'load does not exist in the specifed step or is suppressed or inactive' in message.lower():prior_states[prior_step]='NO_ACTIVE_STATE'
                        else:raise
                    else:
                        if prior_status!='NOT_YET_ACTIVE':raise ValueError('LOAD_ACTIVE_BEFORE_LOADING')
                        prior_states[prior_step]='NOT_YET_ACTIVE'
                state=m.steps['STEP07_LOADING'].loadStates[name]
                if str(state.status)!='CREATED' or abs(state.magnitude-magnitude)>1.e-7:raise ValueError('LOAD_STEP_STATE_MISMATCH')
                member=a.surfaces[surf].faces
                if sorted([f.index for f in member])!=sorted(target['faces']) or any([f.instanceName!=target['instance'] for f in member]):raise ValueError('LOAD_REGION_MEMBERSHIP_MISMATCH')
                applied_area=sum([f.getSize(printResults=False) for f in member]);actual=[state.magnitude*applied_area*v for v in vector]
                for k in range(3):force[k]+=actual[k];total[k]+=actual[k]
                r['loads'].append(dict(name=name,instance=target['instance'],component=component['id'],step='STEP07_LOADING',type='SurfaceTraction',magnitude_N_per_m2=state.magnitude,direction_global=vector,resultant_global_N=actual,force_magnitude_N=abs(resultant),signed_force_N=component['q_N_per_m']*d['tributary_length_m'],area_m2=applied_area,region=surf,actual_state=str(state.status),prior_step_states=prior_states))
            target['resultant_global_N']=force;target['resultant_norm_N']=math.sqrt(sum([x*x for x in force]));target['scalar_component_sum_N']=d['q_N_per_m']*d['tributary_length_m'];target['tributary_length_m']=d['tributary_length_m'];target['load_scale_vs_local_demo']=d['tributary_length_m']/target['length_m']
            theoretical,expected_norm,expected_direction=l5_resultant(d,target)
            if any([abs(force[k]-theoretical[k])>1.e-7 for k in range(3)]):raise ValueError('LOAD_RESULTANT_MISMATCH')
            print(str(d['job_id'])+' '+str(d['case_id'])+' '+target['instance']+' resultant N='+str(force)+'; '+d['engineering_status'])
        if l5_clean_snapshot(db,c,made,surfaces)!=before:raise ValueError('NON_LOAD_MODEL_DATA_CHANGED')
        for pn,digest in digests.items():
            if m3_mesh_digest(m.parts[pn])!=digest:raise ValueError('MESH_CHANGED_DURING_LOAD')
        r.update(load_execution_status='SUCCESS',preservation='PASS',mesh_preservation='PASS',loads_applied=True,total_resultant_global_N=total,total_resultant_norm_N=math.sqrt(sum([x*x for x in total])),inp_eligible=False,solver_complete=False,engineering_stress_valid=False)
        r['warnings']+=d['warnings']
        print('LOADS CREATED: '+str(len(made))+' in STEP07_LOADING: '+str(made))
        print(r['inspection_instructions'])
    except Exception:
        for name in reversed(made):
            if name in m.loads:del m.loads[name]
        for name in reversed(surfaces):
            if name in a.surfaces:del a.surfaces[name]
        r['rollback']='PASS' if m3_snapshot(db,c)==before_full and all([m3_mesh_digest(m.parts[pn])==digest for pn,digest in digests.items()]) else 'INCOMPLETE_RESTORE_MANUAL_SAVE'
        raise
