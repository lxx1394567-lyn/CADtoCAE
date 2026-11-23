"""Generate a separate DP append-only family script after the eight Purlin bolts."""
from pathlib import Path
from .dp_hoop_brace_plan import build_dp_hoop_brace_plan
from .hoop_brace_setup import hoop_brace_source


def dp_hoop_artifacts(summary, holes, components, folder):
    folder=Path(folder);project=summary['project_id']
    plan=build_dp_hoop_brace_plan(summary,holes,components)
    plan['purlin_report_path']=str(folder/(project+'_step06_b_connector_report.json'))
    plan['optional_audit_path']=plan['purlin_report_path']
    plan['purlin_report_policy']='OPTIONAL_AUDIT_LIVE_CAE_REQUIRED'
    report=folder/(project+'_step06_hoop_brace_connector_report.json')
    return plan,hoop_brace_source(plan,report)
