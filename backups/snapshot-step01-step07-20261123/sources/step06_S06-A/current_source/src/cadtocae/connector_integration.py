"""Generate both connector families before CAE runs, defer report consumption to runtime."""
import json
from pathlib import Path
from .hole_setup import _helpers
from .runtime_compatibility import assert_runtime_compatible
from .step06_version import version_fields, preload_record


def integrated_plan(holes, folder):
    result = dict(project_id=holes['project_id'],schema_version='step06-connectors-integrated-v1',
                hole_plan=holes,hole_report_path=str(folder/(holes['project_id']+'_step06_hole_report.json')),
                families=['SUPPORT_PURLIN','SUPPORT_BEAM'],groups=['P01','P02','P03','P04'],
                expected_rps=16,expected_couplings=16,expected_wires=8,expected_connectors=8,
                **version_fields(),**preload_record())
    summary_path=folder/(holes['project_id']+'_assembly_summary.json')
    structure_type=holes.get('structure_type')
    if summary_path.is_file():
        summary=json.loads(summary_path.read_text(encoding='utf-8-sig'))
        if summary.get('project_id')!=holes['project_id']:raise ValueError('Project identity mismatch in assembly summary')
        structure_type=summary.get('structure_type')
    result['structure_type']=structure_type
    strip=lambda p:json.dumps({k:v for k,v in p.items() if k not in ('step06_version','generator_version')},sort_keys=True)
    candidates=[]
    for suffix in ('_step06_plan.json','_step06_connector_plan.json'):
        previous=folder/(holes['project_id']+suffix)
        if previous.is_file():
            try:
                saved=json.loads(previous.read_text(encoding='utf-8-sig'))
                candidates.extend(saved.get('compatible_hole_plans',[]) if suffix.endswith('connector_plan.json') else [saved])
            except (ValueError,OSError):
                pass
    compatible=[]
    for saved in candidates:
        if strip(saved)==strip(holes) and saved not in compatible:compatible.append(saved)
    result['compatible_hole_plans']=compatible
    return result


def integrated_source(plan, report_path):
    root=Path(__file__).parent
    source='# -*- coding: utf-8 -*-\n# Support-Purlin + Support-Beam; run AFTER Step06-A.\nimport math\nimport hashlib\nimport json\n'
    source+=_helpers('analysis_geometry.py',{'add','sub','scale','dot','cross','norm','unit'})
    source+=(root/'hole_transforms.py').read_text(encoding='utf-8-sig')+'\n'
    source+='point = step04_local_point_to_global\nvector = step04_local_vector_to_global\n'
    source+=(root/'connector_geometry.py').read_text(encoding='utf-8-sig')+'\n'
    source+=_helpers('connector_b1_plan.py',{'fingerprint','_one','_near','build_b1_plan'})
    source+=_helpers('connector_groups.py',{'build_group_plan'})
    source+=_helpers('support_beam_connector.py',{'build_support_beam_geometry'})
    for name in ('purlin_bolt_preset_runtime','connector_b1_runtime','connector_groups_runtime','support_beam_connector_runtime','connector_integration_runtime'):
        source+=(root/(name+'.py')).read_text(encoding='utf-8-sig')+'\n'
    # Explicit name inventory also makes the generated script easy to audit before execution.
    source+='# Semantic RPs: STEP06_RP_P01_SUPPORT / STEP06_RP_P04_SUPPORT; SUPPORT_BEAM uses its own namespace.\n'
    source+='PLAN = json.loads(%r)\n'%json.dumps(plan,ensure_ascii=True,sort_keys=True,allow_nan=False)
    source+='REPORT_PATH = json.loads(%r)\n'%json.dumps(str(report_path),ensure_ascii=True)
    source+="if __name__ == '__main__':\n    from abaqus import mdb\n    execute_integrated_connectors(PLAN, mdb, REPORT_PATH)\n"
    assert_runtime_compatible(source)
    return source
