"""Generate a shared-Section-only preset update for an existing Step06-B CAE."""
import argparse
import json
from pathlib import Path
from cadtocae.analysis_discovery import safe_project_id
from cadtocae.runtime_compatibility import assert_runtime_compatible
import cadtocae.purlin_bolt_preset_runtime as runtime

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',required=True);parser.add_argument('--project',required=True)
    args=parser.parse_args();safe_project_id(args.project)
    folder=Path(args.folder).resolve(strict=True)
    output=folder/(args.project+'_step06_b_purlin_bolt_preset_update.py')
    report=folder/(args.project+'_step06_b_purlin_bolt_preset_report.json')
    source='# -*- coding: utf-8 -*-\n'+Path(runtime.__file__).read_text(encoding='utf-8')
    source+='\nREPORT_PATH=json.loads(%r)\n'%json.dumps(str(report))
    source+='PROJECT_ID=json.loads(%r)\n'%json.dumps(args.project)
    source+="if __name__=='__main__':\n    from abaqus import mdb\n    update_existing_bolt_preset(mdb,REPORT_PATH,PROJECT_ID)\n"
    assert_runtime_compatible(source)
    if output.is_symlink():raise ValueError('Output cannot be symlink')
    output.write_text(source,encoding='utf-8');print(output)
