# -*- coding: utf-8 -*-
"""Stage 3 only, appended to existing inspection functions; Abaqus Python 2.7."""

def m3_fields(obj,names):
    result={}
    for key in names:
        if hasattr(obj,key):result[key]=str(getattr(obj,key))
    return result


def m3_snapshot(db,c):
    result=s7_stage1_inventory(db,include_mesh=False)
    def strip(value):
        if isinstance(value,dict):
            for key in list(value.keys()):
                if key in ('nodes','elements'):del value[key]
                else:strip(value[key])
        elif isinstance(value,(list,tuple)):
            for v in value:strip(v)
    strip(result)
    m=db.models[str(c['project_id'])];a=m.rootAssembly
    result['step_values']=s7_stage1_values(m,c)
    result['bc_states']={}
    for st in m.steps.keys():
        data={}
        for name,state in m.steps[st].boundaryConditionStates.items():
            data[name]=m3_fields(state,('status','typeName','u1','u2','u3','ur1','ur2','ur3','u1State','u2State','u3State','ur1State','ur2State','ur3State'))
        result['bc_states'][st]=data
    result['bcs']={}
    for name,bc in m.boundaryConditions.items():result['bcs'][name]=m3_fields(bc,('region','localCsys','suppressed','distributionType','fieldName'))
    result['sections']={}
    for name,sec in m.sections.items():
        data=m3_fields(sec,('material','thickness','thicknessType','integrationRule','numIntPts','translationalType','rotationalType','assembledType','behaviorOptions'))
        data['behavior']=[]
        for behavior in getattr(sec,'behaviorOptions',[]):data['behavior'].append(m3_fields(behavior,('table','components','behavior','coupling','dependencies','temperatureDependency')))
        result['sections'][name]=data
    result['material_elastic']={}
    for name,material in m.materials.items():
        result['material_elastic'][name]=m3_fields(getattr(material,'elastic',None),('table','type','temperatureDependency','dependencies'))
    result['assignments']=[m3_fields(s,('sectionName','region','offset','offsetType','offsetField','thicknessAssignment','suppressed')) for s in a.sectionAssignments]
    result['connector_orientations']=[m3_fields(o,('region','localCsys1','localCsys2','axis1','axis2','angle1','angle2','orient2sameAs1','suppressed')) for o in a.connectorOrientations]
    result['part_orientations']={}
    for name,p in m.parts.items():
        result['part_orientations'][name]=dict(material=[m3_fields(o,('region','localCsys','axis','angle','orientationType','stackDirection','fieldName')) for o in p.materialOrientations],
            sections=[m3_fields(s,('sectionName','region','offset','offsetType','offsetField','thicknessAssignment','suppressed')) for s in p.sectionAssignments])
    return result


def m3_region(a,value):
    if hasattr(value,'faces'):return value
    key=str(value[0])
    # Abaqus 2020 repository membership can leave a pending Unknown key error
    # when a Surface name is tested against SetRepository. Compare key lists.
    if key in list(a.sets.keys()):return a.sets[key]
    if key in list(a.surfaces.keys()):return a.surfaces[key]
    raise ValueError('REGION_REFERENCE_MISSING: '+key)


def m3_connectors(m):
    a=m.rootAssembly;result=[];seen=set()
    for assignment in a.sectionAssignments:
        region=m3_region(a,assignment.region);section=m.sections[assignment.sectionName]
        if type(section).__name__!='ConnectorSection':raise ValueError('UNSUPPORTED_ASSEMBLY_SECTION')
        if assignment.suppressed:raise ValueError('SUPPRESSED_CONNECTOR_ASSIGNMENT')
        if not len(region.edges):raise ValueError('CONNECTOR_EMPTY_WIRE')
        vertices=[]
        for edge in region.edges:
            if edge.index in seen:raise ValueError('DUPLICATE_CONNECTOR_ASSIGNMENT')
            seen.add(edge.index);ids=edge.getVertices()
            if len(ids)!=2:raise ValueError('CONNECTOR_ENDPOINTS_NOT_TWO')
            vertices.append(list(ids))
        orientation=[o for o in a.connectorOrientations if str(o.region)==str(assignment.region) and not o.suppressed]
        if len(orientation)!=1:raise ValueError('CONNECTOR_ORIENTATION_MISSING_OR_AMBIGUOUS')
        result.append(dict(region=str(assignment.region),section=assignment.sectionName,wire_count=len(region.edges),
                           endpoints=vertices,representation='NONMESHABLE_ASSEMBLY_WIRE',expected_input_type='CONN3D2',input_write_verified=False))
    if len(a.edges)!=len(seen):raise ValueError('UNASSIGNED_ASSEMBLY_WIRE')
    return result


def m3_parts(m,c):
    a=m.rootAssembly;parts={};mapped=set();sizes=c['mesh_rules']['sizes']
    for row in c['assembly_summary']['instances']:
        name=str(row['instance_name']);role=row['canonical_role'];mapped.add(name)
        if name not in a.instances:raise ValueError('SUMMARY_INSTANCE_MISSING: '+name)
        i=a.instances[name]
        if not i.dependent:raise ValueError('INDEPENDENT_INSTANCE_REQUIRES_REVIEW: '+name)
        if role not in sizes:raise ValueError('UNSUPPORTED_COMPONENT_ROLE: '+role)
        p=m.parts[i.partName]
        if not len(p.faces):raise ValueError('UNSUPPORTED_WIRE_OR_ORPHAN_PART: '+p.name)
        if not p.sectionAssignments:raise ValueError('SECTION_MISSING: '+p.name)
        size=c['mesh_rules']['role_overrides'].get(role,sizes[role])
        if p.name not in parts:parts[p.name]=dict(roles=[],instances=[],nominal_size_m=sizes[role],size_m=size,kind='Solid' if len(p.cells) else 'Shell')
        d=parts[p.name];d['roles'].append(role);d['instances'].append(name);d['size_m']=min(d['size_m'],size)
        uniform=c['mesh_rules'].get('project_hoop_uniform_sizes',{}).get(c['project_id'],{}).get(name,c['mesh_rules'].get('project_hoop_uniform_sizes',{}).get(c['project_id'],{}).get(row.get('connection_group'))) if role=='HOOP' else None
        if role=='PURLIN_SUPPORT':uniform=c['mesh_rules'].get('project_support_uniform_sizes',{}).get(c['project_id'])
        if uniform:
            d['size_m']=min(d['size_m'],uniform);d['uniform_geometry_seed']=True
            d['size_exception_reason']='Project-specific uniform solid size; bounded local repair if required. Actual size and quality are recorded; not convergence-qualified.'
    if mapped!=set(a.instances.keys()):raise ValueError('UNMAPPED_ANALYSIS_INSTANCE')
    for name,d in parts.items():
        p=m.parts[name];h=d['size_m'];area=sum([f.getSize(printResults=False) for f in p.faces])
        volume=sum([cell.getSize(printResults=False) for cell in p.cells])
        estimate=2*area/h**2 if not len(p.cells) else max(8*volume/h**3,4*area/h**2)
        d.update(existing_nodes=len(p.nodes),existing_elements=len(p.elements),surface_area_m2=area,volume_m3=volume,
                 estimated_elements=int(math.ceil(estimate)),estimated_nodes=int(math.ceil(estimate*(2 if len(p.cells) else 1.3))))
    return parts


