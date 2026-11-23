# -*- coding: utf-8 -*-
"""Planar physical-overlap Tie geometry, Abaqus 2020 / Python 2.7."""
import math,json,os,hashlib,shutil,traceback

def t4_dot(a,b):return sum([a[k]*b[k] for k in range(3)])
def t4_sub(a,b):return [a[k]-b[k] for k in range(3)]
def t4_cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def t4_unit(a):
    norm=math.sqrt(t4_dot(a,a));return [x/norm for x in a]
def t4_hull(points):
    pts=sorted(set([tuple(x) for x in points]))
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower=[];upper=[]
    for q in pts:
        while len(lower)>=2 and cross(lower[-2],lower[-1],q)<=1.e-12:lower.pop()
        lower.append(q)
    for q in reversed(pts):
        while len(upper)>=2 and cross(upper[-2],upper[-1],q)<=1.e-12:upper.pop()
        upper.append(q)
    return lower[:-1]+upper[:-1]
def t4_area(poly):return abs(sum([poly[k][0]*poly[(k+1)%len(poly)][1]-poly[(k+1)%len(poly)][0]*poly[k][1] for k in range(len(poly))]))/2.
def t4_clip(poly,clip):
    result=poly
    for j,a in enumerate(clip):
        b=clip[(j+1)%len(clip)];previous=result;result=[]
        def side(p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
        for k,p in enumerate(previous):
            q=previous[(k+1)%len(previous)];sp=side(p);sq=side(q)
            if sp>=-1.e-10:result.append(p)
            if (sp>1.e-10 and sq< -1.e-10) or (sp< -1.e-10 and sq>1.e-10):
                t=sp/(sp-sq);result.append([p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])])
        if len(result)<3:return []
    return t4_hull(result)
def t4_frame(normal):
    u=t4_unit(t4_cross(normal,[1.,0.,0.] if abs(normal[0])<.9 else [0.,1.,0.]));return u,t4_cross(normal,u)
def t4_faces(i):
    result=[]
    for f in i.faces:
        origin=f.pointOn[0];n=t4_unit(f.getNormal(point=origin));points=[i.vertices[k].pointOn[0] for k in f.getVertices()]
        if len(points)<3 or max([abs(t4_dot(t4_sub(p,origin),n)) for p in points])>2.e-6:continue
        result.append((f,origin,n,points))
    return result

def t4_candidates(m,solid,shell):
    a=m.rootAssembly;s=a.instances[solid];b=a.instances[shell];bp=m.parts[b.partName]
    if not len(m.parts[s.partName].cells) or len(bp.cells):raise ValueError('EXPECTED_SOLID_SHELL')
    if len(bp.sectionAssignments)!=1:raise ValueError('AMBIGUOUS_SHELL_SECTION')
    ass=bp.sectionAssignments[0];sec=m.sections[ass.sectionName];thickness=sec.thickness
    if abs(ass.offset)>1.e-12:raise ValueError('NONZERO_SHELL_OFFSET_REQUIRES_REVIEW')
    results=[]
    for sf,origin,n,sv in t4_faces(s):
        u,v=t4_frame(n);sp=t4_hull([[t4_dot(t4_sub(p,origin),u),t4_dot(t4_sub(p,origin),v)] for p in sv])
        for bf,bo,bn,bv in t4_faces(b):
            alignment=t4_dot(n,bn)
            if abs(alignment)<.99999:continue
            distance=t4_dot(t4_sub(bo,origin),n);gap=distance-thickness/2.
            if distance< -2.e-6 or abs(gap)>.00101:continue
            poly=t4_clip(sp,t4_hull([[t4_dot(t4_sub(p,origin),u),t4_dot(t4_sub(p,origin),v)] for p in bv]))
            if len(poly)<3 or t4_area(poly)<1.e-6:continue
            results.append(dict(solid=solid,shell=shell,solid_face=sf.index,shell_face=bf.index,origin=origin,normal=n,u=u,v=v,polygon=poly,outer_area=t4_area(poly),gap_m=gap,shell_thickness=thickness,shell_offset=ass.offset,shell_side=2 if alignment>0 else 1))
    return results

