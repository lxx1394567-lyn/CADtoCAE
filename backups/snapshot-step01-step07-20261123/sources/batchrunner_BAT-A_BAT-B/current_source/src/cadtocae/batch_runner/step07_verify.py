"""Python 2.7 compatible read-only checks against current-run Step07 reports."""
def verify_step07(model, reports, check, near):
    a = model.rootAssembly
    latest = {}
    for number in range(5, 10):
        r = reports.get(str(number), {})
        if r:
            check('Step07 report identity', r['project_id'], model.name)
            check('Step07 report success', r['status'], 'SUCCESS')
            latest.update(r)
    if not latest:
        return
    check('No legacy Connector sections', any(type(s).__name__ == 'ConnectorSection' for s in model.sections.values()), False)
    check('No legacy Connector objects', any(n.startswith(('STEP06_COUPLING_', 'STEP06_RP_', 'STEP06_WIRE_')) for repo in (model.constraints, a.features, a.sets) for n in repo.keys()), False)
    ties = latest['tie_validation']['pairs']
    check('Exact Tie names', sorted(n for n in model.constraints.keys() if n.startswith('STEP07_TIE_')), sorted(x['name'] for x in ties))
    for t in ties:
        obj = model.constraints[str(t['name'])]
        check('Tie type '+t['name'], type(obj).__name__, 'Tie')
        check('Tie active '+t['name'], bool(obj.suppressed), False)
        for key, value in [('adjust','OFF'), ('thickness','ON'), ('tieRotations','ON')]:
            check('Tie '+key, str(getattr(obj,key)), value)
        for field, side in [('master','shell'), ('slave','solid')]:
            faces = a.surfaces[str(getattr(obj,field)[0])].faces
            check('Tie region '+t['name']+side, sorted((f.instanceName,f.index) for f in faces), sorted((t[side],i) for i in t[side+'_faces']))
            near('Tie area '+t['name']+side, sum(f.getSize(printResults=False) for f in faces), t[side+'_area'])
    if latest.get('step_parameters'):
        steps = latest['step_parameters']
        check('Step sequence', list(model.steps.keys()), ['Initial']+[s['name'] for s in steps])
        for s in steps:
            obj = model.steps[str(s['name'])]
            check('Step procedure', type(obj).__name__, s['procedure'])
            for key in ('initialInc','maxInc','minInc','maxNumInc','timePeriod'):
                near('Step '+s['name']+' '+key, getattr(obj,key), s[key])
            for key in ('nlgeom','timeIncrementationMethod'):
                check('Step '+key, str(getattr(obj,key)), s[key])
    if latest.get('bc_validation'):
        regions = latest['bc_validation']['regions']
        check('Exact BC names', sorted(n for n in model.boundaryConditions.keys() if n.startswith('STEP07_BC_')), sorted(x['bc'] for x in regions))
        for d in regions:
            obj = model.boundaryConditions[str(d['bc'])]
            check('BC active '+d['bc'], bool(obj.suppressed), False)
            region = str(obj.region[0])
            check('BC region '+d['bc'], region, d.get('rp') or d['set'])
            target = a.sets[region]
            if d.get('rp'):
                check('BC RP nonempty', len(target.referencePoints), 1)
                point = a.getCoordinates(target.referencePoints[0])
                for actual, expected in zip(point,d['verified_rp_coordinates_m']):near('BC RP coordinate',actual,expected)
                check('BC type',str(model.steps['Initial'].boundaryConditionStates[str(d['bc'])].typeName),'ENCASTRE')
            else:
                check('BC region members',len(target.edges),d['member_count'])
                check('BC region instance',sorted(set(e.instanceName for e in target.edges)),[d['instance']])
                for key in d['actual_dofs']:
                    check('BC fixed '+key,getattr(model.steps['Initial'].boundaryConditionStates[str(d['bc'])],key.lower()), 0.0)
            for step_name in ('Initial','STEP07_PRELOAD','STEP07_LOADING'):
                state=model.steps[step_name].boundaryConditionStates[str(d['bc'])]
                check('BC propagation '+step_name,str(state.status),'CREATED' if step_name=='Initial' else 'PROPAGATED')
    mesh_report = reports.get('8', {})
    if mesh_report:
        check('Mesh accepted',mesh_report['mesh_acceptance']['status'],'SUCCESS')
        for name, d in mesh_report['parts'].items():
            p = model.parts[str(name)]
            check('Mesh nodes '+name,len(p.nodes),d['nodes'])
            check('Mesh elements '+name,len(p.elements),d['elements'])
            check('Mesh complete '+name,p.getUnmeshedRegions() is None,True)
            check('Mesh nonempty '+name,bool(d['nodes'] and d['elements']),True)
            types = {}
            for e in p.elements:types[str(e.type)] = types.get(str(e.type),0)+1
            check('Mesh element types '+name,types,d['element_types'])
        check('Assembly mesh nodes',sum(len(i.nodes) for i in a.instances.values()),mesh_report['assembly_instance_nodes'])
        check('Assembly mesh elements',sum(len(i.elements) for i in a.instances.values()),mesh_report['assembly_instance_elements'])
    if reports.get('9'):
        r = reports['9']
        check('Exact loads',sorted(model.loads.keys()),sorted(x['name'] for x in r['loads']))
        for d in r['loads']:
            obj = model.loads[str(d['name'])];state = model.steps[str(d['step'])].loadStates[str(d['name'])]
            check('Load type',type(obj).__name__,d['type'])
            check('Load active',bool(obj.suppressed),False)
            check('Load step',str(state.status),'CREATED')
            check('Load amplitude',str(state.amplitude) in ('','UNSET'),True)
            check('Load region',str(obj.region[0]),d['region'])
            near('Load magnitude',state.magnitude,d['magnitude_N_per_m2'])
            vector = obj.directionVector
            if len(vector)==2:vector=[vector[1][k]-vector[0][k] for k in range(3)]
            for actual, expected in zip(vector,d['direction_global']):near('Load direction',actual,expected)
            faces = a.surfaces[str(d['region'])].faces
            check('Load instance',sorted(set(f.instanceName for f in faces)),[d['instance']])
            target = next(x for x in r['loading_regions'] if x['surface']==d['region'])
            check('Load face membership',sorted(f.index for f in faces),sorted(target['faces']))
            near('Load area',sum(f.getSize(printResults=False) for f in faces),d['area_m2'])
