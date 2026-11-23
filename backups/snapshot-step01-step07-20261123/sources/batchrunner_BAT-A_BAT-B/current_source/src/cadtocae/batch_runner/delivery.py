"""Verified fixed-name CAE delivery and independent Abaqus inspection; no modelling here."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime
from .executor import digest
from .state import write_json


def abaqus_command(executor, arguments):
    command = list(executor.command) + list(arguments)
    command[0] = shutil.which(command[0]) or command[0]
    if os.name == 'nt' and str(command[0]).lower().endswith(('.bat', '.cmd')):
        if any(any(c in arg for c in '&|<>^%!\r\n') for arg in command):
            raise ValueError('Unsafe cmd.exe metacharacter in Abaqus command')
        return subprocess.list2cmdline([os.environ.get('COMSPEC', 'cmd.exe')]) + ' /d /s /c "' + subprocess.list2cmdline(command) + '"'
    return command


def expected(project, rows):
    job = dict(model=project.prefix, parts=[], instances=[], steps=[], reports={})
    for stage, row in zip(project.stages, rows):
        for key in ('parts', 'instances', 'steps'):
            job[key].extend(stage.contract.get(key, []))
        checkpoint = Path(row['checkpoint'])
        if digest(checkpoint) != row['checkpoint_hash']:
            raise ValueError('Checkpoint changed: '+str(checkpoint))
        for path, sha in row.get('artifacts', {}).items():
            if digest(path) != sha:
                raise ValueError('Stage evidence changed: '+path)
        if stage.number >= 3 and stage.contract.get('kind') == 'report':
            report_path = checkpoint.parent/'runtime_report.json'
            if str(report_path) not in row.get('artifacts', {}):
                raise ValueError('Runtime report lacks validated provenance')
            report = json.loads(report_path.read_text(encoding='utf-8'))
            if report.get('project_id') != project.prefix or report.get('status') != 'SUCCESS':
                raise ValueError('Runtime report project/status mismatch')
            job['reports'][str(stage.number)] = report
    unsupported = []
    if not job['parts']:
        unsupported.append('No expected Part names in script contract')
    if len(rows) >= 2 and not job['instances']:
        unsupported.append('No expected Assembly instances in script contract')
    if len(rows) >= 3 and '3' not in job['reports'] and not job['steps']:
        unsupported.append('No verifiable Analysis report or expected steps')
    if len(rows) >= 4:
        r = job['reports'].get('4', {})
        if not all(k in r for k in ('support', 'purlin_local', 'inclined_beam', 'hoop_validation', 'created_holes')):
            unsupported.append('Unsupported Hole report: cannot verify saved geometry')
        job['baseline'] = rows[2]['checkpoint']
    for number in range(5, len(rows)+1):
        r = job['reports'].get(str(number), {})
        required = {5: 'tie_validation', 6: 'step_parameters', 7: 'bc_validation', 8: 'parts', 9: 'loads'}[number]
        if not r.get(required) or r.get('stage') != number-4:
            unsupported.append('Unsupported Step07 report at stage %d: missing %s' % (number, required))
    job['workflow'] = 'hole-step07-nine-v1'
    return job, unsupported


def verify_file(executor, job, directory):
    """Open byte-identical snapshots: openMdb itself may touch CAE metadata."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    scratch_root = Path(executor.environment.get('BATCHRUNNER_SCRATCH', tempfile.gettempdir())).resolve()
    if os.name == 'nt' and not str(scratch_root).isascii():
        raise ValueError('BATCHRUNNER_SCRATCH must be an ASCII path for Abaqus 2020')
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cae-verify-', dir=scratch_root) as scratch:
        scratch = Path(scratch)
        job = dict(job, token=uuid.uuid4().hex)
        original_path = job['path']
        snapshot_hashes = {}
        for key in ('path', 'baseline'):
            if job.get(key):
                src = Path(job[key])
                before = digest(src)
                dest = scratch/(key+'.cae')
                shutil.copy2(src, dest)
                if digest(dest) != before or digest(src) != before:
                    raise RuntimeError('Verification snapshot changed: '+str(src))
                snapshot_hashes[key] = dict(source=str(src), sha256=before)
                job[key] = str(dest)
        write_json(scratch/'verify_job.json', job)
        write_json(scratch/'snapshot_hashes.json', snapshot_hashes)
        (scratch/'verify.py').write_text(Path(__file__).with_name('delivery_worker.py').read_text(encoding='utf-8-sig'), encoding='utf-8')
        shutil.copy2(Path(__file__).with_name('step07_verify.py'), scratch/'step07_verify.py')
        command = abaqus_command(executor, ['cae', 'noGUI=verify.py'])
        env = dict(os.environ, **executor.environment)
        write_json(scratch/'command.json', command)
        try:
            with (scratch/'stdout.log').open('wb') as out, (scratch/'stderr.log').open('wb') as err:
                code = subprocess.call(command, cwd=scratch, env=env, stdout=out, stderr=err,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            write_json(scratch/'process.json', dict(returncode=code))
            path = scratch/'verification.json'
            if code != 0 or not path.is_file():
                raise RuntimeError('Independent Abaqus verification failed (exit %s); see %s' % (code, directory))
            evidence = json.loads(path.read_text(encoding='utf-8'))
            if evidence.get('token') != job['token'] or evidence.get('path') != job['path']:
                raise RuntimeError('Verification receipt identity mismatch')
            if evidence.get('status') == 'PASSED' and (evidence.get('model') != job['model'] or not evidence.get('checks') or any(c.get('status') != 'PASSED' for c in evidence['checks'])):
                raise RuntimeError('Incomplete independent validation receipt')
            evidence['inspected_snapshot'] = evidence['path']
            evidence['path'] = original_path
            evidence['snapshot_hashes'] = snapshot_hashes
            return evidence
        finally:
            shutil.copytree(scratch, directory, dirs_exist_ok=True)


def deliver(root, project, current, executor, directory):
    result = dict(workflow='hole-step07-nine-v1', status='NOT_VERIFIED', save_status='NOT_SAVED', path=None, stage=0, logs=str(directory))
    rows = []
    for row in current['stages']:
        if row['status'] != 'SUCCESS':
            break
        rows.append(row)
    if not rows:
        return result
    result['stage'] = len(rows)
    if current.get('execution_result') in ('FAILED', 'BLOCKED', 'SKIPPED', 'REVIEW_REQUIRED'):
        result['error'] = 'Run did not complete successfully; previous deliveries retained'
        return result
    # Test doubles and third-party executors cannot certify a real Abaqus database.
    if getattr(executor, 'kind', None) != 'abaqus':
        result['error'] = 'No real Abaqus executor: model delivery NOT_VERIFIED'
        return result
    try:
        job, unsupported = expected(project, rows)
        from .publication import publish, store, registry
        directory = store(root, project.key)/'runs'/uuid.uuid4().hex
        directory.mkdir(parents=True)
        result['logs'] = str(directory)
        source = Path(rows[-1]['checkpoint'])
        sha = rows[-1]['checkpoint_hash']
        stem = project.prefix + ('_final' if len(rows) == 9 else '_step%02d' % len(rows))
        if Path(stem).name != stem or any(c in stem for c in '/\\:'):
            raise ValueError('Unsafe project filename')
        target = Path(root).resolve()/'CAE_Results'/(stem+'.cae')
        candidate = directory/'candidate.cae'
        shutil.copy2(source, candidate)
        result.update(path=None, target=str(target), sha256=sha, size_bytes=candidate.stat().st_size,
                      project_key=project.key, model=project.prefix, source=str(source), published=False)
        if digest(candidate) != sha or digest(source) != sha:
            raise RuntimeError('CAE changed during staging')
        result['save_status'] = 'SAVED'
        if unsupported:
            result['error'] = '; '.join(unsupported)
        else:
            job['path'] = str(candidate)
            evidence = verify_file(executor, job, directory/'verification')
            result.update(status=evidence['status'], verification=evidence)
            if evidence.get('error'):
                result['error'] = evidence['error']
            if digest(candidate) != sha:
                raise RuntimeError('Candidate CAE changed during verification')
            expected(project, rows)
            if result['status'] == 'PASSED':
                result['path'] = str(target)
                publish(root, project.key, result, candidate)
        result['available'] = registry(root, project.key)
    except Exception as exc:
        result.update(status='FAILED', error=str(exc))
        if not result.get('published'):
            result['path'] = None
    write_json(Path(directory)/'delivery.json', result)
    return result


def checked_model_path(delivery):
    if delivery.get('status') != 'PASSED':
        raise ValueError('模型尚未通过独立验证，请查看模型交付详情并重新运行。')
    path = Path(delivery['path'])
    if not path.is_file():
        raise ValueError('CAE 文件不存在：'+str(path))
    if digest(path) != delivery.get('sha256'):
        raise ValueError('CAE 文件已变化或损坏，需要重新验证：'+str(path))
    return path


def open_model(executor, delivery):
    path = checked_model_path(delivery)
    if not executor.command or not (shutil.which(executor.command[0]) or Path(executor.command[0]).is_file()):
        raise ValueError('Abaqus 启动器不存在，请检查高级设置。')
    command = abaqus_command(executor, ['cae', 'database='+str(path)])
    gui_directory = path.parent.parent/'.batchrunner'/'gui_sessions'/uuid.uuid4().hex
    gui_directory.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(command, cwd=gui_directory, env=dict(os.environ, **executor.environment),
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
