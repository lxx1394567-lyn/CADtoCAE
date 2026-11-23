# -*- coding: utf-8 -*-
"""Abaqus 2020 checkpoint orchestration; never creates a new empty model."""
def p7_hash(path):
    with open(str(path),'rb') as f:return hashlib.sha256(f.read()).hexdigest()

def p7_inventory(m):
    return dict(steps=list(m.steps.keys()),ties=sorted([n for n,o in m.constraints.items() if type(o).__name__=='Tie']),
        bcs=sorted(m.boundaryConditions.keys()),parts=sorted(m.parts.keys()),instances=sorted(m.rootAssembly.instances.keys()),
        nodes=sum([len(i.nodes) for i in m.rootAssembly.instances.values()]),elements=sum([len(i.elements) for i in m.rootAssembly.instances.values()]),loads=list(m.loads.keys()))

def p7_check_input(c):
    if not os.path.isfile(str(c['input_cae'])):raise ValueError('PREVIOUS_CHECKPOINT_MISSING')
    digest=p7_hash(c['input_cae'])
    if c['predecessor_report']:
        with open(str(c['predecessor_report'])) as f:r=json.load(f)
        if r.get('status')!='SUCCESS' or r.get('stage')!=c['stage']-1 or r.get('project_id')!=c['project_id']:raise ValueError('PREVIOUS_STAGE_NOT_SUCCESS')
        if os.path.normcase(os.path.abspath(r['output_cae']))!=os.path.normcase(os.path.abspath(c['input_cae'])) or r['output_sha256']!=digest:raise ValueError('PREVIOUS_CHECKPOINT_CHANGED_OR_WRONG_VERSION')
    elif c['stage']!=1:raise ValueError('PREDECESSOR_REQUIRED')
    if c['input_sha256'] and digest!=c['input_sha256']:raise ValueError('INPUT_CHANGED')
    return digest

def p7_inp(db,m,c,report):
    from abaqusConstants import ON
    if not m.loads:raise ValueError('LOAD_STAGE_REQUIRED_BEFORE_INP')
    if not all([len(i.elements)>0 for i in m.rootAssembly.instances.values()]):raise ValueError('UNMESHED_INSTANCE')
    if os.path.exists(str(c['inp_path'])) or c['job_name'] in db.jobs:raise ValueError('JOB_OR_INP_EXISTS')
    prior=os.getcwd()
    try:
        os.chdir(str(c['output_dir']))
        j=db.Job(name=str(c['job_name']),model=str(c['project_id']))
        j.writeInput(consistencyChecking=ON)
    finally:os.chdir(prior)
    with open(str(c['inp_path'])) as f:text=f.read()
    required=['*NODE','*ELEMENT','*TIE','*BOUNDARY','*MATERIAL','*ELASTIC','*SHELL SECTION','*SOLID SECTION','*STEP','STEP07_PRELOAD','STEP07_LOADING']
    missing=[x for x in required if x not in text.upper()]
    if missing:raise ValueError('INP_MISSING_DEFINITIONS: '+str(missing))
    if len(re.findall(r'^\*Step\b',text,re.M|re.I))!=2:raise ValueError('INP_STEP_COUNT')
    report['inp']=dict(path=c['inp_path'],bytes=os.path.getsize(str(c['inp_path'])),sha256=p7_hash(c['inp_path']),checks=required,loads_applied=False,solver_verified=False)

