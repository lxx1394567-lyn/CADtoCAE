"""Strict full-project-ID discovery and sequential setup; no solver submission."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import shutil
from datetime import datetime
import uuid
from .step07_desktop import read_json,new_run,execute
from .step07_setup import build_plan,generate_stage1
from .step07_rules import configuration,RULE_VERSION,DEFAULTS,STAGE1_STEPS

EXCLUDED={'step07_results','step07_runs','backup','backups','history','archive','archives',
          'temp','tmp','dist','build','__pycache__'}
SUFFIX='_assembly_summary.json'

def linked(p):
    return p.is_symlink() or bool(getattr(p.lstat(),'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT)

def digest(p):
    before=p.stat(); h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    after=p.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('文件读取期间变化：'+str(p))
    return h.hexdigest()

def required(p):
    if not p.is_file() or linked(p):raise ValueError('缺少普通文件或文件为链接：'+str(p))
    return p

def read_loads(path,summary):
    d=read_json(required(path))
    if d.get('schema_version')!=1 or d.get('project_id')!=summary['project_id']:raise ValueError('荷载接口版本或完整项目编号不匹配')
    if d.get('units')!='m-N-Pa' or d.get('coordinate_system')!='GLOBAL':raise ValueError('荷载必须声明 m-N-Pa 和 GLOBAL 全局坐标')
    if not isinstance(d.get('loads'),list) or not d['loads']:raise ValueError('缺少有效静力荷载，禁止使用验证荷载替代')
    return d['loads']

def choose_cae(folder,project,model,warnings):
    """Select by identity and documented stage, never by modification time."""
    candidates=[]
    for directory,dirs,names in os.walk(folder,followlinks=False):
        directory=Path(directory)
        dirs[:]=sorted(d for d in dirs if d.lower() not in EXCLUDED and not d.startswith(('.', '__')) and not linked(directory/d))
        if directory!=folder and (any(n.endswith(SUFFIX) for n in names) or 'step07_plan.json' in names):
            dirs[:]=[];continue
        for filename in sorted(names):
            if not filename.lower().endswith('.cae'):continue
            stem=Path(filename).stem
            if re.search(r'(?:^|_)(?:step07|backup|test|old|temp|tmp|history)(?:_|$|[.-])',stem,re.I):continue
            p=required(directory/filename)
            manifest=p.with_suffix('.delivery.json')
            source=p.with_suffix('.source.json')
            metadata=manifest if manifest.exists() else source if source.exists() else None
            d=read_json(required(metadata)) if metadata else {}
            identity=d.get('project_id') or d.get('model') or d.get('model_name')
            named=stem==project or stem.startswith(project+'_')
            if identity and identity!=project:
                if named:raise ValueError('CAE 元数据项目编号冲突：'+str(p))
                continue
            if not named and identity!=project:continue
            if d.get('model',d.get('model_name',model))!=model:raise ValueError('CAE 目标模型不匹配：'+str(p))
            stage=d.get('upstream_stage');evidence='metadata' if stage else 'unknown'
            if metadata==manifest:
                if d.get('status')!='PASSED' or d.get('save_status')!='SAVED':raise ValueError('CAE 交付清单状态无效：'+str(manifest))
                if not d.get('sha256'):raise ValueError('交付清单缺少哈希：'+str(manifest))
                if not stage:
                    # BatchRunner stages: 2=assembly, 3=connections, 4/5=Step06.
                    stage={2:'Step04',3:'Step05',4:'Step06',5:'Step06'}.get(d.get('stage'))
                    evidence='BatchRunner delivery stage '+str(d.get('stage'))
            if d.get('sha256') and d['sha256'].lower()!=digest(p):raise ValueError('CAE 与来源记录哈希不符：'+str(p))
            if stage and stage not in ('Step04','Step05','Step06'):raise ValueError('不支持的上游阶段记录：'+str(metadata))
            if not stage:
                match=re.fullmatch(re.escape(project)+r'_step0([456])(?:_.*)?',stem,re.I)
                if match:stage='Step0'+match.group(1);evidence='filename declaration (not engineering verification)'
            candidates.append(dict(path=str(p),metadata=str(metadata) if metadata else None,
                                   stage=stage or 'UNKNOWN',evidence=evidence,sha256=digest(p),
                                   documented=bool(metadata and stage)))
    if not candidates:raise ValueError('已识别项目；缺少完整项目编号匹配的 CAE（可用 .source.json 明确关联其他文件名）')
    documented=[c for c in candidates if c['documented']]
    pool=documented or candidates
    # Without a stage record, multiple files cannot be ranked reliably by filename.
    if documented:
        highest=max(c['stage'] for c in pool);pool=[c for c in pool if c['stage']==highest]
    if len({c['sha256'] for c in pool})>1:
        raise ValueError('CAE 来源歧义；不按修改时间选择：'+' | '.join(c['path'] for c in pool))
    chosen=sorted(pool,key=lambda c:c['path'])[0]
    if len(candidates)>1:warnings.append('多个候选：仅按明确阶段记录优先；同优先级须内容一致。请核对输入路径。')
    warnings.append('输入阶段 '+chosen['stage']+'；DEBUG_MODEL，尚未工程验收。')
    provenance=dict(stage=chosen['stage'],evidence=chosen['evidence'],metadata=chosen['metadata'],
                    input_cae=chosen['path'],sha256=chosen['sha256'],candidates=candidates,
                    model_classification='DEBUG_MODEL',engineering_verified=False)
    return Path(chosen['path']),Path(chosen['metadata']) if chosen['metadata'] else None,provenance


def scan_projects(root,stage=1):
    if stage!=1:raise ValueError("Only Step07-1 is enabled")
    root=Path(root).resolve(strict=True)
    if not root.is_dir() or linked(root):raise ValueError('工作文件夹必须是普通目录')
    result=dict(stage=1,root=str(root),projects=[],warnings=[],rule_version=RULE_VERSION)
    for directory,dirs,names in os.walk(root,followlinks=False):
        folder=Path(directory)
        dirs[:]=sorted(d for d in dirs if d.lower() not in EXCLUDED and not d.startswith(('.', '__')) and not linked(folder/d))
        if 'step07_plan.json' in names or 'desktop_run.json' in names:
            dirs[:]=[];continue
        rows=[]
        for filename in sorted(n for n in names if n.endswith(SUFFIX)):
            row=dict(project_id=filename[:-len(SUFFIX)],source_folder=str(folder),key=str(folder/filename),
                     ready=False,selected=False,status='SKIPPED',reason='',warnings=[],files={},
                     checks=dict(project_identified=False,assembly_complete=False,cae_available=False,stage1_ready=False))
            try:
                summary_path=required(folder/filename);s=read_json(summary_path)
                project=s.get('project_id','');row['project_id']=project
                if not isinstance(project,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',project):raise ValueError('摘要缺少有效完整项目编号')
                row['checks']['project_identified']=True;row['files']['summary']=str(summary_path)
                if not isinstance(s.get('model_name'),str) or not s['model_name']:raise ValueError('Missing target model name')
                instances=s.get('instances')
                if not isinstance(instances,list) or not instances:raise ValueError('摘要缺少装配实例信息')
                identifiers=[i.get('instance_name') for i in instances]
                if any(not isinstance(n,str) or not n for n in identifiers) or len(set(identifiers))!=len(identifiers):raise ValueError('摘要实例名称缺失或重复')
                complete=bool(s.get('structure_type')) and all(i.get('canonical_role') and i.get('part_name') and i.get('placement') for i in instances)
                row['checks']['assembly_complete']=complete
                if not complete:row['warnings'].append('装配角色/定位信息不齐；仅允许 Step07-1 计算步设置。')
                if filename!=project+SUFFIX:row['warnings'].append('摘要文件名与内部编号不同；以内部完整项目编号为准。')
                cae,metadata,upstream=choose_cae(folder,project,s['model_name'],row['warnings'])
                row['files']['cae']=str(cae)
                if metadata:row['files']['source_record']=str(metadata)
                row['hashes']={k:digest(Path(p)) for k,p in row['files'].items()}
                c=dict(stage=1,project_id=project,model_name=s['model_name'],input_cae=str(cae),step=copy.deepcopy(STAGE1_STEPS[0]))
                row['checks'].update(cae_available=True,stage1_ready=True)
                row.update(ready=True,selected=True,status='WAITING',config=c,upstream=upstream,
                           reason='Step07-1 输入齐全；'+upstream['stage']+' / DEBUG_MODEL',structure_type=s.get('structure_type','UNKNOWN'))
            except Exception as exc:row['reason']=str(exc)
            rows.append(row)
        for row in rows:
            if sum(r['project_id']==row['project_id'] for r in rows)>1:
                row.update(ready=False,selected=False,status='SKIPPED',reason='同目录存在重复项目摘要，请明确唯一输入')
                row['checks']['stage1_ready']=False
        result['projects'].extend(rows)
    return result


def run_batch(scan,selected,command='',progress=lambda event:None,mode='generate'):
    if scan.get('stage')!=1:raise ValueError('Only Step07-1 is enabled')
    if mode not in ('generate','automatic'):raise ValueError('Unknown execution mode')
    result=copy.deepcopy(scan)
    result['mode']=mode
    root=Path(scan['root'])
    result['output_folder']=str(root)
    def save_row(row):
        project=row['project_id']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',project):return
        for version in range(1,10000):
            suffix='' if version==1 else '_v'+str(version)
            report=root/(project+'_step07_01_generation'+suffix+'.json')
            try:
                with report.open('x',encoding='utf-8') as f:json.dump(row,f,ensure_ascii=False,indent=2)
                row['generation_report']=str(report);return
            except FileExistsError:continue
        raise ValueError('Too many generation reports')
    # Rescan catches new/removed versions and changed file pairings, not only changed bytes.
    duplicate_ids={r['project_id'] for r in scan['projects'] if sum(x['project_id']==r['project_id'] for x in scan['projects'])>1}
    fresh={r['key']:r for r in scan_projects(scan['root'])['projects']}
    for row in result['projects']:
        if not row['ready'] or row['key'] not in selected:
            row.update(status='SKIPPED',reason=row['reason'] if not row['ready'] else '用户取消');progress(dict(row=row));save_row(row);continue
        row['status']='RUNNING';progress(dict(row=copy.deepcopy(row)))
        try:
            if row['project_id'] in duplicate_ids:raise ValueError('Duplicate project summaries in selected root; resolve before flat output')
            now=fresh.get(row['key'])
            if not now or not now['ready'] or now['files']!=row['files'] or now['hashes']!=row['hashes']:raise ValueError('扫描后输入或版本发生变化，请重新扫描')
            if any(digest(Path(p))!=row['hashes'][k] for k,p in row['files'].items()):raise ValueError('输入文件在运行前发生变化')
            folder=root
            plan=generate_stage1(row['files']['summary'],row['files']['cae'],folder,row['config']['step'],row['upstream'],execution_mode='INDEPENDENT_CAE' if mode=='automatic' else 'CURRENT_SESSION_DEBUG')
            row['script']=str(folder/plan['script_name'])
            row['plan']=plan
            row['output_folder']=str(folder)
            progress(dict(log='项目 '+row['project_id']+'：'+str(folder)))
            if mode=='automatic':
                r=execute(folder,command,'setup',lambda x:progress(dict(log=x)),stage_plan=plan)
                row.update(status='SUCCESS',reason='Step07-1 完成并重开核查通过；等待人工验收，不执行后续阶段',report=r)
            else:
                row.update(status='GENERATED',reason='独立 PY 已生成或复用；请在 ABAQUS/CAE 中运行，尚未生成 CAE')
            progress(dict(log='独立脚本：'+row['script']))
        except Exception as exc:row.update(status='FAILED',reason=str(exc))
        save_row(row);progress(dict(row=copy.deepcopy(row)))
    result['counts']={s:sum(r['status']==s for r in result['projects']) for s in ('GENERATED','SUCCESS','FAILED','SKIPPED')}
    return result
