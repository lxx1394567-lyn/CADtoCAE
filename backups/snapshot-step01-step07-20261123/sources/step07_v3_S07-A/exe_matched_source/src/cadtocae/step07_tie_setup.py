"""Independent protected-input Step07 Tie-only script generator."""
import json,hashlib,re,shutil
from pathlib import Path
from .runtime_compatibility import assert_runtime_compatible

def generate_tie_setup(summary_path,input_cae,output_dir):
    summary=json.loads(Path(summary_path).read_text(encoding='utf-8-sig'));project=summary['project_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',project) or summary['model_name']!=project:raise ValueError('PROJECT_IDENTITY_INVALID')
    source=Path(input_cae).resolve(strict=True)
    if not source.name.startswith(project+'_step06_tie_only_'):raise ValueError('FRESH_HOLE_ONLY_INPUT_REQUIRED')
    root=Path(output_dir).resolve();root.mkdir(parents=True,exist_ok=True);cae=root/'CAE_Results';cae.mkdir(exist_ok=True)
    if cae.is_symlink() or cae.resolve()!=cae:raise ValueError('REDIRECTED_OUTPUT')
    runtime=Path(__file__).with_name('step07_tie_runtime.py').read_text(encoding='utf-8-sig')
    for v in range(1,10000):
        suffix='' if v==1 else '_v'+str(v);stem=project+'_step07_04_tie'+suffix
        c=dict(project_id=project,summary=summary,input_cae=str(source),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
               working_copy=str(cae/(stem+'_session_input.cae')),backup_cae=str(cae/(stem+'_before_tie.cae')),output_cae=str(cae/(stem+'.cae')),
               report_path=str(root/(stem+'_report.json')),log_path=str(root/(stem+'.log')))
        script=root/(stem+'.py');plan=root/(stem+'_plan.json')
        if script.exists() or plan.exists() or any(Path(c[k]).exists() for k in ('working_copy','backup_cae','output_cae','report_path','log_path')):continue
        code=runtime+'\nTIE_PLAN=json.loads(%r)\nif __name__=="__main__":\n    t4_run(TIE_PLAN)\n'%json.dumps(c,ensure_ascii=True)
        assert_runtime_compatible(code)
        with script.open('x',encoding='utf-8') as f:f.write(code)
        with plan.open('x',encoding='utf-8') as f:json.dump(c,f,indent=2)
        with source.open('rb') as s,Path(c['working_copy']).open('xb') as d:shutil.copyfileobj(s,d)
        return dict(script=str(script),plan=c)
    raise ValueError('VERSION_LIMIT')