def t4_inverse(instance,point):
    pivot,axis,angle=instance.getRotation();translation=instance.getTranslation()
    q=[point[k]-translation[k] for k in range(3)]
    if abs(angle)>1.e-12:
        axis=t4_unit(axis);theta=-angle*math.pi/180.;c=math.cos(theta);s=math.sin(theta);cross=t4_cross(axis,q);d=t4_dot(axis,q)
        q=[q[k]*c+cross[k]*s+axis[k]*d*(1-c) for k in range(3)]
    return tuple(q)

def t4_inside(point,poly,tol=2.e-6):
    for j,p in enumerate(poly):
        q=poly[(j+1)%len(poly)];length=math.sqrt((q[0]-p[0])**2+(q[1]-p[1])**2)
        if ((q[0]-p[0])*(point[1]-p[1])-(q[1]-p[1])*(point[0]-p[0]))/length< -tol:return False
    return True

def t4_partition_side(m,c,side,partition=True):
    a=m.rootAssembly;i=a.instances[str(c[side])];p=m.parts[i.partName];n=c['normal'];u=c['u'];v=c['v'];origin=c['origin'];poly=c['polygon']
    # Every supporting plane is defined in physical assembly coordinates, then
    # transformed into the Part; no absolute face IDs survive regeneration.
    distance=0. if side=='solid' else c['gap_m']+c['shell_thickness']/2.
    plane_origin=[origin[k]+distance*n[k] for k in range(3)]
    features=[]
    for j,q in enumerate(poly if partition else []):
        end=poly[(j+1)%len(poly)]
        start3=[plane_origin[k]+q[0]*u[k]+q[1]*v[k] for k in range(3)]
        end3=[plane_origin[k]+end[0]*u[k]+end[1]*v[k] for k in range(3)]
        third=[start3[k]+n[k] for k in range(3)]
        cutnormal=t4_unit(t4_cross(t4_sub(end3,start3),n));targets=[]
        for face,fo,fn,points in t4_faces(i):
            if abs(t4_dot(fn,n))<.99999 or abs(t4_dot(t4_sub(fo,plane_origin),n))>2.e-6:continue
            values=[t4_dot(t4_sub(x,start3),cutnormal) for x in points]
            if min(values)<-2.e-6 and max(values)>2.e-6:targets.append(p.faces[face.index])
        if targets:
            datum=p.DatumPlaneByThreePoints(point1=t4_inverse(i,start3),point2=t4_inverse(i,end3),point3=t4_inverse(i,third))
            f=p.PartitionFaceByDatumPlane(faces=tuple(targets),datumPlane=p.datums[datum.id]);features.append(f.name);a.regenerate();i=a.instances[str(c[side])]
    selected=[]
    for face,fo,fn,points in t4_faces(i):
        if abs(t4_dot(fn,n))<.99999 or abs(t4_dot(t4_sub(fo,plane_origin),n))>2.e-6:continue
        projected=[[t4_dot(t4_sub(x,origin),u),t4_dot(t4_sub(x,origin),v)] for x in points]
        if all([t4_inside(q,poly) for q in projected]):selected.append(face)
    if not selected:raise ValueError('TIE_PATCH_EMPTY: '+c[side])
    area=sum([f.getSize(printResults=False) for f in selected])
    if area>c['outer_area']+2.e-7:raise ValueError('TIE_PATCH_EXCEEDS_FOOTPRINT')
    return tuple(selected),features,area

