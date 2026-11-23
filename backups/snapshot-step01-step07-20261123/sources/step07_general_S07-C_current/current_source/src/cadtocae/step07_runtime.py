# -*- coding: utf-8 -*-
"""Standalone Python 2.7 runtime. Geometry and existing connections are preserved."""
import json
import hashlib
import os
import shutil
import traceback
import math
import re


def s7_snapshot(m):
    a=m.rootAssembly
    constraints={}
    for n,c in m.constraints.items():
        values=dict(type=str(type(c)),suppressed=c.suppressed)
        for field in ('controlPoint','surface','master','slave','couplingType','u1','u2','u3','ur1','ur2','ur3','adjust','thickness','tieRotations','positionToleranceMethod','positionTolerance'):
            if hasattr(c,field):values[field]=str(getattr(c,field))
        constraints[n]=values
    return dict(sets=sorted(a.sets.keys()),surfaces=sorted(a.surfaces.keys()),
                rps=sorted(a.referencePoints.keys()),constraints=constraints,
                connector_assignments=len(a.sectionAssignments),connector_orientations=len(a.connectorOrientations))


def s7_preflight(m,c):
    from abaqusConstants import ON
    a=m.rootAssembly
    if any([n.startswith('STEP07_') for n in m.loads.keys()+m.boundaryConditions.keys()]):
        raise ValueError('STEP07_ALREADY_PRESENT: use the upstream CAE for repeatable regeneration')
    rows={}
    for row in c['instances']:
        name=str(row['instance_name']); rows[name]=row
        if name not in a.instances:raise ValueError('INSTANCE_MISSING: '+name)
        i=a.instances[name]
        if i.partName!=row['part_name'] or i.dependent!=ON:raise ValueError('INSTANCE_MAPPING_MISMATCH: '+name)
        if not m.parts[i.partName].sectionAssignments:raise ValueError('SECTION_MISSING: '+name)
    for name in a.instances.keys():
        if name not in rows:raise ValueError('UNMAPPED_INSTANCE: '+name)
    bottoms=[]
    for name,row in rows.items():
        roles=('COLUMN_FRONT','COLUMN_REAR') if c['structure_type']=='DP' else ('COLUMN_DOWN',)
        if row['canonical_role'] in roles:bottoms.append(name)
    expected=2 if c['structure_type']=='DP' else 1
    if len(bottoms)!=expected:raise ValueError('BOTTOM_ROLE_COUNT: expected %d, got %s'%(expected,bottoms))
    for item in c['loads']:
        name=str(item['rp_set'])
        if name not in a.sets or len(a.sets[name].referencePoints)!=1:raise ValueError('PURLIN_RP_SET_MISSING: '+name)
        row=rows[item['instance']]
        expected_name='STEP06_RP_'+str(row.get('connection_group'))+'_PURLIN'
        if name!=expected_name:raise ValueError('RP_TARGET_UNVERIFIED: '+name)
        coupling='STEP06_COUPLING_'+str(row.get('connection_group'))+'_PURLIN'
        if coupling not in m.constraints or m.constraints[coupling].suppressed:raise ValueError('PURLIN_COUPLING_MISSING: '+coupling)
    for name,obj in m.constraints.items():
        if obj.suppressed:raise ValueError('SUPPRESSED_CONNECTION: '+name)
    return rows,bottoms


def s7_column_tie(m,c,report):
    from abaqusConstants import SPECIFIED
    if not c.get('enable_column_tie_correction',False):return
    if 'column_tie' not in c:raise ValueError('TIE_CORRECTION_PLAN_MISSING')
    plan=c['column_tie'];a=m.rootAssembly
    members=plan['members']
    if len(members)!=2:raise ValueError('COLUMN_TIE_MEMBERS_INVALID')
    radii=[]; axes=[]; origins=[]
    for member in members:
        i=a.instances[str(member['instance_name'])]
        if i.partName!=member['part_name']:raise ValueError('COLUMN_TIE_PART_MISMATCH')
        origin=member['origin'];axis=member['axis_direction']
        norm=math.sqrt(sum([x*x for x in axis]))
        if norm<1e-12:raise ValueError('COLUMN_AXIS_INVALID')
        axis=[x/norm for x in axis]
        axes.append(axis);origins.append(origin)
        faces=a.sets[str(member['region'])].faces
        if not faces:raise ValueError('COLUMN_TIE_REGION_EMPTY')
        for face in faces:
            delta=[face.pointOn[0][j]-origin[j] for j in range(3)]
            axial=sum([delta[j]*axis[j] for j in range(3)])
            radius=math.sqrt(sum([(delta[j]-axial*axis[j])**2 for j in range(3)]))
            if abs(radius-member['radius_m'])>1e-5:raise ValueError('COLUMN_TIE_RADIUS_MISMATCH')
        radii.append(member['radius_m'])
    alignment=abs(sum([axes[0][j]*axes[1][j] for j in range(3)]))
    delta=[origins[1][j]-origins[0][j] for j in range(3)]
    axial=sum([delta[j]*axes[0][j] for j in range(3)])
    offset=math.sqrt(sum([(delta[j]-axial*axes[0][j])**2 for j in range(3)]))
    if alignment<.999999 or offset>1e-5:raise ValueError('COLUMN_TIE_NOT_COAXIAL')
    name=str(plan['tie']);obj=m.constraints[name]
    tolerance=abs(radii[0]-radii[1])+max(1e-5,plan['tolerance_m'])
    original=str(obj.positionToleranceMethod)
    obj.setValues(positionToleranceMethod=SPECIFIED,positionTolerance=tolerance)
    report['connection_adjustments']=[dict(name=name,parameter='positionTolerance',before_method=original,
        after_method='SPECIFIED',value_m=tolerance,evidence='UPSTREAM_COLUMN_RADII_VERIFIED_ON_CAE',radii_m=radii)]


