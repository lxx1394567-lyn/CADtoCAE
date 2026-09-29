"""Offline plane calculation for the approved SP_SC ANG28 benchmark only."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.runtime_compatibility import assert_runtime_compatible
from cadtocae.analysis_geometry import (placement_candidates, transform, inverse_point,
    matvec, transpose, unit, cross, dot, add, scale)


def calculate(plan):
    if plan['project']['project_id'] != 'SP_SC_ANG28_1042110101170S-T0204':
        raise ValueError('This experiment is restricted to the approved benchmark')
    beam, brace = plan['instances']
    poses = []
    for member in (beam, brace):
        steps = member['placement']['rotation_steps']
        if (len(steps) != 2 or steps[0]['axis_point'] != [0., 0., 0.]
                or steps[0]['axis_direction'] != [0., 1., 0.]):
            raise ValueError('Expected benchmark Y rotation, translation, then axis roll')
        # Step04 _instance executes initial rotation -> translation -> roll.
        poses.append(placement_candidates(member['placement'])[1])
    bp, rp = poses
    section = beam['component_geometry']['section_params_m']
    yaxis = matvec(bp['rotation'], (0., 1., 0.))
    if abs(yaxis[2]) < 1.e-6:
        raise ValueError('Lower flange cannot be distinguished')
    sign = -1. if yaxis[2] > 0 else 1.
    y = (0. if sign < 0 else section['h_m']) + sign*section['t_m']/2.
    global_point = transform(bp, (section['b_m']/2., y, plan['real_case']['C_beam_local_station_m']))
    global_normal = unit(matvec(bp['rotation'], (0., sign, 0.)))
    local_point = inverse_point(rp, global_point)
    local_normal = unit(matvec(transpose(rp['rotation']), global_normal))
    axis = min(((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)), key=lambda a: abs(dot(a, local_normal)))
    u = unit(cross(local_normal, axis))
    v = unit(cross(local_normal, u))
    return dict(model=plan['project']['model_name'], brace=brace['part_name'],
                point_global=global_point, normal_global=global_normal,
                point_local=local_point, normal_local=local_normal,
                datum_points=[local_point, add(local_point, scale(u, .1)), add(local_point, scale(v, .1))],
                shell_contract='Step02 SectionAssignment default MIDDLE_SURFACE, thickness from components',
                placement_contract='Step04 initial Y rotation -> translation -> axis roll')


def generate(path):
    path = Path(path)
    data = calculate(json.loads(path.read_text(encoding='utf-8')))
    template = Path(__file__).resolve().parents[1]/'src/cadtocae/brace_partition_validation_minimal.py'
    output = path.parent/(data['model']+'_step05_brace_partition_validation.py')
    source = '# -*- coding: utf-8 -*-\nimport json\nDATA = json.loads(%r)\n' % json.dumps(data)
    source += template.read_text(encoding='utf-8')
    assert_runtime_compatible(source, str(output))
    compile(source, str(output), 'exec')
    output.write_text(source, encoding='utf-8')
    return output, data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    path, data = generate(parser.parse_args().plan)
    print(path)
    print(json.dumps(data, indent=2))
