# -*- coding: utf-8 -*-
"""Fail-closed native mesh cleanup, only on the pipeline's input copy."""
def mc_region(r):
    geometry={};counts={}
    for key in ('faces','edges','cells','vertices','referencePoints'):
        values=getattr(r,key,())
        geometry[key]=sorted([(str(getattr(x,'instanceName','')),int(getattr(x,'index',getattr(x,'id',-1)))) for x in values])
    for key in ('nodes','elements'):counts[key]=len(getattr(r,key,()))
    return dict(geometry=geometry,mesh_counts=counts)

def mc_regions(m):
    result={};blockers=[]
    owners=[('Assembly',m.rootAssembly)]
    owners += [('Part:'+n,p) for n,p in m.parts.items()]
    owners += [('Instance:'+n,i) for n,i in m.rootAssembly.instances.items()]
    for owner,obj in owners:
        for repo in ('sets','surfaces','allInternalSets','allInternalSurfaces'):
            for name,r in getattr(obj,repo,{}).items():
                key=owner+'/'+repo+'/'+name;d=mc_region(r);result[key]=d
                if d['mesh_counts']['nodes'] or d['mesh_counts']['elements']:
                    if not any([d['geometry'][k] for k in ('faces','edges','cells','vertices')]):
                        blockers.append('MESH_DEPENDENT_REGION: '+key)
                    else:
                        # Geometry-backed regions may expose derived nodes/elements.
                        # Reject additional members that cannot be traced to that geometry.
                        for kind,method in [('nodes','getNodes'),('elements','getElements')]:
                            known=set()
                            for field in ('faces','edges','cells','vertices'):
                                for g in getattr(r,field,()):
                                    getter=getattr(g,method,None)
                                    if getter:
                                        for x in (getter() or ()):known.add((str(getattr(x,'instanceName','')),x.label))
                            actual=set([(str(getattr(x,'instanceName','')),x.label) for x in getattr(r,kind,())])
                            if not actual.issubset(known):blockers.append('UNRESOLVED_MIXED_REGION: '+key+'/'+kind)
    return result,blockers

def mc_geometry(m):
    result={}
    for name,p in m.parts.items():
        result[name]=dict(features=list(p.features.keys()),vertices=[tuple(v.pointOn[0]) for v in p.vertices],
            edges=[(tuple(e.getVertices()),round(e.getSize(printResults=False),12)) for e in p.edges],
            faces=[(tuple(f.getEdges()),round(f.getSize(printResults=False),12)) for f in p.faces],
            cells=[round(c.getSize(printResults=False),12) for c in p.cells],
            sections=[(s.sectionName,str(s.region),str(s.offsetType),s.offset) for s in p.sectionAssignments],
            orientations=[str(o) for o in p.materialOrientations])
    return result

def mc_cleanup(m,report):
    import mesh
    audit=dict(status='PREFLIGHT',parts={},blockers=[],deleted_parts=[])
    report['mesh_cleanup']=audit
    regions,blockers=mc_regions(m);audit['regions_before']=regions
    audit['referencing_objects']={}
    for repo in ('constraints','boundaryConditions','loads','interactions','predefinedFields'):
        audit['referencing_objects'][repo]={}
        for name,obj in getattr(m,repo,{}).items():
            refs={}
            for field in ('region','master','slave','controlPoint','surface'):
                if hasattr(obj,field):refs[field]=str(getattr(obj,field))
            audit['referencing_objects'][repo][name]=dict(type=type(obj).__name__,regions=refs)
    for name,i in m.rootAssembly.instances.items():
        if (len(i.nodes) or len(i.elements)) and str(getattr(i,'dependent',''))!='ON':
            blockers.append('INDEPENDENT_INSTANCE_MESH_REQUIRES_REVIEW: '+name)
    # These may store labels outside normal Set/Surface repositories. Unsupported
    # data must be reviewed, never assumed independent of the mesh.
    for owner,obj in [('Model',m),('Assembly',m.rootAssembly)]+[('Part:'+n,p) for n,p in m.parts.items()]:
        for repo in ('discreteFields','predefinedFields','skins','stringers'):
            if len(getattr(obj,repo,{})):blockers.append('UNREVIEWED_MESH_SENSITIVE_OBJECTS: '+owner+'/'+repo)
    for name,p in m.parts.items():
        d=dict(nodes=len(p.nodes),elements=len(p.elements),faces=len(p.faces),cells=len(p.cells),
            element_types=sorted(set([str(e.type) for e in p.elements])),safe_to_delete=False,orphan_mesh=False,
            provenance='NO_MESH',creator_history='Not stored by CAE; classification uses actual geometry association')
        audit['parts'][name]=d
        if not (d['nodes'] or d['elements']):continue
        try:
            elements=set();nodes=set()
            for g in (p.cells if len(p.cells) else p.faces):
                elements.update([e.label for e in (g.getElements() or ())])
                nodes.update([n.label for n in (g.getNodes() or ())])
            d['geometry_associated_elements']=len(elements);d['geometry_associated_nodes']=len(nodes)
            d['orphan_mesh']=elements!=set([e.label for e in p.elements]) or nodes!=set([n.label for n in p.nodes]) or not len(p.faces)
            if d['orphan_mesh']:raise ValueError('ORPHAN_OR_UNASSOCIATED_MESH')
            d['provenance']='NATIVE_GEOMETRY_ASSOCIATED';d['safe_to_delete']=True
        except Exception as exc:
            d['safe_to_delete']=False;d['error']=str(exc);blockers.append(name+': '+str(exc))
    audit['blockers']=blockers
    if blockers:
        audit['status']='BLOCKED';raise ValueError('UNSAFE_MESH_CLEANUP: '+str(blockers))
    geometry=mc_geometry(m);existing=t4_existing(m)
    for name,d in audit['parts'].items():
        if not d['safe_to_delete']:continue
        print('REMOVE NATIVE MESH IN WORKING COPY: '+name+' nodes='+str(d['nodes'])+' elements='+str(d['elements']))
        m.parts[name].deleteMesh();audit['deleted_parts'].append(name)
        if len(m.parts[name].nodes) or len(m.parts[name].elements):raise ValueError('NATIVE_MESH_CLEANUP_INCOMPLETE: '+name)
    m.rootAssembly.regenerate()
    after,remaining=mc_regions(m);audit['regions_after']=after
    if set(regions)!=set(after):raise ValueError('CLEANUP_REGION_NAMES_CHANGED')
    for name in regions:
        if regions[name]['geometry']!=after[name]['geometry']:raise ValueError('CLEANUP_REGION_GEOMETRY_CHANGED: '+name)
    if remaining or geometry!=mc_geometry(m) or existing!=t4_existing(m):raise ValueError('CLEANUP_GEOMETRY_OR_ATTRIBUTES_CHANGED')
    audit['geometry_and_holes_preserved']=True;audit['region_members_preserved']=True
    audit['status']='PASS';audit['formal_remesh_stage']=4
