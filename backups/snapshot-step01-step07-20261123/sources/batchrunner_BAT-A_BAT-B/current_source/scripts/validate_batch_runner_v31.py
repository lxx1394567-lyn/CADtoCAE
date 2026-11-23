"""Real CAE V3.1 publication tests, using retained user checkpoints in an isolated root."""
import copy
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.batch_runner.delivery import deliver
from cadtocae.batch_runner.dependencies import check
from cadtocae.batch_runner.scanner import scan
from cadtocae.batch_runner.executor import AbaqusExecutor,digest
from cadtocae.batch_runner.state import write_json
source=Path(sys.argv[1]).resolve()
root=Path(sys.argv[2]).resolve()/uuid.uuid4().hex[:8];root.mkdir(parents=True)
executor=AbaqusExecutor(['abaqus'])
project=check(scan(source,[source/'.batchrunner'])[0])
record=json.loads((source/'.batchrunner/history'/(project.key+'-latest.json')).read_text(encoding='utf-8'))
assert record['execution_result']=='SUCCESS'
results={}
for label in ('first','second'):
 results[label]=deliver(root,project,record,executor,root/'.batchrunner'/label)
 assert results[label]['status']=='PASSED',results[label].get('error')
 assert [p.name for p in (root/'CAE_Results').iterdir()]==[project.prefix+'_final.cae']
old_hash=digest(results['first']['path'])
failed=copy.deepcopy(record);failed['execution_result']='FAILED';failed['stages'][4]['status']='FAILED'
results['failed_run']=deliver(root,project,failed,executor,root/'.batchrunner/failed')
assert digest(results['first']['path'])==old_hash
# Corrupt new checkpoint with valid report snapshots: must fail real openMdb verification.
bad=copy.deepcopy(record);bad_dir=root/'.batchrunner/corrupt';bad_dir.mkdir()
cae=bad_dir/'checkpoint.cae';cae.write_bytes(b'INTENTIONALLY CORRUPT CAE')
row=bad['stages'][4];original_report=Path(row['checkpoint']).with_name('runtime_report.json')
report=bad_dir/'runtime_report.json';report.write_bytes(original_report.read_bytes())
row.update(checkpoint=str(cae),checkpoint_hash=digest(cae),artifacts={str(report):digest(report)})
results['invalid_candidate']=deliver(root,project,bad,executor,root/'.batchrunner/bad')
assert results['invalid_candidate']['status']=='FAILED'
assert digest(results['first']['path'])==old_hash
partial=dict(record,stages=record['stages'][:3],execution_result='PARTIAL_SUCCESS')
results['partial']=deliver(root,project,partial,executor,root/'.batchrunner/partial')
assert results['partial']['status']=='PASSED'
assert digest(results['first']['path'])==old_hash
assert len(list((root/'CAE_Results').iterdir()))==2
results['full_again']=deliver(root,project,record,executor,root/'.batchrunner/full_again')
assert results['full_again']['status']=='PASSED'
assert len(list((root/'CAE_Results').iterdir()))==1
write_json(root/'.batchrunner/validation.json',results)
print(root)
print('Real Abaqus: first, repeat, failed run protection, corrupt candidate rejection, partial preservation and full promotion PASSED')
