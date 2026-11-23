"""Fixed-name publication journal. Only managed CAE_Results files can be retired."""
import json
import re
import os
import shutil
import uuid
from pathlib import Path
from contextlib import contextmanager, nullcontext
from .executor import digest
from .state import write_json


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def store(root, key):
    if not key or not re.fullmatch(r'[A-Za-z0-9_-]+', key):
        raise ValueError('Unsafe project key')
    return Path(root).resolve()/'.batchrunner'/'deliveries'/key


def safe_result(root, path):
    folder = Path(root).resolve()/'CAE_Results'
    path = Path(path)
    if folder.is_symlink() or path.is_symlink() or path.resolve().parent != folder:
        raise ValueError('Delivery path must be a direct, non-symlink CAE_Results file')
    return path


@contextmanager
def publication_lock(root):
    folder = Path(root).resolve()/'.batchrunner'
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder/'delivery.lock'
    try:
        handle = lock.open('x')
    except FileExistsError:
        raise RuntimeError('Delivery lock exists. Check active processes before recovering: '+str(lock))
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def registry(root, key):
    base = store(root, key)
    old = read(base/'current.json')
    pending = read(base/'pending.json')
    # Read-only recovery view: replacement is atomic; never infer by file date.
    if pending:
        target = safe_result(root, pending['delivery']['path'])
        if target.is_file() and digest(target) == pending['delivery']['sha256']:
            return pending['registry']
    return old


def finish(root, base, pending):
    write_json(base/'current.json', pending['registry'])
    for old in pending.get('retire', []):
        path = safe_result(root, old['path'])
        if path.is_file():
            if digest(path) != old['sha256']:
                raise RuntimeError('Managed partial CAE changed; not archived: '+str(path))
            dest = Path(pending['archive'])/path.name
            if dest.exists():
                raise RuntimeError('Archive collision: '+str(dest))
            path.replace(dest)
    write_json(Path(pending['archive'])/'publication.json', pending)
    (base/'pending.json').unlink(missing_ok=True)


def recover(root, key, replacement=None):
    """Caller holds publication lock; failed/unfinished candidates stay internal."""
    base = store(root, key)
    pending = read(base/'pending.json')
    if pending:
        target = safe_result(root, pending['delivery']['path'])
        if target.is_file() and digest(target) == pending['delivery']['sha256']:
            finish(root, base, pending)
        else:
            old = pending.get('old_sha256')
            if (target.exists() and digest(target) != old) or (not target.exists() and old):
                registered = read(base/'current.json')
                managed = any(isinstance(d, dict) and d.get('path') == str(target) for d in registered.values())
                if not (replacement and replacement.get('status') == 'PASSED' and replacement.get('path') == str(target) and managed):
                    raise RuntimeError('Interrupted delivery target changed externally; manual review required')
                # A fresh validated replacement may supersede an interrupted
                # transaction for this same managed file, after preserving its bytes.
                recovery = base/'archive'/('superseded-'+uuid.uuid4().hex)
                recovery.mkdir(parents=True)
                actual = digest(target) if target.is_file() else None
                if actual:
                    shutil.copy2(target, recovery/target.name)
                    if digest(recovery/target.name) != actual or digest(target) != actual:
                        raise RuntimeError('Externally changed delivery changed during backup')
                write_json(recovery/'superseded_pending.json', dict(pending=pending, preserved_sha256=actual, reason='Fresh verified candidate supersedes interrupted managed publication'))
                (base/'pending.json').unlink()
                return
            write_json(Path(pending['archive'])/'aborted.json', pending)
            (base/'pending.json').unlink()


def publish(root, key, result, candidate, locked=False):
    if result.get('status') != 'PASSED' or digest(candidate) != result['sha256']:
        raise ValueError('Unverified candidate cannot be published')
    base = store(root, key)
    with (nullcontext() if locked else publication_lock(root)):
        recover(root, key, result)
        old = registry(root, key)
        target = safe_result(root, result['path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        previous = next((d for d in old.values() if isinstance(d, dict) and d.get('path') == str(target)), None)
        if target.exists() and not previous:
            raise RuntimeError('Existing CAE is unmanaged. Review/confirm migration first: '+str(target))
        archive = base/'archive'/uuid.uuid4().hex
        archive.mkdir(parents=True)
        old_sha = digest(target) if target.exists() else None
        if target.exists():
            shutil.copy2(target, archive/target.name)
            if digest(archive/target.name) != old_sha or digest(target) != old_sha:
                raise RuntimeError('Existing delivery changed during backup')
        result['published'] = True
        updated = dict(old)
        retire = []
        if result['stage'] == 9:
            updated['final'] = dict(result)
            if updated.get('partial'):
                retire.append(updated.pop('partial'))
        else:
            if updated.get('partial') and updated['partial']['path'] != str(target):
                retire.append(updated['partial'])
            updated['partial'] = dict(result)
        pending = dict(delivery=dict(result), registry=updated, retire=retire,
                       old_sha256=old_sha, archive=str(archive), candidate=str(candidate))
        write_json(base/'pending.json', pending)
        try:
            # Same volume: internal candidate and output share the selected root.
            # Windows sharing violations leave the old destination intact.
            if old_sha != result['sha256']:
                os.replace(candidate, target)
        except OSError as exc:
            result['published'] = False
            raise RuntimeError('CAE replacement failed; old delivery retained. Close Abaqus/file handles and retry: '+str(exc))
        try:
            finish(root, base, pending)
        except Exception as exc:
            # Durable validated pending record supports recovery after publication.
            result['warning'] = 'Published; internal journal/partial archive cleanup pending: '+str(exc)
        return result
