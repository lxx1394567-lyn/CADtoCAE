"""Single-folder batch generation using the frozen Step05 engineering rules."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import uuid
import traceback

from .analysis_discovery import REQUIRED, identity, linked, project_files, safe_project_id, output_paths
from .beam_brace_tie import generate
from .analysis_capability import first_blocking_reason
from .analysis_defaults import default_analysis_config, CONFIG_ID, DC_CONFIG_ID, family_analysis_config

_GENERATION_LOCK = threading.Lock()


def _assert_inputs(row):
    folder=Path(row['source_folder']).resolve(strict=True)
    for key,value in row['input_files'].items():
        path=Path(value)
        if linked(path) or path.resolve().parent!=folder:
            raise ValueError('Input must remain in its original source directory')
    for key in REQUIRED:
        if identity(Path(row['input_files'][key]))!=row['input_identity'][key]:
            raise ValueError('Input changed since scan: '+key+'; scan again')


def _publish(stage, paths):
    """Replace generated files with rollback; never replace user configuration."""
    backup=stage/'previous';backup.mkdir()
    replaced=[]
    try:
        for key in ('plan','script'):
            target=paths[key]
            if target.exists():shutil.copy2(target,backup/target.name)
            os.replace(stage/target.name,target)
            replaced.append(target)
    except Exception:
        for target in reversed(replaced):
            old=backup/target.name
            if old.exists():os.replace(old,target)
            else:target.unlink()
        raise


def _generate_project(row, folder):
    project=row['project_id'];safe_project_id(project);_assert_inputs(row)
    paths=output_paths(folder,project)
    for target in paths.values():
        if target.exists() and (linked(target) or not target.is_file()):
            raise ValueError('Expected regular generated file: '+str(target))
    with tempfile.TemporaryDirectory(prefix='.step05-tmp-',dir=folder) as temporary:
        stage=Path(temporary)
        scratch=stage/'work';scratch.mkdir()
        previous=tempfile.tempdir
        try:
            tempfile.tempdir=str(scratch)
            if row['structure_type']=='SP_DC':
                from .sp_dc_setup import generate as generate_dc
                generate_dc(project_files(row),family_analysis_config('SP_DC'),stage,final_output_dir=folder)
            else:
                generate(project_files(row),default_analysis_config(),stage,final_output_dir=folder)
        finally:tempfile.tempdir=previous
        for path in paths.values():
            if not (stage/path.name).is_file():raise ValueError('Incomplete staged output: '+path.name)
        _assert_inputs(row)
        _publish(stage,paths)
    return {key:str(path) for key,path in paths.items()}


def _write_summary(result,output):
    text=['Step05 batch generation', 'Project Folder: '+str(output), '']
    for row in result['projects']:
        text.extend([row['project_id'], '  Structure: '+str(row['structure_type']),
                     '  Input Status: '+row['input_status'], '  Capability: '+str(row['capability']), '  Generation: '+row['generation_status'],
                     '  Source: '+row['source_folder'], '  Rules: '+', '.join(row['supported_rules']),
                     '  Inputs: '+json.dumps(row['input_files'],ensure_ascii=False),
                     '  Missing: '+json.dumps(row['missing_requirements'],ensure_ascii=False),
                     '  First Blocking Reason: '+first_blocking_reason(row),
                     '  Skipped: '+row.get('skip_reason',''),
                     '  Outputs: '+json.dumps(row['generated_files'],ensure_ascii=False),
                     '  Warnings: '+'; '.join(row['warnings']), '  Errors: '+'; '.join(row['errors']), ''])
    summary=copy.deepcopy(result)
    for row in summary['projects']:row.pop('traceback',None)
    for suffix,content in (('json',json.dumps(summary,ensure_ascii=False,indent=2)),('txt','\n'.join(text))):
        final=output/('step05_batch_summary.'+suffix)
        if final.exists() and linked(final): raise ValueError('Linked batch summary is not supported')
        temporary=output/('_tmp_summary_'+uuid.uuid4().hex)
        try:
            temporary.write_text(content,encoding='utf-8')
            os.replace(temporary,final)
        finally:
            if temporary.exists(): temporary.unlink()


def generate_batch(scan, selected=None, progress=None):
    """Flat outputs in the selected folder, including recursively found projects."""
    folder=Path(scan['source_folder']).resolve(strict=True)
    result=copy.deepcopy(scan);result['project_folder']=str(folder)
    eligible=[r for r in result['projects'] if r.get('input_status',r['status'])=='READY' and r.get('capability') in ('SP_SC_FULL_CONNECTION_SETUP','SP_DC_FULL_CONNECTION_SETUP') and
              (selected is None or (r['source_folder'],r['project_id']) in selected)]
    if not eligible:raise ValueError('No READY projects selected')
    def emit(event,row,index):
        if progress:progress(dict(event=event,row=copy.deepcopy(row),index=index,total=len(eligible)))
    result['skipped_projects']=[]
    for row in result['projects']:
        if row not in eligible and (selected is None or (row['source_folder'],row['project_id']) in selected):
            reason=('geometry review required: ' if row.get('geometry_review') else '')+first_blocking_reason(row)
            row['skip_reason']=reason or 'Project is not READY/FULL'
            result['skipped_projects'].append(dict(project_id=row['project_id'],reason=row['skip_reason']))
            emit('skipped',row,0)
    with _GENERATION_LOCK:
        for index,row in enumerate(eligible,1):
            row['input_status']=row.get('input_status',row['status'])
            row['errors']=list(row.get('input_errors',[]));row.pop('traceback',None);row['generation_status']='GENERATING';row['result']='Generating'
            emit('started',row,index)
            try:
                if not Path(row['source_folder']).resolve().is_relative_to(folder):
                    raise ValueError('Project outside selected folder')
                row['generated_files']=_generate_project(row,folder)
                row['analysis_config_source']=DC_CONFIG_ID if row['structure_type']=='SP_DC' else CONFIG_ID
                row['generation_status']='GENERATED';row['result']='Success'
            except Exception as exc:
                row['generation_status']='FAILED';row['errors'].append(str(exc))
                row['result']='Failed: '+str(exc).replace('\n',' ')[:100]
                row['traceback']=traceback.format_exc()
            emit('finished',row,index)
        result['generation_counts']=dict(succeeded=sum(r['generation_status']=='GENERATED' for r in eligible),
                                         failed=sum(r['generation_status']=='FAILED' for r in eligible))
        _write_summary(result,folder)
    return result
