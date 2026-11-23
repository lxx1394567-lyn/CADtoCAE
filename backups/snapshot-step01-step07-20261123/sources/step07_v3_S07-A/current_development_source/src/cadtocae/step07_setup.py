"""Step07 desktop configuration and standalone Abaqus 2020 script generator."""
import copy
import json
import hashlib
import math
import re
from pathlib import Path
from .runtime_compatibility import assert_runtime_compatible
from .step07_rules import STAGE_NAMES, STAGE1_STEPS


def positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(name + ' must be finite and positive')
    return value


def generate_stage1(summary_path, input_cae, output_dir, step_defaults, upstream=None, execution_mode='CURRENT_SESSION_DEBUG'):
    """Stage 1 deliberately bypasses load/mesh/connection planning."""
    if execution_mode not in ('CURRENT_SESSION_DEBUG','INDEPENDENT_CAE'):raise ValueError('Invalid execution mode')
    summary=json.loads(Path(summary_path).read_text(encoding='utf-8-sig'))
    source=Path(input_cae).resolve(strict=True)
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    cae_dir=out/'CAE_Results'
    if cae_dir.is_symlink() or (cae_dir.exists() and cae_dir.resolve()!=cae_dir):raise ValueError('CAE_Results must not redirect to another directory')
    cae_dir.mkdir(exist_ok=True)
    project=summary['project_id']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',project):raise ValueError('Invalid full project identifier')
    runtime_source=Path(__file__).with_name('step07_runtime.py').read_text(encoding='utf-8')
    for version in range(1,10000):
        suffix='' if version==1 else '_v'+str(version)
        prefix=project+'_step07_01'+suffix
        output=cae_dir/(prefix+'.cae')
        if output==source:raise ValueError('Cannot overwrite upstream CAE')
        plan=dict(stage=1,execution_mode=execution_mode,project_id=project,model_name=summary['model_name'],
                  input_cae=str(source),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  output_cae=str(output),output_dir=str(out),step=copy.deepcopy(STAGE1_STEPS[0]),steps=copy.deepcopy(STAGE1_STEPS),output_version=version,
                  script_name=project+'_'+STAGE_NAMES[1]+suffix+'.py',artifact_prefix=prefix,
                  report_path=str(out/(prefix+'_report.json')),log_path=str(out/(prefix+'.log')),
                  scratch_cae=str(cae_dir/(prefix+'_input_copy.cae')),
                  session_backup_cae=str(cae_dir/(prefix+'_before_step.cae')),
                  session_disk_backup_cae=str(cae_dir/(prefix+'_before_step_disk.cae')),
                  console_log=str(out/(prefix+'_console.log')),plan_path=str(out/(prefix+'_plan.json')))
        plan['upstream']=upstream or dict(stage='UNKNOWN',evidence='direct generator input',model_classification='DEBUG_MODEL',engineering_verified=False)
        plan['assembly_summary']=summary;plan['assembly_summary_path']=str(Path(summary_path).resolve())
        runtime=runtime_source+'\nSTAGE1_PLAN=json.loads(%r)\n'%json.dumps(plan,ensure_ascii=True,allow_nan=False)
        runtime+='if __name__ == "__main__":\n    s7_run_stage1_logged(STAGE1_PLAN)\n'
        assert_runtime_compatible(runtime,plan['script_name'])
        script=out/plan['script_name'];plan_file=Path(plan['plan_path'])
        occupied=any(Path(plan[k]).exists() for k in ('output_cae','report_path','log_path','scratch_cae','console_log','session_backup_cae','session_disk_backup_cae'))
        if occupied:continue
        if script.exists():
            if script.read_bytes()==runtime.encode('utf-8') and plan_file.is_file() and json.loads(plan_file.read_text(encoding='utf-8'))==plan:return plan
            continue
        if plan_file.exists():continue
        try:
            with script.open('x',encoding='utf-8',newline='') as f:f.write(runtime)
            with plan_file.open('x',encoding='utf-8') as f:json.dump(plan,f,ensure_ascii=False,indent=2)
        except FileExistsError:continue
        return plan
    raise ValueError('Too many output versions; inspect existing files')



