"""Optional Step06 hole-only dispatch. Existing full mode remains the default."""
import json
import ast
import re
import hashlib
from pathlib import Path
from .hole_setup import script_source


def connection_mode(folder, project):
    path=Path(folder)/(project+'_step06_execution.json')
    data=json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    if data and data.get('project_id')!=project:raise ValueError('Execution configuration project mismatch')
    mode=data.get('connection_mode','full')
    if mode not in ('full','tie_only'):raise ValueError('Unsupported connection_mode: '+str(mode))
    return mode


def write_tie_only(holes, folder):
    folder=Path(folder);project=holes['project_id']
    for version in range(1,10000):
        suffix='' if version==1 else '_v'+str(version)
        stem=project+'_step06_tie_only'+suffix
        paths=dict(plan=folder/(stem+'_plan.json'),script=folder/(stem+'_hole_setup.py'))
        report=folder/(stem+'_hole_report.json')
        if any(p.exists() for p in list(paths.values())+[report]):continue
        plan=dict(holes,connection_mode='tie_only')
        existing=folder/(project+'_step06_hole_setup.py')
        if existing.exists():
            original=existing.read_text(encoding='utf-8-sig')
            tree=ast.parse(original);saved=None
            for node in tree.body:
                if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PLAN' for t in node.targets):
                    saved=json.loads(ast.literal_eval(node.value.args[0]))
            def clean(value):return {k:v for k,v in value.items() if k not in ('generator_version','step06_version','connection_mode')}
            if saved is None or clean(saved)!=clean(holes):raise ValueError('Existing hole script PLAN differs; regenerate it with current Step06 before tie_only')
            marker=re.search(r"^if __name__\s*==\s*'__main__':",original,re.M)
            if not marker:raise ValueError('Unknown hole script entry')
            head=original[:marker.start()]
            entry='execute_step06_with_hoop' if 'def execute_step06_with_hoop(' in head else 'execute_step06_a'
            source=head+'\nPLAN=json.loads(%r)\nREPORT_PATH=%r\n'%(json.dumps(plan,ensure_ascii=True),str(report))
            source+="if __name__ == '__main__':\n    from abaqus import mdb\n    %s(PLAN,mdb,REPORT_PATH,%r)\n"%(entry,hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest())
        else:
            source=script_source(plan,report)
        marker="if __name__ == '__main__':"
        guard="""def _tie_only_guard(mdb):
    model=mdb.models[str(PLAN['project_id'])]
    a=model.rootAssembly
    for repo in (model.constraints,a.features,a.sets,a.surfaces):
        if any([str(n).startswith(('STEP06_RP_','STEP06_COUPLING_','STEP06_WIRE_')) for n in repo.keys()]):
            raise ValueError('TIE_ONLY_REQUIRES_FRESH_MODEL_WITHOUT_STEP06_CONNECTIONS')
    for s in model.sections.values():
        if type(s).__name__=='ConnectorSection':
            raise ValueError('TIE_ONLY_CONNECTOR_SECTION_PRESENT')
"""
        source=source.replace(marker,guard+'\n'+marker)
        source=source.replace('    from abaqus import mdb\n','    from abaqus import mdb\n    _tie_only_guard(mdb)\n')
        with paths['script'].open('x',encoding='utf-8') as f:f.write(source)
        with paths['plan'].open('x',encoding='utf-8') as f:json.dump(plan,f,indent=2)
        return paths
    raise ValueError('Output versions exhausted')
