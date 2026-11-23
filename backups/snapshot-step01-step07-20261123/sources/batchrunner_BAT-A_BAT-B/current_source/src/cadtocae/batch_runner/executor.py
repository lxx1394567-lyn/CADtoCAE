import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
from . import cae_worker_source

# No importing Abaqus in the host interpreter.
def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()

def adapt(source, integrated_hole_report=False):
    """Only alter top-level output assignments and capture Part return, in a COPY."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    edits = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name == 'PLAN' and integrated_hole_report:
                from .dependencies import values
                plan = values(tree)['PLAN']
                plan['hole_report_path'] = 'upstream_hole_report.json'
                replacement = 'PLAN = json.loads(%r)\n' % json.dumps(plan, ensure_ascii=True, sort_keys=True)
                edits.append((node.lineno, node.end_lineno, replacement))
            if name in ('REPORT', 'REPORT_PATH', 'SAVE_AS_PATH', 'SUGGESTED_SAVE_AS_PATH'):
                value = 'runtime_report.json' if name in ('REPORT', 'REPORT_PATH') else ''
                edits.append((node.lineno, node.end_lineno, '%s = %r\n' % (name, value)))
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'create_parts':
            edits.append((node.lineno, node.end_lineno, '_batch_parts_result = create_parts()\n'))
    for start, end, replacement in sorted(edits, reverse=True):
        lines[start-1:end] = [replacement]
    return ''.join(lines)

class AbaqusExecutor:
    kind = 'abaqus'

    def __init__(self, command=('abaqus',), environment=None):
        if not command:
            raise ValueError('Abaqus command cannot be empty')
        self.command = list(command)
        self.environment = dict(environment or {})

    @property
    def identity(self):
        return dict(kind=self.kind, command=self.command, environment=self.environment, adapter_version=3,
                    worker=hashlib.sha256(cae_worker_source().encode()).hexdigest(),
                    step07_validator=digest(Path(__file__).with_name('step07_verify.py')),
                    step07_adapter=digest(Path(__file__).with_name('step07_adapter.py')))

    def execute(self, project, stage, directory, previous):
        directory = Path(directory)
        if os.name == 'nt' and not str(directory).isascii():
            # Abaqus 2020 launcher can fail before Python starts in a Unicode cwd.
            scratch_root = Path(self.environment.get('BATCHRUNNER_SCRATCH', tempfile.gettempdir())).resolve()
            if not str(scratch_root).isascii():
                raise ValueError('Configure BATCHRUNNER_SCRATCH to an ASCII directory for this Abaqus launcher')
            scratch_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='cadtocae-', dir=scratch_root) as scratch:
                try:
                    result = self._execute(project, stage, Path(scratch), previous)
                finally:
                    shutil.copytree(scratch, directory, dirs_exist_ok=True)
                result['checkpoint'] = str(directory/'checkpoint.cae')
                result['artifacts'] = {str(directory/Path(p).relative_to(scratch)): h for p,h in result.get('artifacts', {}).items()}
                result['unicode_staging'] = True
                return result
        return self._execute(project, stage, directory, previous)

    def _execute(self, project, stage, directory, previous):
        source_bytes = Path(stage.script).read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        if source_hash != getattr(stage, 'expected_source_sha256', source_hash):
            raise RuntimeError('Source changed before snapshot: '+stage.script)
        (directory/'source_snapshot.py').write_bytes(source_bytes)
        source = source_bytes.decode('utf-8-sig')
        from .matching import bind_reads
        source = bind_reads(source, stage.contract.get('read_bindings', []))
        if stage.contract.get('step07'):
            from .step07_adapter import adapt_inplace
            source = adapt_inplace(source)
        else:
            source = adapt(source, stage.contract.get('integrated_hole_report', False))
        (directory/'stage.py').write_text(source, encoding='utf-8')
        for item in stage.inputs:
            if item['role'] == 'runtime' and item['found']:
                dest = directory/item['relative']
                if dest.name in ('stage.py', 'worker.py', 'job.json', 'checkpoint.cae', 'receipt.json', 'runtime_report.json'):
                    raise ValueError('Reserved runtime input filename: ' + dest.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                before = digest(item['path'])
                shutil.copy2(item['path'], dest)
                if digest(dest) != before or digest(item['path']) != before:
                    raise RuntimeError('Input changed while snapshotting: ' + item['path'])
        (directory/'input_bindings.json').write_text(json.dumps([dict(source=i['path'], snapshot=i['relative'], sha256=digest(directory/i['relative'])) for i in stage.inputs if i['role']=='runtime' and i['found']], ensure_ascii=False, indent=2), encoding='utf-8')
        previous_copy = None
        if previous:
            previous_copy = 'upstream.cae'
            shutil.copy2(previous, directory/previous_copy)
        token = uuid.uuid4().hex
        (directory/'job.json').write_text(json.dumps(dict(token=token, previous=previous_copy, contract=stage.contract)), encoding='ascii')
        (directory/'worker.py').write_text(cae_worker_source(), encoding='utf-8')
        shutil.copy2(Path(__file__).with_name('step07_verify.py'), directory/'step07_verify.py')
        execution_files = dict(source_path=stage.script, source_sha256=source_hash, runtime_path=str(directory/'stage.py'), runtime_sha256=digest(directory/'stage.py'), wrapper_path=str(directory/'worker.py'), wrapper_sha256=digest(directory/'worker.py'))
        (directory/'execution_files.json').write_text(json.dumps(execution_files, indent=2), encoding='utf-8')
        command = self.command + ['cae', 'noGUI=worker.py']
        launcher = shutil.which(command[0]) or command[0]
        command[0] = launcher
        # Windows batch launchers require cmd.exe. Reject shell metacharacters rather than interpolating them.
        if os.name == 'nt' and str(launcher).lower().endswith(('.bat', '.cmd')):
            if any(any(c in arg for c in '&|<>^%!\r\n') for arg in command):
                raise ValueError('Unsafe cmd.exe metacharacter in Abaqus command')
            command = subprocess.list2cmdline([os.environ.get('COMSPEC', 'cmd.exe')]) + ' /d /s /c "' + subprocess.list2cmdline(command) + '"'
        env = os.environ.copy()
        env.update(self.environment)
        (directory/'command.json').write_text(json.dumps(command, ensure_ascii=False, indent=2), encoding='utf-8')
        with (directory/'stdout.log').open('wb') as out, (directory/'stderr.log').open('wb') as err:
            process = subprocess.Popen(command, cwd=directory, env=env, stdout=out, stderr=err,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            code = process.wait()  # safe stop is handled at stage boundaries, never kill during save
        result = dict(returncode=code, command=command, execution_files=execution_files)
        if digest(directory/'stage.py') != execution_files['runtime_sha256']:
            raise RuntimeError('Execution script changed during execution')
        (directory/'process.json').write_text(json.dumps(result), encoding='utf-8')
        if code != 0:
            raise RuntimeError('Abaqus exited with code %d; see %s' % (code, directory))
        receipt = directory/'receipt.json'
        if not receipt.is_file():
            error_file = directory/'worker_error.txt'
            detail = error_file.read_text(encoding='utf-8', errors='replace').strip() if error_file.is_file() else 'No fresh worker receipt; inspect stdout.log / stderr.log'
            raise RuntimeError(detail)
        evidence = json.loads(receipt.read_text(encoding='utf-8'))
        if evidence.get('token') != token or evidence.get('status') != 'SUCCESS' or evidence.get('model') != project.prefix:
            raise RuntimeError('Worker receipt identity/status mismatch')
        checkpoint = directory/'checkpoint.cae'
        if not checkpoint.is_file() or checkpoint.stat().st_size == 0:
            raise RuntimeError('Missing or empty CAE checkpoint')
        artifacts = {str(receipt): digest(receipt)}
        for filename in ('execution_files.json', 'source_snapshot.py', 'stage.py', 'worker.py', 'step07_verify.py'):
            artifacts[str(directory/filename)] = digest(directory/filename)
        report_path = directory/'runtime_report.json'
        for name in stage.contract.get('outputs', []):
            output = directory/name
            if not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError('Missing required output: ' + str(output))
            artifacts[str(output)] = digest(output)
        if stage.contract['kind'] in ('report', 'assembly'):
            artifacts[str(report_path)] = digest(report_path)
        result.update(checkpoint=str(checkpoint), evidence=evidence, artifacts=artifacts)
        return result

