"""Independent B1 generator. Never executes the Step06-A hole runtime."""
import json
from pathlib import Path
from .analysis_discovery import safe_project_id
from .hole_setup import _helpers
from .connector_b1_plan import build_b1_plan
from .connector_groups import build_group_plan
from .runtime_compatibility import assert_runtime_compatible


def connector_script_source(plan, report_path):
    source = '# -*- coding: utf-8 -*-\n# Step06-B1: run on a clean successful Step06-A CAE.\nimport math\n'
    source += _helpers('analysis_geometry.py', {'add','sub','scale','dot','cross','norm','unit'})
    source += (Path(__file__).parent/'connector_geometry.py').read_text(encoding='utf-8-sig')+'\n'
    source += (Path(__file__).parent/'purlin_bolt_preset_runtime.py').read_text(encoding='utf-8')+'\n'
    source += (Path(__file__).parent/'connector_b1_runtime.py').read_text(encoding='utf-8')
    entry = 'execute_connector_b1'
    if 'connections' in plan:
        source += (Path(__file__).parent/'connector_groups_runtime.py').read_text(encoding='utf-8')
        entry = 'execute_connector_groups'
    source += '\nPLAN = json.loads(%r)\n' % json.dumps(plan,sort_keys=True,ensure_ascii=True,allow_nan=False)
    source += 'REPORT_PATH = json.loads(%r)\n' % json.dumps(str(report_path),ensure_ascii=True)
    source += "if __name__ == '__main__':\n    from abaqus import mdb\n    %s(PLAN,mdb,REPORT_PATH)\n" % entry
    assert_runtime_compatible(source,'step06_b_connector_setup.py')
    return source


def generate_connector_setup(plan_path, report_path, output_folder):
    holes = json.loads(Path(plan_path).read_text(encoding='utf-8-sig'))
    report = json.loads(Path(report_path).read_text(encoding='utf-8-sig'))
    summary=json.loads((Path(plan_path).parent/(holes['project_id']+'_assembly_summary.json')).read_text(encoding='utf-8-sig'))
    plan = build_group_plan(holes,report,summary.get('structure_type'))
    project = plan['project_id']; safe_project_id(project)
    folder = Path(output_folder).resolve(strict=True)
    script = folder/(project+'_step06_b_connector_setup.py')
    b_report = folder/(project+'_step06_b_connector_report.json')
    b_plan = folder/(project+'_step06_b_connector_plan.json')
    source = connector_script_source(plan,b_report)
    for path in (script,b_plan):
        if path.is_symlink():
            raise ValueError('Output cannot be a symbolic link')
    b_plan.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    script.write_text(source,encoding='utf-8')
    return script
