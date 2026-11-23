# -*- coding: utf-8 -*-
"""Current-MDB, current-case TEST_ONLY input export. Never submits a solver."""

def i6_validate_loads(m,c):
    matched=[]
    for entry in c.get('load_case_configs',[]):
        cc=dict(c);cc.update(entry);d=l5_config(cc)
        expected=[l5_prefix(d)+str(g)+'_COMBINED' for g in d['groups']]
        if sorted(m.loads.keys())==sorted(expected):matched.append((cc,d))
    if len(matched)!=1:raise ValueError('INP_REQUIRES_EXACTLY_ONE_VERIFIED_CASE: no mixed, missing, legacy or foreign loads')
    cc,d=matched[0];targets=l5_regions(m,cc,d);actual=[]
    for t in targets:
        name=l5_prefix(d)+str(t['group'])+'_COMBINED';surf=l5_prefix(d)+str(t['group'])+'_UPPER'
        o=m.loads[name];state=m.steps['STEP07_LOADING'].loadStates[name]
        force,norm,direction=l5_resultant(d,t)
        magnitude=norm/t['area_m2']
        if type(o).__name__!='SurfaceTraction' or o.suppressed or str(o.traction)!='GENERAL' or str(o.distributionType)!='UNIFORM' or str(o.follower)!='OFF' or str(o.resultant)!='ON' or o.localCsys is not None:raise ValueError('INP_LOAD_DEFINITION_CHANGED: '+name)
        if str(state.status)!='CREATED' or str(state.amplitude) not in ('','UNSET') or abs(state.magnitude-magnitude)>max(1.e-7,magnitude*1.e-10) or str(o.region[0])!=surf:raise ValueError('INP_LOAD_STATE_CHANGED: '+name)
        if any([abs(o.directionVector[k]-direction[k])>1.e-9 for k in range(3)]):raise ValueError('INP_LOAD_DIRECTION_CHANGED')
        faces=m.rootAssembly.surfaces[surf].faces
        if sorted([f.index for f in faces])!=sorted(t['faces']) or any([f.instanceName!=t['instance'] for f in faces]):raise ValueError('INP_LOAD_SURFACE_CHANGED')
        actual.append(dict(name=name,surface=surf,magnitude=magnitude,direction=direction))
    return cc,d,actual

def i6_materials(m,c,r):
    checked={};missing=[]
    for row in c['summary']['instances']:
        instance=str(row['instance_name']);p=m.parts[m.rootAssembly.instances[instance].partName]
        for assignment in p.sectionAssignments:
            sec=m.sections[assignment.sectionName];name=getattr(sec,'material',None)
            if not name or name not in m.materials:raise ValueError('INP_SECTION_MATERIAL_UNRESOLVED: '+instance)
            material=m.materials[name];elastic=getattr(material,'elastic',None);table=getattr(elastic,'table',())
            permission=c.get('trial_materials',{}).get(name,{})
            if not table and permission.get('confirmed') is True and permission.get('engineering_status')=='DEMO_ONLY':
                young=float(permission['elastic_modulus_Pa']);poisson=float(permission['poisson_ratio'])
                if not (0<young<float('inf') and -1.<poisson<.5) or not permission.get('authorization'):raise ValueError('INVALID_TRIAL_ELASTIC_CONSTANTS')
                material.Elastic(table=((young,poisson),));elastic=material.elastic;table=elastic.table
                r.setdefault('trial_materials_added',[]).append(dict(material=name,elastic_table=[list(x) for x in table],authorization=permission['authorization'],grade_and_strength='PENDING_USER_DATA'))
                r['model_may_be_changed']=True
                r['material_recovery_note']='Explicitly authorized trial elastic data was added. No CAE saved. Review current material before manually saving; no grade or strength inferred.'
                print('AUTHORIZED DEMO_ONLY MATERIAL: '+name+' E='+str(young)+' nu='+str(poisson)+'; grade/strength pending; no CAE saved')
            item=checked.setdefault(name,dict(instances=[],elastic_table=[list(x) for x in table],status='PASS',trial_permission=permission))
            if instance not in item['instances']:item['instances'].append(instance)
            if not table:
                item['status']='MISSING_ELASTIC';missing.append(instance+' -> '+name)
            elif str(getattr(elastic,'type','ISOTROPIC'))=='ISOTROPIC' and not (0<float(table[0][0])<float('inf') and -1.<float(table[0][1])<.5):
                item['status']='INVALID_ELASTIC';missing.append(instance+' -> '+name)
    r['material_validation']=checked
    if missing:raise ValueError('INP_MATERIAL_DATA_REQUIRED: '+str(missing)+'; no assumed steel properties or automatic replacement')
    return checked