def s7_mesh(m,c,rows,report):
    from abaqusConstants import STANDARD,C3D10,S4R,S3,FREE,TET,QUAD_DOMINATED,FINER,CONN3D2
    import mesh
    a=m.rootAssembly; sizes={}
    for name,row in rows.items():
        p=a.instances[name].partName
        size=c['mesh']['by_role'].get(row['canonical_role'],c['mesh']['size'])
        sizes[p]=min(sizes.get(p,size),size)
    report['mesh']={}
    for name,size in sorted(sizes.items()):
        p=m.parts[str(name)]
        try:
            if len(p.elements):
                if p.getUnmeshedRegions() is not None:raise ValueError('Existing mesh incomplete')
                report['mesh'][name]=dict(nodes=len(p.nodes),elements=len(p.elements),policy='PRESERVED_EXISTING_MESH')
                continue
            p.seedPart(size=size,deviationFactor=.1,minSizeFactor=.1)
            # Short geometric edges include bolt hole arcs and connection partitions.
            refined=[]
            for edge in p.edges:
                if edge.getSize(printResults=False)<2*size:refined.append(edge)
            if refined:p.seedEdgeBySize(edges=tuple(refined),size=min(size,c['mesh']['local_size']),constraint=FINER)
            if len(p.cells):
                p.setMeshControls(regions=p.cells,elemShape=TET,technique=FREE)
                p.setElementType(regions=(p.cells,),elemTypes=(mesh.ElemType(elemCode=C3D10,elemLibrary=STANDARD),))
                kind='C3D10'
            elif len(p.faces):
                p.setMeshControls(regions=p.faces,elemShape=QUAD_DOMINATED,technique=FREE)
                p.setElementType(regions=(p.faces,),elemTypes=(mesh.ElemType(elemCode=S4R,elemLibrary=STANDARD),mesh.ElemType(elemCode=S3,elemLibrary=STANDARD)))
                kind='S4R/S3'
            else:raise ValueError('Unsupported wire/orphan part')
            p.generateMesh()
            if not len(p.elements) or p.getUnmeshedRegions() is not None:raise ValueError('Incomplete mesh')
            report['mesh'][name]=dict(nodes=len(p.nodes),elements=len(p.elements),element_type=kind,size_m=size,refined_edges=len(refined))
        except Exception as exc:raise ValueError('MESH_FAILED %s: %s'%(name,exc))
    a.regenerate()
    wires=[]
    for name in a.sets.keys():
        if name.startswith('STEP06_WIRE_'):
            region=a.sets[name]
            if len(region.edges)!=1:raise ValueError('CONNECTOR_WIRE_INVALID: '+name)
            wires.extend(list(region.edges))
    # Nonmeshable connector wires are emitted as CONN3D2 by the input writer.
    report['connector_wires']=len(wires)
    report['mesh_nodes']=int(sum([len(i.nodes) for i in a.instances.values()]))
    report['mesh_elements']=int(sum([len(i.elements) for i in a.instances.values()])+len(wires))


def s7_boundary(m,c,bottoms,report):
    a=m.rootAssembly;tol=c['bottom_tolerance'];report['bottoms']=[]
    for name in sorted(bottoms):
        i=a.instances[str(name)]
        points=[v.pointOn[0] for v in i.vertices]
        if not points:raise ValueError('BOTTOM_GEOMETRY_EMPTY: '+name)
        z=min([p[2] for p in points])
        if max([p[2] for p in points])-z<100*tol:raise ValueError('BOTTOM_AMBIGUOUS: '+name)
        if len(i.cells):
            faces=i.faces.getByBoundingBox(zMin=z-tol,zMax=z+tol)
            if not faces:raise ValueError('BOTTOM_FACE_NOT_FOUND: '+name)
            region=a.Set(name=str('STEP07_BOTTOM_'+name),faces=faces)
        else:
            edges=i.edges.getByBoundingBox(zMin=z-tol,zMax=z+tol)
            if not edges:raise ValueError('BOTTOM_EDGE_NOT_FOUND: '+name)
            region=a.Set(name=str('STEP07_BOTTOM_'+name),edges=edges)
        m.EncastreBC(name=str('STEP07_FIX_'+name),createStepName='Initial',region=region)
        report['bottoms'].append(dict(instance=name,z_m=z,nodes=len(region.nodes),set='STEP07_BOTTOM_'+name))
        if not len(region.nodes):raise ValueError('BOTTOM_NO_MESH_NODES: '+name)


