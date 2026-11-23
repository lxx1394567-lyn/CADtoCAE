# -*- coding: utf-8 -*-
"""Manual current-MDB entry. No database lifecycle or process operations."""

def u7_ties(m,c):
    if c['summary']['structure_type']!='DP':return s8_verify(m,c)
    a=m.rootAssembly;rows=c['assembly_summary']['instances'];verified=[];used=set()
    supports=[str(x['instance_name']) for x in rows if x['canonical_role']=='PURLIN_SUPPORT']
    hoops=[str(x['instance_name']) for x in rows if x['canonical_role']=='HOOP']
    roles={}
    for row in rows:roles[str(row['instance_name'])]=row['canonical_role']
    counts={}
    for name,obj in m.constraints.items():
        if not name.startswith('STEP07_TIE_'):continue
        if type(obj).__name__!='Tie' or obj.suppressed:raise ValueError('TIE_TYPE_OR_SUPPRESSION: '+name)
        master=a.surfaces[str(obj.master[0])];slave=a.surfaces[str(obj.slave[0])]
        solids=set([f.instanceName for f in slave.faces]);shells=set([f.instanceName for f in master.faces])
        if len(solids)!=1 or len(shells)!=1:raise ValueError('TIE_EMPTY_OR_MIXED_REGION: '+name)
        solid=list(solids)[0];shell=list(shells)[0]
        expected='STEP07_TIE_'+solid+'__'+shell
        if name!=expected or str(obj.adjust)!='OFF' or str(obj.thickness)!='ON' or str(obj.tieRotations)!='ON':raise ValueError('TIE_DEFINITION_CONFLICT: '+name)
        family=(roles[solid],roles[shell]);counts[(solid,roles[shell])]=counts.get((solid,roles[shell]),0)+1
        if family not in [('PURLIN_SUPPORT','PURLIN_LOCAL'),('PURLIN_SUPPORT','INCLINED_BEAM'),('HOOP','BRACE_FRONT'),('HOOP','BRACE_REAR')]:raise ValueError('TIE_WRONG_PAIR: '+name)
        candidates=t4_candidates(m,solid,shell)
        allowed_s=set([x['solid_face'] for x in candidates]);allowed_b=set([x['shell_face'] for x in candidates])
        # Recompute physical overlap on live, partitioned geometry, not a saved receipt.
        sf=set([f.index for f in slave.faces]);bf=set([f.index for f in master.faces])
        if not sf.issubset(allowed_s) or not bf.issubset(allowed_b):raise ValueError('TIE_NONCONTACT_REGION: '+name)
        for f in slave.faces:
            key=(solid,f.index)
            if key in used:raise ValueError('DUPLICATE_TIE_SLAVE: '+name)
            used.add(key)
        sa=sum([f.getSize(printResults=False) for f in slave.faces]);ba=sum([f.getSize(printResults=False) for f in master.faces])
        if sa<=0 or sa>ba+2.e-7:raise ValueError('TIE_AREA_INVALID: '+name)
        for f in slave.faces:
            overlap=sum([x['outer_area'] for x in candidates if x['solid_face']==f.index and x['shell_face'] in bf])
            if f.getSize(printResults=False)>overlap+2.e-7:raise ValueError('TIE_SLAVE_EXCEEDS_PHYSICAL_OVERLAP: '+name)
        selected=[x for x in candidates if x['solid_face'] in sf and x['shell_face'] in bf]
        tolerance=max([max(2.e-6,abs(x['gap_m'])+2.e-6) for x in selected])
        if str(obj.positionToleranceMethod)!='SPECIFIED' or abs(obj.positionTolerance-tolerance)>2.e-6:raise ValueError('TIE_TOLERANCE_CONFLICT: '+name)
        verified.append(dict(name=name,solid=solid,shell=shell,solid_faces=sorted(sf),shell_faces=sorted(bf),solid_area=sa,shell_area=ba))
    for solid in supports:
        for role in ('PURLIN_LOCAL','INCLINED_BEAM'):
            if counts.get((solid,role),0)!=1:raise ValueError('TIE_STAGE_INCOMPLETE: '+solid+' '+role)
    for solid in hoops:
        if sum([counts.get((solid,role),0) for role in ('BRACE_FRONT','BRACE_REAR')])!=1:raise ValueError('HOOP_TIE_INCOMPLETE: '+solid)
    graph=t4_graph(m)
    if not graph['all_connected']:raise ValueError('DISCONNECTED_CONSTRAINT_GRAPH')
    return dict(pairs=verified,count=len(verified),graph=graph,scope='Live geometric region and definition checks; not solver enforcement verification')

