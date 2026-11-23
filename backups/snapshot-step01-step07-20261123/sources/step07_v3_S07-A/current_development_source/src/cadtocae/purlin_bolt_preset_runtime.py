"""Shared temporary translational elasticity preset, compatible with Python 2.7."""
import json

PURLIN_BOLT_SECTION = 'STEP06_CONNECTOR_SECTION_PURLIN_BOLT'


def resolve_step06_model(mdb, project_id):
    try:
        string_types = (basestring,)
    except NameError:
        string_types = (str,)
    if not isinstance(project_id, string_types) or not project_id.strip():
        raise ValueError('INVALID_PROJECT_ID: expected nonempty string')
    if project_id not in mdb.models.keys():
        raise ValueError('TARGET_MODEL_NOT_FOUND: ' + project_id +
                         '; Available Models: ' + repr(list(mdb.models.keys())))
    # Abaqus 2020 repositories require their native str key, not JSON unicode.
    for key in mdb.models.keys():
        if key == project_id:
            return mdb.models[key]


def bolt_preset_metadata():
    return dict(parameter_source='TEMPORARY_PRESET',behavior_status='PRESET_FOR_WORKFLOW_VALIDATION',
                elasticity_definition='LINEAR',elasticity_coupling='UNCOUPLED',
                components=[1,2,3],D11=5.0e8,D22=2.0e8,D33=2.0e8,stiffness_units='N/m')


def validate_bolt_preset(section):
    from abaqusConstants import CARTESIAN, NONE, LINEAR, UNCOUPLED
    if section.translationalType!=CARTESIAN or section.rotationalType!=NONE:
        raise ValueError('Expected CARTESIAN without rotational components')
    options=section.behaviorOptions
    if len(options)!=1:raise ValueError('Expected only linear uncoupled elasticity')
    option=options[0]
    table=[]
    for row in option.table:table.append(tuple(row))
    if (option.behavior!=LINEAR or option.coupling!=UNCOUPLED or tuple(option.components)!=(1,2,3)
            or tuple(table)!=((5.0e8,2.0e8,2.0e8),)):
        raise ValueError('PURLIN_BOLT preset mismatch')


def apply_bolt_preset(section):
    from abaqusConstants import CARTESIAN, NONE, LINEAR, UNCOUPLED
    import connectorBehavior
    if section.translationalType!=CARTESIAN or section.rotationalType!=NONE:
        raise ValueError('Expected CARTESIAN without rotational components')
    option=connectorBehavior.ConnectorElasticity(behavior=LINEAR,coupling=UNCOUPLED,
        components=(1,2,3),table=((5.0e8,2.0e8,2.0e8),))
    section.setValues(behaviorOptions=(option,))
    validate_bolt_preset(section)


def update_existing_bolt_preset(mdb,report_path,project_id):
    from abaqusConstants import KINEMATIC, ON, OFF
    report=bolt_preset_metadata()
    report.update(status='FAILED',errors=[],connector_section=PURLIN_BOLT_SECTION,connections=[])
    section=None;old_options=None;changed=False
    try:
        model=resolve_step06_model(mdb,project_id);assembly=model.rootAssembly
        for group in ('P01','P02','P03','P04'):
            for family,sides in (('PURLIN',('SUPPORT','PURLIN')),('SUPPORT_BEAM',('SUPPORT_BEAM','BEAM'))):
                wire='STEP06_WIRE_'+group+'_'+family+'_BOLT'
                if wire not in assembly.sets.keys() or len(assembly.getFeatureEdges(name=wire))!=1:
                    raise ValueError('Missing connector wire: '+wire)
                assignments=[]
                for assignment in assembly.sectionAssignments:
                    region=assignment.region
                    region_name=region.name if hasattr(region,'name') else region[0]
                    if region_name==wire:assignments.append(assignment)
                if len(assignments)!=1 or assignments[0].sectionName!=PURLIN_BOLT_SECTION:
                    raise ValueError('Connector Section assignment mismatch: '+wire)
                for side in sides:
                    c=model.constraints['STEP06_COUPLING_'+group+'_'+side]
                    if c.couplingType!=KINEMATIC or (c.u1,c.u2,c.u3,c.ur1,c.ur2,c.ur3)!=(ON,ON,ON,OFF,OFF,OFF):
                        raise ValueError('KINEMATIC translation-only coupling required')
                report['connections'].append(dict(connection_group=group,family=family,wire=wire,connector_section=PURLIN_BOLT_SECTION))
        section=model.sections[PURLIN_BOLT_SECTION]
        old_options=tuple(section.behaviorOptions)
        changed=True
        apply_bolt_preset(section)
        report.update(status='SUCCESS',verified_connectors=8,verified_couplings=16,updated_sections=1)
    except Exception as exc:
        report['errors'].append(str(exc))
        if changed:
            try:
                section.setValues(behaviorOptions=old_options);report['rollback_status']='PASS'
            except Exception as error:
                report['rollback_status']='FAILED';report['errors'].append(str(error))
        raise
    finally:
        with open(report_path,'w') as handle:json.dump(report,handle,indent=2,ensure_ascii=True)
    return report
