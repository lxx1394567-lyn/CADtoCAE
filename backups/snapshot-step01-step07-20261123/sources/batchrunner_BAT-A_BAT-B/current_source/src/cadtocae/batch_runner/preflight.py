"""Read-only checkpoint preflight. Readiness and historical status stay separate."""
import json
from pathlib import Path
from .state import fingerprint, fingerprint_details, change_reasons, valid

def attach_history(project, output, identity):
    output = Path(output)
    try:
        history = json.loads((output/'history'/(project.key+'.json')).read_text(encoding='utf-8'))['stages']
    except (OSError, ValueError, KeyError):
        history = {}
    try:
        latest = json.loads((output/'history'/(project.key+'-latest.json')).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        latest = {}
        # V1 had no latest pointer. Batch IDs are chronological IDs, not file-match heuristics.
        for batch in sorted(output.glob('????????-??????-*'), reverse=True):
            path = batch/project.key/'record.json'
            if path.is_file():
                try:
                    latest = json.loads(path.read_text(encoding='utf-8'))
                    break
                except (OSError, ValueError):
                    continue
    chain = True
    upstream = ''
    for stage in project.stages:
        old = history.get(str(stage.number), {})
        recent = next((s for s in latest.get('stages', []) if s['number']==stage.number), {})
        stage.history_status = old.get('status') or recent.get('status')
        stage.history_error = recent.get('error')
        if recent.get('status') == 'FAILED' and latest.get('batch'):
            error_path = output/latest['batch']/project.key/('step%d'%stage.number)/'worker_error.txt'
            if error_path.is_file():
                stage.history_error = error_path.read_text(encoding='utf-8', errors='replace')
        for item in stage.inputs:
            producer = item.get('from_stage')
            if producer:
                previous = project.stages[producer-1]
                checkpoint = previous.checkpoint
                if checkpoint.get('valid'):
                    path = Path(checkpoint['path']).parent/item.get('source_name', item['relative'])
                    item.update(path=str(path), found=path.is_file(), validation='VALIDATED_UPSTREAM' if path.is_file() else 'WAITING_UPSTREAM')
                else:
                    item['validation'] = 'WAITING_UPSTREAM'
        signature = None
        if stage.script and stage.status == 'READY':
            try:
                signature = fingerprint(stage, upstream, identity)
            except OSError as exc:
                stage.reasons.append(str(exc))
        reliable = chain and signature is not None and valid(old, signature)
        stage.checkpoint = dict(valid=reliable, path=old.get('checkpoint'), state='VALID' if reliable else 'STALE' if old else 'NOT_CREATED')
        if old:
            stage.history_status = 'SUCCESS' if reliable else 'STALE'
        stage.plan_action = 'REUSED' if reliable else 'RERUN' if old and stage.script else 'RUN' if stage.script else 'MISSING'
        if old and not reliable and signature is not None:
            stage.change_reasons = change_reasons(old, fingerprint_details(stage, upstream, identity))
        if reliable:
            upstream = dict(fingerprint=signature, checkpoint_sha256=old['checkpoint_hash'])
        chain = reliable
    return project
