# -*- coding: utf-8 -*-
"""Source observations and isolation when the selected CAE is the active MDB."""
def sg_stamp(path):
    p=os.path.realpath(os.path.abspath(str(path)));s=os.stat(p)
    return dict(path=p,sha256=p7_hash(p),size=s.st_size,mtime_seconds=s.st_mtime,mtime_ns=getattr(s,'st_mtime_ns',None),mtime_precision='native nanoseconds' if hasattr(s,'st_mtime_ns') else 'Python 2.7 float seconds; nanoseconds unavailable')

def sg_mark(c,r,stage):
    import abaqus
    sample=sg_stamp(c['input_cae']);sample.update(stage=stage,mdb_path=str(abaqus.mdb.pathName))
    r.setdefault('source_audit',[]).append(sample)
    print('SOURCE_AUDIT '+json.dumps(sample,sort_keys=True))
    if sample['sha256']!=r['input_sha256']:
        r['source_changed_at']=stage
        raise ValueError('SOURCE_CHANGED_AT: '+stage)
    snapshot=c['scratch_cae']+'_snapshot.cae'
    if os.path.isfile(str(snapshot)) and p7_hash(snapshot)!=r['input_sha256']:raise ValueError('INPUT_SNAPSHOT_CHANGED_AT: '+stage)

def sg_dispatch(c,digest):
    import abaqus,subprocess
    active=os.path.normcase(os.path.realpath(os.path.abspath(str(abaqus.mdb.pathName))))
    source=os.path.normcase(os.path.realpath(os.path.abspath(str(c['input_cae']))))
    if active!=source:return None
    if os.environ.get('STEP07_SOURCE_WORKER')=='1':raise ValueError('ISOLATED_WORKER_UNEXPECTEDLY_HAS_SOURCE_OPEN')
    command=str(c.get('abaqus_command',''))
    if not command or not os.path.isfile(command):raise ValueError('SOURCE_IS_CURRENT_MDB: isolated Abaqus command unavailable; save session and run script in a separate Abaqus process')
    path=str(c['script'])+'_session_guard.json';console=str(c['script'])+'_worker_console.log'
    if os.path.exists(path) or os.path.exists(console):raise ValueError('SESSION_GUARD_EXISTS: regenerate script version')
    audit=dict(mode='ISOLATED_PROCESS_SOURCE_ACTIVE',before=sg_stamp(c['input_cae']),parent_mdb=str(abaqus.mdb.pathName),parent_pid=os.getpid(),status='RUNNING')
    env=os.environ.copy();env['STEP07_SOURCE_WORKER']='1'
    with open(path,'w') as f:json.dump(audit,f,indent=2)
    print('Input is current MDB; preserving this session and running protected copy in a separate Abaqus process.')
    with open(console,'w') as f:
        code=subprocess.call([command,'cae','noGUI='+str(c['script'])],cwd=str(c['output_dir']),env=env,stdout=f,stderr=subprocess.STDOUT)
    audit.update(after=sg_stamp(c['input_cae']),returncode=code,parent_mdb_after=str(abaqus.mdb.pathName))
    audit['status']='PASS' if audit['after']['sha256']==digest and audit['parent_mdb_after']==audit['parent_mdb'] else 'FAILED_SOURCE_OR_SESSION_CHANGED'
    with open(path,'w') as f:json.dump(audit,f,indent=2)
    if audit['status']!='PASS':
        if os.path.isfile(str(c['report_path'])):
            with open(str(c['report_path'])) as f:failed=json.load(f)
            failed.update(worker_status=failed.get('status'),status='FAILED',next_stage_allowed=False,source_changed_at='parent_after_worker',session_guard=path)
            with open(str(c['report_path']),'w') as f:json.dump(failed,f,indent=2)
        raise ValueError('SOURCE_CHANGED_DURING_ISOLATED_WORKER: '+path)
    if not os.path.isfile(str(c['report_path'])):raise RuntimeError('ISOLATED_WORKER_NO_REPORT: '+console)
    with open(str(c['report_path'])) as f:r=json.load(f)
    if r.get('status') not in ('SUCCESS','REVIEW_REQUIRED'):raise RuntimeError('ISOLATED_WORKER_FAILED: '+str(c['report_path']))
    print('ISOLATED WORKER '+r['status']+': '+str(c['report_path']))
    return r