def m3_quality(p,c):
    from abaqusConstants import ANALYSIS_CHECKS,ASPECT_RATIO,SHAPE_FACTOR
    result={}
    for label,criterion,threshold in (('analysis',ANALYSIS_CHECKS,None),('aspect_ratio',ASPECT_RATIO,c['mesh_rules']['aspect_warning']),('shape_factor',SHAPE_FACTOR,c['mesh_rules']['shape_warning'])):
        raw=p.verifyMeshQuality(criterion=criterion) if threshold is None else p.verifyMeshQuality(criterion=criterion,threshold=threshold)
        data={}
        for key,value in raw.items():
            if key in ('failedElements','warningElements','naElements'):data[key]=[e.label for e in value]
            elif key=='worstElement':data[key]=value.label if value is not None else None
            else:data[key]=value
        data['threshold']=threshold;result[label]=data
    if result['analysis'].get('failedElements'):raise ValueError('ANALYSIS_MESH_QUALITY_FAILED: '+p.name+' '+str(result))
    if result['analysis'].get('naElements'):raise ValueError('ANALYSIS_QUALITY_NOT_EVALUATED: '+p.name)
    if result['shape_factor'].get('failedElements') and not (c.get('stage')==4 and c.get('summary',{}).get('structure_type')=='SP_DC'):
        raise ValueError('LOW_SHAPE_FACTOR_REQUIRES_REVIEW: '+p.name+' '+str(result['shape_factor']))
    return result


def m3_refinements(m,c,parts):
    """Semantic Step06 hole regions, plus geometric verification of reported hoop slots.

    Edge indices are recorded outcomes, never persistent selection rules.
    Ordinary surface boundaries, short edges and fillets are not refinement triggers.
    """
    result={};a=m.rootAssembly
    for pn in parts:result[pn]={};parts[pn]['refinement_regions']=[]
    for name,region in list(a.sets.items())+list(a.surfaces.items()):
        if not name.startswith('STEP06_') or 'HOLE' not in name:continue
        selected={}
        for kind in ('edges','faces'):
            for obj in getattr(region,kind,[]):
                pn=a.instances[obj.instanceName].partName;p=m.parts[pn]
                for index in ([obj.index] if kind=='edges' else obj.getEdges()):
                    try:radius=p.edges[index].getRadius()
                    except Exception:continue
                    if radius<=0:continue
                    result[pn][index]=c['mesh_rules']['local_size']
                    selected.setdefault(pn,set()).add(index)
        if not selected:raise ValueError('HOLE_REGION_HAS_NO_RELIABLE_ARCS: '+name)
        for pn,ids in selected.items():parts[pn]['refinement_regions'].append(dict(source=name,edges=sorted(ids),size_m=c['mesh_rules']['local_size'],reason='STEP06_NAMED_HOLE_ARCS'))
    if c.get('tie_boundary_simplification'):
        holes=list(c.get('hole_report',{}).get('inclined_beam',[]))+list(c.get('hole_report',{}).get('purlin_local',[]))
        for item in c.get('hole_report',{}).get('support',{}).get('created_hole_details',[]):
            h=dict(item);h.update(target_part=item['part'],local_center=item['local_center_m']);holes.append(h)
        for hole in holes:
            pn=str(hole['target_part']);p=m.parts[pn];center=hole['local_center'];axis=hole['local_axis'];major=hole['local_major_axis'] or [0.,0.,0.]
            radius=hole['width_m']/2.;half=(hole['total_length_m']-hole['width_m'])/2.;ids=[]
            if half>1.e-8 and not any(major):raise ValueError('SLOT_MAJOR_AXIS_MISSING')
            for edge in p.edges:
                try:r=edge.getRadius()
                except Exception:continue
                if abs(r-radius)>1.e-6:continue
                v=[edge.pointOn[0][k]-center[k] for k in range(3)];axial=sum([v[k]*axis[k] for k in range(3)]);along=sum([v[k]*major[k] for k in range(3)])
                end=half if along>=0 else -half;radial=[v[k]-axial*axis[k]-end*major[k] for k in range(3)]
                if abs(axial)<=radius+1.e-6 and abs(math.sqrt(sum([x*x for x in radial]))-radius)<2.e-6:
                    ids.append(edge.index);result[pn][edge.index]=c['mesh_rules']['local_size']
            if len(ids)<2:raise ValueError('HOLE_REPORT_ARCS_UNRESOLVED: '+str(hole))
            parts[pn]['refinement_regions'].append(dict(source=hole.get('feature_name',hole.get('name')),edges=ids,size_m=c['mesh_rules']['local_size'],reason='STEP06_NAMED_HOLE_ARCS',selection='Hole report center/axis/radius verified on actual geometry; no Connector region required'))
    hoop_items=[]
    for entry in c.get('hole_report',{}).get('hoop_validation',{}).get('parts',[]):
        if entry['part_name'] in parts:hoop_items.append(entry)
        elif c.get('tie_boundary_simplification'):
            for pn,d in parts.items():
                if 'HOOP' in d['roles'] and pn.startswith('STEP07_ISOLATED_'):
                    item=dict(entry);item['part_name']=pn;hoop_items.append(item)
        else:raise ValueError('HOLE_METADATA_PART_MISSING: '+str(entry['part_name']))
    for item in hoop_items:
        pn=str(item['part_name'])
        if pn not in parts:raise ValueError('HOLE_METADATA_PART_MISSING: '+pn)
        p=m.parts[pn]
        for hole in item['holes']:
            center=hole['local_center'];axis=hole['local_axis'];major=hole['local_major_axis'] or [0.,0.,0.]
            radius=hole['width_m']/2.;half=(hole['total_length_m']-hole['width_m'])/2.;ids=[]
            if half>1.e-8 and not any(major):raise ValueError('SLOT_MAJOR_AXIS_MISSING')
            for edge in p.edges:
                try:r=edge.getRadius()
                except Exception:continue
                if abs(r-radius)>1.e-6:continue
                v=[edge.pointOn[0][k]-center[k] for k in range(3)]
                axial=sum([v[k]*axis[k] for k in range(3)])
                along=sum([v[k]*major[k] for k in range(3)])
                end=half if along>=0 else -half
                radial=[v[k]-axial*axis[k]-end*major[k] for k in range(3)]
                if abs(axial)<=radius and abs(math.sqrt(sum([x*x for x in radial]))-radius)<1.e-6:
                    ids.append(edge.index);result[pn][edge.index]=c['mesh_rules']['local_size']
            if len(ids)<2:raise ValueError('HOOP_HOLE_ARCS_UNRESOLVED: '+hole['hole_id'])
            parts[pn]['refinement_regions'].append(dict(source=hole['hole_id'],edges=ids,size_m=c['mesh_rules']['local_size'],reason='STEP06_SLOT_CENTER_AXIS_WIDTH_AND_ACTUAL_RADIUS'))
    for pn,d in parts.items():
        if 'HOOP' in d['roles'] and not d['refinement_regions']:
            raise ValueError('HOOP_HOLE_METADATA_REQUIRED: '+pn)
        if 'INCLINED_BEAM' in d['roles']:
            p=m.parts[pn];faces=set()
            for entry in d['refinement_regions']:
                if entry['reason']=='STEP06_NAMED_HOLE_ARCS':
                    for index in entry['edges']:faces.update(p.edges[index].getFaces())
            area=sum([p.faces[index].getSize(printResults=False) for index in faces])
            fraction=area/d['surface_area_m2']
            if fraction>c['mesh_rules']['max_hole_face_area_fraction']:raise ValueError('HOLE_TRANSITION_WOULD_REFINE_TOO_MUCH_OF_PART: '+pn)
            ids=set();h=c['mesh_rules']['hole_face_transition_size']
            for index in faces:ids.update(p.faces[index].getEdges())
            for index in ids:result[pn][index]=min(result[pn].get(index,h),h)
            d['refinement_regions'].append(dict(source='STEP06_HOLE_ADJACENT_FACES',faces=sorted(faces),edges=sorted(ids),size_m=h,
                area_fraction=fraction,reason='BOUNDED_HOLE_FACE_TRANSITION_AFTER_COARSE_MESH_SLIVER_FAILURE'))
    for name,obj in m.constraints.items():
        if obj.suppressed:continue
        for field in ('surface','master','slave'):
            if not hasattr(obj,field):continue
            region=m3_region(a,getattr(obj,field));selected={}
            for face in region.faces:
                pn=a.instances[face.instanceName].partName;d=parts[pn]
                if any([r.startswith('COLUMN_') for r in d['roles']]):continue
                h=c['mesh_rules']['hoop_connection_size'] if 'HOOP' in d['roles'] else c['mesh_rules']['connection_size']
                if c['summary']['structure_type']=='SP_DC' and 'INCLINED_BEAM' in d['roles']:h=c['mesh_rules'].get('beam_connection_size',h)
                if h>=d['size_m']:continue
                for index in face.getEdges():
                    edge=m.parts[pn].edges[index]
                    if edge.getSize(printResults=False)>c['mesh_rules']['max_connection_edge_length']:
                        # Large single-pile hoops have long circumferential arcs.
                        # Keep their role seed; do not spread 6 mm seeds over the hoop.
                        radius=None
                        try:radius=edge.getRadius()
                        except Exception:pass
                        if c['summary']['structure_type'] in ('SP_DC','SP_SC') and 'HOOP' in d['roles'] and name.startswith('STEP05_TIE_COLUMN_DOWN_HOOP_') and radius and edge.getSize(printResults=False)<=2*math.pi*radius+1.e-6:
                            d.setdefault('bounded_seed_exclusions',[]).append(dict(source=name,edge=index,length_m=edge.getSize(printResults=False),radius_m=radius,size_m=d['size_m'],reason='Verified hoop circumference retains role seed; not an axial refinement region'))
                            continue
                        raise ValueError('CONNECTION_REGION_TOO_EXTENSIVE_FOR_LOCAL_SEED: '+name)
                    result[pn][index]=min(result[pn].get(index,h),h);selected.setdefault(pn,[]).append(index)
                d['refinement_regions'].append(dict(source=name+':'+field,face=face.index,edges=list(face.getEdges()),size_m=h,reason='EXISTING_TIE_OR_COUPLING_FACE_BOUNDARY'))
    for pn,d in parts.items():
        if d.get('uniform_geometry_seed'):
            result[pn]={}
            for entry in d['refinement_regions']:
                entry['requested_size_m']=entry['size_m'];entry['size_m']=d['size_m'];entry['seed_method']='UNIFORM_PART_SEED_WITH_NATIVE_GEOMETRY_CURVATURE'
    return result


