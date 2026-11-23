# -*- coding: utf-8 -*-
"""Stage 2 only. Appended to the existing Stage 1 runtime for shared inspection."""

def b2_dot(a,b):
    return sum([a[k]*b[k] for k in range(3)])


def b2_rotate(v,axis,degrees):
    norm=math.sqrt(b2_dot(axis,axis))
    if norm<1e-12:raise ValueError('INVALID_ROTATION_AXIS')
    u=[x/norm for x in axis];angle=math.radians(degrees)
    cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
    return [v[k]*math.cos(angle)+cross[k]*math.sin(angle)+u[k]*b2_dot(u,v)*(1-math.cos(angle)) for k in range(3)]


def b2_axis(row):
    axis=[0.,0.,1.];p=row['placement'];rotations=p.get('rotation_steps',[])
    if not rotations and p.get('rotation_angle'):
        rotations=[dict(axis_direction=p['rotation_axis'],angle_deg=p['rotation_angle'])]
    for rotation in rotations:axis=b2_rotate(axis,rotation['axis_direction'],rotation['angle_deg'])
    return axis


def b2_points(i,e):
    points=list(e.pointOn)
    for v in e.getVertices():points.append(i.vertices[v].pointOn[0])
    # Curve samples prevent selecting a curved edge merely by its endpoints.
    for t in (0.15,0.35,0.65,0.85):
        try:points.append(e.getCurvature(parameter=t)['evaluationPoint'])
        except Exception:pass
    return points


def b2_end(i,row,end,tol):
    axis=b2_axis(row);length=float(row['geometry_info']['length'])
    if length<=tol*10:raise ValueError('INVALID_LENGTH: '+i.name)
    # Actual instance vertices determine the two planes. Summary provides axis,
    # length and placement; all three must agree before any objects are created.
    points=[v.pointOn[0] for v in i.vertices]
    projections=[b2_dot(p,axis) for p in points]
    low=min(projections);high=max(projections)
    if abs(high-low-length)>tol*4:raise ValueError('SUMMARY_LENGTH_GEOMETRY_MISMATCH: '+i.name)
    if abs(low-b2_dot(row['placement']['translation'],axis))>tol*4:
        raise ValueError('SUMMARY_PLACEMENT_GEOMETRY_MISMATCH: '+i.name)
    plane=low if end=='FRONT' else high
    edges=[];sample=[]
    for edge in i.edges:
        pts=b2_points(i,edge)
        if all([abs(b2_dot(p,axis)-plane)<=tol for p in pts]):
            edges.append(edge);sample.extend(pts)
    if not edges:raise ValueError('EMPTY_END: '+i.name+' '+end)
    ids=[e.index for e in edges];faces=[]
    if len(i.cells):
        for face in i.faces:
            if face.getEdges() and all([index in ids for index in face.getEdges()]):
                if abs(abs(b2_dot(face.getNormal(),axis))-1)>1e-5:raise ValueError('NON_PLANAR_END_FACE')
                faces.append(face)
        if not faces:raise ValueError('EMPTY_SOLID_END_FACE: '+i.name)
        used=set()
        for face in faces:used.update(face.getEdges())
        if used!=set(ids):raise ValueError('INCOMPLETE_SOLID_END: '+i.name)
    data=dict(instance=i.name,role=row['canonical_role'],end=end,
              end_definition='FRONT=local extrusion z=0; REAR=local extrusion z=length',
              axis_global=axis,plane_projection_m=plane,length_m=length,
              kind='faces' if faces else 'edges',member_count=len(faces) if faces else len(edges),
              diagnostic_indices=[f.index for f in faces] if faces else ids,
              bbox_m=dict(min=[min([p[k] for p in sample]) for k in range(3)],max=[max([p[k] for p in sample]) for k in range(3)]))
    return dict(instance=i,edges=edges,faces=faces,data=data)


def b2_closure(i,edges,faces):
    edge_ids=set([e.index for e in edges]);vertices=set()
    for face in faces:edge_ids.update(face.getEdges())
    for index in edge_ids:vertices.update(i.edges[index].getVertices())
    return edge_ids,vertices


