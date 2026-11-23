# -*- coding: utf-8 -*-
"""Read-only current-model identity and upstream hole feature checks."""
def s8_holes(m,c):
    h=c['hole_report'];required=[]
    for group in ('purlin_local','inclined_beam'):
        for item in h.get(group,[]):
            required.append((str(item['target_instance']),str(item.get('created_feature',item.get('feature_name')))))
    for item in h.get('hoop_validation',{}).get('parts',[]):
        for inherited in item.get('instance_inheritance',[]):
            for name in inherited.get('feature_names',[]):required.append((str(inherited['instance_name']),str(name)))
    support=h.get('support',{})
    if support.get('created_holes',0)>=2:
        for row in c['summary']['instances']:
            if row['canonical_role']=='PURLIN_SUPPORT':
                for feature in ('STEP06_HOLE_PS_TO_BEAM','STEP06_HOLE_PS_TO_PURLIN'):required.append((str(row['instance_name']),feature))
    checked=[]
    for instance,name in sorted(set(required)):
        p=m.parts[m.rootAssembly.instances[instance].partName]
        if name not in p.features or p.features[name].isSuppressed():raise ValueError('INPUT_HOLE_REPORT_MISMATCH: '+instance+' missing/disabled '+name+'; open the manually verified hole-complete model')
        checked.append(dict(instance=instance,part=p.name,feature=name))
    if not checked:raise ValueError('HOLE_FEATURE_EVIDENCE_UNAVAILABLE: cannot verify supplied hole report')
    return dict(status='PASS',checked_features=checked)

def u7_run(c):
    folder=str(c['logs_dir'])
    if not os.path.isdir(folder):os.makedirs(folder)
    path=os.path.join(folder,str(c['project_id'])+'.running.lock')
    try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except OSError:raise ValueError('PROJECT_RUNNING_OR_STALE_LOCK: '+path+'; inspect active process before clearing stale lock')
    os.write(fd,json.dumps(dict(pid=os.getpid(),operation='ABAQUS_STAGE',stage=c['stage'])).encode('utf-8'));os.close(fd)
    try:return u7_execute(c)
    finally:os.remove(path)