def m3_repair_thin_solid(p,d,c):
    """SP_DC only: bounded mesh-only trials, retaining the best measured mesh.

    The trial scale uses current failed tetrahedron edges, not an assumed plate
    thickness. Geometry, sections and all connection surfaces remain unchanged.
    """
    from abaqusConstants import SHAPE_FACTOR,ANALYSIS_CHECKS,FINER
    rule=c['mesh_rules'];initial=dict(d['local_seeds_m']);best=dict(initial)
    trials=[];d['quality_repairs']=trials;current=dict(initial);affected=set()
    def measure():
        q=p.verifyMeshQuality(criterion=SHAPE_FACTOR,threshold=rule['shape_warning'])
        analysis=p.verifyMeshQuality(criterion=ANALYSIS_CHECKS)
        bad=q.get('failedElements',[])
        severe=len(analysis.get('failedElements',[]))+len(analysis.get('naElements',[]))
        incomplete=p.getUnmeshedRegions() is not None or not len(p.elements)
        score=(int(incomplete)+severe,len(bad),-float(q.get('worst') or 0.))
        return score,bad
    def regenerate(seeds):
        p.deleteMesh();p.deleteSeeds(regions=p.edges)
        p.seedPart(size=d['size_m'],deviationFactor=rule['deviation_factor'],minSizeFactor=rule['min_size_factor'])
        for index,h in sorted(seeds.items()):
            p.seedEdgeBySize(edges=p.edges[index:index+1],size=h,constraint=FINER)
        p.generateMesh()
    best_score,bad=measure();initial_score=best_score
    for index in range(5):
        score,bad=measure()
        if not bad or score[0]:break
        ids=set();lengths=[]
        for e in bad:
            nodes=e.getNodes();xyz=tuple([sum([n.coordinates[k] for n in nodes])/len(nodes) for k in range(3)])
            face=p.faces.getClosest(coordinates=(xyz,))[0][0]
            ids.update([i for i in face.getEdges() if p.edges[i].getSize(printResults=False)<=rule['max_connection_edge_length']])
            corners=nodes[:4]
            lengths.extend([math.sqrt(sum([(corners[i].coordinates[k]-corners[j].coordinates[k])**2 for k in range(3)])) for i in range(4) for j in range(i)])
        affected.update(ids)
        if not ids or len(affected)>rule['max_repair_edge_fraction']*len(p.edges):
            d['repair_stopped']='LOCAL_REPAIR_SCOPE_LIMIT; unresolved elements require review';break
        positive=sorted([x for x in lengths if x>1.e-9])
        if not positive:break
        local_scale=positive[len(positive)//2]
        h=max(.001,min(d['size_m']*.75,local_scale*.7)*(.8**index))
        candidate=dict(current)
        for i in ids:candidate[i]=min(candidate.get(i,d['size_m']),h)
        if candidate==current:break
        regenerate(candidate);new_score,new_bad=measure()
        trials.append(dict(reason='ACTUAL_TET_EDGE_SCALE_LOCAL_REPAIR',trial=index+1,size_m=h,
            measured_edge_scale_m=local_scale,edges=sorted(ids),score=list(new_score),failed_elements=[e.label for e in new_bad]))
        current=candidate
        if new_score<best_score:best_score=new_score;best=dict(candidate)
        if new_score[0]:break
    if current!=best:regenerate(best)
    final_score,bad=measure()
    if final_score>initial_score:raise ValueError('LOCAL_REPAIR_RESTORE_FAILED: '+p.name)
    d['local_seeds_m']=best
    d['adaptive_solid_repair']=dict(initial_score=list(initial_score),final_score=list(final_score),
        unresolved_shape_labels=[e.label for e in bad],global_size_unchanged=d['size_m'],geometry_changed=False)


def m3_repair_hoop(p,d,c):
    """Bounded quality repair of newly generated mesh; never changes geometry.

    Re-seeds only boundaries of faces nearest failed tetrahedra. Hole arcs keep
    their explicit 6 mm seeds. Five attempts maximum, no part-wide fallback.
    """
    if c.get('stage')==4 and c.get('summary',{}).get('structure_type')=='SP_DC':
        return m3_repair_thin_solid(p,d,c)
    from abaqusConstants import SHAPE_FACTOR,FINER
    d['quality_repairs']=[];hole_ids=set();all_repaired=set();previous_bad=None
    for entry in d['refinement_regions']:
        if entry['reason'] in ('STEP06_NAMED_HOLE_ARCS','STEP06_SLOT_CENTER_AXIS_WIDTH_AND_ACTUAL_RADIUS'):hole_ids.update(entry['edges'])
    for h in c['mesh_rules']['hoop_quality_repair_sizes']:
        if d.get('uniform_geometry_seed'):h=min(h,d['size_m']*.8)
        bad=p.verifyMeshQuality(criterion=SHAPE_FACTOR,threshold=c['mesh_rules']['shape_warning']).get('failedElements',[])
        if not bad:break
        if c['summary']['structure_type'] in ('SP_DC','SP_SC') and previous_bad is not None and len(bad)>previous_bad:
            d['repair_stopped']='Local refinement increased failed shape checks; no further global densification'
            break
        previous_bad=len(bad)
        print('LOCAL MESH REPAIR: '+p.name+' failed='+str(len(bad))+' trial_size='+str(h))
        faces=set();ids=set()
        for element in bad:
            nodes=element.getNodes();xyz=tuple([sum([n.coordinates[k] for n in nodes])/len(nodes) for k in range(3)])
            face=p.faces.getClosest(coordinates=(xyz,))[0][0];faces.add(face.index)
            for index in face.getEdges():
                if (index not in hole_ids or d.get('uniform_geometry_seed')) and p.edges[index].getSize(printResults=False)<=c['mesh_rules']['max_connection_edge_length']:ids.add(index)
        all_repaired.update(ids)
        if not ids or len(all_repaired)>c['mesh_rules']['max_repair_edge_fraction']*len(p.edges):
            raise ValueError('LOCAL_QUALITY_REPAIR_SCOPE_EXCEEDED: '+p.name)
        d['quality_repairs'].append(dict(reason='LOW_TETRAHEDRAL_SHAPE_FACTOR',failed_elements=[e.label for e in bad],
            faces=sorted(faces),edges=sorted(ids),size_m=h,edge_fraction=float(len(all_repaired))/len(p.edges)))
        p.deleteMesh()
        for index in sorted(ids):
            size=min(h,d['local_seeds_m'].get(index,h))
            p.seedEdgeBySize(edges=p.edges[index:index+1],size=size,constraint=FINER)
            d['local_seeds_m'][index]=size
        p.generateMesh()


def m3_mesh_part(p,d,c,refined):
    import time
    started=time.time()
    import mesh
    from abaqusConstants import STANDARD,C3D10,S4R,S3,TET,FREE,QUAD_DOMINATED,FINER,ADVANCING_FRONT,FIXED,SWEEP,QUAD,STRUCTURED
    expected=set(['C3D10']) if len(p.cells) else set(['S4R','S3'])
    if len(p.nodes) or len(p.elements):
        raise ValueError('EXISTING_MESH_REQUIRES_PROVENANCE_REVIEW: '+p.name+'; optimization requires an unmeshed accepted Step07-02; no mesh deleted or silently retained')
    else:
        d['policy']='GENERATED_NEW_MESH';rule=c['mesh_rules']
        # Upstream may retain old edge seeds after deleting its mesh.
        # Reset mesh-only seeds so the new role rules actually take effect.
        p.deleteSeeds(regions=p.edges)
        p.seedPart(size=d['size_m'],deviationFactor=rule['deviation_factor'],minSizeFactor=rule['min_size_factor'])
        for index,h in sorted(refined.items()):
            p.seedEdgeBySize(edges=p.edges[index:index+1],size=h,deviationFactor=.1,minSizeFactor=.1,constraint=FINER)
        d['local_seeds_m']=refined
        d['circumference_seeds']=[]
        if any([r.startswith('COLUMN_') for r in d['roles']]):
            ring_radii=[]
            for e in p.edges:
                try:radius=e.getRadius()
                except Exception:continue
                if abs(e.getSize(printResults=False)-2*math.pi*radius)<1.e-6:ring_radii.append(radius)
            for e in p.edges:
                try:radius=e.getRadius()
                except Exception:continue
                if not any([abs(radius-r)<1.e-6 for r in ring_radii]):continue
                length=e.getSize(printResults=False)
                # Full rings and partitioned arcs use the same angular density.
                number=max(2,int(round((rule.get('column_down_circumference_divisions',rule['circumference_divisions']) if 'COLUMN_DOWN' in d['roles'] else rule['circumference_divisions'])*length/(2*math.pi*radius))))
                p.seedEdgeByNumber(edges=p.edges[e.index:e.index+1],number=number,constraint=FIXED)
                d['circumference_seeds'].append(dict(edge=e.index,radius_m=radius,number=number))
        if d.get('axial_partition_control'):
            for e in p.edges:
                try:e.getRadius();continue
                except Exception:pass
                number=max(1,int(math.ceil(e.getSize(printResults=False)/d['size_m'])))
                p.seedEdgeByNumber(edges=p.edges[e.index:e.index+1],number=number,constraint=FIXED)
        if len(p.cells):
            p.setMeshControls(regions=p.cells,elemShape=TET,technique=FREE)
            p.setElementType(regions=(p.cells,),elemTypes=(mesh.ElemType(elemCode=C3D10,elemLibrary=STANDARD),))
        else:
            p.setMeshControls(regions=p.faces,elemShape=QUAD_DOMINATED,technique=FREE,algorithm=ADVANCING_FRONT)
            if d['circumference_seeds']:
                p.setMeshControls(regions=p.faces,elemShape=QUAD,technique=SWEEP)
            if d.get('axial_partition_control'):
                for face in p.faces:
                    try:p.setMeshControls(regions=p.faces[face.index:face.index+1],elemShape=QUAD,technique=STRUCTURED)
                    except Exception:pass
            p.setElementType(regions=(p.faces,),elemTypes=(mesh.ElemType(elemCode=S4R,elemLibrary=STANDARD),mesh.ElemType(elemCode=S3,elemLibrary=STANDARD)))
        p.generateMesh()
        if 'HOOP' in d['roles'] or (c['summary']['structure_type'] in ('SP_DC','SP_SC') and 'PURLIN_SUPPORT' in d['roles']):m3_repair_hoop(p,d,c)
    d['generation_seconds']=time.time()-started
    d['nodes']=len(p.nodes);d['elements']=len(p.elements);d['element_types']={}
    for e in p.elements:d['element_types'][str(e.type)]=d['element_types'].get(str(e.type),0)+1
    d['unmeshed']=p.getUnmeshedRegions() is not None
    if d['unmeshed'] or not d['elements']:raise ValueError('MESH_INCOMPLETE: '+p.name)
    quality_started=time.time()
    if c.get('tie_boundary_simplification') and not len(p.cells):
        from abaqusConstants import SHAPE_FACTOR,MEDIAL_AXIS,ANALYSIS_CHECKS,TRI
        check=p.verifyMeshQuality(criterion=SHAPE_FACTOR,threshold=c['mesh_rules']['shape_warning'])
        bad=set([e.label for e in check.get('failedElements',[])])
        if bad:
            affected=[]
            for face in p.faces:
                if bad.intersection(set([e.label for e in face.getElements()])):affected.append(face)
            if not affected:raise ValueError('FAILED_ELEMENT_FACE_UNRESOLVED')
            d['local_quality_repair']=dict(reason='Low shape factor after Tie footprint partition',failed_labels=sorted(bad),faces=[f.index for f in affected],algorithm='MEDIAL_AXIS',size_unchanged=True)
            p.deleteMesh(regions=tuple(affected));p.setMeshControls(regions=tuple(affected),elemShape=QUAD_DOMINATED,technique=FREE,algorithm=MEDIAL_AXIS);p.generateMesh()
            d['nodes']=len(p.nodes);d['elements']=len(p.elements);d['element_types']={}
            for e in p.elements:d['element_types'][str(e.type)]=d['element_types'].get(str(e.type),0)+1
    if c.get('stage')==4 and c.get('tie_boundary_simplification') and any([x in ('BRACE_FRONT','BRACE_REAR') for x in d['roles']]):
        # Diagnostic trial: triangular meshing only on warned brace faces.
        # Beam trial was rejected (shape factor failures); beam stays unchanged.
        from abaqusConstants import ANALYSIS_CHECKS,TRI,FREE
        raw=p.verifyMeshQuality(criterion=ANALYSIS_CHECKS)
        labels=set([e.label for e in raw.get('warningElements',[])])
        affected=[f for f in p.faces if labels.intersection(set([e.label for e in (f.getElements() or ())]))]
        if affected:
            d['warning_local_repair']=dict(method='TRI on warned brace faces only',faces=[f.index for f in affected],warnings_before=sorted(labels),geometry_unchanged=True,seeds_unchanged=True)
            p.deleteMesh(regions=tuple(affected));p.setMeshControls(regions=tuple(affected),elemShape=TRI,technique=FREE);p.generateMesh()
            d['nodes']=len(p.nodes);d['elements']=len(p.elements);d['element_types']={}
            for e in p.elements:d['element_types'][str(e.type)]=d['element_types'].get(str(e.type),0)+1
            if p.getUnmeshedRegions() is not None:raise ValueError('LOCAL_REPAIR_INCOMPLETE')
    d['quality']=m3_quality(p,c);d['quality_seconds']=time.time()-quality_started
    d['mesh_sha256']=m3_mesh_digest(p)


def m3_mesh_digest(p):
    data=dict(nodes=[(n.label,tuple(n.coordinates)) for n in p.nodes],elements=[(e.label,str(e.type),tuple(e.connectivity)) for e in p.elements])
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode('utf-8')).hexdigest()