def b2_conflicts(m,target,allow_tie_master=False):
    a=m.rootAssembly;i=target['instance'];ed,ve=b2_closure(i,target['edges'],target['faces'])
    checked=[]
    repositories=[('constraint',m.constraints,('surface','master','slave','controlPoint')),
                  ('bc',m.boundaryConditions,('region',))]
    for category,repo,fields in repositories:
        for name,obj in repo.items():
            if getattr(obj,'suppressed',False):continue
            for field in fields:
                if not hasattr(obj,field):continue
                if allow_tie_master and type(obj).__name__=='Tie' and field=='master':
                    checked.append('TIE_MASTER_BC_ALLOWED:'+name);continue
                value=getattr(obj,field)
                if hasattr(value,'faces'):region=value
                else:
                    key=str(value[0])
                    if key in a.surfaces:region=a.surfaces[key]
                    elif key in a.sets:region=a.sets[key]
                    else:raise ValueError('UNRESOLVED_EXISTING_REGION: '+name+' '+field+' '+key)
                edges=[];faces=[]
                for edge in getattr(region,'edges',[]):
                    if edge.instanceName==i.name:edges.append(edge)
                for face in getattr(region,'faces',[]):
                    if face.instanceName==i.name:faces.append(face)
                other_ed,other_ve=b2_closure(i,edges,faces)
                if ed.intersection(other_ed) or ve.intersection(other_ve):
                    raise ValueError('EXISTING_CONSTRAINT_REGION_OVERLAP: '+i.name+' '+name+' '+field)
                checked.append(category+':'+name+':'+field)
    return dict(status='PASS_GEOMETRIC_REGION_DISJOINT',checked=checked,
                limitation='Geometry topology check, not a solver rank or engineering stability test; connector definitions preserved.')


def b2_plan(m,c):
    summary=c['assembly_summary'];a=m.rootAssembly;tol=c['geometry_tolerance_m']
    roles={'SP_SC':['COLUMN_DOWN'],'SP_DC':['COLUMN_DOWN'],'DP':['COLUMN_FRONT','COLUMN_REAR']}
    kind=summary['structure_type'];bases=[];ends=[]
    if kind not in roles:raise ValueError('UNSUPPORTED_STRUCTURE_TYPE')
    for row in summary['instances']:
        if str(row['instance_name']) not in a.instances:raise ValueError('SUMMARY_INSTANCE_MISSING: '+row['instance_name'])
    for role in roles[kind]:
        rows=[r for r in summary['instances'] if r['canonical_role']==role]
        if len(rows)!=1:raise ValueError('AMBIGUOUS_BASE_ROLE: '+role)
        row=rows[0];i=a.instances[str(row['instance_name'])]
        if row['geometry_info']['section_kind']!='PIPE':raise ValueError('BASE_NOT_PIPE')
        if b2_axis(row)[2]<0.99:raise ValueError('BASE_AXIS_REQUIRES_REVIEW: '+i.name)
        target=b2_end(i,row,'FRONT',tol);centers=[];radii=[];lengths=[]
        for edge in target['edges']:
            try:
                radius=edge.getRadius();cv=edge.getCurvature(parameter=.5)
            except Exception:continue
            centers.append([cv['evaluationPoint'][k]+cv['curvature'][k]*radius*radius for k in range(3)])
            radii.append(radius);lengths.append(edge.getSize(printResults=False))
        if not centers:raise ValueError('BASE_CIRCLE_NOT_FOUND')
        center=centers[0]
        for point in centers:
            if math.sqrt(sum([(point[k]-center[k])**2 for k in range(3)]))>tol:raise ValueError('BASE_NONCONCENTRIC')
        unique=[]
        for radius in radii:
            if not any([abs(radius-r)<tol for r in unique]):unique.append(radius)
        for radius in unique:
            total=0.
            for j,r in enumerate(radii):
                if abs(r-radius)<tol:total+=lengths[j]
            if abs(total-2*math.pi*radius)>tol*10:raise ValueError('INCOMPLETE_BASE_CIRCUMFERENCE')
        if not target['faces'] and len(radii)!=len(target['edges']):raise ValueError('NONCIRCULAR_SHELL_BASE_EDGE')
        suffix='' if kind!='DP' else '_'+role.split('_')[1]
        target['tag']='BASE'+suffix;target['center']=center
        target['data'].update(center_m=center,radii_m=unique,conflicts=b2_conflicts(m,target,c.get('tie_boundary_simplification',False)))
        bases.append(target)
    for group in c['groups']:
        for role,short in (('PURLIN_SUPPORT','SUPPORT'),('PURLIN_LOCAL','PURLIN')):
            if role=='PURLIN_SUPPORT' and c.get('tie_boundary_simplification',False):continue
            rows=[r for r in summary['instances'] if r['canonical_role']==role and r.get('connection_group')==group]
            if len(rows)!=1:raise ValueError('AMBIGUOUS_PURLIN_GROUP: '+group+' '+role)
            row=rows[0];i=a.instances[str(row['instance_name'])]
            for end in ('FRONT','REAR'):
                target=b2_end(i,row,end,tol);target['tag']=str(group)+'_'+short+'_'+end
                target['data'].update(group=group,conflicts=b2_conflicts(m,target,c.get('tie_boundary_simplification',False)))
                ends.append(target)
    return bases,ends


