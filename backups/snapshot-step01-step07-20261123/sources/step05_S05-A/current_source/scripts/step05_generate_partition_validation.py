"""Copy the approved case-specific minimal script after checking the saved plan."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from cadtocae.runtime_compatibility import assert_runtime_compatible


def generate(plan_path):
    path = Path(plan_path)
    plan = json.loads(path.read_text(encoding='utf-8'))
    project = 'SP_SC_ANG28_1042110101170S-T0204'
    real = plan['real_case']
    if (plan['project']['project_id'] != project or plan['project']['model_name'] != project
            or real['beam_part'] != 'P_SP_SC_ANG28_INCLINED_BEAM'
            or abs(real['C_beam_local_station_m'] - .336) > 1.e-9
            or any(abs(a-b) > 1.e-9 for a, b in zip(real['patch_range_m'], (.256, .416)))
            or len(real['patch_range_m']) != 2):
        raise ValueError('This minimal experiment requires the approved SP_SC ANG28 T0204 plan')
    source = Path(__file__).resolve().parents[1]/'src/cadtocae/partition_validation_minimal.py'
    output = path.parent/(project+'_step05_partition_validation.py')
    assert_runtime_compatible(source.read_text(encoding="utf-8"), str(output))
    output.write_bytes(source.read_bytes())
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    print(generate(parser.parse_args().plan))
