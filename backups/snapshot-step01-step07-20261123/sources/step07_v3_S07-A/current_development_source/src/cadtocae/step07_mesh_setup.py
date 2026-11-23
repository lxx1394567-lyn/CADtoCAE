"""Stage 3 generator. Accepted input is explicit; no automatic version selection."""
import hashlib
import json
import re
import shutil
from pathlib import Path
from .runtime_compatibility import assert_runtime_compatible
from .step07_rules import STAGE1_STEPS
from .step07_mesh_rules import MESH_RULES


def generate_stage3(summary_path, accepted_cae, output_dir, mode='CURRENT_SESSION_DEBUG'):
    if mode not in ('CURRENT_SESSION_DEBUG','INDEPENDENT_CAE'):
        raise ValueError('Invalid execution mode')
    summary=json.loads(Path(summary_path).read_text(encoding='utf-8-sig'))
    project=summary['project_id']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',project) or summary['model_name']!=project:
        raise ValueError('Invalid full project identity')
    source=Path(accepted_cae).resolve(strict=True)
    if not re.fullmatch(re.escape(project)+r'_step07_02(?:_v[2-9][0-9]*|_v1[0-9]+)?\.cae',source.name,re.I):
        raise ValueError('Optimization requires an explicitly accepted Step07-02 CAE')
    hole_path=Path(summary_path).parent/(project+'_step06_hole_report.json')
    holes=json.loads(hole_path.read_text(encoding='utf-8-sig')) if hole_path.exists() else {}
    if holes and (holes.get('project_id')!=project or holes.get('status')!='SUCCESS'):
        raise ValueError('Step06 hole report identity/status invalid')
    baseline_path=Path(summary_path).parent/(project+'_step07_03_report.json')
    baseline=json.loads(baseline_path.read_text(encoding='utf-8-sig')) if baseline_path.exists() else {}
    if baseline and (baseline.get('project_id')!=project or not baseline.get('status','').startswith('MESH_COMPLETE')):
        baseline={}
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    cae=out/'CAE_Results'
    if cae.is_symlink() or (cae.exists() and cae.resolve()!=cae):raise ValueError('Redirected CAE_Results')
    cae.mkdir(exist_ok=True)
    root=Path(__file__).parent
    runtime=(root/'step07_runtime.py').read_text(encoding='utf-8')+'\n'+(root/'step07_mesh_runtime.py').read_text(encoding='utf-8')
    for version in range(1,10000):
        suffix='' if version==1 else '_v'+str(version)
        prefix=project+'_step07_03'+suffix
        plan=dict(project_id=project,assembly_summary=summary,steps=STAGE1_STEPS,hole_report=holes,
                  hole_report_source=str(hole_path) if holes else None,
                  comparison_baseline=baseline,comparison_source=str(baseline_path) if baseline else None,
                  comparison_sha256=hashlib.sha256(baseline_path.read_bytes()).hexdigest() if baseline else None,
                  input_cae=str(source),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  output_dir=str(out),execution_mode=mode,mesh_rules=MESH_RULES,
                  output_cae=str(cae/(prefix+'.cae')),report_path=str(out/(prefix+'_report.json')),
                  log_path=str(out/(prefix+'.log')),scratch_cae=str(cae/(prefix+'_input_copy.cae')),
                  backup_cae=str(cae/(prefix+'_before_mesh.cae')),disk_backup_cae=str(cae/(prefix+'_before_mesh_disk.cae')),
                  manual_working_copy=str(cae/(prefix+'_session_input.cae')),
                  output_version=version,accepted_input_explicitly_selected=True)
        script=out/(project+'_step07_03_mesh'+suffix+'.py');plan_file=out/(prefix+'_plan.json')
        if Path(plan['output_cae'])==source:raise ValueError('Cannot overwrite accepted CAE')
        occupied=any(Path(plan[k]).exists() for k in ('output_cae','report_path','log_path','scratch_cae','backup_cae','disk_backup_cae'))
        if occupied or script.exists() or plan_file.exists() or Path(plan['manual_working_copy']).exists():continue
        text=runtime+'\nSTAGE3_PLAN=json.loads(%r)\n'%json.dumps(plan,ensure_ascii=True,allow_nan=False)
        text+='if __name__ == "__main__":\n    m3_run(STAGE3_PLAN)\n'
        assert_runtime_compatible(text,script.name)
        with script.open('x',encoding='utf-8',newline='') as handle:handle.write(text)
        with plan_file.open('x',encoding='utf-8') as handle:json.dump(plan,handle,indent=2)
        if mode=='CURRENT_SESSION_DEBUG':
            with source.open('rb') as original, Path(plan['manual_working_copy']).open('xb') as working:
                shutil.copyfileobj(original,working)
        return dict(script=str(script),plan=plan)
    raise ValueError('Too many output versions')
