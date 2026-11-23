# SP_DC Part-once reference/count audit. Python 2.7. No geometry algorithm changes.
_spdc_base_prepare = s6h_prepare
_spdc_base_execute = s6h_execute


def spdc_geometry_signature(part):
    vertices=[]
    for vertex in part.vertices:vertices.append(list(point3(vertex)))
    faces=[]
    for face in part.faces:
        center=list(point3(face.getCentroid()))
        normal=list(face.getNormal(point=face.pointOn[0]))
        faces.append([float(face.getSize(printResults=False))]+center+normal+list(face.pointOn[0]))
    edges=[]
    for edge in part.edges:edges.append([float(edge.getSize(printResults=False))]+list(edge.pointOn[0]))
    return dict(volume=[[s6h_volume(part)]],vertices=sorted(vertices),faces=sorted(faces),edges=sorted(edges))


def spdc_close_vectors(a,b,tolerance):
    if len(a)!=len(b):return False
    for x,y in zip(a,b):
        if abs(x-y)>tolerance:return False
    return True


def spdc_validate_prototype(plan,model,report):
    hp=plan['hoop_hole_plan'];evidence=hp.get('prototype_inheritance')
    if not evidence:return
    source=resolve_repository_item(model.parts,evidence['source_part'],'HOOP prototype Part')
    target=resolve_repository_item(model.parts,evidence['target_part'],'HOOP target Part')
    if source.name==target.name or evidence.get('local_mapping')!='IDENTITY':
        raise ValueError('SPDC_PROTOTYPE_MAPPING_AMBIGUOUS')
    left,right=spdc_geometry_signature(source),spdc_geometry_signature(target)
    for key in ('volume','vertices','faces','edges'):
        if len(left[key])!=len(right[key]):raise ValueError('SPDC_PROTOTYPE_ACTUAL_GEOMETRY_MISMATCH: '+key)
        tolerance=1.e-11 if key=='volume' else 1.e-7
        for a,b in zip(left[key],right[key]):
            if not spdc_close_vectors(a,b,tolerance):raise ValueError('SPDC_PROTOTYPE_ACTUAL_GEOMETRY_MISMATCH: '+key)
    source_holes=[];target_holes=[]
    for hole in hp['driving_holes']:
        h=dict(hole);h['part_name']='PROTOTYPE'
        if hole['part_name']==source.name:source_holes.append(h)
        elif hole['part_name']==target.name:target_holes.append(h)
    if spdc_pattern_key(source_holes)!=spdc_pattern_key(target_holes):
        raise ValueError('SPDC_PROTOTYPE_PATTERN_MISMATCH')
    result=dict(actual_geometry_status='PASS',assembly_transform_status='PREFLIGHT',global_hole_mapping=[],
                source_part=source.name,target_part=target.name,geometry_checks=['volume','vertices','faces','edges'])
    report['prototype_inheritance']=result
    report['prototype_plan']=evidence
    seen=set()
    for pair in evidence['pairs']:
        rotation=pair['pair_rotation']
        if abs(abs(float(rotation['angle_deg']))%360.-180.)>1.e-7:
            raise ValueError('SPDC_PROTOTYPE_SYMMETRY_UNCONFIRMED')
        for side,part in (('source',source),('target',target)):
            name=pair[side+'_instance'];placement=pair[side+'_placement']
            if name in seen:raise ValueError('SPDC_PROTOTYPE_DUPLICATE_INSTANCE')
            seen.add(name)
            instance=resolve_repository_item(model.rootAssembly.instances,name,'HOOP prototype instance')
            if instance.partName!=part.name or len(instance.vertices)!=len(part.vertices):
                raise ValueError('SPDC_PROTOTYPE_INSTANCE_GEOMETRY_MISMATCH: '+name)
            # Native dependent vertex correspondence is validation evidence only,
            # never a persistent face/edge selection. Ambiguous correspondence fails.
            for local in part.vertices:
                expected=step04_local_point_to_global(point3(local),placement)
                actual=point3(instance.vertices[local.index])
                if not spdc_close_vectors(actual,expected,1.e-6):
                    raise ValueError('SPDC_PROTOTYPE_ACTUAL_PLACEMENT_MISMATCH: '+name)
        for hole in source_holes:
            local=hole['local_center_m']
            ga=step04_local_point_to_global(local,pair['source_placement'])
            gb=step04_local_point_to_global(local,pair['target_placement'])
            expected=_step04_rotate(ga,rotation)
            if not spdc_close_vectors(gb,expected,1.e-7):raise ValueError('SPDC_PROTOTYPE_GLOBAL_HOLE_MISMATCH')
            result['global_hole_mapping'].append(dict(group_id=pair['group_id'],hole_id=hole['hole_id'],
                source_global_center=ga,target_global_center=gb,status='PASS'))
    required=set()
    for m in hp['instance_mapping']:required.add(m['instance_name'])
    if seen!=required:raise ValueError('SPDC_PROTOTYPE_MAPPING_INCOMPLETE')
    result['assembly_transform_status']='PASS'


