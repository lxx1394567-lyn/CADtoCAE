"""User-mode script generation, entirely independent of CAE file lifecycle."""
import ast
import copy
import hashlib
import json
import re
from pathlib import Path
from .step07_pipeline import RUNTIMES
from .step07_runtime_bundle import bundle_runtime
from .step07_rules import STAGE1_STEPS
from .step07_mesh_rules import MESH_RULES
from .runtime_compatibility import assert_runtime_compatible

STAGES={1:'tie_setup',2:'step_setup',3:'boundary_setup',4:'mesh_setup',5:'load_setup',6:'inp_export'}

def generate_inplace(summary_path,output_dir,hole_report_path,stage=0,overwrite=False,load_workbook=None,job_id="J13",selected_cae=None):
    summary=json.loads(Path(summary_path).read_text(encoding='utf-8-sig'));project=summary['project_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',project) or summary['model_name']!=project:raise ValueError('PROJECT_IDENTITY_INVALID')
    holes=json.loads(Path(hole_report_path).read_text(encoding='utf-8-sig'))
    if holes.get('project_id')!=project or holes.get('status')!='SUCCESS':raise ValueError('HOLE_REPORT_INVALID')
    if stage not in (0,1,2,3,4,5,6):raise ValueError('INVALID_STAGE')
    out=Path(output_dir).resolve();base=Path(__file__).parent
    runtime,audit=bundle_runtime([(n,(base/n).read_text(encoding='utf-8-sig')) for n in RUNTIMES+['step07_load_runtime.py','step07_inp_runtime.py','step07_multitype_runtime.py','step07_hoop_region_runtime.py','step07_inplace_runtime.py','step07_identity_runtime.py']],entry='u7_run')
    forbidden={'openMdb','closeMdb','saveAs','Mdb','p7_run','sg_dispatch','Popen','system','copyfile','copy2'}
    for node in ast.walk(ast.parse(runtime)):
        if isinstance(node,ast.Call):
            name=node.func.attr if isinstance(node.func,ast.Attribute) else (node.func.id if isinstance(node.func,ast.Name) else '')
            if name in forbidden:raise ValueError('USER_RUNTIME_FORBIDDEN_CALL: '+name)
    rules=copy.deepcopy(MESH_RULES);rules['hoop_quality_repair_sizes'] += [.0035,.003,.0025,.002]
    digest=hashlib.sha256(runtime.encode()).hexdigest();plans=[];files={}
    cases=[]
    mapping_path=Path(summary_path).parent/(project+'_step07_project.json')
    mapping=json.loads(mapping_path.read_text(encoding='utf-8-sig')) if mapping_path.exists() else None
    if not load_workbook and mapping and mapping.get('mode') in ('DEMO_REUSE_M07','LUAN_CONFIRMED_POS'):load_workbook=mapping.get('source_workbook')
    if load_workbook is not None:
        from .step07_load_input import read_load_cases
        mapping_path=Path(summary_path).parent/(project+'_step07_project.json')
        mapping=json.loads(mapping_path.read_text(encoding='utf-8-sig')) if mapping_path.exists() else None
        for configuration in read_load_cases(load_workbook,summary,mapping):
            case=configuration['case_id'];job=configuration['job_id']
            load_path=out/(project+'_'+job+'_'+case+'_step07_loads.json')
            load_text=json.dumps(configuration,ensure_ascii=True,indent=2);files[load_path]=load_text
            cases.append(dict(load_config_path=str(load_path),load_config_sha256=hashlib.sha256(load_text.encode('utf-8')).hexdigest(),expected_case_id=case,expected_job_id=job,expected_model_id=configuration['model_id'],groups=configuration['groups']))
    if summary.get('structure_type')=='SP_DC':
        rules['column_down_circumference_divisions']=32
        rules['sizes']['COLUMN_DOWN']=.04
        rules['hole_face_transition_size']=.02
        rules['beam_connection_size']=.02
        if project=='SP_DC_ANG19_LUANLUANLUAN-T0203':
            rules['project_hoop_uniform_sizes'][project]={'HOOP_01':.008,'HOOP_02':.008,'HOOP_03':.008}
    for n in (list(STAGES) if stage==0 else [stage]):
        variants=(cases or [dict(expected_case_id=x,load_config_path=None,load_config_sha256=None) for x in ('POS','NEG')]) if n==5 else [None]
        for entry in variants:
            suffix='load_'+entry['expected_case_id'] if n==5 else STAGES[n]
            path=out/(project+'_step07_%02d_'%n+suffix+'.py')
            c=dict(schema='step07-inplace-2',execution_mode='CURRENT_MDB_IN_PLACE',stage=n,project_id=project,model_name=project,assembly_summary=summary,summary=summary,steps=STAGE1_STEPS,groups=sorted({x['connection_group'] for x in summary.get('instances',[]) if x['canonical_role']=='PURLIN_LOCAL'}),geometry_tolerance_m=2e-6,tie_boundary_simplification=True,mesh_rules=rules,hole_report=holes,comparison_baseline={},output_dir=str(out),logs_dir=str(out/'Step07_Logs'),script=str(path),runtime_sha256=digest)
            if selected_cae:c['selected_cae']=str(Path(selected_cae).resolve(strict=True))
            if entry:c.update(entry)
            if n==6:
                if mapping and mapping.get('project_id')==project:c['trial_materials']=mapping.get('trial_materials',{})
                c['load_case_configs']=cases
                if cases:c['groups']=cases[0]['groups']
            code=runtime+'\nINPLACE_PLAN=json.loads(%r)\nif __name__ == "__main__":\n    u7_run(INPLACE_PLAN)\n'%json.dumps(c,ensure_ascii=True)
            assert_runtime_compatible(code);files[path]=code;plans.append(c)
    manifest=out/(project+'_step07_inplace_manifest.json')
    result=dict(schema='step07-inplace-1',stages=plans,manifest=str(manifest),runtime_sha256=digest,runtime_bundle_audit=audit,mode='CURRENT_MDB_IN_PLACE',cae_files_created=False,load_status=('_'.join(x['expected_case_id'] for x in cases)+'_READY') if cases else 'WAITING_USER_INPUT',inp_status='TEST_ONLY_PERMISSION_REQUIRED',step06_execution=dict(run=['hole_setup.py'],generate_but_do_not_run=['connector_setup.py','hoop_brace_connector_setup.py']))
    files[manifest]=json.dumps(result,indent=2)
    if selected_cae:
        association=out/(project+'_step07_cae.json')
        files[association]=json.dumps(dict(project_id=project,target_model=project,cae_path=str(Path(selected_cae).resolve(strict=True)),internal_check='DEFERRED_TO_CURRENT_MDB_RUNTIME; EXE never opens CAE'),indent=2)
    from .step07_output import write_generated
    result['file_update']=write_generated(files,out,project,overwrite)
    return result