def build_plan(config, summary):
    c = json.loads(json.dumps(config, allow_nan=False))
    if c.get('model_name') != summary['model_name']:
        raise ValueError('Model identity mismatch')
    kind = summary['structure_type']
    if kind not in ('SP_SC', 'SP_DC', 'DP'):
        raise ValueError('Unsupported structure_type')
    if c.get('units', 'm-N-Pa') != 'm-N-Pa':
        raise ValueError('Only m-N-Pa supported')
    c['structure_type'] = kind
    c['instances'] = summary['instances']
    c.setdefault('step', {})
    defaults = dict(name='STEP07_STATIC', previous='Initial', nlgeom=False, initialInc=.1, maxInc=.1, minInc=1e-7, maxNumInc=1000)
    defaults.update(c['step']); c['step'] = defaults
    for key in ('initialInc','maxInc','minInc','maxNumInc'):positive(defaults[key], key)
    if not defaults['minInc'] <= defaults['initialInc'] <= defaults['maxInc'] <= 1:
        raise ValueError('Require minInc <= initialInc <= maxInc <= 1')
    if type(defaults['maxNumInc']) is not int or type(defaults['nlgeom']) is not bool:
        raise ValueError('maxNumInc must be integer; nlgeom must be boolean')
    c.setdefault('mesh', {})
    m = dict(size=.05, local_size=.005, by_role={}); m.update(c['mesh']); c['mesh']=m
    positive(m['size'],'mesh.size'); positive(m['local_size'],'mesh.local_size')
    for v in m['by_role'].values():positive(v,'mesh.by_role')
    c.setdefault('bottom_tolerance',1e-5); positive(c['bottom_tolerance'],'bottom_tolerance')
    c.setdefault('enable_column_tie_correction',False)
    if type(c['enable_column_tie_correction']) is not bool:raise ValueError('Tie correction switch must be boolean')
    c.setdefault('validation_assumptions', {})
    allowed={'fix_purlin_rp_rotations','fix_support_beam_rp_rotations'}
    if set(c['validation_assumptions'])-allowed:raise ValueError('Unknown validation assumption')
    for value in c['validation_assumptions'].values():
        if type(value) is not bool:raise ValueError('Validation assumption must be boolean')
    c.setdefault('job', {}); c['job'].setdefault('name','Step07_Static'); c['job'].setdefault('submit',False)
    if not re.match(r'^[A-Za-z][A-Za-z0-9_]{0,63}$',c['job']['name']):raise ValueError('Invalid job name')
    if type(c['job']['submit']) is not bool:raise ValueError('submit must be boolean')
    roles = {i['instance_name']:i for i in c['instances']}
    seen=set()
    if not c.get('loads'):raise ValueError('At least one purlin load required')
    for load in c['loads']:
        target=load['instance']; row=roles.get(target)
        if not row or row['canonical_role'] not in ('PURLIN','PURLIN_LOCAL'):raise ValueError('Load target must be a purlin')
        if target in seen:raise ValueError('Duplicate purlin load')
        seen.add(target)
        load.setdefault('rp_set','STEP06_RP_'+str(row.get('connection_group'))+'_PURLIN')
        force=load.get('force')
        if not isinstance(force,list) or len(force)!=3 or not any(force):raise ValueError('force must be nonzero [Fx,Fy,Fz]')
        for v in force:
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError('Invalid force')
    return c


def generate(config_path, summary_path, output_dir):
    config_path=Path(config_path).resolve()
    c=json.loads(config_path.read_text(encoding='utf-8-sig'))
    summary=json.loads(Path(summary_path).read_text(encoding='utf-8-sig'))
    plan=build_plan(c,summary)
    source=Path(c['input_cae'])
    if not source.is_absolute():source=config_path.parent/source
    plan['input_cae']=str(source.resolve(strict=True))
    plan['input_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    if c.get('connection_plan'):
        connection=Path(c['connection_plan'])
        if not connection.is_absolute():connection=config_path.parent/connection
        data=json.loads(connection.read_text(encoding='utf-8-sig'))
        if data['project_id']!=summary['project_id']:raise ValueError('Connection plan project mismatch')
        if plan['enable_column_tie_correction'] and data.get('column_column_tie',{}).get('enabled'):
            plan['column_tie']=data['column_column_tie']
    if plan['enable_column_tie_correction'] and 'column_tie' not in plan:
        raise ValueError('Tie correction enabled but no supported column-column connection plan found')
    out=Path(output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    plan['output_dir']=str(out)
    plan['output_cae']=str(out/'step07.cae')
    if Path(plan['output_cae'])==source.resolve():raise ValueError('Cannot overwrite upstream CAE')
    runtime=Path(__file__).with_name('step07_runtime.py').read_text(encoding='utf-8')
    runtime+='\nSTEP07_PLAN=json.loads(%r)\n'%json.dumps(plan,ensure_ascii=True,allow_nan=False)
    runtime+='if __name__ == "__main__":\n    run_step07(STEP07_PLAN)\n'
    assert_runtime_compatible(runtime,'step07_analysis_setup.py')
    script=out/'step07_analysis_setup.py'
    if script.exists():raise ValueError('Use a new output directory per run')
    script.write_text(runtime,encoding='utf-8')
    (out/'step07_verify_results.py').write_text(runtime.replace('run_step07(STEP07_PLAN)','verify_saved_step07(STEP07_PLAN)'),encoding='utf-8')
    (out/'step07_submit_job.py').write_text(runtime.replace('run_step07(STEP07_PLAN)','submit_saved_step07(STEP07_PLAN)'),encoding='utf-8')
    (out/'step07_plan.json').write_text(json.dumps(plan,indent=2,ensure_ascii=False),encoding='utf-8')
    return script