def s7_validate_odb(path,c,report):
    from odbAccess import openOdb
    odb=openOdb(path=str(path),readOnly=True)
    try:
        st=odb.steps[str(c['step']['name'])]
        if not st.frames or abs(st.frames[-1].frameValue-1.)>1e-6:raise ValueError('ODB_INCOMPLETE_STEP')
        frame=st.frames[-1]
        for field in ('U','RF','S'):
            if field not in frame.fieldOutputs or not frame.fieldOutputs[field].values:raise ValueError('ODB_FIELD_MISSING: '+field)
        total=[0.,0.,0.]
        for b in report['bottoms']:
            values=frame.fieldOutputs['RF'].getSubset(region=odb.rootAssembly.nodeSets[str(b['set'].upper())]).values
            for v in values:
                for j in range(3):total[j]+=float(v.data[j])
        force=[float(sum([x['force'][j] for x in c['loads']])) for j in range(3)]
        residual=math.sqrt(sum([(total[j]+force[j])**2 for j in range(3)]))
        scale=max(1.,sum([math.sqrt(sum([v*v for v in x['force']])) for x in c['loads']]))
        max_u=max([math.sqrt(sum([x*x for x in v.data])) for v in frame.fieldOutputs['U'].values])
        report['odb']=dict(path=path,frames=len(st.frames),end_time=frame.frameValue,reaction_n=total,applied_n=force,force_balance_relative=residual/scale,max_displacement_m=max_u)
        if math.isnan(max_u) or math.isinf(max_u):
            raise ValueError('NONFINITE_DISPLACEMENT')
        if residual/scale>.01:raise ValueError('REACTION_BALANCE_FAILED')
        report['additional_restraint_reactions']=[]
        for assumption in report.get('validation_assumptions',[]):
            rp_region=odb.rootAssembly.nodeSets[str(assumption['rp_set'].upper())]
            moments=frame.fieldOutputs['RM'].getSubset(region=rp_region).values
            if not moments:raise ValueError('ADDITIONAL_RESTRAINT_RM_MISSING')
            report['additional_restraint_reactions'].append(dict(rp_set=assumption['rp_set'],moment_nm=[[float(x) for x in v.data] for v in moments]))
        report['untied_nodes_by_instance']={}
        for key in odb.rootAssembly.nodeSets.keys():
            if key.upper()=='WARNNODEMISSMASTERINTERSECT':
                values=frame.fieldOutputs['U'].getSubset(region=odb.rootAssembly.nodeSets[key]).values
                for value in values:
                    instance=value.instance.name
                    report['untied_nodes_by_instance'][instance]=report['untied_nodes_by_instance'].get(instance,0)+1
    finally:odb.close()


def s7_completion_evidence(sta_text,log_text,job_name):
    expected='Abaqus JOB '+job_name+' COMPLETED'
    return ('THE ANALYSIS HAS COMPLETED SUCCESSFULLY' in sta_text and
            (expected in log_text or 'Abaqus/Analysis completed successfully' in log_text))


def s7_solver_diagnostics(c,report):
    diagnostics={}
    critical=[]
    for extension in ('dat','msg'):
        path=c['job']['name']+'.'+extension
        if not os.path.exists(path):raise ValueError('SOLVER_LOG_MISSING: '+path)
        text=open(path).read()
        diagnostics[extension]=dict(warnings=text.count('***WARNING'),errors=text.count('***ERROR'),
            untied_warning_lines=text.count('WILL NOT BE TIED'),
            untied_nodes_reported=int(sum([int(n) for n in re.findall(r'(\d+) nodes are either missing intersection',text)])),singularities=text.count('NUMERICAL SINGULARITY'),
            zero_pivots=text.count('ZERO PIVOT'),negative_eigenvalues=text.count('NEGATIVE EIGENVALUES'))
        for marker in ('***ERROR','NUMERICAL SINGULARITY','ZERO PIVOT','NEGATIVE EIGENVALUES'):
            if marker in text:critical.append(extension+': '+marker)
    report['solver_diagnostics']=diagnostics
    if critical:raise ValueError('UNVERIFIED_STRUCTURAL_STABILITY: '+str(critical))