def u7_tie_preflight(m,c):
    if c['summary']['structure_type']!='DP':return s8_preflight(m,c)
    if any([n.startswith('STEP07_TIE_') for n in m.rootAssembly.surfaces.keys()]) or any([n.startswith('STEP07_ISOLATED_') for n in m.parts.keys()]):raise ValueError('PARTIAL_TIE_STAGE_PRESENT: restore last saved pre-Tie model')
    rows=c['assembly_summary']['instances'];pairs=[]
    for row in rows:
        role=row['canonical_role'];solid=str(row['instance_name'])
        required=['PURLIN_LOCAL','INCLINED_BEAM'] if role=='PURLIN_SUPPORT' else (['BRACE_FRONT','BRACE_REAR'] if role=='HOOP' else [])
        found=[]
        for target in rows:
            if target['canonical_role'] in required:found+=t4_candidates(m,solid,str(target['instance_name']))
        if role=='PURLIN_SUPPORT' and len(found)!=2:raise ValueError('SUPPORT_CONTACT_PREFLIGHT: '+solid)
        if role=='HOOP' and len(found)!=1:raise ValueError('HOOP_CONTACT_PREFLIGHT: '+solid)
        pairs+=found
    return dict(pairs=pairs,count=len(pairs))

def u7_bc(m,c):
    return b2_validate_existing(m,c)


def u7_mesh_existing(m,c):
    result=dict(parts={},status='SUCCESS');parts=m3_parts(m,c)
    for pn,d in parts.items():
        p=m.parts[pn]
        if not len(p.elements) or p.getUnmeshedRegions() is not None:
            raise ValueError('EXISTING_PARTIAL_MESH: '+pn+'; restore the manually saved pre-mesh model. A prior failed run may have left partial mesh; no unknown mesh is deleted automatically.')
        q=m3_quality(p,c);types=sorted(set([str(e.type) for e in p.elements]))
        if any([t not in ('S4R','S3','C3D10') for t in types]):raise ValueError('UNEXPECTED_ELEMENT_TYPE: '+pn)
        if q['analysis'].get('warningElements') or q['aspect_ratio'].get('failedElements') or q.get('shape_factor',{}).get('failedElements'):result['status']='REVIEW_REQUIRED'
        result['parts'][pn]=dict(nodes=len(p.nodes),elements=len(p.elements),types=types,quality=q)
    result['regions']=m3_regions(m);result['constraint_nodes']=m3_constraint_nodes(m)
    if result['constraint_nodes']['overlaps']:raise ValueError('CONSTRAINT_NODE_OVERLAP')
    # Existing mesh provenance/partition checks cannot be reconstructed safely.
    result['status']='REVIEW_REQUIRED';result['reason']='Existing mesh rechecked, not regenerated; provenance and prior acceptance require human review.'
    return result