def i6_apply(db,c,r):
    from abaqusConstants import ON
    m=db.models[str(c['project_id'])];cc,d,loads=i6_validate_loads(m,c)
    r['mesh_acceptance']=u7_mesh_existing(m,c)
    i6_materials(m,c,r)
    snapshot=m3_snapshot(db,c);snapshot.pop('jobs',None);digests=dict([(n,m3_mesh_digest(p)) for n,p in m.parts.items()])
    payload=dict(snapshot=snapshot,mesh=digests,loads=loads,config_sha256=cc['load_config_sha256'])
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True).encode('utf-8')).hexdigest()
    folder=str(c['output_dir']);stem=str(d['model_id'])+'_'+str(d['job_id'])+'_'+str(d['case_id'])
    approval_path=os.path.join(folder,str(c['project_id'])+'_'+stem+'_TEST_ONLY_approval.json')
    risks=['Mesh quality/provenance not formally accepted','Tie solver enforcement including unmatched slave nodes is not proven by geometric checks','Simplified Tie benchmark, not refined bolt engineering validation']+d['warnings']
    request=dict(schema='step07-test-only-permission-1',project_id=c['project_id'],case_id=d['case_id'],job_id=d['job_id'],model_sha256=fingerprint,approved=False,reviewed_by='',reason='',scope='TEST_ONLY_INP',risks=risks)
    r.update(engineering_status='TEST_ONLY',approval_path=approval_path,model_sha256=fingerprint,load_configuration=d,verified_loads=loads)
    if not os.path.isfile(approval_path):
        with open(approval_path,'w') as f:json.dump(request,f,indent=2)
        raise ValueError('TEST_ONLY_PERMISSION_REQUIRED: review risks and set approved/reviewed_by/reason in '+approval_path)
    with open(approval_path) as f:permission=json.load(f)
    for key in ('project_id','case_id','job_id','model_sha256','scope'):
        if permission.get(key)!=request[key]:raise ValueError('TEST_ONLY_PERMISSION_MISMATCH: '+key+'; current fingerprint '+fingerprint)
    if permission.get('approved') is not True or not str(permission.get('reviewed_by','')).strip() or not str(permission.get('reason','')).strip():raise ValueError('TEST_ONLY_PERMISSION_REQUIRED: '+approval_path)
    name=stem;version=1
    while name in db.jobs or any([os.path.exists(os.path.join(folder,name+ext)) for ext in ('.inp','.odb','.lck','.dat','.log')]):
        version+=1;name=stem+'_v'+str(version)
    path=os.path.join(folder,name+'.inp');prior=os.getcwd()
    try:
        os.chdir(folder)
        obj=db.Job(name=name,model=str(c['project_id']),description='TEST_ONLY '+str(d['case_id'])+'; engineering review pending; no automatic submission')
        obj.writeInput(consistencyChecking=ON)
    finally:os.chdir(prior)
    r.update(job_name=name,inp_path=path,job_submitted=False)
    with open(path,'r') as f:text=f.read()
    for token in ('*Node','*Element','*Tie','*Boundary','*Material','*Section','STEP07_PRELOAD','STEP07_LOADING'):
        if token=='*Section':
            if '*Shell Section' not in text and '*Solid Section' not in text:raise ValueError('INP_SECTION_MISSING')
        elif token.lower() not in text.lower():raise ValueError('INP_DEFINITION_MISSING: '+token)
    lines=[x.strip() for x in text.splitlines() if ', TRVEC,' in x]
    if len(lines)!=len(loads):raise ValueError('INP_LOAD_COUNT_MISMATCH')
    for load in loads:
        found=[x for x in lines if x.split(',')[0].strip()==load['surface']]
        if len(found)!=1:raise ValueError('INP_CASE_SURFACE_MISMATCH')
        values=[float(v.strip()) for v in found[0].split(',')[2:]]
        if len(values)!=4 or abs(values[0]-load['magnitude'])>max(1.e-6,load['magnitude']*1.e-5) or any([abs(values[k+1]-load['direction'][k])>1.e-6 for k in range(3)]):raise ValueError('INP_LOAD_DATA_MISMATCH')
    after=m3_snapshot(db,c);after.pop('jobs',None)
    if after!=snapshot or any([m3_mesh_digest(m.parts[n])!=h for n,h in digests.items()]):raise ValueError('INP_MODEL_CHANGED')
    r.update(inp_verified=True,inp_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),preservation='PASS',permission=permission,formal_engineering_acceptance=False)
    r['warnings']+=risks
    with open(path+'.TEST_ONLY.json','w') as f:json.dump(dict(job=name,engineering_status='TEST_ONLY',approval=permission,config_sha256=cc['load_config_sha256']),f,indent=2)
