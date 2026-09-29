"""Audit all CAE templates and optionally a final generated script."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.runtime_compatibility import check_templates, assert_runtime_compatible

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', type=Path)
    args = parser.parse_args()
    print('Runtime templates passed: %d' % check_templates())
    if args.script:
        assert_runtime_compatible(args.script.read_text(encoding='utf-8'), str(args.script))
        print('Generated script passed: '+str(args.script))
