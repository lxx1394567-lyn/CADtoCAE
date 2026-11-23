"""Explicitly confirmed legacy migration; plan contains immutable file hashes."""
import json
import shutil
import uuid
from pathlib import Path
from .executor import digest
from .publication import read, store, safe_result, publication_lock, publish, registry
from .state import write_json


def plan_migration(root):
    root = Path(root).resolve()
    files = []
    records = []
    for path in (root/'.batchrunner').rglob('record.json'):
        record = read(path)
        delivery = record.get('delivery', {})
        if delivery.get('status') == 'PASSED' and delivery.get('stage') == 9 and len(record.get('stages', [])) == 9 and all(s.get('status') == 'SUCCESS' for s in record['stages']):
            records.append((path, record))
    folder = root/'CAE_Results'
    for path in sorted(folder.glob('*')):
        safe_result(root, path)
        if not path.is_file() or not (path.suffix.lower() == '.cae' or path.name.endswith('.delivery.json')):
            continue
        sha = digest(path)
        evidence = read(path.with_suffix('.delivery.json')) if path.suffix.lower()=='.cae' else read(path)
        matches = [(str(p), r) for p,r in records if r['delivery'].get('path') == str(path) and r['delivery'].get('sha256') == sha]
        files.append(dict(path=str(path), sha256=sha, bytes=path.stat().st_size,
                          validation=evidence.get('status', 'NO_SIDECAR'), records=[p for p,r in matches], action='ARCHIVE'))
    selected = {}
    for file in files:
        for record_path in file['records']:
            r=read(record_path);d=r['delivery']
            # Matching run receipt is required; sidecars alone never determine newest.
            if d.get('verification', {}).get('status') != 'PASSED' or not r.get('ended'):
                continue
            key=r['key']; prior=selected.get(key)
            if not prior or r['ended'] > prior['ended']:
                selected[key]=dict(prefix=r['prefix'], path=file['path'], sha256=file['sha256'],
                                   record=record_path, record_sha256=digest(record_path), ended=r['ended'])
            elif r['ended']==prior['ended'] and file['sha256'] != prior['sha256']:
                raise ValueError('Conflicting successful run records require manual resolution')
    for key, item in selected.items():
        item['target']=str(folder/(item['prefix']+'_final.cae'))
        safe_result(root,item['target'])
    # Unknown files remain untouched; only names linked to a known project are proposed.
    for file in files:
        name=Path(file['path']).name
        if not any(name.startswith(s['prefix']+'_final') or name.startswith(s['prefix']+'_step') for s in selected.values()):
            file['action']='LEAVE_UNRECOGNIZED'
    plan=dict(root=str(root), id=uuid.uuid4().hex, files=files, selected=selected, status='AWAITING_CONFIRMATION')
    destination=root/'.batchrunner'/'migration'/plan['id']/'plan.json'
    write_json(destination,plan)
    return destination,plan


def apply_migration(plan_path, executor, confirmed=False):
    if not confirmed:
        raise ValueError('User confirmation of the file inventory is required')
    plan_path=Path(plan_path).resolve();plan=read(plan_path);root=Path(plan['root']).resolve()
    if plan_path.parent.parent != root/'.batchrunner'/'migration':
        raise ValueError('Migration plan must be inside the project internal migration directory')
    if read(plan_path.with_name('completed.json')):
        return read(plan_path.with_name('completed.json'))
    from .dependencies import check
    from .scanner import scan
    from .delivery import expected, verify_file
    projects={p.key:check(p) for p in scan(root,[root/'.batchrunner'])}
    prepared=[]
    archive=plan_path.parent/'archive'
    def located(file):
        original=safe_result(root,file['path'])
        if original.is_file() and digest(original)==file['sha256']:
            return original
        archived=archive/original.name
        if archived.is_file() and digest(archived)==file['sha256']:
            return archived
        raise ValueError('Inventory changed; review required: '+str(original))
    # Verify every candidate before any user file is moved or replaced.
    for key,item in plan['selected'].items():
        if digest(item['record']) != item['record_sha256'] or digest(located(item)) != item['sha256']:
            raise ValueError('Migration source/record changed; create a new inventory')
        record=read(item['record']);job,unsupported=expected(projects[key],record['stages'])
        if unsupported:
            raise ValueError('; '.join(unsupported))
        work=plan_path.parent/key;work.mkdir(exist_ok=True)
        candidate=work/'candidate.cae';shutil.copy2(located(item),candidate)
        job['path']=str(candidate)
        evidence=verify_file(executor,job,work/'verification')
        if evidence['status'] != 'PASSED' or digest(candidate)!=item['sha256']:
            raise ValueError('Migration candidate failed independent verification: '+str(evidence.get('error')))
        expected(projects[key],record['stages'])
        delivery=dict(record['delivery'],path=item['target'],verification=evidence,published=False,logs=str(work))
        prepared.append((key,item,candidate,delivery))
    with publication_lock(root):
        for file in plan['files']:
            path=safe_result(root,file['path'])
            promoted = any(item['target']==str(path) and registry(root,key).get('final', {}).get('sha256')==item['sha256'] and path.is_file() and digest(path)==item['sha256'] for key,item in plan['selected'].items())
            if not promoted:
                located(file)
        for key,item,candidate,delivery in prepared:
            target=safe_result(root,item['target'])
            if target.exists():
                # Explicit migration consent authorizes backup/replacement of this listed legacy target.
                if not any(f['path']==str(target) for f in plan['files']):
                    raise ValueError('Unlisted existing target')
                write_json(store(root,key)/'current.json',dict(final=dict(path=str(target),sha256=digest(target),status='NOT_VERIFIED',stage=9)))
            publish(root,key,delivery,candidate,locked=True)
        archive.mkdir(exist_ok=True)
        targets={item['target'] for item in plan['selected'].values()}
        moved=[]
        for file in plan['files']:
            if file['action']=='LEAVE_UNRECOGNIZED' or file['path'] in targets:
                continue
            src=safe_result(root,file['path']);dest=archive/src.name
            if not src.exists() and dest.is_file() and digest(dest)==file['sha256']:
                moved.append(dict(source=str(src),archive=str(dest),sha256=file['sha256']))
                continue
            if dest.exists():
                raise ValueError('Archive destination exists')
            src.replace(dest)
            moved.append(dict(source=str(src),archive=str(dest),sha256=file['sha256']))
            write_json(plan_path.with_name('progress.json'),dict(moved=moved))
        result=dict(status='COMPLETED',deliveries=[d for k,i,c,d in prepared],moved=moved)
        write_json(plan_path.with_name('completed.json'),result)
    return result