def spdc_post_prototype(model,report):
    evidence=report.get('prototype_plan')
    if not evidence:return
    holes=[]
    for p in report['part_patterns']:
        if p['part_name']==evidence['source_part']:holes=p['hole_pattern']
    checks=[]
    report['prototype_inheritance']['global_hole_geometry_status']='FAIL'
    for pair in evidence['pairs']:
        for side in ('source','target'):
            name=pair[side+'_instance'];placement=pair[side+'_placement']
            instance=resolve_repository_item(model.rootAssembly.instances,name,'HOOP cut instance')
            for h in holes:
                center=h['local_center_m'];thickness=2.*center[1]
                for fraction in (.001,.5,.999):
                    for offset,normal in hoop_boundary_probes(h):
                        local=(center[0]+offset[0],thickness*fraction,center[2]+offset[1])
                        point=step04_local_point_to_global(local,placement)
                        face=instance.faces.findAt(coordinates=point,printWarning=False)
                        expected=step04_local_vector_to_global((-normal[0],0.,-normal[1]),placement)
                        if not spdc_close_vectors(vector3(face.getNormal(point=point)),expected,1.e-5):
                            raise ValueError('SPDC_PROTOTYPE_GLOBAL_HOLE_WALL_MISMATCH: '+name+' '+h['hole_id'])
                checks.append(dict(instance_name=name,hole_id=h['hole_id'],status='PASS',
                    global_center=step04_local_point_to_global(center,placement)))
    report['prototype_inheritance']['global_hole_geometry_checks']=checks
    report['prototype_inheritance']['global_hole_geometry_status']='PASS'


def spdc_pattern_key(holes):
    result=[]
    for h in sorted(holes,key=lambda x:x['hole_id']):
        item={}
        for k,v in h.items():
            if k!='shared_part_info':item[k]=v
        result.append(item)
    return json.dumps(result,sort_keys=True)


