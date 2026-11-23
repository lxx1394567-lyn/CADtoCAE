# -*- coding: utf-8 -*-
"""V3 D1 current-MDB loads. Python 2.7 compatible, no CAE lifecycle."""

def v3_validate_config(d,c):
    if (d['project_id'],d['case_id'],d['job_id'],d['model_id'])!=(c['project_id'],c['expected_case_id'],c['expected_job_id'],c['expected_model_id']):raise ValueError('V3_IDENTITY_MISMATCH')
    if d['engineering_status'] not in ('TEST_ONLY','DESIGN_INPUT_CONFIRMED_NOT_MODEL_ACCEPTED'):raise ValueError('V3_DESIGN_INPUT_PENDING: '+str(d['pending_design_parameters']))
    v=d['inputs']
    for key in ('model_binding_confirmation','units_confirmation','mass_inventory_confirmation'):
        if v.get(key)!='CONFIRMED':raise ValueError('V3_LIVE_MODEL_CONFIRMATION_REQUIRED: '+key)
    if v['unit_system']!='N-m-Pa':raise ValueError('V3_UNIT_SYSTEM_UNSUPPORTED: do not apply m/s2 in an mm model')
    if v['self_weight_mode']!='CAE_GRAVITY' or d['create_step']!='STEP07_LOADING':raise ValueError('V3_MODE_MISMATCH')
    if sorted([x['id'] for x in d['components']])!=['DEAD','SNOW','WIND']:raise ValueError('V3_COMPONENTS_INVALID')
    if any([x['q_N_per_m'] is None or not 0<x['q_N_per_m']<float('inf') for x in d['components']]):raise ValueError('V3_INVALID_LOAD_VALUE')
    L=d['tributary_length_m'];sp=d['support_spacing_m'];idx=d['support_index']
    if len(sp)!=d['support_count']-1 or not 0<=idx<d['support_count']:raise ValueError('V3_SUPPORT_MISMATCH')
    expected=d['cantilever_left_m']+sp[0]/2 if idx==0 else (d['cantilever_right_m']+sp[-1]/2 if idx==len(sp) else (sp[idx-1]+sp[idx])/2)
    if abs(L-expected)>1.e-9:raise ValueError('V3_TRIBUTARY_MISMATCH')
    if abs(d['calculation']['gravity_z_m_s2']+1.3*9.81)>1.e-9:raise ValueError('V3_GRAVITY_FACTOR_MISMATCH')
    return d