def run_step07(c):
    from abaqus import openMdb
    from abaqusConstants import ON,OFF,COMPLETED
    import part, assembly, interaction, load, step, mesh, job, section
    report=dict(status='RUNNING',units='m-N-Pa',stage='preflight')
    output=str(c['output_dir']); os.chdir(output)
    report_path=os.path.join(output,'step07_report.json')
    try:
        if os.path.exists(c['output_cae']) or os.path.exists(c['job']['name']+'.odb'):
            raise ValueError('OUTPUT_EXISTS: use a new run directory')
        # openMdb can request write access; never open the upstream original.
        scratch=os.path.join(output,'input_copy.cae')
        if os.path.exists(scratch):raise ValueError('INPUT_COPY_EXISTS: use a new run directory')
        with open(c['input_cae'],'rb') as handle:source_hash=hashlib.sha256(handle.read()).hexdigest()
        if source_hash!=c['input_sha256']:raise ValueError('UPSTREAM_CHANGED_SINCE_GENERATION')
        report['input_sha256']=source_hash
        shutil.copy2(str(c['input_cae']),scratch)
        db=openMdb(pathName=scratch)
        m=db.models[str(c['model_name'])];a=m.rootAssembly
        rows,bottoms=s7_preflight(m,c)
        before=s7_snapshot(m);report['upstream']=before
        s7_column_tie(m,c,report)
        expected=s7_snapshot(m)
        if m.loads.keys() or m.boundaryConditions.keys():raise ValueError('EXISTING_LOAD_OR_BC: explicit combination policy required')
        st=c['step'];name=str(st['name']);previous=str(st['previous'])
        if list(m.steps.keys())!=['Initial']:raise ValueError('EXISTING_ANALYSIS_STEP: explicit reuse policy required')
        m.StaticStep(name=name,previous=previous,nlgeom=ON if st['nlgeom'] else OFF,initialInc=st['initialInc'],maxInc=st['maxInc'],minInc=st['minInc'],maxNumInc=st['maxNumInc'])
        report['stage']='mesh';s7_mesh(m,c,rows,report)
        report['stage']='boundary';s7_boundary(m,c,bottoms,report)
        report['validation_assumptions']=[]
        if c.get('validation_assumptions',{}).get('fix_purlin_rp_rotations',False):
            for instance,row in sorted(rows.items()):
                if row['canonical_role']!='PURLIN_LOCAL':continue
                rp_name='STEP06_RP_'+str(row['connection_group'])+'_PURLIN'
                if rp_name not in a.sets:raise ValueError('STABILIZATION_RP_MISSING: '+rp_name)
                m.DisplacementBC(name=str('STEP07_ROT_'+instance),createStepName='Initial',region=a.sets[rp_name],ur1=0.,ur2=0.,ur3=0.)
                report['validation_assumptions'].append(dict(instance=instance,rp_set=rp_name,restrained=['UR1','UR2','UR3'],reason='USER_AUTHORIZED_WORKFLOW_ONLY_MISSING_CONTINUOUS_PURLIN'))
        if c.get('validation_assumptions',{}).get('fix_support_beam_rp_rotations',False):
            for instance,row in sorted(rows.items()):
                if row['canonical_role']!='PURLIN_SUPPORT':continue
                rp_name='STEP06_RP_'+str(row['connection_group'])+'_SUPPORT_BEAM'
                if rp_name not in a.sets:raise ValueError('STABILIZATION_RP_MISSING: '+rp_name)
                m.DisplacementBC(name=str('STEP07_ROT_'+instance),createStepName='Initial',region=a.sets[rp_name],ur1=0.,ur2=0.,ur3=0.)
                report['validation_assumptions'].append(dict(instance=instance,rp_set=rp_name,restrained=['UR1','UR2','UR3'],reason='USER_AUTHORIZED_WORKFLOW_ONLY_SUPPORT_ROTATION_RESTRAINT'))
        report['loads']=[]
        for index,item in enumerate(c['loads']):
            region=a.sets[str(item['rp_set'])];force=item['force']
            m.ConcentratedForce(name='STEP07_LOAD_%02d'%(index+1),createStepName=name,region=region,cf1=force[0],cf2=force[1],cf3=force[2])
            rp=region.referencePoints[0]
            report['loads'].append(dict(instance=item['instance'],rp_set=item['rp_set'],force_global_n=force,position_m=list(a.getCoordinates(rp))))
        after=s7_snapshot(m)
        for key in ('surfaces','rps','constraints','connector_assignments','connector_orientations'):
            if expected[key]!=after[key]:raise ValueError('CONNECTION_PRESERVATION_FAILED: '+key)
        for n in before['sets']:
            if n not in a.sets:raise ValueError('UPSTREAM_SET_LOST: '+n)
        report['connection_preservation']='PASS_WITH_RECORDED_TIE_TOLERANCE' if report.get('connection_adjustments') else 'PASS'
        m.FieldOutputRequest(name='STEP07_OUTPUT',createStepName=name,variables=('S','U','RF','RM'))
        report['stage']='job';j=db.Job(name=str(c['job']['name']),model=str(c['model_name']),numCpus=1)
        j.writeInput(consistencyChecking=ON)
        db.saveAs(pathName=str(c['output_cae']))
        report['cae']=c['output_cae'];report['job']=c['job']['name']
        report['status']='SETUP_COMPLETE'
        if c['job']['submit']:
            report['stage']='solve';j.submit(consistencyChecking=ON);j.waitForCompletion()
            report['job_status']=str(j.status)
            sta_path=os.path.join(output,c['job']['name']+'.sta')
            sta_text=open(sta_path).read() if os.path.exists(sta_path) else ''
            log_path=os.path.join(output,c['job']['name']+'.log')
            log_text=open(log_path).read() if os.path.exists(log_path) else ''
            # Abaqus 2020 noGUI may leave Job.status as None; require solver evidence.
            if not s7_completion_evidence(sta_text,log_text,c['job']['name']):
                raise ValueError('JOB_NOT_COMPLETED: '+str(j.status))
            report['job_status']='COMPLETED_CONFIRMED_BY_STA_AND_LOG'
            report['stage']='verify';s7_solver_diagnostics(c,report)
            s7_validate_odb(os.path.join(output,c['job']['name']+'.odb'),c,report)
            report['status']='VERIFIED_WORKFLOW_ONLY' if report['validation_assumptions'] else 'VERIFIED'
        with open(c['input_cae'],'rb') as handle:source_after=hashlib.sha256(handle.read()).hexdigest()
        if source_after!=source_hash:raise ValueError('UPSTREAM_CHANGED_DURING_EXECUTION')
        report['upstream_unchanged']=True
        report['stage']='finished'
    except Exception:
        report['status']='FAILED';report['error']=traceback.format_exc()
        if c['job']['submit']:
            try:s7_solver_diagnostics(c,report)
            except Exception as diagnostic_error:report['solver_diagnostic_error']=str(diagnostic_error)
        print(report['error'])
    finally:
        serialized=json.dumps(report,indent=2,allow_nan=False)
        with open(report_path,'w') as handle:handle.write(serialized)
    if report['status']=='FAILED':raise RuntimeError('Step07 failed; see '+report_path)
    return report




