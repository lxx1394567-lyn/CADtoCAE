"""Python 2.7 orchestration of the two validated connector families."""
import os


def integrated_beam_preflight(plan, model):
    from abaqusConstants import ON
    a = model.rootAssembly
    regions = []
    for connection in plan['connections']:
        for key, name in sb_names(connection['connection_group']).items():
            if key == 'connector_section':
                continue
            for repo in (a.features, a.sets, a.surfaces, model.constraints):
                if name in repo.keys():
                    raise ValueError('EXISTING_STEP06_B_OBJECT: Existing SUPPORT_BEAM object: ' + name)
        b1_frame(connection)
        for side, solid in (('source', True), ('target', False)):
            name = str(connection[side + '_instance'])
            if name not in a.instances.keys():
                raise ValueError('STEP06_A_REQUIRED: INSTANCE_MISSING: target model missing instance ' + name)
            instance = a.instances[name]
            if instance.partName != connection[side + '_part'] or instance.dependent != ON:
                raise ValueError('STEP06_A_REQUIRED: instance/Part mismatch ' + name)
            center = connection['rp_support'] if solid else connection['rp_purlin']
            try:
                region, evidence = b1_resolve(instance, center, connection, solid)
            except Exception as error:
                raise ValueError('STEP06_A_REQUIRED: HOLE_REGION_MISSING: ' + name + ': ' + str(error))
            if not solid:
                regions.append(region)
    return sb_unique(regions)


def integrated_step05_state(model):
    constraints = sorted([n for n in model.constraints.keys() if n.startswith('STEP05_')])
    if not constraints:
        raise ValueError('STEP05_REQUIRED: expected existing Step05 constraints')
    a = model.rootAssembly
    return dict(constraints=[(n, str(model.constraints[n])) for n in constraints],
                features=[(n, a.features[n].id) for n in sorted(a.features.keys()) if n.startswith('STEP05_')])


def execute_integrated_connectors(plan, mdb, report_path):
    before = None
    report = dict(project_id=plan['project_id'], status='FAILED', errors=[],
                  step06_version=plan['step06_version'], generator_version=plan['generator_version'],
                  preload_target_n=20000.0, preload_local_component=1,
                  preload_policy='PRESERVE_EXISTING_NO_LOAD_CREATED')
    try:
        try:
            with open(plan['hole_report_path']) as handle:
                holes_report = json.load(handle)
            holes = plan['hole_plan']
            for compatible in plan.get('compatible_hole_plans', []):
                if fingerprint(compatible) == holes_report.get('plan_fingerprint'):
                    holes = compatible
                    break
        except Exception as error:
            raise ValueError('STEP06_A_REQUIRED: ' + str(error))
        purlin = build_group_plan(holes, holes_report, plan.get('structure_type'))
        beam = build_support_beam_geometry(holes, holes_report, plan.get('structure_type'))
        prepared = bg_preflight(purlin, mdb)
        model = prepared[0][0]
        step05 = integrated_step05_state(model)
        keys = integrated_beam_preflight(beam, model)
        before = bg_state(model)
        first = execute_connector_groups(purlin, mdb, report_path)
        beam['support_purlin_connections'] = first['connections']
        final = execute_support_beam(beam, mdb, report_path)
        if integrated_step05_state(model) != step05:
            raise ValueError('Step05 objects changed')
        report.update(final)
        report.update(status='SUCCESS', step05_regression_status='PASS',
                      beam_edge_geometry_keys=keys, step06_total_connectors=8)
    except Exception as error:
        report['status'] = 'FAILED'
        report['errors'].append(str(error))
        if before is not None:
            try:
                bg_rollback(model, before)
                report['integration_rollback_status'] = 'PASS'
            except Exception as rollback_error:
                report['integration_rollback_status'] = 'FAILED'
                report['errors'].append(str(rollback_error))
        raise
    finally:
        with open(report_path, 'w') as handle:
            json.dump(report, handle, indent=2, ensure_ascii=True, allow_nan=False)
    return report
