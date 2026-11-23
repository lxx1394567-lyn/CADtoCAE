"""Project identity from assembly metadata, explicit CAE association, no Abaqus launch."""
import json
from pathlib import Path

def scan_inplace(folder):
    root=Path(folder).resolve();result=[]
    for summary in root.rglob('*_assembly_summary.json'):
        if any(x in ('Step07_Results','Step07_Archive','Archive','Step07_Logs','.git') for x in summary.relative_to(root).parts):continue
        s=json.loads(summary.read_text(encoding='utf-8-sig'));project=s['project_id']
        if s['model_name']!=project:raise ValueError('SUMMARY_PROJECT_MODEL_CONFLICT: '+str(summary))
        holes=summary.parent/(project+'_step06_hole_report.json')
        ready=holes.exists()
        if ready:
            h=json.loads(holes.read_text(encoding='utf-8-sig'));ready=h.get('project_id')==project and h.get('status')=='SUCCESS'
        candidates=[]
        for parent in [summary.parent,summary.parent/'CAE_Results']:
            if parent.is_dir():candidates += [str(p.resolve()) for p in parent.glob('*.cae') if '_step07_' not in p.name.lower() and not any(x in p.stem.lower() for x in ('backup','snapshot','verify','input_copy'))]
        candidates=sorted(set(candidates),key=lambda x:(Path(x).stem!=project,x))
        chosen=None;method='REQUIRES_EXPLICIT_SELECTION'
        association=root/(project+'_step07_cae.json')
        if association.exists():
            a=json.loads(association.read_text(encoding='utf-8-sig'))
            if a.get('project_id')==project and a.get('target_model')==project and Path(a.get('cae_path','')).is_file():chosen=a['cae_path'];method='EXPLICIT_ASSOCIATION'
        if chosen is None and len(candidates)==1 and Path(candidates[0]).stem==project:chosen=candidates[0];method='EXACT_PROJECT_FILENAME'
        result.append(dict(project=project,summary=str(summary),holes=str(holes),ready=ready,candidates=candidates,cae=chosen,association=method,model=project,internal_validation='CURRENT_MDB_RUNTIME_REQUIRED'))
    if len({r['project'] for r in result})!=len(result):raise ValueError('DUPLICATE_PROJECT_SUMMARIES: choose a narrower work folder')
    return result