def s6h_prepare(plan, model, report):
    hp=plan['hoop_hole_plan']
    if hp.get('spdc_part_schema')!='spdc-part-inheritance-v1':
        raise ValueError('SPDC_HOOP_PART_EVIDENCE_REQUIRED: regenerate current Plan')
    patterns={}
    for p in hp['part_patterns']:
        name=p['part_name']
        if name in patterns:raise ValueError('SPDC_HOOP_DUPLICATE_PART_PATTERN: '+name)
        patterns[name]=p
    if set(patterns)!=set(hp['part_geometry']):raise ValueError('SPDC_HOOP_PART_COVERAGE_MISMATCH')
    groups,seen={},set()
    for m in hp['instance_mapping']:
        name,part,g=m['instance_name'],m['part_name'],m['group_id']
        if name in seen or part not in patterns or not g:raise ValueError('SPDC_HOOP_REFERENCE_MISMATCH: '+name)
        if m.get('hole_pattern_override') or m.get('requires_instance_isolation'):
            raise ValueError('PART_PATTERN_VARIATION_REQUIRES_ISOLATION: '+name+' '+part)
        actual=resolve_repository_item(model.rootAssembly.instances,name,'SPDC HOOP Instance')
        if actual.partName!=part:raise ValueError('SPDC_HOOP_INSTANCE_PART_MISMATCH: '+name)
        seen.add(name);groups.setdefault(g,[]).append(m)
    counts=dict(unique_hoop_parts=len(patterns),unique_part_cut_count=0,hoop_group_count=len(groups),
                half_instance_count=len(seen),assembly_instance_hole_count=0)
    for name,p in patterns.items():
        holes=[]
        for hole in hp['driving_holes']:
            if hole['part_name']==name:holes.append(hole)
        if spdc_pattern_key(holes)!=spdc_pattern_key(p['hole_pattern']) or len(holes)!=p['expected_cut_features']:
            raise ValueError('PART_PATTERN_VARIATION_REQUIRES_ISOLATION: '+name+' inconsistent Part pattern')
        refs=[]
        for m in hp['instance_mapping']:
            if m['part_name']==name:refs.append(m['instance_name'])
        if sorted(refs)!=sorted(p['referencing_instances']):raise ValueError('SPDC_HOOP_REFERENCE_MISMATCH: '+name)
        part=resolve_repository_item(model.parts,name,'SPDC HOOP Part')
        s6a_references(model.rootAssembly,part,refs)
        counts['unique_part_cut_count']+=len(holes)
        counts['assembly_instance_hole_count']+=len(holes)*len(refs)
    if counts!=hp['expected_counts']:raise ValueError('SPDC_HOOP_COUNT_MISMATCH: Plan expected counts')
    spdc_validate_prototype(plan,model,report)
    report['expected_counts']=counts
    report['instance_mapping']=hp['instance_mapping']
    report['part_patterns']=hp['part_patterns']
    report['groups']=[]
    for g in sorted(groups):
        expected=0
        for m in groups[g]:expected+=patterns[m['part_name']]['expected_cut_features']
        report['groups'].append(dict(group_id=g,expected_holes=expected,actual_holes=0,instances=[]))
    prepared=_spdc_base_prepare(plan,model,report)
    for part,holes,geometry,entry in prepared:
        entry['expected_cut_features']=len(holes);entry['actual_cut_features']=0
    return prepared


def s6h_execute(model, prepared, report):
    try:
        _spdc_base_execute(model,prepared,report)
        spdc_post_prototype(model,report)
    finally:
        entries={}
        for p,h,g,e in prepared:
            e['actual_cut_features']=e['created_holes'];entries[e['part_name']]=e
        report['unique_part_cut_count']=0
        for e in entries.values():report['unique_part_cut_count']+=e['actual_cut_features']
        report['assembly_instance_hole_count']=0
        expected_by_part={}
        for p in report['part_patterns']:expected_by_part[p['part_name']]=p['expected_cut_features']
        for group in report['groups']:
            group['actual_holes']=0;group['instances']=[]
            for m in report['instance_mapping']:
                if m['group_id']!=group['group_id']:continue
                entry=entries.get(m['part_name'],{})
                actual=entry.get('created_holes',0) if entry.get('assembly_inheritance_status')=='PASS' else 0
                group['instances'].append(dict(instance_name=m['instance_name'],part_name=m['part_name'],
                    expected_holes=expected_by_part[m['part_name']],actual_holes=actual))
                group['actual_holes']+=actual
                report['assembly_instance_hole_count']+=actual
        for key in ('hoop_group_count','half_instance_count','unique_hoop_parts'):report[key]=report['expected_counts'][key]
    mismatch=False
    for g in report['groups']:
        if g['actual_holes']!=g['expected_holes']:mismatch=True
    for e in entries.values():
        if e['actual_cut_features']!=e['expected_cut_features']:mismatch=True
    for k,v in report['expected_counts'].items():
        if report[k]!=v:mismatch=True
    if mismatch:
        report['status']='FAILED'
        raise ValueError('SPDC_HOOP_COUNT_MISMATCH: post-cut counts')