def t4_apply(m,summary,report):
    from abaqusConstants import ON,OFF,SPECIFIED,SURFACE_TO_SURFACE
    a=m.rootAssembly
    if any([type(s).__name__=='ConnectorSection' for s in m.sections.values()]):raise ValueError('REQUIRES_FRESH_HOLE_ONLY_MODEL')
    if any([n.startswith(('STEP06_COUPLING_','STEP06_RP_','STEP06_WIRE_')) for repo in (m.constraints,a.features,a.sets) for n in repo.keys()]):raise ValueError('STEP06_CONNECTION_OBJECT_PRESENT')
    if any([len(p.nodes) or len(p.elements) for p in m.parts.values()]):raise ValueError('TIE_PATCH_REQUIRES_UNMESHED_FRESH_MODEL')
    if any([n.startswith('STEP07_TIE_') for n in m.constraints.keys()]):raise ValueError('TIE_ALREADY_EXISTS')
    rows=summary['instances'];supports=[r['instance_name'] for r in rows if r['canonical_role']=='PURLIN_SUPPORT'];purlins=[r['instance_name'] for r in rows if r['canonical_role']=='PURLIN_LOCAL'];beams=[r['instance_name'] for r in rows if r['canonical_role']=='INCLINED_BEAM'];hoops=[r['instance_name'] for r in rows if r['canonical_role']=='HOOP'];braces=[r['instance_name'] for r in rows if r['canonical_role'] in ('BRACE_FRONT','BRACE_REAR')]
    pairs=[]
    for solid,targets,family in [(s,purlins,'PURLIN_SUPPORT') for s in supports]+[(s,beams,'SUPPORT_BEAM') for s in supports]+[(h,braces,'HOOP_BRACE') for h in hoops]:
        for shell in targets:
            for c in t4_candidates(m,str(solid),str(shell)):c['family']=family;pairs.append(c)
    for s in supports:
        for family in ['PURLIN_SUPPORT','SUPPORT_BEAM']:
            if len([c for c in pairs if c['solid']==s and c['family']==family])!=1:raise ValueError('SUPPORT_PAIR_AMBIGUOUS_OR_MISSING: '+s)
    for b in braces:
        if not any([c['shell']==b and c['family']=='HOOP_BRACE' for c in pairs]):raise ValueError('BRACE_NOT_CONNECTED: '+b)
    existing=t4_existing(m)
    report['pairs']=pairs;old_constraints=set(m.constraints.keys());old_rps=set(a.referencePoints.keys());old_bcs=set(m.boundaryConditions.keys())
    # Partition all footprints before creating surfaces. Shared Parts are handled
    # once per physical cut; the selected member IDs are re-resolved afterwards.
    report['partitions']=[]
    for c in pairs:
        for side in ['solid','shell']:
            faces,features,area=t4_partition_side(m,c,side)
            report['partitions'].append(dict(instance=c[side],features=features,area=area))
    used_slave=set()
    for index,c in enumerate(pairs):
        solid,_,sa=t4_partition_side(m,c,'solid',False);shell,_,ba=t4_partition_side(m,c,'shell',False)
        if sa>ba+2.e-7:raise ValueError('SOLID_SLAVE_AREA_EXCEEDS_SHELL_MASTER: '+str((sa,ba)))
        for face in solid:
            key=(c['solid'],face.index)
            if key in used_slave:raise ValueError('DUPLICATE_SLAVE_FACE')
            used_slave.add(key)
        stem='STEP07_TIE_'+c['solid']+'__'+c['shell'];slave_name=stem+'_SOLID';master_name=stem+'_SHELL'
        # Solid slaves avoid tying a shell node twice where two hoop halves
        # sandwich a brace. Existing Step05 secondary regions checked below.
        for name,obj in m.constraints.items():
            for field in ('slave','surface'):
                if not hasattr(obj,field):continue
                value=getattr(obj,field);key=str(value[0])
                repo=a.surfaces if key in list(a.surfaces.keys()) else a.sets
                if key not in list(repo.keys()):raise ValueError('EXISTING_REGION_MISSING')
                r=repo[key]
                if any([f.instanceName==c['solid'] and f.index in [q.index for q in solid] for f in r.faces]):raise ValueError('EXISTING_SLAVE_OR_COUPLING_OVERLAP: '+name)
        report['active_pair']=dict(name=stem,solid_indices=[f.index for f in solid],shell_indices=[f.index for f in shell])
        solids=a.instances[str(c['solid'])].faces[0:0]
        for f in solid:solids=solids+a.instances[str(c['solid'])].faces[f.index:f.index+1]
        slave=a.Surface(name=slave_name,side1Faces=solids)
        shells=a.instances[str(c['shell'])].faces[0:0]
        for f in shell:shells=shells+a.instances[str(c['shell'])].faces[f.index:f.index+1]
        kw={'side1Faces':shells} if c['shell_side']==1 else {'side2Faces':shells}
        master=a.Surface(name=master_name,**kw)
        tolerance=max(2.e-6,abs(c['gap_m'])+2.e-6)
        m.Tie(name=stem,master=master,slave=slave,positionToleranceMethod=SPECIFIED,positionTolerance=tolerance,
              adjust=OFF,tieRotations=ON,thickness=ON,constraintEnforcement=SURFACE_TO_SURFACE)
        c.update(name=stem,master=master_name,slave=slave_name,solid_faces=[f.index for f in solid],shell_faces=[f.index for f in shell],solid_area=sa,shell_area=ba,tolerance_m=tolerance,adjust=False)
    if set(a.referencePoints.keys())!=old_rps or set(m.boundaryConditions.keys())!=old_bcs:raise ValueError('RP_OR_BC_CHANGED')
    for name in old_constraints:
        if name not in m.constraints:raise ValueError('OLD_CONSTRAINT_LOST')
    report['new_ties']=len(set(m.constraints.keys())-old_constraints)
    report['existing_before']=existing;report['existing_after']=t4_existing(m)
    if report['existing_after']!=existing:raise ValueError('EXISTING_GEOMETRY_OR_CONNECTION_CHANGED')
    report['graph']=t4_graph(m)
    if not report['graph']['all_connected']:raise ValueError('DISCONNECTED_COMPONENTS')





