"""Desktop release adapter for existing Step06-A and Step06-B generators."""
import copy
import json
import re
from pathlib import Path
from . import hole_projects
from .hole_setup import write_hole_setup
from .connector_b1_plan import fingerprint
from .connector_groups import build_group_plan
from .connector_setup import connector_script_source
from .support_beam_connector import build_support_beam_plan, script_source as beam_source
from .step06_version import STEP06_VERSION, version_fields, preload_record
from .runtime_compatibility import assert_runtime_compatible
from .connector_integration import integrated_plan, integrated_source


def versioned_source(source):
    """Stamp new runtime reports without rewriting historical successful reports."""
    marker=re.search(r"^if __name__\s*==\s*'__main__':\s*$",source,re.M)
    if not marker:raise ValueError('Missing generated entry point')
    head=source[:marker.start()]
    body=source[marker.end():].strip('\n')
    head+='\nSTEP06_VERSION = %r\nGENERATOR_VERSION = STEP06_VERSION\n'%STEP06_VERSION
    head+='''def _step06_version_report(path):
    import os
    if os.path.isfile(path):
        with open(path) as handle:
            data = json.load(handle)
        data.update(step06_version=STEP06_VERSION,generator_version=GENERATOR_VERSION)
        with open(path,'w') as handle:
            json.dump(data,handle,indent=2,ensure_ascii=True,allow_nan=False)
if __name__ == '__main__':
    try:
'''
    source=head+'\n'.join('    '+line for line in body.splitlines())+'\n    finally:\n        _step06_version_report(REPORT_PATH)\n'
    assert_runtime_compatible(source)
    return source


def matching_hole_plan(fresh,report,folder,project):
    candidates=[fresh,dict(fresh,**version_fields())]
    previous=folder/(project+'_step06_plan.json')
    if previous.is_file():
        saved=json.loads(previous.read_text(encoding='utf-8-sig'))
        stripped=lambda p:{k:v for k,v in p.items() if k not in ('step06_version','generator_version')}
        if stripped(saved)==stripped(fresh):candidates.append(saved)
    for candidate in candidates:
        if fingerprint(candidate)==report.get('plan_fingerprint'):return candidate
    raise ValueError('Step06-A report does not match current inputs; rerun Step06-A before generating connectors')


def generate_release_batch(scan,selected=None,progress=None):
    result=copy.deepcopy(scan);result.update(version_fields())
    fresh=hole_projects.scan_projects(scan['source_folder'],scan['include_subfolders'])
    current={(r['source_folder'],r['project_id']):r for r in fresh['projects']}
    counts=dict(succeeded=0,failed=0,skipped=0)
    for row in result['projects']:
        key=(row['source_folder'],row['project_id'])
        if selected is not None and key not in selected:continue
        if not hole_projects.can_generate(row):counts['skipped']+=1;continue
        try:
            now=current.get(key)
            if not now or not hole_projects.can_generate(now) or now['input_identity']!=row['input_identity']:
                raise ValueError('Inputs changed; Scan Projects again')
            folder=Path(row['source_folder']);project=row['project_id']
            a_plan=dict(now['plan'],**version_fields())
            from .step06_execution_mode import connection_mode,write_tie_only
            mode=connection_mode(folder,project)
            if mode=='tie_only':
                paths=write_tie_only(a_plan,folder)
                row.update(status='GENERATED',generation_status='GENERATED',connection_mode=mode,
                           generated_files={k:str(v) for k,v in paths.items()},
                           result='Generated holes only; skip all Step06 connector scripts',**version_fields())
                counts['succeeded']+=1
                if progress:progress(dict(event='completed',row=copy.deepcopy(row)))
                continue
            connector=integrated_plan(a_plan,folder)
            source=integrated_source(connector,folder/(project+'_step06_b_connector_report.json'))
            extra={'connector_plan':folder/(project+'_step06_connector_plan.json'),
                   'connector_script':folder/(project+'_step06_connector_setup.py')}
            for path in extra.values():
                if path.is_symlink() or (path.exists() and not path.is_file()):
                    raise ValueError('Expected a regular output file: '+str(path))
            paths=write_hole_setup(a_plan,folder,now['input_identity'])
            paths['script'].write_text(versioned_source(paths['script'].read_text(encoding='utf-8')),encoding='utf-8')
            extra['connector_plan'].write_text(json.dumps(connector,ensure_ascii=False,indent=2),encoding='utf-8')
            extra['connector_script'].write_text(source,encoding='utf-8')
            paths.update(extra)
            row.update(status='GENERATED',generation_status='GENERATED',generated_files={k:str(v) for k,v in paths.items()},
                       result='Generated Step06 '+STEP06_VERSION+': Hole + Connector',**version_fields())
            counts['succeeded']+=1
        except Exception as exc:
            row.update(status='NEEDS_REVIEW',result=str(exc));row['errors'].append(str(exc));counts['failed']+=1
        if progress:progress(dict(event='completed',row=copy.deepcopy(row)))
    result['generation_counts']=counts
    return result
