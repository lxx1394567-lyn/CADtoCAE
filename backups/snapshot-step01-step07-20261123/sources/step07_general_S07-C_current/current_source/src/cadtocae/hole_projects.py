"""Single-folder Step06 discovery, capability checks and same-folder batch generation."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile

from .analysis_discovery import identity, linked, safe_project_id
from .hole_plan import build_step06_a_plan
from .workbook import export_abaqus_json


def output_paths(folder, project):
    safe_project_id(project)
    return {"plan": Path(folder)/(project+"_step06_plan.json"),
            "script": Path(folder)/(project+"_step06_hole_setup.py")}


def _row(folder, project):
    return dict(project_id=project, source_folder=str(folder), structure_type=None,
                input_status="NEEDS_REVIEW", capability="NEEDS_REVIEW", status="NEEDS_REVIEW",
                generation_status="NOT_GENERATED", result="", hole_tables=[], input_files={},
                missing_requirements=[], warnings=[], errors=[], first_blocking_reason="",
                supported_holes=[], driving_hole_count=0, derived_hole_count=0,
                shared_parts=[], instance_isolation_required=False, generated_files={}, input_identity={})


def _load_project(row):
    summary = json.loads(Path(row['input_files']['assembly_summary']).read_text(encoding='utf-8-sig'))
    if summary.get('project_id') != row['project_id']:
        raise ValueError('Summary/project filename mismatch')
    with tempfile.TemporaryDirectory(prefix='step06_scan_') as temporary:
        path = export_abaqus_json(row['input_files']['components'], Path(temporary)/'components.json', selection='complete')
        components = json.loads(path.read_text(encoding='utf-8'))['components']
    return summary, components


def _inspect(row):
    from .hole_workbooks import workbook_path, read_project_hole_workbook, NeedsInput
    folder, project = Path(row['source_folder']), row['project_id']
    try:
        safe_project_id(project)
        for key,suffix in (('components','_components.xlsx'),('assembly_summary','_assembly_summary.json')):
            path=folder/(project+suffix)
            if not path.is_file():
                row['missing_requirements'].append(key+' file')
            elif linked(path):
                raise ValueError('Linked input is unsupported: '+str(path))
            else:
                row['input_files'][key]=str(path)
        outputs=output_paths(folder,project)
        row['generated_files']={k:str(p) for k,p in outputs.items() if p.is_file() and not linked(p)}
        if len(row['generated_files'])==2:
            row.update(generation_status='GENERATED',result='Outputs found')
        if row['missing_requirements']:return
        files=list(row['input_files'].values())
        row['input_identity']={p:identity(Path(p)) for p in files}
        summary,components=_load_project(row)
        row['structure_type']=summary.get('structure_type')
        table=workbook_path(folder,project)
        if not table.exists():
            row.update(input_status='MISSING_TABLE',status='MISSING_TABLE')
            row['missing_requirements'].append(table.name)
            return
        if not table.is_file() or linked(table):raise ValueError('Expected regular project workbook')
        row['hole_tables']=[str(table)]
        row['input_identity'][str(table)]=identity(table)
        rows,hoop_plan=read_project_hole_workbook(table,project,summary,components,row['warnings'])
        plan=build_step06_a_plan(summary,rows,components)
        plan['hoop_hole_plan']=hoop_plan
        row['plan']=plan
        if {p:identity(Path(p)) for p in row['input_identity']} != row['input_identity']:
            raise ValueError('Inputs changed while reading; scan again')
        validation=plan['summary_transform_validation']
        if validation['status']!='PASSED':
            row['warnings'].append('Summary transform anchor validation failed; generated script stops before mutation: '+ '; '.join(validation['errors']))
        row['supported_holes']=sorted({h['hole_id']+' / '+h['hole_type'] for h in plan['driving_holes']})
        row['driving_hole_count']=len(plan['driving_holes'])
        row['derived_hole_count']=len(plan['derived_holes'])
        row['hoop_plan_hole_count']=len(hoop_plan['driving_holes'])
        row['warnings'].append('HOOP: native round cuts enabled after Step06-A; reopen clean Step05 model before execution.')
        row['part_executions']=plan['part_executions']
        row['instance_isolation_required']=any(e['requires_instance_isolation'] for e in plan['part_executions'])
        for execution in plan['part_executions']:
            if execution['blocking_reasons']:
                raise ValueError(execution['execution_policy']+': '+'; '.join(execution['blocking_reasons']))
        row['shared_parts']=[dict(part_name=e['source_part'],instance_names=e['referencing_instances'])
                             for e in plan['part_executions'] if e['shared_part']]
        row.update(input_status='READY',capability='READY',
                   status='GENERATED' if row['generation_status']=='GENERATED' else 'READY')
    except NeedsInput as exc:
        row.update(input_status='NEEDS_INPUT',status='NEEDS_INPUT')
        row['missing_requirements'].append(str(exc))
    except Exception as exc:
        row.update(input_status='NEEDS_REVIEW',status='NEEDS_REVIEW',capability='NEEDS_REVIEW')
        row['errors'].append(str(exc))
    finally:
        problems=row['errors']+row['missing_requirements']
        row['first_blocking_reason']=problems[0] if problems else ''
        if problems:row['result']=row['first_blocking_reason']


def scan_projects(source, include_subfolders=False):
    from .hole_workbooks import SUFFIX, project_id_from_filename
    root=Path(source).resolve(strict=True)
    if not root.is_dir():raise ValueError('Project Folder must be a directory')
    result=dict(source_folder=str(root),include_subfolders=bool(include_subfolders),projects=[],warnings=[])
    for directory,dirs,filenames in os.walk(root,followlinks=False):
        folder=Path(directory)
        dirs[:]=sorted(d for d in dirs if not d.startswith(('.', '__')) and not linked(folder/d)) if include_subfolders else []
        projects=set()
        warnings=[]
        for name in sorted(filenames):
            if name.startswith('~$'):continue
            for suffix in ('_components.xlsx','_assembly_summary.json'):
                if name.endswith(suffix):projects.add(name[:-len(suffix)])
            # Legacy is diagnostic only, never an input fallback.
            if name=='Step06_螺栓孔定位表_中文版.xlsx':
                warnings.append('LEGACY_AGGREGATE_TABLE: '+name+'; use per-project hole workbooks.')
        for project in sorted(projects):
            row=_row(folder,project);row['warnings'].extend(warnings)
            _inspect(row);result['projects'].append(row)
        for name in sorted(filenames):
            if name.startswith('~$') or not name.endswith(SUFFIX):continue
            try:
                project=project_id_from_filename(name)
                if project in projects:continue
                reason='Workbook filename identity does not match any scanned project: '+project
            except ValueError as exc:
                project=name[:-len(SUFFIX)]
                reason=str(exc)
            row=_row(folder,project)
            row.update(hole_tables=[str(folder/name)],errors=[reason],first_blocking_reason=reason,result=reason)
            result['projects'].append(row)
    return result


def generate_hole_tables(scan, progress=None):
    from .hole_workbooks import workbook_path, create_hole_workbook
    events=[]
    counts=dict(created=0,preserved=0,failed=0)
    # Fresh discovery prevents stale component/summary mappings being used.
    fresh=scan_projects(scan['source_folder'],scan['include_subfolders'])
    for row in fresh['projects']:
        try:
            path=workbook_path(row['source_folder'],row['project_id'])
            if path.exists() or path.is_symlink():
                event=dict(path=str(path),status='PRESERVED',message='Existing hole table preserved.')
            else:
                if len(row['input_files'])!=2:raise ValueError('Missing components/summary input')
                before={p:identity(Path(p)) for p in row['input_files'].values()}
                # Read the data again under identity verification before publication.
                summary,components=_load_project(row)
                if before != {p:identity(Path(p)) for p in before}:raise ValueError('Inputs changed; scan again')
                event=create_hole_workbook(row['source_folder'],row['project_id'],summary,components)
            counts[event['status'].lower()]+=1
        except Exception as exc:
            event=dict(status='FAILED',message=str(exc));counts['failed']+=1
        event['project_id']=row['project_id'];events.append(event)
        if progress:progress(dict(event='table',row=dict(row,result=event['message'])))
    result=scan_projects(scan['source_folder'],scan['include_subfolders'])
    result.update(table_counts=counts,table_events=events)
    return result


def can_generate(row):
    return row.get("input_status") == "READY" and row.get("capability") == "READY"


def project_details(row):
    labels = (("Supported Holes", "supported_holes"), ("Driving Hole Count", "driving_hole_count"),
              ("Derived Hole Count", "derived_hole_count"), ("HOOP Driving Holes", "hoop_plan_hole_count"), ("Shared Part", "shared_parts"),
              ("Instance Isolation Required", "instance_isolation_required"),
              ("Part Execution Policy", "part_executions"),
              ("Missing Requirements", "missing_requirements"), ("Warnings", "warnings"),
              ("First Blocking Reason", "first_blocking_reason"), ("Generated Files", "generated_files"))
    lines = [row["project_id"], "Project Folder: "+row["source_folder"], "Benchmark Scope: P01-P04 / Step06-A"]
    for label, key in labels:
        lines.append(label+": "+json.dumps(row.get(key), ensure_ascii=False))
    return "\n".join(lines)


def generate_batch(scan, selected=None, progress=None):
    """Rescan to prevent stale capability/mapping; publish in each input folder."""
    from .hole_setup import write_hole_setup
    result = copy.deepcopy(scan)
    fresh = scan_projects(scan["source_folder"], scan["include_subfolders"])
    current = {(r["source_folder"], r["project_id"]):r for r in fresh["projects"]}
    counts = dict(succeeded=0, failed=0, skipped=0)
    for row in result["projects"]:
        key = (row["source_folder"], row["project_id"])
        if selected is not None and key not in selected:
            continue
        if not can_generate(row):
            counts["skipped"] += 1
            if progress: progress(dict(event="skipped", row=copy.deepcopy(row)))
            continue
        try:
            now = current.get(key)
            if not now or not can_generate(now) or now["input_identity"] != row["input_identity"]:
                raise ValueError("Inputs/project mapping changed since scan; Scan Projects again")
            paths = write_hole_setup(now["plan"], Path(row["source_folder"]), now["input_identity"])
            row.update(status="GENERATED", generation_status="GENERATED", generated_files={k:str(p) for k,p in paths.items()}, result="Outputs found")
            counts["succeeded"] += 1
        except Exception as exc:
            row.update(result=str(exc), input_status="NEEDS_REVIEW", capability="NEEDS_REVIEW",
                       status="NEEDS_REVIEW", first_blocking_reason=str(exc))
            row["errors"].append(str(exc))
            counts["failed"] += 1
        if progress: progress(dict(event="completed", row=copy.deepcopy(row)))
    result["generation_counts"] = counts
    return result
