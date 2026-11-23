import csv
import hashlib
import json
import os
from pathlib import Path
from .executor import digest

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)

def fingerprint_details(stage, upstream, executor_identity):
    files = {stage.script: digest(stage.script)}
    roles = {stage.script: 'script'}
    for item in stage.inputs:
        # Generator sources are not consumed by embedded scripts. Reports only
        # participate when explicitly bound as a current upstream runtime input.
        if item.get('role') not in ('runtime', 'config'):
            continue
        path = Path(item['path'])
        name = str(path)
        files[name] = digest(path) if path.is_file() else None
        roles[name] = 'upstream_output' if item.get('from_stage') else item['role']
    return dict(files=files, roles=roles, upstream=upstream, contract=stage.contract,
                executor=executor_identity, version=3, workflow='hole-step07-nine-v1')


def fingerprint(stage, upstream, executor_identity):
    return hashlib.sha256(json.dumps(fingerprint_details(stage, upstream, executor_identity), sort_keys=True).encode()).hexdigest()


def change_reasons(prior, details):
    old = prior.get('fingerprint_details')
    if not prior:
        return ['No previous successful checkpoint']
    if not old:
        return ['Legacy fingerprint metadata requires one-time revalidation']
    reasons = []
    for path in sorted(set(old['files']) | set(details['files'])):
        if old['files'].get(path) != details['files'].get(path):
            reasons.append('Content changed: '+path)
    for key in ('upstream', 'contract', 'executor'):
        if old.get(key) != details.get(key):
            reasons.append(key+' changed')
    return reasons or ['Checkpoint or evidence missing/changed, or upstream invalid']


def valid(record, signature):
    if not record or record.get('status') != 'SUCCESS' or record.get('fingerprint') != signature:
        return False
    try:
        for artifact, expected in record.get('artifacts', {}).items():
            if digest(artifact) != expected:
                return False
        path = Path(record['checkpoint'])
        return path.is_file() and path.stat().st_size > 0 and digest(path) == record['checkpoint_hash'] and record['evidence']['status'] == 'SUCCESS'
    except (OSError, KeyError):
        return False

def summary(directory, projects):
    write_json(Path(directory)/'summary.json', projects)
    with (Path(directory)/'summary.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['project', 'directory', 'result', 'Part', 'Assembly', 'Analysis', 'Hole', 'Tie', 'Step', 'BC', 'Mesh', 'Load', 'execution_result', 'model_save', 'model_validation', 'model_path'])
        for p in projects:
            # Prevent spreadsheet formula interpretation of user-controlled names.
            prefix = p['prefix']
            if prefix.startswith(('=', '+', '-', '@')):
                prefix = "'" + prefix
            writer.writerow([prefix, p['folder'], p['result']] + [('REUSED' if s.get('action') == 'REUSED' and s['status'] == 'SUCCESS' else ('RERUN / ' if s.get('action') == 'RERUN' else '')+s['status']) for s in p['stages']] + [p.get('execution_result', ''), p.get('delivery', {}).get('save_status', ''), p.get('delivery', {}).get('status', ''), p.get('delivery', {}).get('path', '')])
