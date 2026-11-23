"""Opt-in real Abaqus delivery checks against an existing successful five-stage run."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.batch_runner.delivery import deliver, expected, verify_file
from cadtocae.batch_runner.executor import AbaqusExecutor, digest
from cadtocae.batch_runner.runner import BatchRunner
from cadtocae.batch_runner.state import write_json
root=Path(sys.argv[1]).resolve()
output=Path(sys.argv[2]).resolve()
config=json.loads(Path(sys.argv[3]).read_text(encoding='utf-8-sig'))
executor=AbaqusExecutor(config['command'],config.get('environment'))
runner=BatchRunner(root,root/'.batchrunner',executor)
project=runner.inspect()[0]
record=json.loads((root/'.batchrunner/history'/(project.key+'-latest.json')).read_text(encoding='utf-8'))
assert record['execution_result']=='SUCCESS'
rows=record['stages']
assert all(row.get('reused') for row in rows), 'Run smart with matching configuration first'
job, unsupported=expected(project,rows)
assert not unsupported
partial=deliver(root,project,{'stages':rows[:3]},executor,output/'partial')
assert partial['status']=='PASSED',partial.get('error')
# Negative checks use disposable copies only; no modelling and no original writes.
output.mkdir(parents=True,exist_ok=True)
wrong=dict(job,path=rows[2]['checkpoint'])
wrong_result=verify_file(executor,wrong,output/'step3-as-final')
assert wrong_result['status']=='FAILED'
corrupt=output/'corrupt.cae';corrupt.write_bytes(b'INTENTIONALLY INVALID TEST DATABASE')
corrupt_result=verify_file(executor,dict(job,path=str(corrupt)),output/'corrupt-check')
assert corrupt_result['status']=='FAILED'
# Explicitly test the retained V2 checkpoints, without invoking execute().
old_batch=root/'.batchrunner/20261011-085234-b228d76d'/project.key
last_batch=root/'.batchrunner/20261011-085609-1e4fbd8b'/project.key
old_record=json.loads((old_batch/'record.json').read_text(encoding='utf-8'))
last_record=json.loads((last_batch/'record.json').read_text(encoding='utf-8'))
old_rows=old_record['stages'][:4]+last_record['stages'][4:5]
v2=deliver(root,project,{'stages':old_rows},executor,output/'retained-v2')
assert v2['status']=='PASSED',v2.get('error')
write_json(output/'results.json',dict(partial=partial, retained_v2=v2, step3_as_final=wrong_result, corrupt=corrupt_result))
print(json.dumps(dict(partial=partial['path'],retained_v2=v2['path'],negative_checks='PASSED'),ensure_ascii=False))
