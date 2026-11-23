"""Compose SP_DC from common runtimes without changing the SP_SC generator."""
import hashlib
import json
from pathlib import Path

from .analysis_defaults import DC_CONFIG_ID, family_analysis_config
from .analysis_project import validate_project_files
from .beam_brace_tie import build_plan
from .main_frame_assembly import _read_named_points
from .runtime_compatibility import assert_runtime_compatible
from .sp_dc_rules import normalized_components, column_beam_plan, hoop_group_plans, input_warnings, DC_RULES


def build_sp_dc_plan(files,config=None):
    summary=validate_project_files(files)
    if summary['structure_type']!='SP_DC':raise ValueError('SP_DC ruleset requires SP_DC summary')
    config=config or family_analysis_config('SP_DC')
    for rule in DC_RULES:
        if config.get(rule,{}).get('enabled') is not True:raise ValueError('SP_DC full setup requires '+rule)
    plan=build_plan(files,config)
    components=normalized_components(files.components)
    column=column_beam_plan(summary,components,config['COLUMN_BEAM_TIE'])
    hoops=hoop_group_plans(summary,components)
    for c in column['connections']:
        for b in plan['connections']:
            if max(c['beam_range'][0],b['beam_range'][0])<min(c['beam_range'][1],b['beam_range'][1]):
                raise ValueError('Column/brace beam slave patches overlap')
    # The common executor partitions all shell members before selecting regions.
    for member in column['columns']:
        plan['instances'].append({k:member[k] for k in ('instance_name','part_name','role','component_geometry')})
    for part,stations in column['partitions'].items():plan['partitions'].setdefault(part,[]).extend(stations)
    points,_=_read_named_points(files.coordinate)
    plan.update(structure_type='SP_DC',ruleset='SP_DC',supported_rules=DC_RULES,
                column_beam_tie=column,column_hoop_groups=hoops,
                warnings=input_warnings(summary,components,points))
    plan['source_files']['analysis_config']=DC_CONFIG_ID
    names=[c['tie'] for c in plan['connections']+column['connections']]
    for group in hoops:names.extend(h['tie'] for h in group['halves'])
    plan['expected_constraints']=dict(ties=names,tie_count=len(names),reference_points=0,couplings=0)
    return plan


def generate(files,config=None,output_dir=None,final_output_dir=None):
    plan=build_sp_dc_plan(files,config)
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
                 'column_column_tie_runtime.py','column_hoop_tie_runtime.py','column_beam_tie_runtime.py','sp_dc_runtime.py'):
        content=(root/name).read_text(encoding='utf-8')
        if name=='beam_brace_tie_runtime.py':content=content.split("\nif __name__ == '__main__':",1)[0]
        source+='\n'+content+'\n'
    source+="\nif __name__ == '__main__':\n    from abaqus import mdb\n    from abaqusConstants import XYPLANE, ON, COMPUTED\n    import assembly\n    import interaction\n    import mesh\n    execute_sp_dc(PLAN,mdb,REPORT,FINGERPRINT,XYPLANE,ON,COMPUTED)\n"
    assert_runtime_compatible(source,str(paths['script']));compile(source,str(paths['script']),'exec')
    paths['plan'].write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    paths['script'].write_text(source,encoding='utf-8')
    return paths
