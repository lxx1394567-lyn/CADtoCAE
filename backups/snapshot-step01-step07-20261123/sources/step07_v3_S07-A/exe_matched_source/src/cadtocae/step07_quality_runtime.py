# -*- coding: utf-8 -*-
"""Stage04 diagnostic metrics; warning review never grants automatic acceptance."""
def q4_metrics(p,e):
    from abaqusConstants import ASPECT_RATIO,SMALL_ANGLE,LARGE_ANGLE,SHAPE_FACTOR,GEOM_DEVIATION_FACTOR
    result={}
    for name,criterion in [('aspect_ratio',ASPECT_RATIO),('small_angle_deg',SMALL_ANGLE),('large_angle_deg',LARGE_ANGLE),('shape_factor',SHAPE_FACTOR),('geometry_deviation',GEOM_DEVIATION_FACTOR)]:
        raw=p.verifyMeshQuality(criterion=criterion,regions=p.elements.sequenceFromLabels((e.label,)))
        result[name]=raw.get('worst')
    return result

def q4_diagnostics(m,c,r):
    from abaqusConstants import ANALYSIS_CHECKS
    result=dict(parts={},severe=[],review_reasons=[],policy='ANALYSIS_CHECKS errors/unmeshed/degenerate -> FAILED; unresolved warnings -> REVIEW_REQUIRED; no automatic warning waiver')
    r['mesh_acceptance']=result
    for pn,d in sorted(r['parts'].items()):
        p=m.parts[str(pn)];q=d['quality'];warnings=q['analysis'].get('warningElements',[])
        aspect=q['aspect_ratio'].get('failedElements',[])
        shape=q.get('shape_factor',{}).get('failedElements',[])
        issues=sorted(set(warnings+aspect+shape));rows=[];members={};hole_faces=set()
        hole_edges=set([i for x in d.get('refinement_regions',[]) if 'HOLE' in x.get('reason','') or 'SLOT' in x.get('reason','') for i in x.get('edges',[])])
        for f in p.faces:
            if hole_edges.intersection(set(f.getEdges())):hole_faces.add(f.index)
            # Node membership also handles boundary faces of solid elements.
            members[f.index]=set([n.label for n in (f.getNodes() or ())])
        ties={}
        for name,obj in m.constraints.items():
            for attr in ('master','slave','surface'):
                value=getattr(obj,attr,None)
                if value is None:continue
                key=str(value[0]);region=m.rootAssembly.surfaces[key] if key in m.rootAssembly.surfaces else None
                if region is None:continue
                ids=[f.index for f in region.faces if f.instanceName in d['instances']]
                if ids:ties[name+':'+attr]=ids
        for label in issues:
            e=p.elements.sequenceFromLabels((label,))[0];nodes=e.getNodes();labels=set([n.label for n in nodes])
            faces=[i for i,ns in members.items() if len(labels.intersection(ns))>=3]
            metrics=q4_metrics(p,e)
            row=dict(label=label,type=str(e.type),analysis_warning=label in warnings,aspect_threshold_exceeded=label in aspect,
                shape_threshold_exceeded=label in shape,
                metrics=metrics,centroid_local_m=[sum([n.coordinates[k] for n in nodes])/len(nodes) for k in range(3)],faces=faces,
                same_face_as_hole=bool(hole_faces.intersection(set(faces))),
                connection_regions=[name for name,ids in ties.items() if set(ids).intersection(set(faces))],
                cause_status='MEASURED_GEOMETRIC_INDICATORS; ANALYSIS_CHECKS does not return individual warning text')
            rows.append(row)
        bad=[];minimum=None
        for e in p.elements:
            xyz=[tuple(n.coordinates) for n in e.getNodes()];typ=str(e.type)
            if typ=='C3D10':
                value=t4_dot(t4_sub(xyz[1],xyz[0]),t4_cross(t4_sub(xyz[2],xyz[0]),t4_sub(xyz[3],xyz[0])))/6.
                minimum=value if minimum is None else min(minimum,value)
                if value<=0:bad.append(e.label)
            elif typ in ('S3','S4R'):
                v=t4_cross(t4_sub(xyz[1],xyz[0]),t4_sub(xyz[2],xyz[0]));area=math.sqrt(t4_dot(v,v))/2.
                if typ=='S4R':
                    v=t4_cross(t4_sub(xyz[2],xyz[0]),t4_sub(xyz[3],xyz[0]));area+=math.sqrt(t4_dot(v,v))/2.
                if area<=0:bad.append(e.label)
            else:result['severe'].append(pn+': UNSUPPORTED_ELEMENT_CHECK '+typ)
        sets={}
        for name,labels in [('STEP07_QA_ANALYSIS_WARN',warnings),('STEP07_QA_ASPECT',aspect),('STEP07_QA_SHAPE',shape),('STEP07_QA_DEGENERATE',bad)]:
            if not labels:continue
            if name in p.sets:raise ValueError('QUALITY_SET_EXISTS: '+pn+'/'+name)
            p.Set(name=name,elements=p.elements.sequenceFromLabels(tuple(labels)));sets[name]=sorted(labels)
        complete=p.getUnmeshedRegions() is None and len(p.elements)>0
        failed=q['analysis'].get('failedElements',[]);na=q['analysis'].get('naElements',[])
        if not complete or failed or na or bad:result['severe'].append(pn+': incomplete, unevaluated, analysis error or degenerate element')
        if warnings or aspect or shape:result['review_reasons'].append(pn+': unresolved analysis, aspect or shape warnings')
        result['parts'][pn]=dict(nodes=len(p.nodes),elements=len(p.elements),types=d['element_types'],instances=d['instances'],complete=complete,
            analysis_error_labels=failed,analysis_warning_labels=warnings,aspect_labels=aspect,shape_labels=shape,degenerate_labels=bad,minimum_corner_tet_volume_m3=minimum,
            jacobian_check='Abaqus ANALYSIS_CHECKS; corner-volume check supplementary, not proof of full quadratic Jacobian positivity',issues=rows,sets=sets)
    result['status']='FAILED' if result['severe'] else ('REVIEW_REQUIRED' if result['review_reasons'] else 'SUCCESS')
    result['next_stage_allowed']=False
    if result['severe']:raise ValueError('SEVERE_MESH_QUALITY_FAILURE: '+str(result['severe']))

def q4_reopen(m,r):
    for pn,d in r['mesh_acceptance']['parts'].items():
        p=m.parts[str(pn)]
        if m3_mesh_digest(p)!=r['parts'][pn]['mesh_sha256']:raise ValueError('REOPEN_MESH_CHANGED: '+pn)
        for name,labels in d['sets'].items():
            if sorted([e.label for e in p.sets[str(name)].elements])!=labels:raise ValueError('REOPEN_QUALITY_SET_CHANGED')
    r['quality_reopen']='PASS'