def m3_comparison(c,report):
    old=c.get('comparison_baseline',{});result=dict(source=c.get('comparison_source'),source_sha256=c.get('comparison_sha256'),
        baseline_available=bool(old),old_timing_note='Not recorded in old report' if 'mesh_generation_seconds' not in old else None,metrics={},parts={})
    for key in ('unique_part_nodes','unique_part_elements','assembly_instance_nodes','assembly_instance_elements','mesh_generation_seconds','quality_warning_unique_elements','quality_warning_instance_elements'):
        before=old.get(key);after=report.get(key)
        result['metrics'][key]=dict(before=before,after=after,change_percent=(100.*(after-before)/before) if before and after is not None else None)
    for pn,data in report['parts'].items():
        previous=old.get('parts',{}).get(pn,{})
        result['parts'][pn]=dict(roles=sorted(set(data['roles'])),instances=data['instances'],
            before_nodes=previous.get('nodes'),after_nodes=data['nodes'],before_elements=previous.get('elements'),after_elements=data['elements'],
            before_types=previous.get('element_types'),after_types=data['element_types'],generation_seconds=data['generation_seconds'],
            before_generation_seconds=previous.get('generation_seconds'),target_size_m=data['size_m'])
    for label,multiplier in (('unique_part',False),('assembly_instance',True)):
        for kind in ('Shell','Solid'):
            before=sum([d['elements']*(len(d['instances']) if multiplier else 1) for d in old.get('parts',{}).values() if d['kind']==kind]) if old else None
            after=sum([d['elements']*(len(d['instances']) if multiplier else 1) for d in report['parts'].values() if d['kind']==kind])
            result['metrics'][label+'_'+kind.lower()+'_elements']=dict(before=before,after=after,change_percent=100.*(after-before)/before if before else None)
    return result


