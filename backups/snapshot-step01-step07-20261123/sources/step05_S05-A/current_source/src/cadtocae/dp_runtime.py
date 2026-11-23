"""DP ordering only; geometry, Tie and Coupling algorithms are shared."""


def execute_dp(plan,mdb,path,fingerprint,XYPLANE,ON,OFF,COMPUTED,DISTRIBUTING,WHOLE_SURFACE,UNIFORM):
    previous = {}
    if os.path.isfile(path):
        with open(path) as handle: previous = json.load(handle)
    model = item(mdb.models,plan['model_name'])
    existing = False
    for part in model.parts.values():
        for name in part.features.keys():
            if text(name).startswith(('STEP05_BBT_','STEP05_CHT_','STEP05_CCT_')): existing = True
    if existing and (previous.get('fingerprint') != fingerprint or previous.get('overall_status') != 'SUCCESS'):
        raise ValueError('Existing DP geometry lacks matching successful report; reopen clean Step02 + Step04 model')
    batch = Step05TieBatch()
    try:
        # Validate both projected stations before the first geometry mutation.
        for rule in plan['column_beam_couplings']: cpl_verify_face_station(model,rule,ON)
        contexts = []
        # Beam patch cuts are added to the common beam executor, so its existing
        # fingerprint guard sees only the successful previous run, never new cuts.
        working = dict(plan)
        working['partitions'] = {}
        for name in plan['partitions']: working['partitions'][name] = plan['partitions'][name][:]
        for rule in plan['column_beam_couplings']:
            working['partitions'][rule['beam']['part_name']].extend(rule['beam_range'])
        geometry_report = execute(working,mdb,path,fingerprint,XYPLANE,ON,COMPUTED,batch,geometry_only=True)
        for rule in plan['column_beam_couplings']:
            contexts.append(prepare_face_coupling(plan,rule,mdb,path,XYPLANE,ON))
        hoop_contexts = []
        prepared_parts = set()
        for group in plan['column_hoop_groups']:
            subplan = dict(plan)
            subplan['column_hoop_tie'] = group
            old = previous.get('column_hoop_groups',{}).get(group['group_id'])
            hoop_contexts.append(prepare_hoop(subplan,mdb,path,fingerprint,old,XYPLANE,ON,prepared_parts,group['group_id']))
        # All partitions are complete. Never carry pre-partition face indices.
        for context in contexts: cpl_face_selections(context,ON)
        execute(working,mdb,path,fingerprint,XYPLANE,ON,COMPUTED,batch,prepared=True)
        for context in hoop_contexts: execute_hoop(context,ON,COMPUTED,batch)
        batch.finish(path)
        for context in contexts: execute_coupling(context,ON,OFF,DISTRIBUTING,WHOLE_SURFACE,UNIFORM)
        with open(path) as handle: report = json.load(handle)
        report['ruleset'] = 'DP'
        report['warnings'] = plan.get('warnings',[])[:]
        report['expected_constraints'] = plan['expected_constraints']
        report['geometry_preparation'] = dict(partitions=geometry_report['partitions'],mesh_removed=geometry_report['mesh_removed'])
        for name in geometry_report['mesh_removed']:
            if name not in report['mesh_removed']: report['mesh_removed'].append(name)
        actual = dict(ties=0,reference_points=0,couplings=0)
        for name in plan['expected_constraints']['ties']:
            item(model.constraints,name)
            actual['ties'] += 1
        for name in plan['expected_constraints']['rp_names']:
            item(model.rootAssembly.features,name)
            actual['reference_points'] += 1
        for name in plan['expected_constraints']['coupling_names']:
            item(model.constraints,name)
            actual['couplings'] += 1
        report['actual_counts'] = actual
        report['overall_status'] = 'SUCCESS'
        with open(path,'w') as handle: json.dump(report,handle,ensure_ascii=True,indent=2)
    except Exception as exc:
        if os.path.isfile(path):
            with open(path) as handle: report = json.load(handle)
        else: report = dict(project_id=plan['project_id'],model_name=plan['model_name'],fingerprint=fingerprint)
        report['overall_status'] = 'FAILED'
        report['warnings'] = plan.get('warnings',[])[:]
        report.setdefault('errors',[]).append(str(exc))
        report['traceback'] = traceback.format_exc()
        with open(path,'w') as handle: json.dump(report,handle,ensure_ascii=True,indent=2)
        raise