def p7_isolate_hoops(m,c,report):
    before=t4_existing(m);report['isolated_parts']=[]
    for row in c['assembly_summary']['instances']:
        if row['canonical_role']!='HOOP':continue
        i=m.rootAssembly.instances[str(row['instance_name'])];old=i.partName;name='STEP07_ISOLATED_'+i.name
        if name in m.parts:
            if c['summary']['structure_type']!='DP' and i.partName==name:continue
            raise ValueError('ISOLATED_PART_EXISTS')
        p=m.Part(name=name,objectToCopy=m.parts[old]);i.replace(instanceOf=p,applyConstraints=True);m.rootAssembly.regenerate()
        report['isolated_parts'].append(dict(instance=i.name,source_part=old,new_part=name,reason='Different brace footprints must not partition all shared hoop instances'))
    after=t4_existing(m)
    for x in report['isolated_parts']:del after['parts'][x['new_part']]
    if before!=after:raise ValueError('HOOP_ISOLATION_CHANGED_EXISTING_REGIONS_OR_CONSTRAINTS')
    report['isolation_preservation']='PASS'

def p7_precise_tie_geometry(m,c,report):
    global t4_faces,t4_inverse
    rows={}
    for row in c['assembly_summary']['instances']:rows[str(row['instance_name'])]=row
    errors={}
    for name,row in rows.items():
        i=m.rootAssembly.instances[name];p=m.parts[i.partName];worst=0.
        for v in i.vertices:
            predicted=step04_local_point_to_global(p.vertices[v.index].pointOn[0],row['placement'])
            worst=max(worst,math.sqrt(sum([(predicted[k]-v.pointOn[0][k])**2 for k in range(3)])))
        if worst>2.e-6:raise ValueError('SUMMARY_ACTUAL_GEOMETRY_MISMATCH: '+name+' '+str(worst))
        errors[name]=worst
    face_cache={}
    def precise_faces(i):
        p=m.parts[i.partName];placement=rows[i.name]['placement'];result=[]
        cache_key=(i.name,p.name,len(p.features),len(p.faces),len(p.vertices))
        if c['assembly_summary']['structure_type']!='DP' and cache_key in face_cache:
            return [(i.faces[index],origin,normal,points) for index,origin,normal,points in face_cache[cache_key]]
        for f in i.faces:
            local=p.faces[f.index];origin=step04_local_point_to_global(local.pointOn[0],placement)
            n=step04_local_vector_to_global(local.getNormal(point=local.pointOn[0]),placement)
            points=[step04_local_point_to_global(p.vertices[k].pointOn[0],placement) for k in local.getVertices()]
            hu,hv=t4_frame(n)
            hull=t4_hull([[t4_dot(t4_sub(q,origin),axis) for axis in (hu,hv)] for q in points])
            if c['assembly_summary']['structure_type']!='DP' and (len(points)<3 or t4_area(hull)+2.e-7<local.getSize(printResults=False)):
                # Rounded hole boundaries need arc samples: endpoint-only hulls
                # underestimate planar patches after the new SP partitions.
                for ei in local.getEdges():
                    edge=p.edges[ei]
                    try:
                        edge.getCurvature(parameter=.5)
                    except Exception:continue
                    for sample in range(65):
                        point=edge.getCurvature(parameter=(sample+.5)/65.)['evaluationPoint']
                        points.append(step04_local_point_to_global(point,placement))
            if len(points)<3 or max([abs(t4_dot(t4_sub(q,origin),n)) for q in points])>2.e-6:continue
            result.append((f,origin,n,points))
        if c['assembly_summary']['structure_type']!='DP':face_cache[cache_key]=[(f.index,origin,normal,points) for f,origin,normal,points in result]
        return result
    def precise_inverse(i,point):return step04_global_point_to_local(point,rows[i.name]['placement'])
    t4_faces=precise_faces;t4_inverse=precise_inverse
    report['geometry_transform']=dict(source='Step04 full precision placement, validated against actual CAE vertices',maximum_errors_m=errors)