def v3_gravity_preflight(m,c,d):
    from abaqusConstants import UNIFORM
    v=d['inputs'];records=[]
    if v.get('model_mass_scope')!='MODELED_STEEL_ONLY_UNMODELED_EXCLUDED_ACKNOWLEDGED':raise ValueError('V3_MASS_SCOPE_REQUIRED')
    # Whole-model Gravity must not also include explicitly loaded PV modules.
    allowed=('COLUMN_DOWN','COLUMN_FRONT','COLUMN_REAR','COLUMN','INCLINED_BEAM','BRACE_FRONT','BRACE_REAR','PURLIN_LOCAL','PURLIN_SUPPORT','HOOP')
    for row in c['assembly_summary']['instances']:
        role=row['canonical_role']
        if role not in allowed:raise ValueError('V3_UNREVIEWED_MASS_ROLE: '+str(role))
    if len(m.rootAssembly.engineeringFeatures.inertias):raise ValueError('V3_POINT_MASS_DOUBLE_COUNT_REVIEW')
    parts=m3_parts(m,c)
    for pn in sorted(parts.keys()):
        p=m.parts[pn]
        if len(p.engineeringFeatures.inertias):raise ValueError('V3_PART_POINT_MASS_REVIEW: '+pn)
        if not len(p.sectionAssignments):raise ValueError('V3_SECTION_REQUIRED: '+pn)
        for assignment in p.sectionAssignments:
            section=m.sections[assignment.sectionName]
            if not hasattr(section,'material'):raise ValueError('V3_COMPOSITE_MASS_REVIEW: '+pn)
            material=m.materials[section.material]
            if not hasattr(material,'density'):raise ValueError('V3_ACTUAL_DENSITY_MISSING: '+section.material)
            den=material.density
            if str(den.distributionType)!='UNIFORM' or den.dependencies!=0 or str(den.temperatureDependency)!='OFF' or len(den.table)!=1 or len(den.table[0])!=1:raise ValueError('V3_DENSITY_DEFINITION_REVIEW')
            rho=float(den.table[0][0])
            # Bound catches mm-unit densities and densities inflated by gammaG.
            if not 7000<=rho<=8500:raise ValueError('V3_DENSITY_UNITS_OR_FACTOR_REVIEW: '+str(rho))
            records.append(dict(part=pn,material=section.material,density_kg_m3=rho,source='actual CAE; unchanged'))
    existing=[]
    for name,obj in m.loads.items():
        if type(obj).__name__!='Gravity':raise ValueError('RESTORE_UNLOADED_BASE: '+name)
        state=m.steps['STEP07_LOADING'].loadStates[name]
        if obj.suppressed or tuple(obj.region)!=('',0,0,0) or str(obj.distributionType)!='UNIFORM':raise ValueError('V3_EXISTING_GRAVITY_SCOPE_REVIEW')
        if str(m.steps['STEP07_PRELOAD'].loadStates[name].status)!='NOT_YET_ACTIVE':raise ValueError('V3_GRAVITY_ACTIVE_IN_PRELOAD')
        if str(state.status)!='CREATED' or abs(state.comp1)+abs(state.comp2)>1.e-10 or abs(state.comp3-d['calculation']['gravity_z_m_s2'])>1.e-9:raise ValueError('V3_EXISTING_GRAVITY_VALUE_REVIEW')
        if str(state.amplitude) not in ('UNSET',''):raise ValueError('V3_EXISTING_GRAVITY_AMPLITUDE_REVIEW')
        existing.append(name)
    if len(existing)>1:raise ValueError('V3_DUPLICATE_GRAVITY')
    return dict(materials=records,existing_gravity=existing,unit_system='N-m-Pa',unit_confirmation=v['units_confirmation'],mass_scope=v['model_mass_scope'],unmodeled_mass='EXCLUDED_AND_REQUIRES_ENGINEERING_REVIEW',density_scaled=False)

def v3_face_centroid(f):
    point=f.getCentroid()
    if len(point)==1 and hasattr(point[0],'__len__'):point=point[0]
    if len(point)!=3:raise ValueError('V3_FACE_CENTROID_UNAVAILABLE')
    return [float(x) for x in point]

def v3_cross(a,b):
    return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]

def v3_add_gravity(m,d,r,made):
    from abaqusConstants import UNIFORM
    reused=r['gravity_preflight']['existing_gravity']
    name=reused[0] if reused else l5_prefix(d)+'STEEL_GRAVITY'
    if not reused:
        m.Gravity(name=name,createStepName='STEP07_LOADING',comp1=0.,comp2=0.,comp3=d['calculation']['gravity_z_m_s2'],distributionType=UNIFORM)
        made.append(name)
    obj=m.loads[name];state=m.steps['STEP07_LOADING'].loadStates[name]
    if obj.suppressed or str(state.status)!='CREATED' or abs(state.comp3-d['calculation']['gravity_z_m_s2'])>1.e-9 or str(m.steps['STEP07_PRELOAD'].loadStates[name].status)!='NOT_YET_ACTIVE':raise ValueError('V3_GRAVITY_VERIFY_FAILED')
    r['gravity']=dict(name=name,acceleration_global_m_s2=[state.comp1,state.comp2,state.comp3],step='STEP07_LOADING',reused=bool(reused),steel_weight_resultant='NOT_IN_TRACTION_TOTAL; requires actual model mass/inertia and reaction audit',material_density_unchanged=True)

def v3_component_resultant(d,target,component):
    force=component['q_N_per_m']*d['tributary_length_m']
    direction=target['wind_direction'] if component['id']=='WIND' else [0.,0.,-1.]
    return [force*x for x in direction],force,direction