def m3_regions(m):
    a=m.rootAssembly;result={}
    for category,repo in (('set',a.sets),('surface',a.surfaces)):
        for name,region in repo.items():
            if name.startswith('STEP06_WIRE_'):continue
            labels=set();members=0
            for kind in ('edges','faces','cells'):
                for obj in getattr(region,kind,[]):
                    nodes=obj.getNodes();members+=1
                    if not len(nodes):raise ValueError('REGION_GEOMETRY_WITHOUT_NODES: '+name+' '+kind+' '+str(obj.index))
                    for n in nodes:labels.add((obj.instanceName,n.label))
            rps=len(getattr(region,'referencePoints',[]))
            for n in getattr(region,'nodes',[]):labels.add((getattr(n,'instanceName',''),n.label))
            if not members and not labels and not rps:raise ValueError('EMPTY_ASSEMBLY_REGION: '+name)
            result[category+':'+name]=dict(geometry_members=members,mapped_nodes=len(labels),reference_points=rps)
    for name,bc in m.boundaryConditions.items():m3_region(a,bc.region)
    for name,obj in m.constraints.items():
        for field in ('surface','controlPoint','master','slave'):
            if hasattr(obj,field):m3_region(a,getattr(obj,field))
    return result


def m3_node_keys(region):
    result=set()
    for kind in ('faces','edges','cells'):
        for obj in getattr(region,kind,[]):
            for node in obj.getNodes():result.add((obj.instanceName,node.label))
    return result


