"""Real Step07 change/reuse experiment, restoring source bytes on completion."""
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.batch_runner.runner import BatchRunner
from cadtocae.batch_runner.executor import AbaqusExecutor, digest
from cadtocae.batch_runner.settings import detected_command
from cadtocae.batch_runner.state import write_json


def main():
    root=Path(sys.argv[1]).resolve()
    executor=AbaqusExecutor(['abaqus'])
    runner=BatchRunner(root,root/'.batchrunner',executor,through=7)
    project=runner.inspect()[0]
    source=Path(project.stages[6].script)
    original=source.read_bytes()
    evidence=root/'.batchrunner'/'v4-validation'/uuid.uuid4().hex
    evidence.mkdir(parents=True)
    (evidence/'original_boundary.py').write_bytes(original)
    before={str(p):digest(p) for p in root.iterdir() if p.is_file()}
    write_json(evidence/'inputs_before.json',before)
    marker='BatchRunner V4 change probe '+evidence.name
    probe=original+('\nfrom abaqus import mdb as _batch_probe_db\n_batch_probe_db.models[%r].setValues(description=%r)\n'%(project.prefix,marker)).encode()
    def run(label):
        _,records=runner.run()
        write_json(evidence/(label+'.json'),records)
        r=records[0]
        print(label,r['execution_result'],r['delivery']['status'],[(s['number'],s.get('action'),s['status']) for s in r['stages']],flush=True)
        if r['delivery']['status']!='PASSED':raise RuntimeError(r['delivery'])
        return r
    run('baseline')
    try:
        source.write_bytes(probe)
        r=run('modified')
        assert all(s.get('action')=='REUSED' for s in r['stages'][:6])
        assert r['stages'][6]['action']=='RERUN'
        assert r['delivery']['verification']['description']==marker
    finally:
        if source.read_bytes()!=probe:raise RuntimeError('Concurrent source edit; original backup retained at '+str(evidence))
        source.write_bytes(original)
    r=run('restored')
    assert r['delivery']['verification']['description']!=marker
    r=run('unchanged')
    assert all(s.get('action')=='REUSED' for s in r['stages'][:7])
    assert all(digest(p)==sha for p,sha in before.items())
    print('PASSED; source bytes restored; evidence:',evidence,flush=True)


if __name__=='__main__':main()