def v3_apply(db,c,r):
    from abaqusConstants import GENERAL,UNIFORM,OFF,ON
    m=db.models[str(c['project_id'])];a=m.rootAssembly;d=l5_config(c)
    l5_user_feedback(m,d,r)
    r['gravity_preflight']=v3_gravity_preflight(m,c,d)
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
    for target in targets:
        fs=[a.instances[str(target['instance'])].faces[k] for k in target['faces']]
        target['centroid_global_m']=[sum([f.getSize(printResults=False)*v3_face_centroid(f)[k] for f in fs])/target['area_m2'] for k in range(3)]
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
                theoretical,resultant,direction=v3_component_resultant(d,target,component)
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
                integrated_moment=[sum([v3_cross(v3_face_centroid(f),[state.magnitude*f.getSize(printResults=False)*v for v in vector])[k] for f in member]) for k in range(3)]
                reference_moment=v3_cross(target['centroid_global_m'],theoretical)
                if any([abs(integrated_moment[k]-reference_moment[k])>1.e-6 for k in range(3)]):raise ValueError('V3_LOCAL_TRACTION_MOMENT_MISMATCH')
                for k in range(3):force[k]+=actual[k];total[k]+=actual[k]
                r['loads'].append(dict(name=name,instance=target['instance'],component=component['id'],step='STEP07_LOADING',type='SurfaceTraction',magnitude_N_per_m2=state.magnitude,direction_global=vector,resultant_global_N=actual,force_magnitude_N=abs(resultant),signed_force_N=component['q_N_per_m']*d['tributary_length_m'],area_m2=applied_area,region=surf,actual_state=str(state.status),prior_step_states=prior_states,integrated_moment_Nm=integrated_moment,centroid_equivalent_moment_Nm=reference_moment,moment_numerical_equivalence='PASS'))
            target['resultant_global_N']=force;target['resultant_norm_N']=math.sqrt(sum([x*x for x in force]));target['scalar_component_sum_N']=sum([x['q_N_per_m'] for x in d['components']])*d['tributary_length_m'];target['tributary_length_m']=d['tributary_length_m'];target['load_scale_vs_local_demo']=d['tributary_length_m']/target['length_m']
            theoretical,expected_norm,expected_direction=l5_resultant(d,target)
            if any([abs(force[k]-theoretical[k])>1.e-7 for k in range(3)]):raise ValueError('LOAD_RESULTANT_MISMATCH')
            print(str(d['job_id'])+' '+str(d['case_id'])+' '+target['instance']+' resultant N='+str(force)+'; '+d['engineering_status'])
        v3_add_gravity(m,d,r,made)
        r['traction_moment_global_Nm']=[sum([v3_cross(t['centroid_global_m'],t['resultant_global_N'])[k] for t in targets]) for k in range(3)]
        r['moment_validation']='LOCAL_DISTRIBUTION_EQUIVALENT_AT_AREA_CENTROID; ENGINEERING_APPLICATION_POINT_NOT_INDEPENDENTLY_VERIFIED'
        if l5_clean_snapshot(db,c,made,surfaces)!=before:raise ValueError('NON_LOAD_MODEL_DATA_CHANGED')
        for pn,digest in digests.items():
            if m3_mesh_digest(m.parts[pn])!=digest:raise ValueError('MESH_CHANGED_DURING_LOAD')
        for record in r['gravity_preflight']['materials']:
            if float(m.materials[record['material']].density.table[0][0])!=record['density_kg_m3']:raise ValueError('V3_DENSITY_CHANGED')
        r.update(load_execution_status='SUCCESS',preservation='PASS',mesh_preservation='PASS',loads_applied=True,total_resultant_global_N=total,total_resultant_norm_N=math.sqrt(sum([x*x for x in total])),inp_eligible=False,solver_complete=False,engineering_stress_valid=False)
        r['warnings']+=d['warnings']
        r['mesh_acceptance']={'status':'REVIEW_REQUIRED','reason':'V3 load execution is independent of mesh/design acceptance'}
        print('LOADS CREATED: '+str(len(made))+' in STEP07_LOADING: '+str(made))
        print(r['inspection_instructions'])
    except Exception:
        for name in reversed(made):
            if name in m.loads:del m.loads[name]
        for name in reversed(surfaces):
            if name in a.surfaces:del a.surfaces[name]
        r['rollback']='PASS' if m3_snapshot(db,c)==before_full and all([m3_mesh_digest(m.parts[pn])==digest for pn,digest in digests.items()]) else 'INCOMPLETE_RESTORE_MANUAL_SAVE'
        raise