def t4_existing(m):
    a=m.rootAssembly;result=dict(constraints={},regions={},parts={})
    for name,c in m.constraints.items():
        if name.startswith('STEP07_TIE_'):continue
        result['constraints'][name]={}
        for key in ('master','slave','controlPoint','surface','couplingType','u1','u2','u3','ur1','ur2','ur3','adjust','positionTolerance','positionToleranceMethod','tieRotations','thickness','suppressed'):
            if hasattr(c,key):result['constraints'][name][key]=str(getattr(c,key))
    for category,repo in [('set',a.sets),('surface',a.surfaces)]:
        for name,r in repo.items():
            if name.startswith('STEP07_TIE_'):continue
            result['regions'][category+':'+name]=dict(area=round(sum([f.getSize(printResults=False) for f in r.faces]),8),edge_length=round(sum([e.getSize(printResults=False) for e in r.edges]),8),instances=sorted(set([getattr(x,'instanceName','') for x in list(r.faces)+list(r.edges)])))
    for name,p in m.parts.items():
        result['parts'][name]=dict(area=round(sum([f.getSize(printResults=False) for f in p.faces]),8),volume=round(sum([c.getSize(printResults=False) for c in p.cells]),10),sections=[(s.sectionName,str(s.region),s.offset,str(s.offsetType)) for s in p.sectionAssignments])
    return result

def t4_graph(m):
    a=m.rootAssembly;edges=[];controls={}
    def members(value):
        key=str(value[0]);r=a.surfaces[key] if key in list(a.surfaces.keys()) else a.sets[key]
        if not (len(r.faces) or len(r.edges)):raise ValueError('EMPTY_CONNECTION_REGION: '+key)
        return set([getattr(x,'instanceName','') for x in list(r.faces)+list(r.edges)])
    for name,c in m.constraints.items():
        if c.suppressed:raise ValueError('SUPPRESSED_CONNECTION: '+name)
        if hasattr(c,'master') and hasattr(c,'slave'):
            x=members(c.master);y=members(c.slave)
            for s in x:
                for t in y:edges.append((s,t,name))
        elif hasattr(c,'controlPoint') and hasattr(c,'surface'):
            controls.setdefault(str(c.controlPoint),set()).update(members(c.surface))
    for key,group in controls.items():
        for s in group:
            for t in group:
                if s!=t:edges.append((s,t,key))
    components=[];remaining=set(a.instances.keys())
    while remaining:
        found=set([next(iter(remaining))]);changed=True
        while changed:
            changed=False
            for s,t,_ in edges:
                if (s in found or t in found) and not set([s,t]).issubset(found):found.update([s,t]);changed=True
        components.append(sorted(found));remaining-=found
    return dict(components=components,edges=edges,all_connected=len(components)==1,scope='geometric constraint graph, not solver rank verification')