def u7_execute(c):
    import abaqus,part,assembly,interaction,load,step,section,mesh,job,sys,time
    db=abaqus.mdb;folder=str(c['logs_dir'])
    if not os.path.isdir(folder):os.makedirs(folder)
    stem=str(c['project_id'])+'_step07_%02d'%c['stage'];index=1
    while True:
        prefix=os.path.join(folder,stem+'_run%03d'%index)
        if not os.path.exists(prefix+'.json') and not os.path.exists(prefix+'.log'):break
        index+=1
    r=dict(stage=c['stage'],project_id=c['project_id'],execution_mode='CURRENT_MDB_IN_PLACE',status='FAILED',action='EXECUTED',next_stage_allowed=False,automatic_next_stage=False,solver_verified=False,mdb_path_before=str(db.pathName),report_path=prefix+'.json',warnings=[])
    start=time.time();old=sys.stdout;olderr=sys.stderr;handle=open(prefix+'.log','w');m=None;mutating=False;before=None;old_constraints=[];old_surfaces=[]
    class Tee(object):
        def write(self,text):handle.write(text);handle.flush();old.write(text)
        def flush(self):handle.flush()
    sys.stdout=Tee();sys.stderr=sys.stdout
    try:
        name=str(c['project_id'])
        if name not in db.models:raise ValueError('CURRENT_TARGET_MODEL_NOT_FOUND: '+name+'; no model loaded automatically')
        m=db.models[name];r['before']=p7_inventory(m);before=t4_existing(m)
        old_constraints=list(m.constraints.keys());old_surfaces=list(m.rootAssembly.surfaces.keys())
        if sorted(m.rootAssembly.instances.keys())!=sorted([str(x['instance_name']) for x in c['assembly_summary']['instances']]):raise ValueError('SUMMARY_INSTANCE_MISMATCH')
        r['hole_validation']=s8_holes(m,c)
        p7_precise_tie_geometry(m,c,r)
        if c['stage']>1:r['tie_validation']=u7_ties(m,c)
        if c['stage']>2:r['step_parameters']=s7_stage1_values(m,c)
        if c['stage']>3:b2_validate_existing(m,c,r)
        if c['stage']==1:
            complete=any([n.startswith('STEP07_TIE_') for n in m.constraints.keys()])
            if c['summary']['structure_type']!='DP':complete=all([bool(s8_pair_ties(m,p)) for p in s8_plan(m,c)])
            if complete:
                r['tie_validation']=u7_ties(m,c);r['action']='ALREADY_COMPLETE'
            else:
                if c['assembly_summary']['structure_type'] not in ('DP','SP_DC','SP_SC'):raise ValueError('UNKNOWN_STRUCTURE_TYPE')
                if any([type(s).__name__=='ConnectorSection' for s in m.sections.values()]):raise ValueError('REQUIRES_HOLE_ONLY_MODEL')
                if any([n.startswith(('STEP06_COUPLING_','STEP06_RP_','STEP06_WIRE_')) for repo in (m.constraints,m.rootAssembly.features,m.rootAssembly.sets) for n in repo.keys()]):raise ValueError('STEP06_CONNECTION_OBJECT_PRESENT')
                r['contact_preflight']=u7_tie_preflight(m,c)
                print('RISK: native mesh cleanup and Tie partitions cannot be fully rolled back. Use a manually saved model. No automatic save will occur.')
                mutating=True;mc_cleanup(m,r);p7_isolate_hoops(m,c,r);p7_precise_tie_geometry(m,c,r)
                if c['summary']['structure_type']=='DP':t4_apply(m,c['assembly_summary'],r)
                else:s8_apply(m,c,r)
                r['tie_validation']=u7_ties(m,c)
        elif c['stage']==2:
            already=list(m.steps.keys())!=['Initial']
            if not already:mutating=True;s7_apply_static_step(db,c,r)
            r['step_parameters']=s7_stage1_values(m,c)
            if c['summary']['structure_type']=='SP_DC':
                from abaqusConstants import LAST_INCREMENT
                output_name='STEP07_LOADING_OUTPUT'
                if output_name in m.fieldOutputRequests:
                    output=m.steps['STEP07_LOADING'].fieldOutputRequestStates[output_name]
                    if str(output.status)!='CREATED' or sorted(output.variables)!=['MISES','RF','U'] or output.frequency!=LAST_INCREMENT:raise ValueError('FIELD_OUTPUT_CONFLICT')
                else:
                    m.FieldOutputRequest(name=output_name,createStepName='STEP07_LOADING',variables=('MISES','U','RF'),frequency=LAST_INCREMENT)
                output=m.steps['STEP07_LOADING'].fieldOutputRequestStates[output_name]
                if str(output.status)!='CREATED' or sorted(output.variables)!=['MISES','RF','U'] or output.frequency!=LAST_INCREMENT or m.fieldOutputRequests[output_name].suppressed:raise ValueError('FIELD_OUTPUT_VERIFICATION_FAILED')
                r['field_output']=dict(name=output_name,step='STEP07_LOADING',variables=['MISES','U','RF'],frequency='LAST_INCREMENT',note='Standard may store S tensor for MISES')
            if already:r['action']='ALREADY_COMPLETE'
        elif c['stage']==3:
            if any([n.startswith('STEP07_BC_') for n in m.boundaryConditions.keys()]):b2_validate_existing(m,c,r);r['action']='ALREADY_COMPLETE'
            else:mutating=True;b2_apply(db,c,r);r['bc_validation']=u7_bc(m,c)
        elif c['stage']==4:
            if any([len(i.elements) or len(i.nodes) for i in m.rootAssembly.instances.values()]):
                r['mesh_acceptance']=u7_mesh_existing(m,c);r['action']='EXISTING_MESH_REVALIDATED'
            else:
                print('RISK: mesh/auxiliary partitions cannot be fully rolled back. On failure restore your last manually saved model.')
                mutating=True;m3_apply(db,c,r)
            r['bc_validation']=u7_bc(m,c)
        elif c['stage']==5:l5_apply(db,c,r)
        elif c['stage']==6:i6_apply(db,c,r)
        else:raise ValueError('INVALID_STAGE')
        r['after']=p7_inventory(m)
        if c['stage']>1 and t4_existing(m)['constraints']!=before['constraints'] and c['stage']!=3:raise ValueError('EXISTING_CONSTRAINTS_CHANGED')
        if c['stage']>1 and r['before']['ties']!=r['after']['ties']:raise ValueError('TIES_CHANGED')
        if c['stage']>2:s7_stage1_values(m,c)
        if c['stage']!=5 and r['before']['loads']!=r['after']['loads']:raise ValueError('LOADS_CHANGED')
        if str(abaqus.mdb.pathName)!=r['mdb_path_before']:raise ValueError('MDB_PATH_CHANGED')
        r['status']='REVIEW_REQUIRED' if r.get('mesh_acceptance',{}).get('status')=='REVIEW_REQUIRED' else 'SUCCESS'
        r['next_stage_allowed']=r['status']=='SUCCESS' and c['stage']<4
        r['save_instruction']='Inspect current model, then save manually. No CAE created by this script.'
        print(r['status']+' / '+r['action']+'; current MDB retained; inspect and save manually.')
    except Exception:
        r['error']=traceback.format_exc();print(r['error']);r['status']='FAILED'
        mutating=mutating or r.get('load_mutation_started',False)
        if c['stage']==5 and r.get('rollback')=='PASS':mutating=False
        if m is not None and mutating:
            r['model_may_be_changed']=True
            if c['stage']==1:
                r['rollback_removed']=[]
                try:
                    for n in list(m.constraints.keys()):
                        if n not in old_constraints and n.startswith('STEP07_TIE_'):del m.constraints[n];r['rollback_removed'].append(n)
                    for n in list(m.rootAssembly.surfaces.keys()):
                        if n not in old_surfaces and n.startswith('STEP07_TIE_'):del m.rootAssembly.surfaces[n];r['rollback_removed'].append(n)
                except Exception:r['rollback_error']=traceback.format_exc()
            r['recovery']='Do not save failed model. Restore your last manually saved CAE; geometry/mesh changes may remain.'
            print(r['recovery'])
        else:r['model_may_be_changed']=False
    finally:
        if m is not None:r['current_inventory']=p7_inventory(m)
        r['mdb_path_after']=str(abaqus.mdb.pathName);r['seconds']=time.time()-start
        with open(prefix+'.json','w') as f:json.dump(r,f,indent=2)
        sys.stdout=old;sys.stderr=olderr;handle.close()
    if r['status']=='FAILED':raise RuntimeError('STEP07_FAILED: '+prefix+'.json')
    return r
