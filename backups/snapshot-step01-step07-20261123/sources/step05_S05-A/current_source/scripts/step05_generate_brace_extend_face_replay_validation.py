"""Copy the fixed, user-confirmed macro replay without geometry parameterization."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from cadtocae.runtime_compatibility import assert_runtime_compatible


def generate(output_dir):
    source = Path(__file__).resolve().parents[1]/'src/cadtocae/brace_extend_face_replay_validation.py'
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir/'SP_SC_ANG28_1042110101170S-T0204_step05_brace_extend_face_replay_validation.py'
    assert_runtime_compatible(source.read_text(encoding="utf-8"), str(output))
    output.write_bytes(source.read_bytes())
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    print(generate(parser.parse_args().output_dir))
