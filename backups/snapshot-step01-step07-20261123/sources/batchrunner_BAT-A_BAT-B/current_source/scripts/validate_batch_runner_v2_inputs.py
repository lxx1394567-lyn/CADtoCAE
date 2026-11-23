"""Opt-in preflight matrix on COPIES of a real project's inputs; never run mutated geometry scripts."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.batch_runner.scanner import scan, SUFFIXES
from cadtocae.batch_runner.dependencies import check
from cadtocae.batch_runner.state import write_json

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source')
    args=parser.parse_args()
    source=Path(args.source).resolve()
    project=scan(source,[source/'.batchrunner'])[0]
    prefix=project.prefix
    output=Path('outputs/v2-real-input-matrix')/uuid.uuid4().hex[:8]
    results=[]
    cases=['complete','three_steps','missing_hole_input','missing_connector_input','wrong_project','duplicate','absolute_path','embedded_sidecar_missing']
    for case in cases:
        folder=output/case
        folder.mkdir(parents=True)
        for path in source.iterdir():
            if path.is_file() and path.name.startswith(prefix+'_') and not path.name.endswith('_report.json'):
                if case=='three_steps' and any(path.name.endswith(s) for suffixes in SUFFIXES[3:] for s in suffixes):
                    continue
                shutil.copy2(path,folder/path.name)
        stage_num=5 if case=='missing_connector_input' else 4
        filename=prefix+('_step06_connector_plan.json' if stage_num==5 else '_step06_plan.json')
        script=folder/(prefix+SUFFIXES[stage_num-1][0])
        if case in ('missing_hole_input','missing_connector_input','wrong_project','duplicate','absolute_path'):
            reference=('C:/old/export/'+filename) if case=='absolute_path' else filename
            with script.open('a',encoding='utf-8') as handle:
                handle.write('\n# Static dependency test fixture only; never execute this modified script.\nopen(%r).close()\n'%reference)
        if case in ('missing_hole_input','missing_connector_input','embedded_sidecar_missing'):
            (folder/filename).unlink()
        if case=='wrong_project':
            data=json.loads((folder/filename).read_text(encoding='utf-8-sig'))
            data['project_id']='ANOTHER_PROJECT'
            (folder/filename).write_text(json.dumps(data),encoding='utf-8')
        if case=='duplicate':
            (folder/'json').mkdir()
            shutil.copy2(folder/filename,folder/'json'/filename)
        p=check(scan(folder)[0])
        states=[s.status for s in p.stages]
        expected={'complete':['READY']*5,'three_steps':['READY']*3+['MISSING']*2,
                  'missing_hole_input':['READY']*3+['MISSING_INPUT','BLOCKED'],
                  'missing_connector_input':['READY']*4+['MISSING_INPUT'],
                  'wrong_project':['READY']*3+['BLOCKED']*2,'duplicate':['READY']*3+['BLOCKED']*2,
                  'absolute_path':['READY']*5,'embedded_sidecar_missing':['READY']*5}[case]
        assert states==expected,(case,states,expected,[s.reasons for s in p.stages])
        results.append(dict(case=case,statuses=states,result='PASS',project=p.to_dict()))
    write_json(output/'matrix.json',results)
    print(output/'matrix.json')

if __name__=='__main__':
    main()
