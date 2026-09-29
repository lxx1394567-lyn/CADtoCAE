"""Generate the standalone Assembly Extend Face experiment; no plane calculation."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from cadtocae.runtime_compatibility import assert_runtime_compatible


def generate(path):
    path = Path(path)
    plan = json.loads(path.read_text(encoding='utf-8'))
    project = 'SP_SC_ANG28_1042110101170S-T0204'
    if plan['project']['project_id'] != project or plan['project']['model_name'] != project:
        raise ValueError('Expected approved SP_SC ANG28 T0204 benchmark')
    members = {m['component_code']: m for m in plan['instances']}
    beam = members['INCLINED_BEAM']
    data = dict(model=project, beam_instance=beam['instance_name'],
                brace_instance=members['BRACE_FRONT']['instance_name'],
                beam_width=beam['component_geometry']['section_params_m']['b_m'])
    source = '# -*- coding: utf-8 -*-\nimport json\nDATA = json.loads(%r)\n' % json.dumps(data)
    source += (Path(__file__).resolve().parents[1]/'src/cadtocae/brace_extend_face_validation.py').read_text(encoding='utf-8')
    output = path.parent/(project+'_step05_brace_extend_face_validation.py')
    assert_runtime_compatible(source, str(output))
    compile(source, str(output), 'exec')
    output.write_text(source, encoding='utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    print(generate(parser.parse_args().plan))