def m3_constraint_nodes(m):
    a=m.rootAssembly;clouds=[];result=dict(checked_couplings=[],checked_bcs=[],overlaps=[])
    for name,obj in m.constraints.items():
        if type(obj).__name__!='Coupling' or obj.suppressed:continue
        nodes=m3_node_keys(m3_region(a,obj.surface));result['checked_couplings'].append(dict(name=name,nodes=len(nodes),type=str(obj.couplingType)))
        if str(obj.couplingType)=='KINEMATIC':clouds.append((name,nodes))
    for index,pair in enumerate(clouds):
        for other in clouds[index+1:]:
            overlap=pair[1].intersection(other[1])
            if overlap:result['overlaps'].append(dict(objects=[pair[0],other[0]],nodes=sorted(overlap)))
    for name,bc in m.boundaryConditions.items():
        if bc.suppressed:continue
        nodes=m3_node_keys(m3_region(a,bc.region));result['checked_bcs'].append(dict(name=name,nodes=len(nodes)))
        for coupling,cloud in clouds:
            overlap=nodes.intersection(cloud)
            if overlap:result['overlaps'].append(dict(objects=[name,coupling],nodes=sorted(overlap)))
    result['status']='OVERLAP_REQUIRES_REVIEW' if result['overlaps'] else 'NO_DIRECT_KINEMATIC_NODE_OVERLAP'
    result['scope']='Checks geometry-mapped nodes of kinematic clouds and BCs; intentionally excludes shared control RPs. Not a full solver constraint-rank test.'
    return result


def m3_spatial_regions(m):
    """Physical membership, independent of indices renumbered by Partition.

    Existing connection members must remain geometrically identical. Full-Part
    section sets may gain faces, but must still cover every face and same area.
    """
    a=m.rootAssembly
    def point(v):return [round(float(x),10)+0.0 for x in v]
    def edge(e,owner):
        return dict(instance=getattr(e,'instanceName',''),length=round(e.getSize(printResults=False),10),
                    point=point(e.pointOn[0]),vertices=sorted([point(owner.vertices[k].pointOn[0]) for k in e.getVertices()]))
    def boundary(face,owner):
        straight=[];circles={}
        for k in face.getEdges():
            e=owner.edges[k]
            try:radius=e.getRadius()
            except Exception:straight.append(edge(e,owner));continue
            pts=[e.getCurvature(parameter=t)['evaluationPoint'] for t in (.1,.5,.9)]
            u=[pts[1][j]-pts[0][j] for j in range(3)];v=[pts[2][j]-pts[0][j] for j in range(3)]
            def cross(x,y):return [x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]]
            w=cross(u,v);ww=sum([x*x for x in w]);uu=sum([x*x for x in u]);vv=sum([x*x for x in v])
            vxw=cross(v,w);wxu=cross(w,u)
            center=[pts[0][j]+(uu*vxw[j]+vv*wxu[j])/(2*ww) for j in range(3)]
            normal=[x/math.sqrt(ww) for x in w]
            for x in normal:
                if abs(x)>1.e-8:
                    if x<0:normal=[-x for x in normal]
                    break
            key=json.dumps(dict(center=point(center),normal=point(normal),radius=round(radius,10)),sort_keys=True)
            circles[key]=circles.get(key,0.)+e.getSize(printResults=False)
        return dict(straight=sorted(straight,key=lambda x:json.dumps(x,sort_keys=True)),circles=sorted([(k,round(v,9)) for k,v in circles.items()]))
    def region(r,owner,full=False):
        result={}
        if full and len(r.faces)==len(owner.faces) and len(owner.faces):
            result['faces']=dict(full_part=True,area=round(sum([f.getSize(printResults=False) for f in r.faces]),10))
        else:
            faces=[]
            for f in r.faces:
                obj=a.instances[f.instanceName] if getattr(f,'instanceName','') else owner
                faces.append(dict(instance=getattr(f,'instanceName',''),area=round(f.getSize(printResults=False),10),point=point(f.pointOn[0]),
                    boundary=boundary(f,obj)))
            result['faces']=sorted(faces,key=lambda x:json.dumps(x,sort_keys=True))
        edges=[]
        for e in r.edges:
            obj=a.instances[e.instanceName] if getattr(e,'instanceName','') else owner
            edges.append(edge(e,obj))
        result['edges']=sorted(edges,key=lambda x:json.dumps(x,sort_keys=True))
        result['vertices']=[point(v.pointOn[0]) for v in getattr(r,'vertices',[])]
        result['rps']=sorted([point(owner.getCoordinates(rp)) for rp in getattr(r,'referencePoints',[])])
        return result
    result={}
    for name,r in a.sets.items():result['assembly_set:'+name]=region(r,a)
    for name,r in a.surfaces.items():result['assembly_surface:'+name]=region(r,a)
    for pn,p in m.parts.items():
        for name,r in p.sets.items():result['part:'+pn+':set:'+name]=region(r,p,True)
        for name,r in p.surfaces.items():result['part:'+pn+':surface:'+name]=region(r,p)
    return result


def m3_partition_invariants(db,c,changed):
    """Retain all non-geometric state; spatial check separately replaces indices."""
    result=m3_snapshot(db,c);model=result['models'][str(c['project_id'])]
    model.pop('assembly_sets');model.pop('assembly_surfaces')
    for pn in changed:
        p=db.models[str(c['project_id'])].parts[pn]
        model['parts'][pn]=dict(area=round(sum([f.getSize(printResults=False) for f in p.faces]),10),
            cells=len(p.cells),section_assignments=model['parts'][pn]['section_assignments'])
    for name,i in model['instances'].items():
        if i['part'] in changed:i['geometry']=model['parts'][i['part']]
    return result