def b2_clean_inventory(db,model,created):
    result=s7_stage1_inventory(db);d=result['models'][model];conn=d['connections']
    for name in created['bcs']:
        if name in d['boundaryConditions']:d['boundaryConditions'].remove(name)
    for name in created['constraints']:conn['constraints'].pop(name,None)
    for kind,key in (('sets','assembly_sets'),('surfaces','assembly_surfaces')):
        for name in created[kind]:
            d[key].pop(name,None)
            if name in conn[kind]:conn[kind].remove(name)
    d['assembly_rps']=[v for v in d['assembly_rps'] if v[0] not in created['rp_ids']]
    conn['rps']=[v for v in conn['rps'] if v not in created['rp_ids']]
    return result


def b2_entities(a,target):
    i=a.instances[str(target['data']['instance'])]
    repo=i.faces if target['data']['kind']=='faces' else i.edges
    result=repo[0:0]
    for index in target['data']['diagnostic_indices']:result=result+repo[index:index+1]
    return result


def b2_verify(m,report):
    values={}
    for data in report['regions']:
        name=str(data['bc']);bc=m.boundaryConditions[name];states={}
        if bc.suppressed or bc.localCsys is not None:raise ValueError('BC_FRAME_OR_SUPPRESSION_MISMATCH')
        a=m.rootAssembly
        if data.get('type')=='ENCASTRE':
            region=a.surfaces[str(data['surface'])];coupling=m.constraints[str(data['coupling'])]
            if str(coupling.couplingType)!='KINEMATIC':raise ValueError('BASE_COUPLING_TYPE_MISMATCH')
            if str(coupling.controlPoint[0])!=data['rp'] or str(coupling.surface[0])!=data['surface']:raise ValueError('BASE_COUPLING_REGION_MISMATCH')
            for dof in ('u1','u2','u3','ur1','ur2','ur3'):
                if str(getattr(coupling,dof))!='ON':raise ValueError('BASE_COUPLING_DOF_MISMATCH')
            rps=a.sets[str(data['rp'])].referencePoints
            if len(rps)!=1:raise ValueError('BASE_RP_COUNT_MISMATCH')
            xyz=a.getCoordinates(rps[0]);data['verified_rp_coordinates_m']=xyz
            if any([abs(xyz[k]-data['center_m'][k])>1e-8 for k in range(3)]):raise ValueError('BASE_RP_COORDINATES_MISMATCH')
            expected_region=data['rp']
        else:region=a.sets[str(data['set'])];expected_region=data['set']
        if str(bc.region[0])!=expected_region:raise ValueError('BC_REGION_MISMATCH')
        actual_members=getattr(region,str(data['kind']))
        actual_ids=[obj.index for obj in actual_members]
        if sorted(actual_ids)!=sorted(data['diagnostic_indices']):raise ValueError('SAVED_REGION_MEMBERSHIP_MISMATCH')
        if any([obj.instanceName!=data['instance'] for obj in actual_members]):raise ValueError('SAVED_REGION_INSTANCE_MISMATCH')
        data['saved_region_membership']='PASS'
        for step_name in ('Initial','STEP07_PRELOAD','STEP07_LOADING'):
            state=m.steps[step_name].boundaryConditionStates[name]
            status=str(state.status)
            if status!=('CREATED' if step_name=='Initial' else 'PROPAGATED'):raise ValueError('BC_PROPAGATION_FAILED')
            actual=dict(status=status)
            if data.get('type')=='ENCASTRE':
                actual['type']=str(state.typeName)
                if actual['type']!='ENCASTRE':raise ValueError('BASE_BC_NOT_ENCASTRE')
            else:
                for dof in ('u1','u2','u3','ur1','ur2','ur3'):
                    flag=str(getattr(state,dof+'State'));value=getattr(state,dof)
                    fixed=dof.upper() in data['actual_dofs']
                    if fixed and (flag not in ('SET','UNCHANGED') or value!=0.):raise ValueError('BC_COMPONENT_MISMATCH: '+name+' '+dof)
                    if not fixed and flag!='UNSET':raise ValueError('UNEXPECTED_FIXED_DOF: '+name+' '+dof)
                    actual[dof]=dict(state=flag,value=value)
            states[step_name]=actual
        values[name]=states
    report['actual_bc_states']=values


