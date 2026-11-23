"""Generate holes only from an existing, matching Step06 plan/runtime pair."""
import argparse
import json
from pathlib import Path
from cadtocae.step06_execution_mode import connection_mode, write_tie_only

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8-sig'))
    if connection_mode(args.output, plan['project_id']) != 'tie_only':
        parser.error('Project execution configuration must explicitly select tie_only')
    if not (Path(args.output)/(plan['project_id']+'_step06_hole_setup.py')).is_file():
        parser.error('Existing validated project hole script required for this adapter')
    print(json.dumps({k: str(v) for k, v in write_tie_only(plan, args.output).items()}, indent=2))
