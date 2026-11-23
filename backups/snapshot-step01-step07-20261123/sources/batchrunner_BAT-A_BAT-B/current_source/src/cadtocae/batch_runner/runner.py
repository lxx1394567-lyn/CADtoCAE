import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .dependencies import check
from .scanner import scan
from .state import fingerprint, fingerprint_details, change_reasons, valid, write_json, summary
from .executor import digest

def now():
    return datetime.now(timezone.utc).isoformat()

class BatchRunner:
    def __init__(self, root, output, executor, on_update=None, through=9):
        if through not in range(1, 10):
            raise ValueError('Invalid final stage')
        self.through = through
        self.root = Path(root).resolve()
        self.output = Path(output).resolve()
        if self.output == self.root or self.output in self.root.parents:
            raise ValueError('Output must be a separate directory, not the project root or its parent')
        self.executor = executor
        self.stop = threading.Event()
        self.on_update = on_update or (lambda data: None)

    def inspect(self):
        from .preflight import attach_history
        projects = [attach_history(check(p), self.output, self.executor.identity) for p in scan(self.root, [self.output])]
        for project in projects:
            for stage in project.stages:
                if stage.number > self.through and stage.script:
                    stage.status = 'SKIPPED'
                    stage.plan_action = 'SKIPPED'
                    stage.reasons.append('Excluded by through=%d' % self.through)
        return projects

    def run(self, mode='smart', start=1, selected=None, continue_on_error=True):
        if mode == 'smart':
            mode = 'resume'
        if mode not in ('full', 'resume', 'from') or start not in range(1, 10):
            raise ValueError('Invalid mode/start')
        self.output.mkdir(parents=True, exist_ok=True)
        # Exclusive history writer; a crashed lock must be reviewed, never silently stolen.
        lock = self.output/'runner.lock'
        with lock.open('x', encoding='ascii') as handle:
            import os
            handle.write(str(os.getpid()))
        try:
            return self._run(mode, start, selected, continue_on_error)
        finally:
            lock.unlink()

    def _run(self, mode, start, selected, continue_on_error):
        batch = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        directory = self.output/batch
        directory.mkdir()
        records = []
        for project in self.inspect():
            pdir = directory/project.key
            pdir.mkdir()
            history_path = self.output/'history'/(project.key + '.json')
            try:
                history = json.loads(history_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                history = {}
            old = history.get('stages', {})
            historical = dict(old)
            current = dict(workflow='hole-step07-nine-v1', total_stages=9, batch=batch, prefix=project.prefix, folder=project.folder, key=project.key,
                           started=now(), result='PENDING', stages=[], update_plan=[dict(number=s.number, action=s.plan_action, reasons=s.change_reasons) for s in project.stages])
            records.append(current)
            upstream = ''
            previous = None
            blocked = False
            chain_valid = True
            for stage in project.stages:
                row = dict(number=stage.number, script=stage.script, scan_status=stage.status,
                           status=stage.status, reasons=list(stage.reasons), inputs=stage.inputs,
                           warnings=stage.warnings, history_status=stage.history_status or historical.get(str(stage.number), {}).get('status'))
                current['stages'].append(row)
                if selected is not None and project.key not in selected:
                    if stage.script:
                        row['status'] = 'SKIPPED'
                    continue
                if stage.status == 'SKIPPED':
                    blocked = True
                    chain_valid = False
                    continue
                if stage.status == 'MISSING':
                    blocked = True
                    chain_valid = False
                    continue
                if blocked or stage.status in ('BLOCKED', 'MISSING_INPUT'):
                    row['status'] = 'MISSING_INPUT' if stage.status == 'MISSING_INPUT' else 'BLOCKED'
                    row['reasons'].append('Predecessor did not complete in this plan')
                    blocked = True
                    chain_valid = False
                    continue
                try:
                    missing_upstream = []
                    for item in stage.inputs:
                        producer = item.get('from_stage')
                        if producer is not None:
                            source_row = current['stages'][producer-1]
                            source_path = Path(source_row['checkpoint']).parent/item.get('source_name', item['relative'])
                            item.update(path=str(source_path), found=source_path.is_file())
                            if item['required'] and not item['found']:
                                missing_upstream.append(str(source_path))
                    if missing_upstream:
                        row.update(status='BLOCKED', reasons=['Missing upstream outputs: ' + ', '.join(missing_upstream)])
                        blocked = True
                        continue
                    if stage.inspected_source_sha256 and digest(stage.script) != stage.inspected_source_sha256:
                        raise RuntimeError('Source changed after inspection; rescan required: '+stage.script)
                    details = fingerprint_details(stage, upstream, self.executor.identity)
                    stage.expected_source_sha256 = details['files'][stage.script]
                    signature = fingerprint(stage, upstream, self.executor.identity)
                    prior = historical.get(str(stage.number), {})
                    reusable = chain_valid and valid(prior, signature)
                    if prior and not reusable:
                        row['history_status'] = 'STALE'
                    chain_valid = reusable
                    row['fingerprint'] = signature
                    row['fingerprint_details'] = details
                    row['change_reasons'] = change_reasons(prior, details) if not reusable else []
                    if (mode == 'resume' or (mode == 'from' and stage.number < start)) and reusable:
                        row.update(status='SUCCESS', action='REUSED', reused=True, execution_files=prior.get('execution_files'), checkpoint=prior['checkpoint'],
                                   checkpoint_hash=prior['checkpoint_hash'], evidence=prior['evidence'], artifacts=prior.get('artifacts', {}))
                        previous = prior['checkpoint']
                        upstream = dict(fingerprint=signature, checkpoint_sha256=row['checkpoint_hash'])
                        continue
                    if mode == 'from' and stage.number < start:
                        row['status'] = 'BLOCKED'
                        row['reasons'].append('No valid predecessor checkpoint; full/resume required')
                        blocked = True
                        continue
                    if self.stop.is_set():
                        row['status'] = 'SKIPPED'
                        row['reasons'].append('User requested safe stop')
                        blocked = True
                        continue
                    # Retire superseded history before any attempted mutation, including failures.
                    old = {k: v for k, v in old.items() if int(k) < stage.number}
                    write_json(history_path, dict(prefix=project.prefix, stages=old))
                    row.update(status='RUNNING', action='RERUN' if prior else 'RUN', reused=False, started=now())
                    write_json(pdir/'record.json', current)
                    self.on_update(current)
                    stage_dir = pdir/('step%d' % stage.number)
                    stage_dir.mkdir()
                    started = time.monotonic()
                    try:
                        result = self.executor.execute(project, stage, stage_dir, previous)
                        row.update(result)
                        if fingerprint(stage, upstream, self.executor.identity) != signature:
                            raise RuntimeError('Source changed during execution; checkpoint not accepted')
                        checkpoint = Path(result['checkpoint'])
                        if not checkpoint.is_file() or not checkpoint.stat().st_size or result.get('returncode') != 0 or result.get('evidence', {}).get('status') != 'SUCCESS':
                            raise RuntimeError('Missing checkpoint or success evidence')
                        row.update(status='SUCCESS', checkpoint_hash=digest(checkpoint))
                        previous = str(checkpoint)
                        upstream = dict(fingerprint=signature, checkpoint_sha256=row['checkpoint_hash'])
                        # Invalidate every downstream entry before publishing this stage.
                        old = {k: v for k, v in old.items() if int(k) < stage.number}
                        old[str(stage.number)] = dict(row)
                        write_json(history_path, dict(prefix=project.prefix, stages=old))
                    except Exception as exc:
                        row.update(status='REVIEW_REQUIRED' if 'REVIEW_REQUIRED:' in str(exc) else 'FAILED', error=str(exc))
                        process_file = stage_dir/'process.json'
                        if process_file.exists():
                            row.update(json.loads(process_file.read_text(encoding='utf-8')))
                        blocked = True
                        if not continue_on_error:
                            self.stop.set()
                    finally:
                        row.update(ended=now(), elapsed_seconds=time.monotonic()-started)
                        if row['status'] == 'SUCCESS':
                            old[str(stage.number)] = dict(row)
                            write_json(history_path, dict(prefix=project.prefix, stages=old))
                except Exception as exc:
                    row.update(status='FAILED', error=str(exc))
                    blocked = True
                    if not continue_on_error:
                        self.stop.set()
                write_json(pdir/'record.json', current)
                self.on_update(current)
            statuses = [s['status'] for s in current['stages']]
            current['result'] = ('FAILED' if 'FAILED' in statuses else 'REVIEW_REQUIRED' if 'REVIEW_REQUIRED' in statuses else 'SUCCESS' if all(s == 'SUCCESS' for s in statuses)
                                 else 'PARTIAL_SUCCESS' if 'SUCCESS' in statuses else 'BLOCKED' if any(s in ('MISSING_INPUT', 'BLOCKED') for s in statuses) else 'SKIPPED' if 'SKIPPED' in statuses else 'BLOCKED')
            current['execution_result'] = current['result']
            from .delivery import deliver
            current['delivery'] = deliver(self.root, project, current, self.executor, pdir/'delivery')
            if current['result'] in ('SUCCESS', 'PARTIAL_SUCCESS') and current['delivery']['status'] != 'PASSED':
                current['result'] = 'DELIVERY_FAILED' if current['delivery']['status'] == 'FAILED' else 'NOT_VERIFIED'
            if current['result'] == 'DELIVERY_FAILED' and not continue_on_error:
                self.stop.set()
            current['ended'] = now()
            write_json(pdir/'record.json', current)
            write_json(self.output/'history'/(project.key+'-latest.json'), current)
            summary(directory, records)
            self.on_update(current)
        summary(directory, records)
        return directory, records
