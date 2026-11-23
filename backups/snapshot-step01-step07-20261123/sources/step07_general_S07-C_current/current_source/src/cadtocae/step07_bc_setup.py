"""Stage 2 generator. Accepted input is explicit; no automatic version selection."""
import hashlib
import json
import re
import shutil
from pathlib import Path
from .runtime_compatibility import assert_runtime_compatible
from .step07_rules import STAGE1_STEPS


def generate_stage2(summary_path, accepted_cae, output_dir, mode='CURRENT_SESSION_DEBUG', groups=('P01','P02','P03','P04')):
    if mode not in ('CURRENT_SESSION_DEBUG','INDEPENDENT_CAE'):
        raise ValueError('Invalid execution mode')
    if tuple(groups) not in (('P01',), ('P01','P02','P03','P04')):
        raise ValueError('Validate P01 first, then all four groups')
    summary=json.loads(Path(summary_path).read_text(encoding='utf-8-sig'))
    project=summary['project_id']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',project) or summary['model_name']!=project:
        raise ValueError('Invalid full project identity')
    source=Path(accepted_cae).resolve(strict=True)
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    cae=out/'CAE_Results'
    if cae.is_symlink() or (cae.exists() and cae.resolve()!=cae):raise ValueError('Redirected CAE_Results')
    cae.mkdir(exist_ok=True)
    root=Path(__file__).parent
    runtime=(root/'step07_runtime.py').read_text(encoding='utf-8')+'\n'+(root/'step07_bc_runtime.py').read_text(encoding='utf-8')
    for version in range(1,10000):
        suffix='' if version==1 else '_v'+str(version)
        prefix=project+'_step07_02'+suffix
        plan=dict(project_id=project,assembly_summary=summary,steps=STAGE1_STEPS,
                  input_cae=str(source),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  output_dir=str(out),execution_mode=mode,groups=list(groups),geometry_tolerance_m=2e-6,
                  output_cae=str(cae/(prefix+'.cae')),report_path=str(out/(prefix+'_report.json')),
                  log_path=str(out/(prefix+'.log')),scratch_cae=str(cae/(prefix+'_input_copy.cae')),
                  backup_cae=str(cae/(prefix+'_before_bc.cae')),disk_backup_cae=str(cae/(prefix+'_before_bc_disk.cae')),
                  manual_working_copy=str(cae/(prefix+'_session_input.cae')),
                  output_version=version,accepted_input_explicitly_selected=True)
        script=out/(project+'_step07_02_bc'+suffix+'.py');plan_file=out/(prefix+'_plan.json')
        if Path(plan['output_cae'])==source:raise ValueError('Cannot overwrite accepted CAE')
        occupied=any(Path(plan[k]).exists() for k in ('output_cae','report_path','log_path','scratch_cae','backup_cae','disk_backup_cae'))
        if occupied or script.exists() or plan_file.exists() or Path(plan['manual_working_copy']).exists():continue
        text=runtime+'\nSTAGE2_PLAN=json.loads(%r)\n'%json.dumps(plan,ensure_ascii=True,allow_nan=False)
        text+='if __name__ == "__main__":\n    b2_run(STAGE2_PLAN)\n'
        assert_runtime_compatible(text,script.name)
        with script.open('x',encoding='utf-8',newline='') as handle:handle.write(text)
        with plan_file.open('x',encoding='utf-8') as handle:json.dump(plan,handle,indent=2)
        if mode=='CURRENT_SESSION_DEBUG':
            with source.open('rb') as original, Path(plan['manual_working_copy']).open('xb') as working:
                shutil.copyfileobj(original,working)
        return dict(script=str(script),plan=plan)
    raise ValueError('Too many output versions')
