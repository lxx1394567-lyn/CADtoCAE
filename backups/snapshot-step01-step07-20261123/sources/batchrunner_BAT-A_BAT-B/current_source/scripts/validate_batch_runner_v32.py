"""Explicit real V3.2 change/rebuild probe; restores the source only if still ours."""
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.batch_runner.runner import BatchRunner
from cadtocae.batch_runner.executor import AbaqusExecutor,digest
from cadtocae.batch_runner.state import write_json
root=Path(sys.argv[1]).resolve()
work=root/'.batchrunner'/'v32-validation'/uuid.uuid4().hex
work.mkdir(parents=True)
inputs={str(p):digest(p) for p in root.iterdir() if p.is_file()}
others={str(p):digest(p) for p in (root/'CAE_Results').iterdir() if p.is_file() and '_step04.cae' not in p.name}
write_json(work/'before.json',dict(inputs=inputs,other_deliveries=others))
runner=BatchRunner(root,root/'.batchrunner',AbaqusExecutor(['abaqus']),lambda r: print([(s['number'],s.get('action'),s['status']) for s in r['stages']],flush=True),through=4)
_,baseline=runner.run('smart');r=baseline[0]
write_json(work/'baseline.json',r)
assert r['result']=='PARTIAL_SUCCESS',r['delivery'].get('error')
source=Path(r['stages'][1]['script']);original=source.read_bytes()
(work/'assembly_original.py').write_bytes(original)
marker='BatchRunner V3.2 change probe '+work.name
probe=original+("\nfrom abaqus import mdb as _batch_v32_mdb\n_batch_v32_mdb.models[%r].setValues(description=%r)\n"%(r['prefix'],marker)).encode('utf-8')
source.write_bytes(probe);probe_hash=digest(source)
try:
    preview=runner.inspect()[0]
    assert [s.plan_action for s in preview.stages[:4]]==['REUSED','RERUN','RERUN','RERUN']
    _,modified=runner.run('smart');m=modified[0];write_json(work/'modified.json',m)
    assert m['result']=='PARTIAL_SUCCESS',m['delivery'].get('error')
    assert [s.get('action') for s in m['stages'][:4]]==['REUSED','RERUN','RERUN','RERUN']
    assert m['delivery']['verification']['description']==marker
    assert m['stages'][1]['execution_files']['source_sha256']==probe_hash
finally:
    if digest(source)!=probe_hash:
        raise RuntimeError('Source changed externally; refusing to overwrite it. Original backup: '+str(work/'assembly_original.py'))
    source.write_bytes(original)
_,restored=runner.run('smart');r=restored[0];write_json(work/'restored.json',r)
assert r['result']=='PARTIAL_SUCCESS',r['delivery'].get('error')
_,unchanged=runner.run('smart');r=unchanged[0];write_json(work/'unchanged.json',r)
assert all(s.get('action')=='REUSED' for s in r['stages'][:4])
assert r['delivery']['status']=='PASSED'
assert all(digest(p)==sha for p,sha in inputs.items())
assert all(digest(p)==sha for p,sha in others.items())
print('REAL VALIDATION PASSED',work,flush=True)
print('Final model',r['delivery']['path'],r['delivery']['size_bytes'],flush=True)