def m3_partition_axial(db,c,parts,report):
    from abaqusConstants import XYPLANE,XZPLANE
    m=db.models[str(c['project_id'])];a=m.rootAssembly
    changed=[pn for pn,d in parts.items() if 'INCLINED_BEAM' in d['roles'] or (c['assembly_summary']['structure_type']=='DP' and any([r in ('COLUMN_FRONT','COLUMN_REAR') for r in d['roles']]))]
    before=m3_spatial_regions(m);invariants=m3_partition_invariants(db,c,changed)
    report['auxiliary_partitions']=[]
    for pn in changed:
        p=m.parts[pn];d=parts[pn];h=d['size_m']
        if len(p.cells):raise ValueError('AXIAL_PARTITION_REQUIRES_SHELL: '+pn)
        bounds=[]
        for k in range(3):bounds.append([min([v.pointOn[0][k] for v in p.vertices]),max([v.pointOn[0][k] for v in p.vertices])])
        spans=[x[1]-x[0] for x in bounds]
        if spans.index(max(spans))!=2:raise ValueError('AXIAL_PARTITION_LOCAL_Z_REQUIRED: '+pn)
        positions=[]
        if 'INCLINED_BEAM' in d['roles']:
            centers=[]
            for name,r in a.surfaces.items():
                if 'BEAM_HOLE' not in name or not len(r.edges):continue
                if a.instances[r.edges[0].instanceName].partName!=pn:continue
                centers.append(sum([p.edges[e.index].pointOn[0][2] for e in r.edges])/len(r.edges))
            if not centers and c.get('tie_boundary_simplification'):
                centers=[x['local_center'][2] for x in c.get('hole_report',{}).get('inclined_beam',[]) if x.get('target_part')==pn]
            if not centers:raise ValueError('BEAM_HOLE_CENTERS_MISSING')
            d['hole_axial_centers']=centers
            for center in sorted(set(centers)):
                positions.extend([center-h,center+h])
            if min(positions)<=bounds[2][0] or max(positions)>=bounds[2][1]:raise ValueError('HOLE_TRANSITION_EXCEEDS_BEAM')
        else:
            positions=[bounds[2][0]+h]
        for z in positions:
            faces=[]
            for face in p.faces:
                zs=[p.vertices[k].pointOn[0][2] for k in face.getVertices()]
                if min(zs)<z-1.e-6 and max(zs)>z+1.e-6:faces.append(face)
            if faces:
                datum=p.DatumPlaneByPrincipalPlane(principalPlane=XYPLANE,offset=z)
                feature=p.PartitionFaceByDatumPlane(faces=tuple(faces),datumPlane=p.datums[datum.id])
                report['auxiliary_partitions'].append(dict(part=pn,feature=feature.name,plane='LOCAL_XY',offset_m=z,purpose='Bound axial mesh transition'))
        if 'INCLINED_BEAM' not in d['roles']:
            # Preserve the existing uppermost face (top coupling band), and all
            # bottom-collar faces. No connection region is rebuilt or replaced.
            limit=bounds[2][1];top=[]
            for face in p.faces:
                zs=[p.vertices[k].pointOn[0][2] for k in face.getVertices()]
                if max(zs)>=limit-1.e-6:top.append(min(zs))
            upper=min(top);faces=[]
            for face in p.faces:
                zs=[p.vertices[k].pointOn[0][2] for k in face.getVertices()]
                if min(zs)>=positions[0]-1.e-6 and max(zs)<=upper+1.e-6:faces.append(face)
            if not faces or upper<=positions[0]:raise ValueError('COLUMN_FREE_AXIAL_BAND_NOT_IDENTIFIED')
            datum=p.DatumPlaneByPrincipalPlane(principalPlane=XZPLANE,offset=(bounds[1][0]+bounds[1][1])/2.)
            feature=p.PartitionFaceByDatumPlane(faces=tuple(faces),datumPlane=p.datums[datum.id])
            report['auxiliary_partitions'].append(dict(part=pn,feature=feature.name,plane='LOCAL_XZ',offset_m=(bounds[1][0]+bounds[1][1])/2.,axial_range_m=[positions[0],upper],purpose='Independent axial and circular seeding; end regions protected'))
            d['axial_partition_control']=True
        a.regenerate()
    after=m3_spatial_regions(m)
    differences=[key for key in set(before.keys())|set(after.keys()) if before.get(key)!=after.get(key)]
    report['partition_region_check']=dict(status='FAIL' if differences else 'PASS',changed_regions=differences,before=before,after=after)
    if differences:raise ValueError('PARTITION_CHANGED_PHYSICAL_REGION: '+str(differences))
    if m3_partition_invariants(db,c,changed)!=invariants:raise ValueError('PARTITION_CHANGED_NON_GEOMETRIC_STATE')
    report['partition_non_geometry_preservation']='PASS'


def m3_apply(db,c,report):
    name=str(c['project_id']);m=db.models[name];a=m.rootAssembly
    before=m3_snapshot(db,c);report['parts']=m3_parts(m,c);report['connectors']=m3_connectors(m)
    b2_validate_existing(m,c,report)
    estimate=sum([d['estimated_elements']*len(d['instances']) for d in report['parts'].values()])
    report['estimated_assembly_elements']=estimate
    report['estimate_basis']='Shell 2A/h^2; solid max(8V/h^3,4A/h^2); excludes local refinement; planning estimate, not a prediction.'
    if estimate>c['mesh_rules']['max_estimated_elements']:raise ValueError('ESTIMATED_MESH_SCALE_REQUIRES_REVIEW')
    for pn,d in report['parts'].items():
        if d['existing_nodes'] or d['existing_elements']:raise ValueError('EXISTING_MESH_REQUIRES_PROVENANCE_REVIEW: '+pn)
    m3_partition_axial(db,c,report['parts'],report)
    before=m3_snapshot(db,c)
    refinement=m3_refinements(m,c,report['parts'])
    for pn,d in sorted(report['parts'].items()):
        report['active_part']=pn;print('MESH: '+pn)
        m3_mesh_part(m.parts[pn],d,c,refinement[pn]);d['status']='MESHED_CHECKED'
    a.regenerate()
    report['region_nodes']=m3_regions(m)
    report['constraint_node_check']=m3_constraint_nodes(m)
    if report['constraint_node_check']['overlaps']:raise ValueError('MESH_CONSTRAINT_NODE_OVERLAP_REQUIRES_REVIEW')
    if m3_snapshot(db,c)!=before:raise ValueError('NON_MESH_MODEL_DATA_CHANGED')
    report['preservation']='PASS';report['unique_part_nodes']=sum([d['nodes'] for d in report['parts'].values()])
    report['unique_part_elements']=sum([d['elements'] for d in report['parts'].values()])
    report['assembly_instance_nodes']=sum([len(i.nodes) for i in a.instances.values()])
    report['assembly_instance_elements']=sum([len(i.elements) for i in a.instances.values()])
    report['connector_wire_count']=sum([d['wire_count'] for d in report['connectors']])
    report['assembly_reference_points']=len(a.referencePoints)
    report['connector_mesh_elements_current']=len(a.elements)
    report['mesh_generation_seconds']=sum([d['generation_seconds'] for d in report['parts'].values()])
    report['quality_warning_unique_elements']=sum([len(d['quality']['analysis'].get('warningElements',[])) for d in report['parts'].values()])
    report['quality_warning_instance_elements']=sum([len(d['quality']['analysis'].get('warningElements',[]))*len(d['instances']) for d in report['parts'].values()])
    if c.get('stage')==4:q4_diagnostics(m,c,report)
    elif report['quality_warning_unique_elements']:raise ValueError('NEW_MESH_QUALITY_WARNING_REQUIRES_REVIEW')
    if report['assembly_instance_elements']>c['mesh_rules']['max_actual_elements']:raise ValueError('ACTUAL_MESH_SCALE_REQUIRES_REVIEW')
    return before