def b2_validate_existing(m,c,report=None):
    # Exclude only our own expected BCs from the conflict preflight, then verify
    # their actual regions, coordinates, DOFs and propagated states on m.
    class View(object):
        def __init__(self,model):
            self.model=model;self.constraints={};self.boundaryConditions={}
            for k,v in model.constraints.items():
                if not k.startswith('STEP07_COUPLING_BASE'):self.constraints[k]=v
            for k,v in model.boundaryConditions.items():
                if not k.startswith('STEP07_BC_'):self.boundaryConditions[k]=v
        def __getattr__(self,key):return getattr(self.model,key)
    bases,ends=b2_plan(View(m),c);r=dict(regions=[])
    for target in bases:
        tag=target['tag'];d=target['data'];d.update(rp='STEP07_RP_'+tag,surface='STEP07_SURF_'+tag,coupling='STEP07_COUPLING_'+tag,bc='STEP07_BC_'+tag,type='ENCASTRE',actual_dofs=['U1','U2','U3','UR1','UR2','UR3']);r['regions'].append(d)
    for target in ends:
        tag=target['tag'];d=target['data'];d.update(set='STEP07_SET_'+tag,bc='STEP07_BC_'+tag,actual_dofs=['U2'] if target['faces'] else ['U2','UR1','UR2','UR3']);r['regions'].append(d)
    expected=set([d['bc'] for d in r['regions']]);actual=set([n for n in m.boundaryConditions.keys() if n.startswith('STEP07_BC_')])
    r.update(expected_bc_names=sorted(expected),actual_bc_names=sorted([str(n) for n in m.boundaryConditions.keys()]),
             missing_bc_names=sorted(expected-actual),unexpected_bc_names=sorted(actual-expected),
             required_dofs=dict([(str(d['bc']),d['actual_dofs']) for d in r['regions']]),
             constrained_regions=r['regions'],validation_status='FAILED')
    if report is not None:report['bc_validation']=r
    if actual!=expected:raise ValueError('BC_STAGE_INCOMPLETE_OR_EXTRA: '+str(sorted(actual.symmetric_difference(expected))))
    b2_verify(m,r)
    r['validation_status']='SUCCESS'
    return r

def b2_rollback(db,c,created,before):
    m=db.models[str(c['project_id'])];a=m.rootAssembly
    for key,repo in (('bcs',m.boundaryConditions),('constraints',m.constraints),('surfaces',a.surfaces),('sets',a.sets),('rp_features',a.features)):
        for item in reversed(created[key]):
            if item in repo:del repo[item]
    if s7_stage1_inventory(db)!=before:raise ValueError('ROLLBACK_INCOMPLETE_USE_BACKUP')


