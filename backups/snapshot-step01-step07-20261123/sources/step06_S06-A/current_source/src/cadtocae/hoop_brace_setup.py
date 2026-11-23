"""Independent HOOP/Brace script generator; never rewrites the validated eight bolts."""
import json
from pathlib import Path
from .hole_setup import _helpers
from .hoop_brace_plan import build_hoop_brace_plan
from .runtime_compatibility import assert_runtime_compatible


def hoop_brace_source(plan,report_path):
    root=Path(__file__).parent
    source='# -*- coding: utf-8 -*-\nimport math\nimport json\n'
    source+=_helpers('analysis_geometry.py',{'add','sub','scale','dot','cross','norm','unit'})
    source+=_helpers('beam_brace_tie_runtime.py',{'is_numeric_triple','point3'})
    for module in ('hole_transforms','connector_geometry','purlin_bolt_preset_runtime','connector_b1_runtime','connector_groups_runtime','support_beam_connector_runtime','hoop_brace_runtime'):
        source+=(root/(module+'.py')).read_text(encoding='utf-8-sig')+'\n'
    source+=_helpers('connector_integration_runtime.py',{'safe_suppressed','integrated_step05_state'})
    source+=(root/'dp_hoop_brace_runtime.py').read_text(encoding='utf-8')+'\n'
    source+='PLAN=json.loads(%r)\n'%json.dumps(plan,ensure_ascii=True,sort_keys=True,allow_nan=False)
    source+='REPORT_PATH=json.loads(%r)\n'%json.dumps(str(report_path),ensure_ascii=True)
    source+="if __name__=='__main__':\n    from abaqus import mdb\n    execute_hoop_brace(PLAN,mdb,REPORT_PATH)\n"
    assert_runtime_compatible(source)
    return source


def generate_hoop_brace(folder,project):
    from .analysis_discovery import safe_project_id
    safe_project_id(project);folder=Path(folder).resolve(strict=True)
    summary=json.loads((folder/(project+'_assembly_summary.json')).read_text(encoding='utf-8-sig'))
    holes=json.loads((folder/(project+'_step06_plan.json')).read_text(encoding='utf-8-sig'))
    if holes['project_id']!=project or summary['project_id']!=project:raise ValueError('Project identity mismatch')
    from .hole_projects import _load_project
    _,components=_load_project(dict(project_id=project,input_files=dict(assembly_summary=str(folder/(project+'_assembly_summary.json')),components=str(folder/(project+'_components.xlsx')))))
    from .hoop_brace_plan import spsc_hoop_artifacts
    plan,_=spsc_hoop_artifacts(summary,holes,components,folder)
    script=folder/(project+'_step06_hoop_brace_connector_setup.py')
    target=folder/(project+'_step06_hoop_brace_connector_plan.json')
    source=hoop_brace_source(plan,folder/(project+'_step06_hoop_brace_connector_report.json'))
    for path in (script,target):
        if path.is_symlink():raise ValueError('Output cannot be symlink')
    target.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    script.write_text(source,encoding='utf-8')
    return script
