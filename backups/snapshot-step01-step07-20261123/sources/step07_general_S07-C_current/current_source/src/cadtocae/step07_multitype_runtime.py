# -*- coding: utf-8 -*-
"""Multi-role planar Tie adapter. Reuses validated DP geometry primitives."""
def s8_plan(m,c):
    rows=c['assembly_summary']['instances'];pairs={};roles={}
    for row in rows:roles[str(row['instance_name'])]=str(row['canonical_role'])
    for solid,role in roles.items():
        targets=('PURLIN_LOCAL','INCLINED_BEAM') if role=='PURLIN_SUPPORT' else (('BRACE_FRONT','BRACE_REAR','COLUMN_FRONT','COLUMN_REAR') if role=='HOOP' else ())
        for shell,target in roles.items():
            if target not in targets:continue
            patches=t4_candidates(m,solid,shell)
            if patches:
                family=('PURLIN_SUPPORT' if target=='PURLIN_LOCAL' else 'SUPPORT_BEAM') if role=='PURLIN_SUPPORT' else ('HOOP_BRACE' if target.startswith('BRACE_') else 'HOOP_'+target)
                pairs[(solid,shell)]=dict(solid=solid,shell=shell,family=family,patches=patches)
    for name,role in roles.items():
        if role=='PURLIN_SUPPORT':
            for target in ('PURLIN_LOCAL','INCLINED_BEAM'):
                if len([x for x in pairs.values() if x['solid']==name and roles[x['shell']]==target])!=1:raise ValueError('SUPPORT_PAIR_MISSING_OR_AMBIGUOUS: '+name+' '+target)
        if role=='HOOP' and not any([x['solid']==name for x in pairs.values()]):raise ValueError('HOOP_HAS_NO_PHYSICAL_PAIR: '+name)
        if role.startswith('BRACE_') or (c['summary']['structure_type']=='SP_DC' and role in ('COLUMN_FRONT','COLUMN_REAR')):
            if not any([x['shell']==name and roles[x['solid']]=='HOOP' for x in pairs.values()]):raise ValueError('REQUIRED_HOOP_PAIR_MISSING: '+name)
    for pair in pairs.values():
        if pair['family']=='HOOP_BRACE':s8_user_hoop_brace(m,c,pair)
    return [pairs[k] for k in sorted(pairs)]

def s8_pair_ties(m,pair):
    result=[];a=m.rootAssembly
    for name,obj in m.constraints.items():
        if type(obj).__name__!='Tie':continue
        master=m3_region(a,obj.master);slave=m3_region(a,obj.slave)
        x=set([f.instanceName for f in master.faces]);y=set([f.instanceName for f in slave.faces])
        if (x==set([pair['shell']]) and y==set([pair['solid']])) or (y==set([pair['shell']]) and x==set([pair['solid']])):
            if obj.suppressed:raise ValueError('EXISTING_PAIR_TIE_SUPPRESSED: '+name)
            result.append((name,obj,master if pair['solid'] in x else slave,slave if pair['solid'] in x else master))
    if len(result)>1:raise ValueError('DUPLICATE_PAIR_TIE: '+str((pair['solid'],pair['shell'])))
    return result

def s8_expected_faces(m,pair):
    selected={'solid':{},'shell':{}}
    for side in ('solid','shell'):
        for patch in pair.get('selection_patches',{}).get(side,pair['patches']):
            faces,_,area=t4_partition_side(m,patch,side,False)
            for f in faces:selected[side][f.index]=f
    return selected

def s8_validate_pair(m,pair):
    ties=s8_pair_ties(m,pair)
    if not ties:raise ValueError('MISSING_TIE: '+pair['solid']+' '+pair['shell'])
    name,obj,solid,shell=ties[0];expected={}
    if str(obj.thickness)!='ON' or str(obj.tieRotations)!='ON':raise ValueError('TIE_THICKNESS_ROTATION_CONFLICT: '+name)
    if pair.get('region_rule'):
        selected=s8_expected_faces(m,pair)
        if set([f.index for f in solid.faces])!=set(selected['solid']) or set([f.index for f in shell.faces])!=set(selected['shell']):raise ValueError('USER_DEFINED_TIE_REGION_MISMATCH: '+name+'; restore a pre-Tie base model')
        return dict(name=name,solid=pair['solid'],shell=pair['shell'],family=pair['family'],region_rule=pair['region_rule'],solid_faces=sorted(selected['solid']),shell_faces=sorted(selected['shell']),solid_area=sum([f.getSize(printResults=False) for f in solid.faces]),shell_area=sum([f.getSize(printResults=False) for f in shell.faces]),mesh_tie_enforcement='PENDING_INP_OR_SOLVER_CHECK')
    for side,region,other in [('solid',solid,shell),('shell',shell,solid)]:
        opposite='shell' if side=='solid' else 'solid'
        ids=set([f.index for f in region.faces]);other_ids=set([f.index for f in other.faces])
        allowed=set([x[side+'_face'] for x in pair['patches']])
        if not ids or not ids.issubset(allowed):raise ValueError('EXISTING_TIE_NONCONTACT_FACE: '+name)
        for f in region.faces:
            coverage=sum([x['outer_area'] for x in pair['patches'] if x[side+'_face']==f.index and x[opposite+'_face'] in other_ids])
            if side=='solid' and f.getSize(printResults=False)>coverage+2.e-7:raise ValueError('TIE_FACE_EXCEEDS_PHYSICAL_OVERLAP: '+name+' '+side+' face='+str(f.index)+' area='+str(f.getSize(printResults=False))+' coverage='+str(coverage))
        if side=='shell':
            # A shell master may span a bolt-hole void in its solid slave.
            # Bound it by the joint footprint, not by the net metal area.
            base=pair['patches'][0];poly=[]
            for patch in pair['patches']:
                for q in patch['polygon']:
                    point=[patch['origin'][k]+q[0]*patch['u'][k]+q[1]*patch['v'][k] for k in range(3)]
                    poly.append([t4_dot(t4_sub(point,base['origin']),axis) for axis in (base['u'],base['v'])])
            hull=t4_hull(poly)
            for face,origin,normal,points in t4_faces(m.rootAssembly.instances[str(pair['shell'])]):
                if face.index not in ids:continue
                if not all([t4_inside([t4_dot(t4_sub(point,base['origin']),axis) for axis in (base['u'],base['v'])],hull) for point in points]):raise ValueError('SHELL_MASTER_EXCEEDS_JOINT_FOOTPRINT: '+name)
        expected[side]=ids
    if str(obj.thickness)!='ON' or str(obj.tieRotations)!='ON':raise ValueError('TIE_THICKNESS_ROTATION_CONFLICT: '+name)
    return dict(name=name,solid=pair['solid'],shell=pair['shell'],family=pair['family'],solid_faces=sorted(expected['solid']),shell_faces=sorted(expected['shell']),solid_area=sum([f.getSize(printResults=False) for f in solid.faces]),shell_area=sum([f.getSize(printResults=False) for f in shell.faces]))