def verify_saved_step07(c):
    """Recheck an existing solve without remeshing, resubmitting or editing CAE."""
    os.chdir(str(c['output_dir']))
    path='step07_report.json'
    with open(path) as handle:report=json.load(handle)
    prior=report.get('error')
    if not os.path.exists('step07_report.before_reverification.json'):
        shutil.copy2(path,'step07_report.before_reverification.json')
    try:
        sta=open(c['job']['name']+'.sta').read()
        log=open(c['job']['name']+'.log').read()
        if not s7_completion_evidence(sta,log,c['job']['name']):raise ValueError('SOLVER_INCOMPLETE')
        s7_solver_diagnostics(c,report)
        s7_validate_odb(c['job']['name']+'.odb',c,report)
        report['status']='VERIFIED_WORKFLOW_ONLY' if report.get('validation_assumptions') else 'VERIFIED'
        report['job_status']='COMPLETED_CONFIRMED_BY_STA_AND_LOG'
        report['stage']='finished'
        report['independent_verification']='PASS'
        report.pop('error',None);report.pop('solver_diagnostic_error',None)
        if prior:report['previous_validation_error']=prior
    except Exception:
        report['status']='FAILED';report['error']=traceback.format_exc()
        raise
    finally:
        serialized=json.dumps(report,indent=2,allow_nan=False)
        with open(path,'w') as handle:handle.write(serialized)
    return report