def t4_run(c):
    import abaqus,part,assembly,interaction,load,step,section,mesh,job,sys
    for key in ('output_cae','report_path','log_path','backup_cae'):
        if os.path.exists(str(c[key])):raise ValueError('OUTPUT_EXISTS: regenerate a new version')
    db=abaqus.mdb
    if os.path.normcase(os.path.abspath(str(db.pathName)))!=os.path.normcase(os.path.abspath(str(c['working_copy']))):raise ValueError('OPEN_SUPPLIED_FRESH_WORKING_COPY_FIRST: '+str(c['working_copy']))
    if hashlib.sha256(open(str(c['input_cae']),'rb').read()).hexdigest()!=c['input_sha256']:raise ValueError('INPUT_CHANGED')
    report=dict(status='RUNNING',connection_mode='tie_only',project_id=c['project_id'],input_cae=c['input_cae'],output_cae=c['output_cae'],engineering_verified=False,solver_verified=False,loads_created=False)
    log=os.fdopen(os.open(str(c['log_path']),os.O_CREAT|os.O_EXCL|os.O_WRONLY),'w');old=sys.stdout;olderr=sys.stderr
    class Tee(object):
        def write(self,text):log.write(text);log.flush();old.write(text)
        def flush(self):log.flush()
    sys.stdout=Tee();sys.stderr=sys.stdout
    try:
        m=db.models[str(c['project_id'])]
        if c['summary']['structure_type']!='DP':raise ValueError('FIRST_VALIDATION_SCOPE_DP_ONLY')
        if any([type(s).__name__=='ConnectorSection' for s in m.sections.values()]):raise ValueError('OLD_CONNECTOR_MODEL_FORBIDDEN')
        db.saveAs(pathName=str(c['backup_cae']));report['recovery_cae']=c['backup_cae']
        t4_apply(m,c['summary'],report)
        if os.path.exists(str(c['output_cae'])):raise ValueError('OUTPUT_EXISTS')
        db.saveAs(pathName=str(c['output_cae']))
        report['source_unchanged']=hashlib.sha256(open(str(c['input_cae']),'rb').read()).hexdigest()==c['input_sha256']
        if not report['source_unchanged']:raise ValueError('INPUT_CHANGED')
        if abaqus.mdb is not db:raise ValueError('CURRENT_MDB_REPLACED')
        report['status']='TIE_SETUP_COMPLETE_PENDING_MESH_AND_SOLVER'
        report['warnings']=['All-Tie is an infinitely bonded connection simplification, not bolt/contact stiffness validation.',
            'Shell physical thickness overlaps: purlin about 0.9 mm, brace about 1 mm. adjust=OFF preserves geometry; thickness=ON. No contact or preload created.',
            'Fresh hole-only input is unmeshed. Reapply accepted step/BC rules and regenerate mesh on this branch before loads and solver validation.',
            'Constraint graph connectivity is not proof of solver rank or successful Tie enforcement at mesh nodes.']
    except Exception:
        report['status']='FAILED_NOT_RELEASED';report['error']=traceback.format_exc();print(report['error'])
    finally:
        with open(str(c['report_path']),'w') as f:json.dump(report,f,indent=2)
        sys.stdout=old;sys.stderr=olderr;log.close()
    if report['status'].startswith('FAILED'):raise RuntimeError('Tie setup failed; reopen recovery copy; inspect '+str(c['report_path']))
    return report