def b2_apply(db,c,report):
    from abaqusConstants import ON,OFF,UNSET,WHOLE_SURFACE,KINEMATIC
    name=str(c['project_id'])
    if name not in db.models:raise ValueError('CURRENT_TARGET_MODEL_NOT_FOUND: '+name)
    m=db.models[name];a=m.rootAssembly
    expected=s7_stage1_values(m,c)
    for repo in (a.sets,a.surfaces,m.boundaryConditions,m.constraints,a.features):
        if any([str(k).startswith(('STEP07_SET_','STEP07_RP_BASE','STEP07_BC_','STEP07_COUPLING_','STEP07_SURF_')) for k in repo.keys()]):
            raise ValueError('STAGE2_OBJECT_CONFLICT; no automatic deletion')
    bases,ends=b2_plan(m,c)
    report['regions']=[t['data'] for t in bases+ends]
    before=s7_stage1_inventory(db)
    created=dict(bcs=[],constraints=[],sets=[],surfaces=[],rp_features=[],rp_ids=[])
    report['created']=created
    try:
        for target in bases:
            tag=target['tag'];data=target['data'];rp=a.ReferencePoint(point=tuple(target['center']))
            created['rp_ids'].append(rp.id)
            old_name=None
            for feature_name,feature in a.features.items():
                if feature.id==rp.id:old_name=feature_name;break
            if old_name is None:raise ValueError('RP_FEATURE_NOT_FOUND')
            created['rp_features'].append(old_name)
            rp_name='STEP07_RP_'+tag;a.features.changeKey(fromName=old_name,toName=rp_name);created['rp_features'][-1]=rp_name
            a.Set(name=rp_name,referencePoints=(a.referencePoints[rp.id],));created['sets'].append(rp_name)
            surf='STEP07_SURF_'+tag
            entities=b2_entities(a,target)
            if target['faces']:a.Surface(name=surf,side1Faces=entities)
            else:a.Surface(name=surf,side1Edges=entities)
            created['surfaces'].append(surf)
            coupling='STEP07_COUPLING_'+tag
            m.Coupling(name=coupling,controlPoint=a.sets[rp_name],surface=a.surfaces[surf],influenceRadius=WHOLE_SURFACE,
                       couplingType=KINEMATIC,u1=ON,u2=ON,u3=ON,ur1=ON,ur2=ON,ur3=ON)
            created['constraints'].append(coupling)
            bc='STEP07_BC_'+tag;m.EncastreBC(name=bc,createStepName='Initial',region=a.sets[rp_name]);created['bcs'].append(bc)
            data.update(rp=rp_name,surface=surf,coupling=coupling,bc=bc,type='ENCASTRE',actual_dofs=['U1','U2','U3','UR1','UR2','UR3'])
        for target in ends:
            data=target['data'];tag=target['tag'];set_name='STEP07_SET_'+tag
            entities=b2_entities(a,target)
            if target['faces']:a.Set(name=set_name,faces=entities)
            else:a.Set(name=set_name,edges=entities)
            created['sets'].append(set_name);bc='STEP07_BC_'+tag
            solid=bool(target['faces']);rotation=UNSET if solid else 0.
            m.DisplacementBC(name=bc,createStepName='Initial',region=a.sets[set_name],u1=UNSET,u2=0.,u3=UNSET,
                             ur1=rotation,ur2=rotation,ur3=rotation,localCsys=None)
            created['bcs'].append(bc)
            data.update(set=set_name,bc=bc,actual_dofs=['U2'] if solid else ['U2','UR1','UR2','UR3'],
                        u1='UNSET',u3='UNSET',csys='GLOBAL',rotation_status='PENDING_ENGINEERING_CONFIRMATION' if solid else 'APPLIED')
        if b2_clean_inventory(db,name,created)!=before:raise ValueError('ORIGINAL_MODEL_CHANGED')
        if s7_stage1_values(m,c)!=expected:raise ValueError('STEP_PARAMETERS_CHANGED')
        b2_verify(m,report)
        b2_validate_existing(m,c,report)
        report['preservation']='PASS';report['step_parameters']=expected
        return before
    except Exception:
        try:b2_rollback(db,c,created,before);report['rollback']='PASS'
        except Exception:report['rollback']='FAILED_USE_BACKUP';report['rollback_error']=traceback.format_exc()
        raise


