"""Mesh-stage discovery and generation only. No scheduling or solver calls."""
import copy,json,os,re
from pathlib import Path
from .step07_batch import EXCLUDED,linked
from .step07_mesh_setup import generate_stage3

def scan_mesh_projects(root):
    root=Path(root).resolve(strict=True);rows=[];seen={}
    for folder,dirs,files in os.walk(root,followlinks=False):
        folder=Path(folder);dirs[:]=sorted(d for d in dirs if d.lower() not in EXCLUDED and not d.startswith('.') and not linked(folder/d))
        for filename in sorted(files):
            if not filename.endswith('_assembly_summary.json'):continue
            path=folder/filename
            if linked(path):continue
            row=dict(key=str(path),source_folder=str(folder),files={'summary':str(path)},warnings=[],ready=False,selected=False,status='SKIPPED')
            try:
                s=json.loads(path.read_text(encoding='utf-8-sig'));project=s['project_id'];row['project_id']=project
                if s['model_name']!=project or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',project):raise ValueError('完整项目编号冲突')
                if not s['instances']:raise ValueError('装配实例为空')
                candidates=sorted(p for p in (folder/'CAE_Results').glob(project+'_step07_02*.cae') if re.fullmatch(re.escape(project)+r'_step07_02(?:_v[0-9]+)?\.cae',p.name) and not linked(p))
                row['files']['stage2_candidates']=[str(p) for p in candidates]
                if not candidates:raise ValueError('缺少 Step07-02 CAE')
                row.update(ready=True,selected=True,status='WAITING',reason='发现 %d 个 Stage2 版本；生成时需明确选择已验收文件'%len(candidates))
            except Exception as exc:row.setdefault('project_id',path.stem);row['reason']=str(exc)
            rows.append(row);seen.setdefault(row['project_id'],[]).append(row)
    for group in seen.values():
        if len(group)>1:
            for row in group:row.update(ready=False,selected=False,status='SKIPPED',reason='同一完整项目编号存在多份摘要，需人工消除歧义')
    return dict(stage=3,root=str(root),projects=rows,warnings=[])

def validate_accepted(row,path):
    path=Path(path).resolve(strict=True)
    if not re.fullmatch(re.escape(row['project_id'])+r'_step07_02(?:_v[0-9]+)?\.cae',path.name):raise ValueError('必须选择本项目已验收的 Step07-02 CAE，不接受备份/其他项目')
    if linked(path):raise ValueError('不接受链接 CAE')
    return str(path)

def generate_mesh_projects(scan,accepted,progress=lambda e:None):
    result=copy.deepcopy(scan);result['output_folder']=scan['root'];counts={}
    for row in result['projects']:
        if row['key'] not in accepted:row['status']='SKIPPED';continue
        try:
            source=validate_accepted(row,accepted[row['key']])
            generated=generate_stage3(row['files']['summary'],source,scan['root'])
            row.update(status='GENERATED',reason='PY 已生成，尚未执行；请先打开 session_input 工作副本',script=generated['script'],mesh_plan=generated['plan'])
            progress(dict(log=generated['script']+'\n工作副本：'+generated['plan']['manual_working_copy']))
        except Exception as exc:row.update(status='FAILED',reason=str(exc))
        progress(dict(row=row))
    for row in result['projects']:counts[row['status']]=counts.get(row['status'],0)+1
    result['counts']=counts;return result
