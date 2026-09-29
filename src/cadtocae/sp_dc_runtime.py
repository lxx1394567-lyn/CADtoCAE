"""SP_DC orchestration only. All shared geometry algorithms are reused."""


def execute_sp_dc(plan,mdb,path,fingerprint,XYPLANE,ON,COMPUTED):
    previous = {}
    if os.path.isfile(path):
        with open(path) as handle:
            previous = json.load(handle)
    model = item(mdb.models,plan['model_name'])
    # All groups share COLUMN_DOWN. Validate ownership once before permitting
    # subsequent groups in this same run to encounter newly created features.
    has_existing = False
    for p in model.parts.values():
        for name in p.features.keys():
            if text(name).startswith(('STEP05_BBT_','STEP05_CHT_')):
                has_existing = True
    if has_existing and (previous.get('fingerprint')!=fingerprint or previous.get('overall_status')!='SUCCESS'):
        raise ValueError('Existing SP_DC geometry lacks matching successful report; reopen clean Step02 + Step04 model')
    batch = Step05TieBatch()
    try:
        execute(plan,mdb,path,fingerprint,XYPLANE,ON,COMPUTED,batch)
        with open(path) as handle:
            report = json.load(handle)
        report['warnings'] = plan.get('warnings',[])[:]
        report['ruleset'] = 'SP_DC'
        with open(path,'w') as handle:
            json.dump(report,handle,ensure_ascii=True,indent=2)
        contexts = []
        prepared_parts = set()
        for group in plan['column_hoop_groups']:
            group_plan = dict(plan)
            group_plan['column_hoop_tie'] = group
            old = previous.get('column_hoop_groups',{}).get(group['group_id'])
            contexts.append(prepare_hoop(group_plan,mdb,path,fingerprint,old,XYPLANE,ON,
                                         prepared_parts,group['group_id']))
        # No more geometry edits after this point. Resolve faces on final topology.
        execute_column_beam(plan,mdb,path,ON,COMPUTED,batch)
        for context in contexts:
            execute_hoop(context,ON,COMPUTED,batch)
        batch.finish(path)
    except Exception as exc:
        if os.path.isfile(path):
            with open(path) as handle:
                report = json.load(handle)
        else:
            report = dict(project_id=plan['project_id'],model_name=plan['model_name'])
        report['overall_status'] = 'FAILED'
        report['warnings'] = plan.get('warnings',[])[:]
        report.setdefault('errors',[]).append(str(exc))
        report['traceback'] = traceback.format_exc()
        with open(path,'w') as handle:
            json.dump(report,handle,ensure_ascii=True,indent=2)
        raise