def submit_saved_step07(c):
    """Submit the reviewed CAE in a separate solve folder, preserving setup files."""
    from abaqus import openMdb
    from abaqusConstants import ON
    import part,assembly,interaction,load,step,mesh,job,section
    import time,uuid
    setup_dir=str(c['output_dir'])
    with open(os.path.join(setup_dir,'step07_report.json')) as handle:report=json.load(handle)
    if report.get('status') not in ('SETUP_COMPLETE','VERIFIED','VERIFIED_WORKFLOW_ONLY'):
        raise ValueError('SETUP_NOT_COMPLETE')
    solve_dir=os.path.join(setup_dir,'solve_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
    os.mkdir(solve_dir);os.chdir(solve_dir)
    locator=os.path.join(setup_dir,'step07_last_submission.json')
    record=dict(status='RUNNING',output_dir=solve_dir,job=c['job']['name'])
    with open(locator,'w') as handle:json.dump(record,handle,indent=2)
    try:
        source=str(c['output_cae'])
        if not os.path.isfile(source):raise ValueError('REVIEWED_CAE_MISSING: '+source)
        with open(source,'rb') as handle:source_hash=hashlib.sha256(handle.read()).hexdigest()
        report['reviewed_cae_sha256']=source_hash
        scratch=os.path.join(solve_dir,'reviewed_copy.cae');shutil.copy2(source,scratch)
        db=openMdb(pathName=scratch)
        model=db.models[str(c['model_name'])]
        if str(c['step']['name']) not in model.steps:raise ValueError('CONFIGURED_STEP_MISSING')
        name=str(c['job']['name'])
        if name in db.jobs:j=db.jobs[name]
        else:j=db.Job(name=name,model=str(c['model_name']),numCpus=1)
        j.writeInput(consistencyChecking=ON)
        j.submit(consistencyChecking=ON);j.waitForCompletion()
        sta=open(name+'.sta').read() if os.path.exists(name+'.sta') else ''
        log=open(name+'.log').read() if os.path.exists(name+'.log') else ''
        if not s7_completion_evidence(sta,log,name):raise ValueError('JOB_NOT_COMPLETED: '+str(j.status))
        s7_solver_diagnostics(c,report)
        s7_validate_odb(os.path.join(solve_dir,name+'.odb'),c,report)
        with open(source,'rb') as handle:after_hash=hashlib.sha256(handle.read()).hexdigest()
        if after_hash!=source_hash:raise ValueError('REVIEWED_CAE_CHANGED_DURING_SOLVE')
        report['status']='VERIFIED_WORKFLOW_ONLY' if report.get('validation_assumptions') else 'VERIFIED'
        report['job_status']='COMPLETED_CONFIRMED_BY_STA_AND_LOG'
        report['stage']='finished';report.pop('error',None)
    except Exception:
        report['status']='FAILED';report['error']=traceback.format_exc()
        try:s7_solver_diagnostics(c,report)
        except Exception as exc:report['solver_diagnostic_error']=str(exc)
        print(report['error'])
    finally:
        report['solve_dir']=solve_dir
        serialized=json.dumps(report,indent=2,allow_nan=False)
        with open('step07_solver_report.json','w') as handle:handle.write(serialized)
        record.update(status=report['status'],report_path=os.path.join(solve_dir,'step07_solver_report.json'))
        with open(locator,'w') as handle:json.dump(record,handle,indent=2)
    if report['status']=='FAILED':raise RuntimeError('Job failed; see '+solve_dir)
    return report


def s7_stage1_inventory(db,include_mesh=True):
    """Read-only inventory, including geometry/mesh and named region membership."""
    def regions(repo):
        result={}
        for name,obj in repo.items():
            values={}
            for kind in ('vertices','edges','faces','cells','nodes','elements','referencePoints'):
                if not include_mesh and kind in ('nodes','elements'):continue
                if not hasattr(obj,kind):continue
                seq=getattr(obj,kind)
                def ids(items):
                    data=[]
                    for item in items:
                        if hasattr(item,'label'):data.append((getattr(item,'instanceName',''),item.label))
                        elif hasattr(item,'index'):data.append(item.index)
                        elif hasattr(item,'id'):data.append(item.id)
                        else:
                            try:data.append(ids(item))
                            except TypeError:data.append(str(item))
                    return data
                values[kind]=ids(seq)
            result[name]=values
        return result
    def geometry(obj):
        result={}
        for k in ('vertices','edges','faces','cells'):
            result[k]=[(v.index,str(v.pointOn)) for v in getattr(obj,k)]
        if include_mesh:
            result['nodes']=[(v.label,tuple(v.coordinates)) for v in obj.nodes]
            result['elements']=[(v.label,str(v.type),tuple(v.connectivity)) for v in obj.elements]
        result['sets']=regions(obj.sets);result['surfaces']=regions(obj.surfaces)
        result['rps']=sorted(obj.referencePoints.keys())
        result['section_assignments']=[(x.sectionName,str(x.region)) for x in getattr(obj,'sectionAssignments',[])]
        return result
    result=dict(jobs=sorted(db.jobs.keys()),models={})
    for name,m in db.models.items():
        a=m.rootAssembly
        d=dict(connections=s7_snapshot(m),parts={},instances={},assembly_sets=regions(a.sets),assembly_surfaces=regions(a.surfaces),
               assembly_rps=[(k,a.getCoordinates(v)) for k,v in a.referencePoints.items()])
        for repo in ('loads','boundaryConditions','interactions','interactionProperties','materials','sections','profiles','fieldOutputRequests','historyOutputRequests'):
            d[repo]=sorted(getattr(m,repo).keys())
        for n,p in m.parts.items():d['parts'][n]=geometry(p)
        for n,i in a.instances.items():
            d['instances'][n]=dict(part=i.partName,dependent=str(i.dependent),translation=i.getTranslation(),rotation=i.getRotation(),geometry=geometry(i))
        result['models'][name]=d
    return result


def s7_stage1_target(db,c):
    name=str(c['project_id'])
    if str(c['model_name'])!=name:raise ValueError('PROJECT_MODEL_IDENTITY_MISMATCH')
    if name not in db.models:raise ValueError('CURRENT_TARGET_MODEL_NOT_FOUND: '+name+'; available: '+str(db.models.keys()))
    m=db.models[name]
    for name in ('STEP07_STATIC','STEP07_PRELOAD','STEP07_LOADING'):
        if name in m.steps:raise ValueError('STEP_ALREADY_EXISTS: '+name+'; no changes made; no automatic deletion')
    if list(m.steps.keys())!=['Initial']:raise ValueError('EXISTING_ANALYSIS_STEP_CONFLICT: '+str(m.steps.keys()))
    for instance in c.get('assembly_summary',{}).get('instances',[]):
        if str(instance['instance_name']) not in m.rootAssembly.instances:
            raise ValueError('SUMMARY_INSTANCE_NOT_FOUND: '+str(instance['instance_name']))
    return m


def s7_stage1_values(m,c):
    result=[];order=list(m.steps.keys())
    expected=['Initial']
    for st in c['steps']:expected.append(str(st['name']))
    if order!=expected:raise ValueError('STEP_SEQUENCE_MISMATCH: '+str(order))
    for st in c['steps']:
        actual=m.steps[str(st['name'])]
        # The ordered repository independently confirms the predecessor chain.
        previous=order[order.index(str(st['name']))-1]
        values=dict(name=str(st['name']),previous=previous,initialInc=actual.initialInc,maxInc=actual.maxInc,minInc=actual.minInc,
                    maxNumInc=actual.maxNumInc,nlgeom=str(actual.nlgeom),procedure=type(actual).__name__,timePeriod=actual.timePeriod,
                    timeIncrementationMethod=str(actual.timeIncrementationMethod))
        for key in ('initialInc','maxInc','minInc','maxNumInc','timePeriod','previous','timeIncrementationMethod'):
            if values[key]!=st[key]:raise ValueError('STEP_PARAMETER_MISMATCH: '+str(st['name'])+' '+key)
        if values['nlgeom']!='OFF' or values['procedure']!='StaticStep':raise ValueError('STEP_TYPE_MISMATCH')
        result.append(values)
    return result


def s7_stage1_rollback(db,c,before,steps):
    m=db.models[str(c['project_id'])]
    for st in reversed(c['steps']):
        name=str(st['name'])
        if name in m.steps and name not in steps[str(c['project_id'])]:del m.steps[name]
    for key in ('fieldOutputRequests','historyOutputRequests'):
        repo=getattr(m,key)
        for n in list(repo.keys()):
            if n not in before['models'][str(c['project_id'])][key]:del repo[n]
    if s7_stage1_inventory(db)!=before:raise ValueError('ROLLBACK_INCOMPLETE: use pre-step backup; model not saved')
    for n,keys in steps.items():
        if list(db.models[n].steps.keys())!=keys:raise ValueError('ROLLBACK_STEP_LIST_MISMATCH')


def s7_apply_static_step(db,c,report):
    """One calculation implementation shared by both execution modes."""
    from abaqusConstants import OFF,AUTOMATIC
    m=s7_stage1_target(db,c);before=s7_stage1_inventory(db);steps={}
    for n,v in db.models.items():steps[n]=list(v.steps.keys())
    try:
        for st in c['steps']:
            m.StaticStep(name=str(st['name']),previous=str(st['previous']),nlgeom=OFF,
                         timePeriod=st['timePeriod'],timeIncrementationMethod=AUTOMATIC,
                         initialInc=st['initialInc'],maxInc=st['maxInc'],minInc=st['minInc'],maxNumInc=st['maxNumInc'])
        report['automatic_output_requests_removed']=[]
        for key in ('fieldOutputRequests','historyOutputRequests'):
            repo=getattr(m,key)
            for request in list(repo.keys()):
                if request not in before['models'][str(c['project_id'])][key]:
                    report['automatic_output_requests_removed'].append(request);del repo[request]
        if s7_stage1_inventory(db)!=before:raise ValueError('NON_STEP_MODEL_DATA_CHANGED')
        values=s7_stage1_values(m,c)
        return before,steps,values
    except Exception:
        s7_stage1_rollback(db,c,before,steps);report['rollback']='PASS';raise


def s7_run_current_session_stage1(c,report):
    # Never import/call openMdb or close here. Do not replace the current MDB.
    import abaqus
    db=abaqus.mdb;s7_stage1_target(db,c)
    report['session_path_before']=str(db.pathName)
    report['source_kind']='CURRENT_ABAQUS_MDB_NOT_DISK_INPUT'
    report['input_cae_used']=False
    before=s7_stage1_inventory(db);steps={}
    for n,v in db.models.items():steps[n]=list(v.steps.keys())
    backup=str(c['session_backup_cae']);output=str(c['output_cae'])
    for path in (backup,output):
        if os.path.exists(path):raise ValueError('OUTPUT_EXISTS: '+path+'; regenerate script')
    if os.path.normcase(os.path.abspath(output))==os.path.normcase(os.path.abspath(str(db.pathName))):raise ValueError('OUTPUT_EQUALS_CURRENT_MDB')
    # Native saveAs may update bytes of the file backing the current MDB.
    # Preserve exact disk bytes separately from the live-memory recovery model.
    disk_source=str(db.pathName)
    if os.path.isfile(disk_source):
        disk_backup=str(c['session_disk_backup_cae'])
        if os.path.exists(disk_backup):raise ValueError('OUTPUT_EXISTS: '+disk_backup)
        shutil.copy2(disk_source,disk_backup)
        with open(disk_backup,'rb') as f:report['source_disk_sha256_before']=hashlib.sha256(f.read()).hexdigest()
        report['source_disk_backup']=disk_backup
        print('Original disk CAE preserved at: '+disk_backup)
    print('CURRENT_SESSION_DEBUG: saving pre-step recovery copy: '+backup)
    db.saveAs(pathName=backup)
    report['pre_step_backup']=backup
    if os.path.isfile(disk_source) and report.get('source_disk_sha256_before'):
        with open(disk_source,'rb') as f:report['source_disk_sha256_after_backup']=hashlib.sha256(f.read()).hexdigest()
        report['source_disk_bytes_unchanged']=report['source_disk_sha256_before']==report['source_disk_sha256_after_backup']
        if not report['source_disk_bytes_unchanged']:
            report['warnings']=['ABAQUS_NATIVE_SAVEAS_CHANGED_SOURCE_BYTES: exact pre-run disk copy preserved; not restored automatically']
            print(report['warnings'][0])
    if s7_stage1_inventory(db)!=before:raise ValueError('BACKUP_PRESERVATION_FAILED; no step created')
    applied=False
    try:
        before,steps,values=s7_apply_static_step(db,c,report);applied=True
        # Recheck after calculation: another process must not occupy the target.
        if os.path.exists(output):raise ValueError('OUTPUT_EXISTS: '+output+'; regenerate script')
        print('CURRENT_SESSION_DEBUG: saving stage CAE: '+output)
        db.saveAs(pathName=output)
        if abaqus.mdb is not db or str(c['project_id']) not in db.models:raise ValueError('CURRENT_SESSION_IDENTITY_CHANGED')
        if s7_stage1_inventory(db)!=before:raise ValueError('SAVED_SESSION_PRESERVATION_FAILED')
        if os.path.isfile(disk_source) and report.get('source_disk_sha256_before'):
            with open(disk_source,'rb') as f:report['source_disk_sha256_after']=hashlib.sha256(f.read()).hexdigest()
            report['source_disk_bytes_unchanged']=report['source_disk_sha256_before']==report['source_disk_sha256_after']
            if not report['source_disk_bytes_unchanged']:
                report['warnings']=['ABAQUS_NATIVE_SAVEAS_CHANGED_SOURCE_BYTES: exact pre-run disk copy preserved; not restored automatically']
        report.update(session_alive=True,reopen='PENDING_EXTERNAL_VERIFICATION',session_path_after=str(db.pathName))
        return before,values
    except Exception:
        if applied:
            try:s7_stage1_rollback(db,c,before,steps);report['rollback']='PASS_NOT_SAVED'
            except Exception:report['rollback']='FAILED_USE_PRE_STEP_BACKUP';report['rollback_error']=traceback.format_exc()
        report['partial_output_possible']=os.path.exists(output)
        raise


def s7_run_independent_stage1(c,report):
    from abaqus import openMdb
    source=str(c['input_cae']);output=str(c['output_cae']);scratch=str(c['scratch_cae'])
    with open(source,'rb') as f:original=hashlib.sha256(f.read()).hexdigest()
    if original!=c['input_sha256']:raise ValueError('UPSTREAM_CHANGED_SINCE_SCAN')
    if os.path.exists(scratch) or os.path.exists(output):raise ValueError('OUTPUT_EXISTS: regenerate script')
    shutil.copy2(source,scratch);db=openMdb(pathName=scratch)
    try:
        before,steps,values=s7_apply_static_step(db,c,report)
        with open(source,'rb') as f:current=hashlib.sha256(f.read()).hexdigest()
        if current!=original:raise ValueError('UPSTREAM_CHANGED_BEFORE_SAVE')
        if os.path.exists(output):raise ValueError('OUTPUT_EXISTS: regenerate script')
        db.saveAs(pathName=output)
    finally:db.close()
    db=openMdb(pathName=output)
    try:
        if s7_stage1_inventory(db)!=before:raise ValueError('REOPEN_PRESERVATION_CHECK_FAILED')
        expected=dict(steps);expected[str(c['project_id'])]=['Initial']
        for st in c['steps']:expected[str(c['project_id'])].append(str(st['name']))
        for n,keys in expected.items():
            if list(db.models[n].steps.keys())!=keys:raise ValueError('REOPEN_STEP_LIST_MISMATCH')
        values=s7_stage1_values(db.models[str(c['project_id'])],c)
    finally:db.close()
    with open(source,'rb') as f:current=hashlib.sha256(f.read()).hexdigest()
    if current!=original:raise ValueError('UPSTREAM_CHANGED_AFTER_SAVE')
    report.update(reopen='PASS',input_sha256=original,upstream_unchanged=True,input_cae_used=True)
    return before,values


def run_step07_stage1(c):
    import part,assembly,interaction,load,step,mesh,job,section
    mode=c.get('execution_mode','INDEPENDENT_CAE')
    report=dict(stage=1,status='RUNNING',project_id=c['project_id'],human_review='PENDING',automatic_next_stage=False,
                execution_mode=mode,output_version=c.get('output_version',1),artifact_prefix=c.get('artifact_prefix'),
                upstream=c.get('upstream',{}),input_cae=c['input_cae'],analysis_parameters=c['steps'],
                model_classification='DEBUG_MODEL',engineering_verified=False)
    os.chdir(str(c['output_dir']))
    try:
        if mode=='CURRENT_SESSION_DEBUG':before,values=s7_run_current_session_stage1(c,report)
        elif mode=='INDEPENDENT_CAE':before,values=s7_run_independent_stage1(c,report)
        else:raise ValueError('INVALID_EXECUTION_MODE')
        report.update(status='SETUP_COMPLETE',cae=c['output_cae'],step_names=['STEP07_PRELOAD','STEP07_LOADING'],step_parameters=values,
                      preservation='PASS',inventory=before,summary_instances_check='PASS',
                      inventory_sha256=hashlib.sha256(json.dumps(before,sort_keys=True).encode('utf-8')).hexdigest(),
                      added=dict(steps=2,bcs=0,loads=0,nodes=0,elements=0,jobs=0))
    except Exception:
        report['status']='FAILED';report['error']=traceback.format_exc();print(report['error'])
    with open(str(c['report_path']),'w') as f:json.dump(report,f,indent=2,allow_nan=False)
    if report['status']=='FAILED':raise RuntimeError('Step07-1 failed; see '+str(c['report_path']))
    return report


def s7_run_stage1_logged(c):
    """Identical standalone entry for CAE File/Run Script and desktop noGUI."""
    import sys
    previous_dir=os.getcwd();old_out=sys.stdout;old_err=sys.stderr
    # A script version is single use. Do not truncate a previous report or log.
    for key in ('output_cae','report_path','log_path','scratch_cae','session_backup_cae','session_disk_backup_cae'):
        if c.get(key) and os.path.exists(str(c[key])):
            raise ValueError('OUTPUT_EXISTS: '+str(c[key])+'; regenerate to obtain a new version')
    log_path=str(c.get('log_path',os.path.join(str(c['output_dir']),str(c['project_id'])+'_step07_01.log')))
    handle=os.fdopen(os.open(log_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_BINARY),'wb')
    class Tee(object):
        def __init__(self,original):self.original=original
        def write(self,text):
            raw=text.encode('utf-8') if isinstance(text,unicode) else text
            handle.write(raw);handle.flush()
            self.original.write(text)
        def flush(self):
            handle.flush()
            if hasattr(self.original,'flush'):self.original.flush()
    try:
        sys.stdout=Tee(old_out);sys.stderr=Tee(old_err)
        print('STEP07-1 START: '+str(c['project_id']))
        print('EXECUTION MODE: '+str(c.get('execution_mode','INDEPENDENT_CAE')))
        print('DISK INPUT (unused in current-session mode): '+str(c['input_cae']))
        print('OUTPUT: '+str(c['output_cae']))
        # Preserve the accepted report if this single-use script is run again.
        if os.path.exists(str(c['output_cae'])):raise ValueError('OUTPUT_EXISTS: generate a fresh script; previous CAE/report preserved')
        result=run_step07_stage1(c)
        print('STEP07-1 COMPLETE: pending human review; no next stage')
        return result
    except Exception:
        traceback.print_exc();raise
    finally:
        sys.stdout=old_out;sys.stderr=old_err;handle.close();os.chdir(previous_dir)