def s8_verify(m,c):
    pairs=s8_plan(m,c);verified=[s8_validate_pair(m,p) for p in pairs];counts={}
    for pair in verified:counts[pair['family']]=counts.get(pair['family'],0)+1
    graph=t4_graph(m)
    if not graph['all_connected']:raise ValueError('DISCONNECTED_CONSTRAINT_GRAPH')
    return dict(pairs=verified,count=len(verified),families=counts,graph=graph,scope='Physical overlap and geometry membership; not solver enforcement verification')

def s8_preflight(m,c):
    pairs=s8_plan(m,c)
    for p in pairs:
        if s8_pair_ties(m,p):s8_validate_pair(m,p)
    # Reject shared physical slave area before partitioning or model changes.
    patches=[]
    for p in pairs:patches+=p['patches']
    for j,a in enumerate(patches):
        for b in patches[j+1:]:
            if a['solid']!=b['solid'] or a['solid_face']!=b['solid_face'] or a['shell']==b['shell']:continue
            points=[[b['origin'][k]+q[0]*b['u'][k]+q[1]*b['v'][k] for k in range(3)] for q in b['polygon']]
            poly=[[t4_dot(t4_sub(q,a['origin']),axis) for axis in (a['u'],a['v'])] for q in points]
            intersection=t4_clip(a['polygon'],t4_hull(poly))
            if len(intersection)>2 and t4_area(intersection)>1.e-10:raise ValueError('OVERLAPPING_PHYSICAL_TIE_PATCHES: '+a['solid'])
    return dict(pairs=pairs,count=len(pairs))

def s8_apply(m,c,r):
    from abaqusConstants import ON,OFF,SPECIFIED,SURFACE_TO_SURFACE
    before=t4_existing(m);a=m.rootAssembly;pairs=s8_plan(m,c);r['connection_families']={};r['new_ties']=0;r['partitions']=[]
    for p in pairs:
        family=r['connection_families'].setdefault(p['family'],dict(expected=0,existing=0,created=0,failed=[]));family['expected']+=1
        if s8_pair_ties(m,p):s8_validate_pair(m,p);family['existing']+=1;p['existing']=True
        else:
            p['existing']=False
            for side in ('solid','shell'):
                for patch in p.get('selection_patches',{}).get(side,p['patches']):
                    _,features,area=t4_partition_side(m,patch,side)
                    r['partitions'].append(dict(instance=patch[side],features=features,area=area))
    used=set()
    for p in pairs:
        if p['existing']:continue
        faces=s8_expected_faces(m,p)
        for f in faces['solid'].values():
            key=(p['solid'],f.index)
            if key in used:raise ValueError('DUPLICATE_SLAVE_FACE')
            used.add(key)
        for name,obj in m.constraints.items():
            for field in ('slave','surface'):
                if not hasattr(obj,field):continue
                region=m3_region(a,getattr(obj,field))
                if any([f.instanceName==p['solid'] and f.index in faces['solid'] for f in region.faces]):raise ValueError('EXISTING_SLAVE_OR_COUPLING_OVERLAP: '+name)
        stem='STEP07_TIE_'+p['solid']+'__'+p['shell'];surfaces={}
        sides=set([x['shell_side'] for x in p['patches']])
        if len(sides)!=1:raise ValueError('MIXED_SHELL_SIDES: '+stem)
        for side,suffix in [('solid','_SOLID'),('shell','_SHELL')]:
            seq=a.instances[str(p[side])].faces[0:0]
            for idx in sorted(faces[side]):seq=seq+a.instances[str(p[side])].faces[idx:idx+1]
            kw='side1Faces' if side=='solid' or list(sides)[0]==1 else 'side2Faces'
            surfaces[side]=a.Surface(name=stem+suffix,**{kw:seq})
        tolerance=max([max(2.e-6,abs(x['gap_m'])+2.e-6) for x in p['patches']])
        m.Tie(name=stem,master=surfaces['shell'],slave=surfaces['solid'],positionToleranceMethod=SPECIFIED,positionTolerance=tolerance,adjust=OFF,tieRotations=ON,thickness=ON,constraintEnforcement=SURFACE_TO_SURFACE)
        r['new_ties']+=1;r['connection_families'][p['family']]['created']+=1
    if t4_existing(m)!=before:raise ValueError('EXISTING_GEOMETRY_OR_CONNECTION_CHANGED')
    r['tie_validation']=s8_verify(m,c);r['preservation']='PASS'
