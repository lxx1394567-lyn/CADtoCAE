"""Generate standalone Abaqus 2020 script for the DP ruleset."""
import hashlib
import json
from pathlib import Path
from .dp_rules import build_dp_plan
from .runtime_compatibility import assert_runtime_compatible


def generate(files,config=None,output_dir=None,final_output_dir=None):
    plan=build_dp_plan(files,config)
    encoded=json.dumps(plan,sort_keys=True,ensure_ascii=True,allow_nan=False)
    fingerprint=hashlib.sha256(encoded.encode('utf-8')).hexdigest()
    output=Path(output_dir or files.assembly_summary.parent);output.mkdir(parents=True,exist_ok=True)
    project=plan['project_id']
    paths=dict(plan=output/(project+'_analysis_plan.json'),script=output/(project+'_analysis_setup.py'),
               runtime_report=Path(final_output_dir or output)/(project+'_analysis_setup_report.json'))
    source='# -*- coding: utf-8 -*-\nimport json\nPLAN = json.loads(%r)\n' % encoded
    source+='FINGERPRINT = %r\nREPORT = %r\n' % (fingerprint,str(paths['runtime_report'].resolve()).replace('\\','/'))
    root=Path(__file__).parent
    for name in ('tie_preflight_runtime.py','beam_brace_tie_runtime.py','column_axis.py',
                 'column_column_tie_runtime.py','column_hoop_tie_runtime.py','column_beam_coupling_runtime.py','dp_runtime.py'):
        content=(root/name).read_text(encoding='utf-8')
        if name=='beam_brace_tie_runtime.py':content=content.split("\nif __name__ == '__main__':",1)[0]
        source+='\n'+content+'\n'
    source+="\nif __name__ == '__main__':\n    from abaqus import mdb\n    from abaqusConstants import XYPLANE, ON, OFF, COMPUTED, DISTRIBUTING, WHOLE_SURFACE, UNIFORM\n    import assembly\n    import interaction\n    import mesh\n    execute_dp(PLAN,mdb,REPORT,FINGERPRINT,XYPLANE,ON,OFF,COMPUTED,DISTRIBUTING,WHOLE_SURFACE,UNIFORM)\n"
    assert_runtime_compatible(source,str(paths['script']));compile(source,str(paths['script']),'exec')
    paths['plan'].write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    paths['script'].write_text(source,encoding='utf-8')
    return paths
