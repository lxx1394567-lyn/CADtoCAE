"""SP_SC single-group A/A topology; shared geometry with DP."""
from .hoop_brace_geometry_plan import build_hoop_geometry_plan


def build_hoop_brace_plan(summary, hole_plan, components, half_selection=None):
    if summary.get('structure_type')!='SP_SC' or summary['project_id']!=hole_plan['project_id']:
        raise ValueError('SP_SC_HOOP_BRACE_SCOPE')
    if half_selection and half_selection!={'FRONT':'A','REAR':'A'}:
        raise ValueError('SP_SC requires explicit A/A rule')
    members=[m for m in summary['instances'] if m.get('canonical_role')=='HOOP']
    if set(m.get('connection_group') for m in members)!={'HOOP_01'}:
        raise ValueError('SP_SC_HOOP_GROUP_MAPPING_AMBIGUOUS')
    group=dict(group_id='HOOP_01',instance_a='HOOP_01_A')
    groups={s:group for s in ('FRONT','REAR')}
    mapping={s:dict(method='SP_SC_SINGLE_GROUP_A_A',group_id='HOOP_01') for s in groups}
    try:
        plan=build_hoop_geometry_plan(summary,hole_plan,components,groups,mapping)
    except ValueError as error:
        raise ValueError(str(error).replace('DP_','SP_SC_'))
    plan.update(structure_type='SP_SC',schema_version='step06-spsc-hoop-brace-v1')
    if plan['connections'][0]['selected_hole_id']==plan['connections'][1]['selected_hole_id']:
        raise ValueError('SP_SC_HOOP_BRACE_HOLE_AMBIGUOUS: same hole for Front/Rear')
    return plan


def spsc_hoop_artifacts(summary,holes,components,folder):
    from pathlib import Path
    from .hoop_brace_setup import hoop_brace_source
    folder=Path(folder);project=summary['project_id']
    plan=build_hoop_brace_plan(summary,holes,components)
    plan['purlin_report_path']=str(folder/(project+'_step06_b_connector_report.json'))
    plan['optional_audit_path']=plan['purlin_report_path']
    plan['purlin_report_policy']='OPTIONAL_AUDIT_LIVE_CAE_REQUIRED'
    return plan,hoop_brace_source(plan,folder/(project+'_step06_hoop_brace_connector_report.json'))
