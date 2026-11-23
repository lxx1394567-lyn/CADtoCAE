"""Independent ODB postprocessor generation. No dependency on Stage01-06."""
import hashlib
import json
import re
from pathlib import Path

VERSION = '0.9.2'

def generate_postprocess(summary, odb, output, step='', frame=-1, job_id='', case_label='', stress_max=None):
    summary, odb, output = Path(summary).resolve(), Path(odb).resolve(), Path(output).resolve()
    if not odb.is_file() or odb.suffix.lower() != '.odb':
        raise ValueError('ODB_NOT_FOUND: ' + str(odb))
    data = json.loads(summary.read_text(encoding='utf-8-sig'))
    project = data['project_id']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', project):
        raise ValueError('INVALID_PROJECT_ID')
    groups = {'supports': {}, 'hoops': {}}
    for row in data['instances']:
        role = row.get('canonical_role')
        if role not in ('PURLIN_SUPPORT', 'HOOP'): continue
        name = row['instance_name']
        key = name if role == 'PURLIN_SUPPORT' else row.get('connection_group')
        if not key: raise ValueError('HOOP_GROUP_MISSING: ' + name)
        groups['supports' if role == 'PURLIN_SUPPORT' else 'hoops'].setdefault(key, []).append(name)
    if not groups['supports'] or not groups['hoops']: raise ValueError('RESULT_GROUPS_MISSING')
    if project == 'SP_DC_ANG19_LUANLUANLUAN-T0203' and (len(groups['supports']),len(groups['hoops'])) != (4,3):
        raise ValueError('LUAN_EXPECTED_4_SUPPORTS_3_HOOP_GROUPS')
    job_id = job_id or odb.stem
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', job_id): raise ValueError('INVALID_JOB_ID')
    if stress_max is not None and float(stress_max) <= 0: raise ValueError('INVALID_STRESS_RANGE')
    output.mkdir(parents=True, exist_ok=True)
    runtime = Path(__file__).with_name('step07_postprocess_runtime.py').read_text(encoding='utf-8')
    plan = dict(version=VERSION, project_id=project, model_name=data.get('model_name',project), job_id=job_id,
                case_label=case_label or 'USER_SELECTED_ODB_CASE_NOT_INFERRED', odb=str(odb), summary=str(summary),
                summary_sha256=hashlib.sha256(summary.read_bytes()).hexdigest(), groups=groups,
                expected_instances=[r['instance_name'] for r in data['instances'] if r.get('required',True)],
                output_root=str(output/'Step07_ODB_Results'), step=step, frame=int(frame), stress_max=stress_max,
                material_strengths={}, strength_status='PENDING_MATERIAL_STRENGTH')
    text = runtime + '\n\nPOSTPROCESS_PLAN = json.loads(' + repr(json.dumps(plan,ensure_ascii=True)) + ')\nif __name__ == "__main__":\n    pp_run(POSTPROCESS_PLAN)\n'
    target = output/(project+'_step07_07_odb_postprocess.py')
    # Keep prior generated scripts rather than silently changing user files.
    if target.exists() and target.read_text(encoding='utf-8') != text:
        archive=output/'Step07_Archive';archive.mkdir(exist_ok=True)
        digest=hashlib.sha256(target.read_bytes()).hexdigest()[:12]
        backup=archive/(target.stem+'_'+digest+'.py')
        if not backup.exists(): backup.write_bytes(target.read_bytes())
    target.write_text(text,encoding='utf-8')
    return {'script':str(target),'plan':plan,'status':'GENERATED_NOT_EXECUTED'}