def p7_run(c):
    import abaqus,part,assembly,interaction,load,step,section,mesh,job,sys,time
    try: digest=p7_check_input(c)
    except Exception:
        failure=dict(stage=c['stage'],project_id=c['project_id'],status='FAILED',input_cae=c['input_cae'],output_cae=c['output_cae'],next_stage_allowed=False,error=traceback.format_exc(),solver_verified=False)
        if not os.path.exists(str(c['report_path'])) and not os.path.exists(str(c['log_path'])):
            with open(str(c['report_path']),'w') as f:json.dump(failure,f,indent=2)
            with open(str(c['log_path']),'w') as f:f.write(failure['error'])
        raise
    if os.path.exists(str(c['report_path'])):
        with open(str(c['report_path'])) as f:existing=json.load(f)
        if existing.get('status')=='SUCCESS' and existing.get('input_sha256')==digest and existing.get('runtime_sha256')==c['runtime_sha256'] and os.path.isfile(str(c['output_cae'])) and p7_hash(c['output_cae'])==existing.get('output_sha256'):
            print('ALREADY_COMPLETE: '+str(c['output_cae']));return existing
        raise ValueError('OUTPUT_REPORT_EXISTS: regenerate version')
    for key in ('output_cae','scratch_cae','verify_cae','diagnostic_cae','log_path','inp_path'):
        if os.path.exists(str(c[key])):raise ValueError('OUTPUT_EXISTS: '+str(c[key])+'; regenerate version')
    dispatched=sg_dispatch(c,digest)
    if dispatched is not None:return dispatched
    r=dict(stage=c['stage'],project_id=c['project_id'],status='RUNNING',input_cae=c['input_cae'],input_sha256=digest,output_cae=c['output_cae'],runtime_sha256=c['runtime_sha256'],next_stage_allowed=False,loads_applied=False,solver_verified=False,warnings=['Load input pending user data; load stage not implemented for this model yet; INP generation is not solver verification.'])
    old=sys.stdout;err=sys.stderr;log=open(str(c['log_path']),'w');start=time.time()
    class Tee(object):
        def write(self,text):log.write(text);log.flush();old.write(text)
        def flush(self):log.flush()
    sys.stdout=Tee();sys.stderr=sys.stdout
    try:
        r['execution_isolation']='SOURCE_ACTIVE_WORKER' if os.environ.get('STEP07_SOURCE_WORKER')=='1' else 'INDEPENDENT_WORKING_COPY'
        sg_mark(c,r,'before_snapshot_copy')
        snapshot=str(c['scratch_cae'])+'_snapshot.cae'
        if os.path.exists(snapshot):raise ValueError('SNAPSHOT_EXISTS: regenerate version')
        shutil.copyfile(str(c['input_cae']),snapshot)
        r['input_snapshot']=sg_stamp(snapshot)
        sg_mark(c,r,'after_snapshot_copy')
        shutil.copyfile(snapshot,str(c['scratch_cae']))
        if p7_hash(c['scratch_cae'])!=digest:raise ValueError('WORK_COPY_HASH_MISMATCH')
        sg_mark(c,r,'after_work_copy')
        print('OPEN EXPLICIT CHECKPOINT COPY: '+str(c['scratch_cae']))
        db=abaqus.openMdb(pathName=str(c['scratch_cae']));m=db.models[str(c['project_id'])]
        sg_mark(c,r,'after_open_work_copy')
        r['before']=p7_inventory(m)
        if c['stage']==1:
            hu,hv=t4_frame(n)
            hull=t4_hull([[t4_dot(t4_sub(q,origin),axis) for axis in (hu,hv)] for q in points])
            if c['assembly_summary']['structure_type']!='DP' and (len(points)<3 or t4_area(hull)+2.e-7<local.getSize(printResults=False)):raise ValueError('TIE_GEOMETRY_VALIDATION_CURRENTLY_DP_ONLY')
            mc_cleanup(m,r)
            p7_isolate_hoops(m,c,r)
            p7_precise_tie_geometry(m,c,r)
            t4_apply(m,c['assembly_summary'],r)
        elif c['stage']==2:
            if list(m.steps.keys())==['Initial']:s7_apply_static_step(db,c,r)
            r['step_parameters']=s7_stage1_values(m,c)
        elif c['stage']==3:b2_apply(db,c,r)
        elif c['stage']==4:m3_apply(db,c,r)
        elif c['stage']==5:raise ValueError('LOAD_INPUT_PENDING_USER_DATA: '+str(c['load_input_path']))
        elif c['stage']==6:p7_inp(db,m,c,r)
        r['after']=p7_inventory(m)
        for key in ('parts','instances'):
            if key=='parts' and c['stage']==1:
                expected=sorted(r['before'][key]+[x['new_part'] for x in r.get('isolated_parts',[])])
                if expected!=r['after'][key]:raise ValueError('UNEXPECTED_PART_CHANGE')
            elif r['before'][key]!=r['after'][key]:raise ValueError('MODEL_INVENTORY_CHANGED: '+key)
        if c['stage']>1 and r['before']['ties']!=r['after']['ties']:raise ValueError('TIES_CHANGED')
        if c['stage']>2:s7_stage1_values(m,c)
        if c['stage']>3 and r['before']['bcs']!=r['after']['bcs']:raise ValueError('BCS_CHANGED')
        if c['stage']>1 and not r['after']['ties']:raise ValueError('TIES_MISSING')
        if r['after']['loads']!=r['before']['loads']:raise ValueError('LOADS_CHANGED')
        review=c['stage']==4 and r.get('mesh_acceptance',{}).get('status')=='REVIEW_REQUIRED'
        saved=c['diagnostic_cae'] if review else c['output_cae']
        if review:r['diagnostic_cae']=saved
        db.saveAs(pathName=str(saved))
        r['output_validation']=dict(path=saved,saved=True,reopen='PENDING',eligible_for_next_stage=False)
        sg_mark(c,r,'after_save_output')
        db.close()
        sg_mark(c,r,'after_close_output')
        shutil.copyfile(str(saved),str(c['verify_cae']))
        db=abaqus.openMdb(pathName=str(c['verify_cae']));m=db.models[str(c['project_id'])]
        sg_mark(c,r,'after_open_verify_copy')
        if p7_inventory(m)!=r['after']:raise ValueError('REOPEN_INVENTORY_MISMATCH')
        if c['stage']>=2:r['step_parameters']=s7_stage1_values(m,c)
        if c['stage']==3:
            b2_verify(m,r)
            r['boundary_simplification']='USER_CONFIRMED_TIE_ROUTE: omit solid support end U2 BC; retain foundation and shell purlin end BC; original Connector route unchanged.'
        if c['stage']==4:q4_reopen(m,r)
        r['reopen']='PASS'
        if c['stage']==4:r['warnings'].append('Stage 05 awaiting user load input; Stage 06 blocked.')
        r['output_validation'].update(reopen='PASS',sha256=p7_hash(saved))
        sg_mark(c,r,'final_source_check')
        r.update(status='REVIEW_REQUIRED' if review else 'SUCCESS',output_sha256=p7_hash(saved),next_stage_allowed=c['stage']<4)
        if review:r['reviewed_artifact']=dict(path=saved,sha256=p7_hash(saved),approval='PENDING_SEPARATE_HUMAN_REVIEW_FILE')
    except Exception:
        r['status']='FAILED';r['error']=traceback.format_exc();print(r['error'])
        if c['stage']==4 and r.get('preservation')=='PASS' and all([d.get('status')=='MESHED_CHECKED' for d in r.get('parts',{}).values()]):
            db.saveAs(pathName=str(c['diagnostic_cae']));r['diagnostic_cae']=c['diagnostic_cae'];r['warnings'].append('REVIEW_ONLY: not an accepted checkpoint; next stage remains blocked.')
    finally:
        r['seconds']=time.time()-start
        with open(str(c['report_path']),'w') as f:json.dump(r,f,indent=2)
        sys.stdout=old;sys.stderr=err;log.close()
    if r['status'] not in ('SUCCESS','REVIEW_REQUIRED'):raise RuntimeError('STAGE_FAILED: '+str(c['report_path']))
    return r

