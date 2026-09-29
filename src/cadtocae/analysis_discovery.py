"""Read-only folder discovery. Never merge inputs across source directories."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from .analysis_project import ProjectFiles, validate_project_files
from .analysis_capability import is_hoop_member, match_hoop_component, hoop_mapping, GeometryReviewError, first_blocking_reason
from .main_frame_assembly import _read_named_points, is_hoop_component_code
from .workbook import load_dimension_complete_components, component_code_from_row

SUFFIXES = {'components': '_components.xlsx', 'coordinate': '_coordinate.xlsx',
            'assembly_summary': '_assembly_summary.json', 'part_script': '_create_parts_in_cae.py',
            'assembly_script': '_assembly_frame.py'}
REQUIRED = ('components', 'coordinate', 'assembly_summary')
ROLES = ('INCLINED_BEAM', 'BRACE_FRONT', 'BRACE_REAR', 'COLUMN_UP', 'COLUMN_DOWN')
RULES = ['BEAM_BRACE_TIE', 'COLUMN_COLUMN_TIE', 'COLUMN_HOOP_TIE', 'COLUMN_BEAM_COUPLING']


def output_paths(folder, project):
    return {key:Path(folder)/(project+suffix) for key,suffix in (
        ('plan','_analysis_plan.json'),('script','_analysis_setup.py'))}


def linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def safe_project_id(value):
    if not value or value != value.strip() or value.endswith('.') or re.search(r'[<>:"/\\|?*\x00-\x1f]', value):
        raise ValueError('Unsafe project ID: '+repr(value))
    if value in ('.', '..') or value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        raise ValueError('Reserved project ID: '+value)


def identity(path):
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''): digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Input changed while reading: '+str(path))
    return dict(sha256=digest.hexdigest(), size=after.st_size, mtime_ns=after.st_mtime_ns)


def project_files(record):
    return ProjectFiles(**{key: Path(value) for key,value in record['input_files'].items()})


def inspect_project(folder, project, candidates):
    row = dict(project_id=project, source_folder=str(folder), structure_type=None, status='READY',
               generation_status='NOT_GENERATED', capability=None, supported_rules=[], input_files={},
               missing_requirements=dict(files=[], roles=[], points=[], hoop_groups=[]), warnings=[], errors=[],
               generated_files={}, input_identity={})
    try:
        safe_project_id(project)
        for key, paths in candidates.items():
            if len(paths) != 1: raise ValueError('Duplicate '+key+': '+', '.join(map(str,paths)))
            if linked(paths[0]): raise ValueError('Linked input is not supported: '+str(paths[0]))
            row['input_files'][key] = str(paths[0])
        before = {key:identity(Path(row['input_files'][key])) for key in REQUIRED if key in row['input_files']}
        missing = row['missing_requirements']
        missing['files'] = [key for key in REQUIRED if key not in candidates]
        for key in ('part_script','assembly_script'):
            if key not in candidates: row['warnings'].append('Optional script missing: '+key)
        if 'assembly_summary' in row['input_files']:
            summary = json.loads(Path(row['input_files']['assembly_summary']).read_text(encoding='utf-8-sig'))
            row['structure_type'] = summary.get('structure_type')
            if summary.get('project_id') != project: raise ValueError('Summary/project prefix mismatch')
            if not isinstance(row['structure_type'],str) or not row['structure_type'].strip():
                raise ValueError('Missing structure_type in summary')
            if row['structure_type'] not in ('SP_SC','SP_DC'):
                row['status'] = 'UNSUPPORTED_STRUCTURE'
                return row
        if missing['files']:
            row['status'] = 'INPUT_INCOMPLETE'
            return row
        files = project_files(row)
        summary = validate_project_files(files)
        members = summary.get('instances',[])
        roles = defaultdict(list)
        for member in members: roles[member.get('canonical_role') or member.get('component_code')].append(member)
        raw = load_dimension_complete_components(files.components)
        normalized = Counter((component_code_from_row(r), r.get('abaqus_part_name')) for r in raw)
        from .sp_dc_rules import DC_ROLES, DC_RULES, DC_CAPABILITY, normalized_components, column_beam_plan, hoop_group_plans, input_warnings
        is_dc = row['structure_type']=='SP_DC'
        for role in (DC_ROLES if is_dc else ROLES):
            selected = roles[role]
            if not selected: missing['roles'].append(role)
            elif len(selected)!=1: row['errors'].append('Ambiguous role: '+role)
            elif normalized[(selected[0]['component_code'], selected[0]['part_name'])] != 1:
                missing['roles'].append(role+' (missing/ambiguous dimension-complete component)')
        points,_ = _read_named_points(files.coordinate)
        for key in (('B','C','D','E','UF1','UR1') if is_dc else ('B','C','D','E','F')):
            a,b = summary.get('assembly_points',{}).get(key), points.get(key)
            def valid(v):
                return isinstance(v,(tuple,list)) and len(v)==3 and all(type(x) in (int,float) and math.isfinite(x) for x in v)
            if not valid(a) or not valid(b): missing['points'].append(key)
            elif max(abs(x-y) for x,y in zip(a,b))>1.e-6: row['errors'].append('Coordinate/summary mismatch: '+key)
        hoops = [m for m in members if is_hoop_member(m)]
        groups = defaultdict(list)
        for m in hoops: groups[m.get('connection_group')].append(m)
        if not groups: missing['hoop_groups'].append('Complete HOOP A/B connection_group')
        elif len(groups)!=1 and not is_dc: row['errors'].append('Frozen v1 supports exactly one HOOP A/B group')
        row['hoop_component_mappings']=[]
        row['complete_hoop_group_count']=0
        for group, halves in groups.items():
            labels = [h.get('pair_member') or h.get('instance_name','').rsplit('_',1)[-1] for h in halves]
            if not group or sorted(labels)!=['A','B']:
                missing['hoop_groups'].append(str(group)+' (requires unique A/B pair)')
            else:row['complete_hoop_group_count']+=1
            for h in halves:
                try:
                    matched=match_hoop_component(h,raw)
                    row['hoop_component_mappings'].append(hoop_mapping(h,matched))
                except ValueError as exc:
                    missing['hoop_groups'].append(str(group)+' ('+str(exc)+')')
        if is_dc and not any(missing.values()) and not row['errors']:
            from .analysis_defaults import DEFAULT_SP_DC_ANALYSIS_CONFIG
            normalized_geometry=normalized_components(files.components)
            column=column_beam_plan(summary,normalized_geometry,DEFAULT_SP_DC_ANALYSIS_CONFIG['COLUMN_BEAM_TIE'])
            row['warnings'].extend(input_warnings(summary,normalized_geometry,points))
            try:
                resolved_groups=hoop_group_plans(summary,normalized_geometry)
            except GeometryReviewError as exc:
                resolved_groups=exc.groups
                row['geometry_review']=exc.issues
                row['first_blocking_reason']=exc.issues[0]['reason']
                row['warnings'].extend(i['details'] for i in exc.issues)
                row['capability']='NEEDS_REVIEW'
                row['supported_rules']=list(DC_RULES)
                row['errors'].append(str(exc))
            row['column_stations']=[c['station_m'] for c in column['connections']]
            row['hoop_groups']=[g['group_id'] for g in resolved_groups]
            row['expected_nominal_tie_count']=4+2*len(resolved_groups)
            row['executable_tie_count']=None if row.get('geometry_review') else row['expected_nominal_tie_count']
            if not row.get('geometry_review'):row['expected_tie_count']=row['expected_nominal_tie_count']
        after = {key:identity(Path(row['input_files'][key])) for key in REQUIRED}
        if before!=after: raise ValueError('Inputs changed during scan; scan again')
        row['input_identity'] = after
        if any(missing.values()) or row['errors']: row['status']='NEEDS_REVIEW'
        else:
            row['capability']=DC_CAPABILITY if is_dc else 'SP_SC_FULL_CONNECTION_SETUP'
            row['supported_rules']=list(DC_RULES if is_dc else RULES)
    except (ValueError, KeyError, TypeError) as exc:
        row['status']='NEEDS_REVIEW';row['errors'].append(str(exc))
    except Exception as exc:
        row['status']='FAILED';row['errors'].append(str(exc))
    return row


def scan_projects(source, include_subfolders=False):
    root=Path(source).resolve(strict=True)
    if not root.is_dir(): raise ValueError('Source folder does not exist')
    groups=defaultdict(lambda:defaultdict(list))
    for folder, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not linked(Path(folder)/d)) if include_subfolders else []
        for name in sorted(names):
            if name.startswith('~$'): continue
            for key,suffix in SUFFIXES.items():
                if name.lower().endswith(suffix):
                    groups[(Path(folder),name[:-len(suffix)])][key].append(Path(folder)/name)
                    break
    rows=[inspect_project(folder,project,files) for (folder,project),files in sorted(groups.items(),key=lambda x:str(x[0]).casefold())]
    by_id=defaultdict(list)
    for row in rows: by_id[row['project_id'].casefold()].append(row)
    for matches in by_id.values():
        if len(matches)>1:
            for row in matches:
                row['status']='NEEDS_REVIEW'
                row['errors'].append('Duplicate project sources: '+', '.join(m['source_folder'] for m in matches))
    for row in rows:
        row['input_status']=row['status']
        row['input_errors']=list(row['errors'])
        row['first_blocking_reason']=first_blocking_reason(row)
        try:
            safe_project_id(row['project_id'])
            paths=output_paths(root,row['project_id'])
            found={key:str(path) for key,path in paths.items() if path.is_file()}
            row['generated_files']=found
            row['generation_status']='GENERATED' if len(found)==2 else ('PARTIAL' if found else 'NOT_GENERATED')
        except ValueError:
            row['generation_status']='NEEDS_REVIEW'
    return dict(source_folder=str(root),include_subfolders=bool(include_subfolders),projects=rows)