def m3_run(c):
    import abaqus,part,assembly,interaction,load,step,mesh,job,section,sys
    for key in ('output_cae','report_path','log_path','scratch_cae','backup_cae','disk_backup_cae'):
        if os.path.exists(str(c[key])):raise ValueError('OUTPUT_EXISTS: '+str(c[key])+'; regenerate script')
    report=dict(stage=3,project_id=c['project_id'],execution_mode=c['execution_mode'],status='RUNNING',parts={},
                engineering_verified=False,human_review='PENDING',automatic_next_stage=False,input_cae=c['input_cae'],output_cae=c['output_cae'],rules=c['mesh_rules'])
    olddir=os.getcwd();oldout=sys.stdout;olderr=sys.stderr;db=None
    handle=os.fdopen(os.open(str(c['log_path']),os.O_CREAT|os.O_EXCL|os.O_WRONLY),'w')
    class Tee(object):
        def write(self,text):handle.write(text);handle.flush();oldout.write(text)
        def flush(self):handle.flush()
    sys.stdout=Tee();sys.stderr=sys.stdout
    try:
        os.chdir(str(c['output_dir']));source=str(c['input_cae'])
        with open(source,'rb') as f:original=hashlib.sha256(f.read()).hexdigest()
        if original!=c['input_sha256']:raise ValueError('ACCEPTED_INPUT_CHANGED')
        if c['execution_mode']=='CURRENT_SESSION_DEBUG':
            db=abaqus.mdb
            if os.path.normcase(os.path.abspath(str(db.pathName)))==os.path.normcase(os.path.abspath(source)):
                raise ValueError('ACCEPTED_CAE_IS_CURRENT_MDB: open supplied session_input copy first')
            if os.path.normcase(os.path.abspath(str(db.pathName)))!=os.path.normcase(os.path.abspath(str(c['manual_working_copy']))):
                raise ValueError('CURRENT_SESSION_NOT_SUPPLIED_STAGE2_WORKING_COPY: open '+str(c['manual_working_copy'])+'; old stage outputs are protected')
        elif c['execution_mode']=='INDEPENDENT_CAE':
            from abaqus import openMdb
            shutil.copy2(source,str(c['scratch_cae']));db=openMdb(pathName=str(c['scratch_cae']))
        else:raise ValueError('INVALID_MODE')
        if str(c['project_id']) not in db.models:raise ValueError('TARGET_MODEL_MISSING')
        s7_stage1_values(db.models[str(c['project_id'])],c)
        disk=str(db.pathName);report['session_path_before']=disk
        if os.path.isfile(disk):shutil.copy2(disk,str(c['disk_backup_cae']))
        db.saveAs(pathName=str(c['backup_cae']));report['recovery_cae']=c['backup_cae']
        before=m3_apply(db,c,report)
        if os.path.exists(str(c['output_cae'])):raise ValueError('OUTPUT_EXISTS')
        db.saveAs(pathName=str(c['output_cae']))
        if m3_snapshot(db,c)!=before:raise ValueError('SAVE_PRESERVATION_FAILED')
        if c['execution_mode']=='INDEPENDENT_CAE':
            db.close();db=openMdb(pathName=str(c['output_cae']))
            if m3_snapshot(db,c)!=before:raise ValueError('REOPEN_PRESERVATION_FAILED')
            m3_regions(db.models[str(c['project_id'])]);report['reopen']='PASS'
            for pn,data in report['parts'].items():
                if m3_mesh_digest(db.models[str(c['project_id'])].parts[str(pn)])!=data['mesh_sha256']:raise ValueError('REOPEN_MESH_CHANGED: '+pn)
        else:
            if abaqus.mdb is not db:raise ValueError('CURRENT_SESSION_CHANGED')
            report['session_alive']=True;report['reopen']='PENDING_EXTERNAL_CHECK'
        with open(source,'rb') as f:report['accepted_input_unchanged']=hashlib.sha256(f.read()).hexdigest()==original
        if not report['accepted_input_unchanged']:raise ValueError('ACCEPTED_INPUT_CHANGED')
        report['status']='MESH_COMPLETE_WITH_WARNINGS_PENDING_REVIEW' if report['quality_warning_unique_elements'] else 'MESH_COMPLETE_PENDING_REVIEW'
        report['comparison']=m3_comparison(c,report)
        report['warnings']=['Mesh sizes are first-trial rules, not mesh-convergence qualification.',
                            'Tie transfer and solver-level overconstraints require later input/solver checks; no tolerance changed.',
                            'Connector definitions preserved; actual CONN3D2 writing intentionally not tested at this stage.',
                            'Solid support end rotations remain pending engineering confirmation; only existing U2 is retained.']
    except Exception:
        report['status']='FAILED_PARTIAL_MESH_POSSIBLE';report['error']=traceback.format_exc();print(report['error'])
        report['recovery']='Open before_mesh recovery CAE; current session may contain partial mesh. Not saved as a successful stage result.'
        report['partial_output_possible']=os.path.exists(str(c['output_cae']))
    finally:
        if db is not None and c['execution_mode']=='INDEPENDENT_CAE':db.close()
        with open(str(c['report_path']),'w') as f:json.dump(report,f,indent=2)
        sys.stdout=oldout;sys.stderr=olderr;handle.close();os.chdir(olddir)
    if report['status'].startswith('FAILED'):raise RuntimeError('Step07-03 failed; inspect '+str(c['report_path']))
    return report

