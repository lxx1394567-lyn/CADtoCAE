"""Batch preflight and transaction around the validated single-connection method."""


def bg_preflight(plan,mdb):
    connections = plan['connections']
    if [p['connection_group'] for p in connections] != ['P01','P02','P03','P04']:
        raise ValueError('Expected exactly P01-P04, in order')
    prepared = []
    for p in connections:
        context = b1_preflight(p,mdb)
        if prepared and context[0].name != prepared[0][0].name:
            raise ValueError('All groups must belong to the same model')
        frame = context[1]
        axes = [frame['connector_local_1'],frame['connector_local_2'],frame['connector_local_3']]
        for axis in axes:
            if abs(norm(axis)-1.)>1.e-10:
                raise ValueError('Nonunit connector frame')
        if (abs(dot(axes[0],axes[1]))>1.e-10 or abs(dot(axes[1],axes[2]))>1.e-10
                or abs(dot(axes[0],axes[2]))>1.e-10 or dot(cross(axes[0],axes[1]),axes[2])<1.-1.e-10):
            raise ValueError('Nonorthogonal or left-handed connector frame')
        prepared.append(context)
    return prepared


def bg_state(model):
    a = model.rootAssembly
    return dict(features=list(a.features.keys()),sets=list(a.sets.keys()),surfaces=list(a.surfaces.keys()),
                constraints=list(model.constraints.keys()),sections=list(model.sections.keys()),
                assignments=len(a.sectionAssignments),orientations=len(a.connectorOrientations),rps=list(a.referencePoints.keys()))


def bg_rollback(model,before):
    """Remove only objects introduced by this batch after a kernel mutation error."""
    a = model.rootAssembly
    for seq,key in ((a.connectorOrientations,'orientations'),(a.sectionAssignments,'assignments')):
        for index in range(len(seq)-1,before[key]-1,-1):
            del seq[index]
    for repo,key in ((model.constraints,'constraints'),(a.surfaces,'surfaces'),(a.sets,'sets')):
        for name in list(repo.keys()):
            if name not in before[key]:
                del repo[name]
    new_features = []
    for name in a.features.keys():
        if name not in before['features']:
            new_features.append((a.features[name].id,name))
    for feature_id,name in sorted(new_features,reverse=True):
        if name in a.features.keys():
            del a.features[name]
    for name in list(model.sections.keys()):
        if name not in before['sections']:
            del model.sections[name]
    a.regenerate()
    if bg_state(model) != before:
        raise ValueError('Rollback state differs from pre-batch state')


def execute_connector_groups(plan,mdb,report_path):
    report = dict(project_id=plan['project_id'],status='FAILED',connections=[],errors=[],warnings=[],
        expected_connections=4,created_connections=0,expected_rps=8,created_rps=0,
        expected_couplings=8,created_couplings=0,expected_wires=4,created_wires=0,
        expected_sections=1,created_sections=0,behavior_status='PRESET_FOR_WORKFLOW_VALIDATION')
    report.update(bolt_preset_metadata())
    before = None
    try:
        prepared = bg_preflight(plan,mdb)
        model = prepared[0][0]; before = bg_state(model)
        report['preflight_status'] = 'PASS'
        for p,context in zip(plan['connections'],prepared):
            r = execute_connector_b1(p,mdb,None,prepared=context,shared_section=bool(report['connections']))
            names = b1_names(p['connection_group'])
            r.update(support_instance=p['source_instance'],purlin_instance=p['target_instance'],
                support_rp=names['rp_support'],purlin_rp=names['rp_purlin'],
                support_rp_global=p['rp_support'],purlin_rp_global=p['rp_purlin'],
                rp_distance=r['rp_distance_m'],coaxial_error=r['coaxial_error_m'],
                local_1=r['connector_local_1'],local_2=r['connector_local_2'],local_3=r['connector_local_3'])
            report['connections'].append(r)
        after = bg_state(model)
        if (len(after['constraints'])-len(before['constraints'])!=8 or len(after['sections'])-len(before['sections'])!=1
                or len(after['rps'])-len(before['rps'])!=8 or after['assignments']-before['assignments']!=4
                or after['orientations']-before['orientations']!=4):
            raise ValueError('Unexpected batch object counts')
        report.update(status='SUCCESS',created_connections=4,created_rps=8,created_couplings=8,
                      created_wires=4,created_sections=1)
    except Exception as exc:
        report['errors'].append(str(exc))
        if before is not None:
            try:
                bg_rollback(model,before)
                report['rollback_status'] = 'PASS'
                for r in report['connections']:
                    r['status'] = 'ROLLED_BACK'
            except Exception as rollback_error:
                report['rollback_status'] = 'FAILED'
                report['errors'].append(str(rollback_error))
                report['warnings'].append('Reopen clean Step06-A CAE; rollback could not be confirmed.')
        raise
    finally:
        with open(report_path,'w') as handle:
            json.dump(report,handle,indent=2,ensure_ascii=True,allow_nan=False)
    return report
