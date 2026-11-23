"""Real Abaqus smoke, opt-in. Uses synthetic geometry, never user's CAE files."""
from pathlib import Path
import argparse
import json
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from make_cae_runner import generate_cae_runner
from cadtocae.batch_runner.runner import BatchRunner
from cadtocae.batch_runner.executor import AbaqusExecutor
from cadtocae.batch_runner.state import write_json

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='outputs/batchrunner-integration')
    parser.add_argument('--abaqus', default='abaqus')
    args = parser.parse_args()
    base = Path(args.output).resolve()/uuid.uuid4().hex[:10]
    root = base/'中文 项目'
    root.mkdir(parents=True)
    payload = {'components':[{'part_name':'P_SMOKE', 'model_policy':'SHELL', 'section_kind':'ANGLE', 'section_params_m':{'leg_a_m':0.05,'leg_b_m':0.05}, 'length_m':0.2, 'thickness_m':0.002, 'material':{'abaqus_name':'STEEL','elastic_modulus_pa':2.1e11,'poisson_ratio':0.3,'density_kg_per_m3':7850}}]}
    (root/'source.json').write_text(json.dumps(payload))
    generate_cae_runner(root/'source.json', root/'SMOKE_create_parts_in_cae.py', model_name='SMOKE')
    (root/'SMOKE_assembly_inputs.json').write_text(json.dumps({"project_id":"SMOKE","instance":"SMOKE-1"}))
    (root/'SMOKE_assembly_frame.py').write_text("import json, os\nfrom abaqus import mdb\nfrom abaqusConstants import ON\nINPUT = 'C:/old/export/SMOKE_assembly_inputs.json'\nassert os.path.isfile(INPUT)\nwith open(INPUT) as handle:\n    data = json.load(handle)\nm = mdb.models['SMOKE']\nm.rootAssembly.Instance(name=str(data['instance']), part=m.parts['P_SMOKE'], dependent=ON)\n")
    analysis = root/'SMOKE_analysis_setup.py'
    analysis.write_text("from abaqus import mdb\nmdb.models['SMOKE'].StaticStep(name='Load', previous='Initial')\n")
    (root/'SMOKE_batchrunner.json').write_text(json.dumps({'project':'SMOKE','stages':{'2':{'validation':{'instances':['SMOKE-1']}},'3':{'validation':{'instances':['SMOKE-1'], 'steps':['Load']}}}}))
    runner = BatchRunner(root, base/'中文 运行记录', AbaqusExecutor([args.abaqus], {'BATCHRUNNER_SCRATCH':str(base/'ascii-scratch')}), lambda p: print(p['prefix'],[(s['number'],s['status']) for s in p['stages']],flush=True))
    results = []
    for mode in ('full','resume','from'):
        if mode == 'from':
            with analysis.open('a') as handle:
                handle.write('# changed version for explicit stage 3 replay\n')
        directory, records = runner.run(mode, start=3)
        assert records[0]['result'] == 'PARTIAL_SUCCESS', str(directory)
        if mode == 'resume':
            assert all(s.get('reused') for s in records[0]['stages'][:3])
        if mode == 'from':
            assert all(s.get('reused') for s in records[0]['stages'][:2])
            assert not records[0]['stages'][2].get('reused')
        results.append(dict(mode=mode, report=str(directory), result=records[0]['result']))
    write_json(base/'validation.json', dict(type='REAL_ABAQUS_SYNTHETIC_SMOKE', results=results))
    print('Validation:', base/'validation.json')

if __name__ == '__main__':
    main()
