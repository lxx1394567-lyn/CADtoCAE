"""Versioned six-stage chain; legacy generators remain available."""
import json,hashlib,re,copy,shutil
from pathlib import Path
from .step07_rules import STAGE1_STEPS
from .step07_mesh_rules import MESH_RULES
from .runtime_compatibility import assert_runtime_compatible
from .step07_runtime_bundle import bundle_runtime
STAGES={1:'tie',2:'step',3:'bc',4:'mesh',5:'load',6:'inp'}
RUNTIMES=['hole_transforms.py','step07_runtime.py','step07_tie_runtime.py','step07_bc_runtime.py','step07_mesh_runtime.py','step07_quality_runtime.py','step07_mesh_cleanup_runtime.py','step07_source_guard_runtime.py','step07_pipeline_runtime.py']

def generate_pipeline(summary_path,input_cae,output_dir,hole_report_path,stage=0,predecessor_report=None):
    summary=json.loads(Path(summary_path).read_text(encoding='utf-8-sig'));project=summary['project_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',project) or summary['model_name']!=project:raise ValueError('PROJECT_IDENTITY_INVALID')
    source=Path(input_cae).resolve(strict=True);out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    cae=out/'CAE_Results';cae.mkdir(exist_ok=True)
    if cae.is_symlink():raise ValueError('REDIRECTED_OUTPUT')
    holes=json.loads(Path(hole_report_path).read_text(encoding='utf-8-sig'))
    if holes.get('project_id')!=project or holes.get('status')!='SUCCESS':raise ValueError('HOLE_REPORT_INVALID')
    if stage not in (0,1,2,3,4,5,6):raise ValueError('INVALID_STAGE')
    predecessor=None
    tail=stage==0 and bool(predecessor_report)
    if tail:
        previous=json.loads(Path(predecessor_report).read_text(encoding='utf-8-sig'))
        stage=previous.get('stage',0)+1
        if stage not in (2,3,4,5,6):raise ValueError('INVALID_TAIL_PREDECESSOR')
    if stage>1:
        if not predecessor_report:raise ValueError('EXPLICIT_PREDECESSOR_REPORT_REQUIRED')
        predecessor=Path(predecessor_report).resolve(strict=True)
        previous=json.loads(predecessor.read_text(encoding='utf-8-sig'))
        if previous.get('stage')!=stage-1 or previous.get('status')!='SUCCESS' or previous.get('project_id')!=project:raise ValueError('PREDECESSOR_NOT_SUCCESS')
        if Path(previous['output_cae']).resolve()!=source or previous['output_sha256']!=hashlib.sha256(source.read_bytes()).hexdigest():raise ValueError('PREDECESSOR_HASH_MISMATCH')
    occupied_versions=[int(match.group(1)) for folder in (out,cae) for path in folder.glob(project+'_step07_*') for match in [re.search(r'_v(\d+)(?:[_.]|$)',path.name)] if match]
    first_version=max(occupied_versions)+1 if occupied_versions else 1
    for v in range(first_version,10000):
        suffix='' if v==1 else '_v'+str(v);bundle=out/(project+'_step07_pipeline'+suffix+'.json')
        numbers=list(range(stage,7)) if tail else (list(STAGES) if stage==0 else [stage])
        stems={n:project+'_step07_%02d_'%n+STAGES[n]+suffix for n in numbers}
        paths=[bundle]
        for stem in stems.values():paths += [out/(stem+'.py'),out/(stem+'_report.json'),out/(stem+'.log'),cae/(stem+'.cae'),cae/(stem+'_input_copy.cae'),out/(stem+'.inp')]
        if any(p.exists() for p in paths):continue
        break
    else:raise ValueError('VERSION_LIMIT')
    rules=copy.deepcopy(MESH_RULES)
    rules['hoop_quality_repair_sizes'] += [.0035,.003,.0025,.002]
    rules['tie_local_repair_reason']='After isolated Tie footprint partition: retry only failed tetrahedron neighborhood; nominal role sizes unchanged'
    base=Path(__file__).parent;runtime,bundle_audit=bundle_runtime([(name,(base/name).read_text(encoding='utf-8-sig')) for name in RUNTIMES])
    runtime_hash=hashlib.sha256(runtime.encode()).hexdigest();plans=[]
    for n in numbers:
        stem=stems[n];c=dict(schema='step07-chain-2',abaqus_command=shutil.which('abaqus') or '',stage=n,project_id=project,model_name=project,assembly_summary=summary,summary=summary,
            input_cae=str(source),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest() if not plans else None,
            predecessor_report=str(predecessor) if predecessor else None,output_cae=str(cae/(stem+'.cae')),
            diagnostic_cae=str(cae/(stem+'_REVIEW_ONLY.cae')),verify_cae=str(cae/(stem+'_verify_copy.cae')),scratch_cae=str(cae/(stem+'_input_copy.cae')),report_path=str(out/(stem+'_report.json')),log_path=str(out/(stem+'.log')),
            script=str(out/(stem+'.py')),output_dir=str(out),steps=STAGE1_STEPS,groups=['P01','P02','P03','P04'],geometry_tolerance_m=2e-6,
            tie_boundary_simplification=True,load_input_path=str(out/(project+'_step07_loads.json')),mesh_rules=rules,hole_report=holes,comparison_baseline={},job_name=stem,inp_path=str(out/(stem+'.inp')),runtime_sha256=runtime_hash,runtime_bundle_audit=bundle_audit)
        code=runtime+'\nPIPELINE_PLAN=json.loads(%r)\nif __name__ == "__main__":\n    p7_run(PIPELINE_PLAN)\n'%json.dumps(c,ensure_ascii=True)
        assert_runtime_compatible(code)
        with Path(c['script']).open('x',encoding='utf-8') as f:f.write(code)
        plans.append(c);source=Path(c['output_cae']);predecessor=Path(c['report_path'])
    result=dict(schema='step07-chain-2',project_id=project,stages=plans,manifest=str(bundle),runtime_sha256=runtime_hash,runtime_bundle_audit=bundle_audit,
        step06_execution=dict(run=['hole_setup.py'],generate_but_do_not_run=['connector_setup.py','hoop_brace_connector_setup.py'],other_connection_scripts='Do not execute; reject Step06 connection objects at stage 01'),loads_applied=False)
    with bundle.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    return result