def b2_run(c):
    import abaqus,part,assembly,interaction,load,step,mesh,job,section,sys
    report=dict(stage=2,project_id=c['project_id'],execution_mode=c['execution_mode'],status='RUNNING',
                engineering_verified=False,human_review='PENDING',automatic_next_stage=False,
                support_rotation='PENDING_ENGINEERING_CONFIRMATION',input_cae=c['input_cae'],output_cae=c['output_cae'])
    for key in ('output_cae','report_path','log_path','scratch_cae','backup_cae','disk_backup_cae'):
        if os.path.exists(str(c[key])):raise ValueError('OUTPUT_EXISTS: '+str(c[key])+'; regenerate script')
    output=str(c['output_cae']);source=str(c['input_cae']);db=None;before=None;old_dir=os.getcwd()
    log=open(str(c['log_path']),'w');old_out=sys.stdout;old_err=sys.stderr
    class Tee(object):
        def write(self,text):log.write(text);log.flush();old_out.write(text)
        def flush(self):log.flush()
    sys.stdout=Tee();sys.stderr=sys.stdout
    try:
        os.chdir(str(c['output_dir']));print('STEP07-02 OUTPUT: '+output)
        if c['execution_mode']=='CURRENT_SESSION_DEBUG':
            db=abaqus.mdb
            if os.path.normcase(os.path.abspath(str(db.pathName)))==os.path.normcase(os.path.abspath(source)):
                raise ValueError('ACCEPTED_CAE_IS_CURRENT_MDB: open the supplied session_input working copy before Run Script; native saveAs can alter the previously opened file')
        elif c['execution_mode']=='INDEPENDENT_CAE':
            from abaqus import openMdb
            with open(source,'rb') as f:original=hashlib.sha256(f.read()).hexdigest()
            if original!=c['input_sha256']:raise ValueError('ACCEPTED_INPUT_CHANGED')
            shutil.copy2(source,str(c['scratch_cae']));db=openMdb(pathName=str(c['scratch_cae']))
        else:raise ValueError('INVALID_MODE')
        m=db.models[str(c['project_id'])];s7_stage1_values(m,c)
        for repo in (m.rootAssembly.sets,m.rootAssembly.surfaces,m.rootAssembly.features,m.constraints,m.boundaryConditions):
            if any([str(k).startswith(('STEP07_SET_','STEP07_RP_BASE','STEP07_BC_','STEP07_COUPLING_','STEP07_SURF_')) for k in repo.keys()]):
                raise ValueError('STAGE2_OBJECT_CONFLICT; no automatic deletion')
        # All geometry/constraint checks occur before saving or mutation.
        b2_plan(m,c)
        if os.path.normcase(os.path.abspath(output))==os.path.normcase(os.path.abspath(str(db.pathName))):raise ValueError('OUTPUT_EQUALS_CURRENT_MDB')
        disk=str(db.pathName);report['current_mdb_source']=disk
        if os.path.isfile(disk):
            shutil.copy2(disk,str(c['disk_backup_cae']))
            with open(disk,'rb') as f:report['source_disk_sha256_before']=hashlib.sha256(f.read()).hexdigest()
        db.saveAs(pathName=str(c['backup_cae']));report['recovery_cae']=c['backup_cae']
        before=b2_apply(db,c,report)
        if os.path.exists(output):raise ValueError('OUTPUT_EXISTS: regenerate script')
        db.saveAs(pathName=output)
        if b2_clean_inventory(db,str(c['project_id']),report['created'])!=before:raise ValueError('SAVE_PRESERVATION_FAILED')
        b2_verify(db.models[str(c['project_id'])],report)
        report['session_alive']=True
        if c['execution_mode']=='INDEPENDENT_CAE':
            db.close();db=openMdb(pathName=output)
            if b2_clean_inventory(db,str(c['project_id']),report['created'])!=before:raise ValueError('REOPEN_PRESERVATION_FAILED')
            s7_stage1_values(db.models[str(c['project_id'])],c);report['reopen']='PASS'
            b2_verify(db.models[str(c['project_id'])],report)
            with open(source,'rb') as f:report['accepted_input_unchanged']=hashlib.sha256(f.read()).hexdigest()==original
            if not report['accepted_input_unchanged']:raise ValueError('ACCEPTED_INPUT_CHANGED')
        if os.path.isfile(disk):
            with open(disk,'rb') as f:report['source_disk_bytes_unchanged']=hashlib.sha256(f.read()).hexdigest()==report.get('source_disk_sha256_before')
        report['status']='PARTIAL_ENGINEERING_PENDING'
        report['warnings']=['Solid support rotations are not constrained. No support RP/coupling added.',
                            'Native saveAs can update the previously open CAE bytes; exact disk copy is preserved.',
                            'No mesh, solver or reaction-force verification performed. RF/RM should be extracted at base RPs without summing them again with coupled geometry.']
        print('Boundary setup saved; solid support rotations pending engineering confirmation.')
    except Exception:
        report['status']='FAILED';report['error']=traceback.format_exc();print(report['error'])
        if before is not None and db is not None:
            try:b2_rollback(db,c,report['created'],before);report['rollback']='PASS_NOT_SAVED'
            except Exception:report['rollback']='FAILED_USE_BACKUP';report['rollback_error']=traceback.format_exc()
        report['partial_output_possible']=os.path.exists(output)
    finally:
        if db is not None and c['execution_mode']=='INDEPENDENT_CAE':db.close()
        with open(str(c['report_path']),'w') as f:json.dump(report,f,indent=2)
        sys.stdout=old_out;sys.stderr=old_err;log.close();os.chdir(old_dir)
    if report['status']=='FAILED':raise RuntimeError('Step07-02 failed; see '+str(c['report_path']))
    return report
