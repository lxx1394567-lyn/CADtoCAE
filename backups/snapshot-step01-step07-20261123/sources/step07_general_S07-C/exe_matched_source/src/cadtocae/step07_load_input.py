"""Read-only workbook adapter. Formulas are evaluated by a restricted AST, not eval."""
import ast
import hashlib
import json
import math
import re
from pathlib import Path
import openpyxl

BINDINGS={'DP_ANG14_FA03521S-T0104-02':('M07','平塘','双桩双立柱','DP',14.)}

class WorkbookValues:
    def __init__(self,path):
        self.formulas=openpyxl.load_workbook(path,data_only=False)
        self.cached=openpyxl.load_workbook(path,data_only=True)
        self.used={};self.active=set()
    def close(self):
        self.formulas.close();self.cached.close()
    def value(self,sheet,cell):
        cell=cell.replace('$','');key=sheet+'!'+cell
        if key in self.used:return self.used[key]['value']
        if key in self.active:raise ValueError('FORMULA_CYCLE: '+key)
        self.active.add(key);raw=self.formulas[sheet][cell].value;cache=self.cached[sheet][cell].value
        if raw is None:raise ValueError('MISSING_CELL: '+key)
        formula=isinstance(raw,str) and raw.startswith('=')
        if formula:
            refs=[]
            def ref(match):
                refs.append((match.group(1) or sheet,match.group(2)));return 'R'+str(len(refs)-1)
            expression=re.sub(r"(?:'([^']+)'!)?(\$?[A-Z]+\$?\d+)",ref,raw[1:])
            def walk(n):
                if isinstance(n,ast.Constant) and isinstance(n.value,(int,float)):return n.value
                if isinstance(n,ast.Name) and re.fullmatch('R[0-9]+',n.id):return self.value(*refs[int(n.id[1:])])
                if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):return walk(n.operand)*(1 if isinstance(n.op,ast.UAdd) else -1)
                if isinstance(n,ast.BinOp):
                    a,b=walk(n.left),walk(n.right)
                    if isinstance(n.op,ast.Add):return a+b
                    if isinstance(n.op,ast.Sub):return a-b
                    if isinstance(n.op,ast.Mult):return a*b
                    if isinstance(n.op,ast.Div):return a/b
                if isinstance(n,ast.Compare) and len(n.ops)==1:
                    a,b=walk(n.left),walk(n.comparators[0]);op=n.ops[0]
                    if isinstance(op,ast.LtE):return a<=b
                    if isinstance(op,ast.GtE):return a>=b
                    if isinstance(op,ast.Lt):return a<b
                    if isinstance(op,ast.Gt):return a>b
                if isinstance(n,ast.Call) and isinstance(n.func,ast.Name):
                    if n.func.id=='IF' and len(n.args)==3:return walk(n.args[1] if walk(n.args[0]) else n.args[2])
                    if n.func.id=='MAX':return max(walk(a) for a in n.args)
                raise ValueError('UNSUPPORTED_FORMULA: '+key+' '+raw)
            calculated=walk(ast.parse(expression,mode='eval').body)
            if not isinstance(calculated,(int,float)) or not math.isfinite(calculated):raise ValueError('INVALID_FORMULA_RESULT: '+key)
            if cache is not None and (not isinstance(cache,(int,float)) or not math.isclose(cache,calculated,rel_tol=1e-9,abs_tol=1e-9)):raise ValueError('STALE_OR_INVALID_FORMULA_CACHE: '+key)
            value=calculated if cache is None else cache
        else:value=raw
        self.used[key]=dict(source_sheet=sheet,source_cell=cell,formula=raw if formula else None,cached=cache,value=value,method='RECALCULATED_NO_CACHE' if formula and cache is None else ('CACHE_VERIFIED_BY_FORMULA' if formula else 'LITERAL'))
        self.active.remove(key);return value
    def unique_row(self,sheet,column,value):
        rows=[r for r in range(1,self.formulas[sheet].max_row+1) if self.formulas[sheet].cell(r,column).value==value]
        if len(rows)!=1:raise ValueError('MISSING_OR_DUPLICATE_KEY: '+sheet+' '+value)
        return rows[0]

def read_load_cases(workbook,summary,mapping=None):
    from .step07_tributary import tributary_layout
    path=Path(workbook).resolve(strict=True);project=summary['project_id']
    if mapping and mapping.get('mode')=='LUAN_CONFIRMED_POS':
        from .step07_luan_load import read_luan_pos
        return read_luan_pos(workbook,summary,mapping)
    if mapping and mapping.get('mode')=='DEMO_REUSE_M07':
        if mapping.get('confirmed') is not True or mapping.get('project_id')!=project or not mapping.get('source'):raise ValueError('DEMO_REUSE_REQUIRES_EXPLICIT_PROJECT_AUTHORIZATION')
        import copy
        borrowed=copy.deepcopy(summary);borrowed.update(project_id='DP_ANG14_FA03521S-T0104-02',model_name='DP_ANG14_FA03521S-T0104-02',structure_type='DP')
        cases=read_load_cases(workbook,borrowed)
        for d in cases:
            d.update(source_model_id=d['model_id'],source_job_id=d['job_id'],project_id=project,model_id='DEMO_'+summary['structure_type'],job_id='TRIAL_'+d['case_id'],project_site='DEMO_ONLY_USER_AUTHORIZED_REUSE',structure_type=summary['structure_type'],angle_deg=float(mapping['actual_angle_deg']),engineering_status='DEMO_ONLY',demo_authorization=mapping['source'])
            d['warnings'].insert(0,'DEMO_ONLY: borrowed M07 line load AND 3.7m tributary length by user authorization; not Luan design data; actual model normal is used')
        return cases

    if mapping is None:
        if project not in BINDINGS:raise ValueError('PROJECT_MODEL_BINDING_REQUIRED: '+project)
        model,site,kind,structure,angle=BINDINGS[project];layout_data=None
        binding_source='User-confirmed exact project mapping'
    else:
        if mapping.get('confirmed') is not True or not mapping.get('source') or mapping['project_id']!=project:raise ValueError('UNCONFIRMED_PROJECT_MAPPING')
        model=mapping['model_id'];site=mapping['project_site'];structure=mapping['structure_type'];angle=float(mapping['angle_deg']);layout_data=mapping['support_layout'];binding_source=mapping['source']
        kind={'SP_SC':'单桩单立柱','SP_DC':'单桩双立柱','DP':'双桩双立柱'}[structure]
    if model=='M08':raise ValueError('M08_MODEL_MISSING: load catalogue only; no model execution')
    if summary['model_name']!=project or summary['structure_type']!=structure:raise ValueError('SUMMARY_IDENTITY_MISMATCH')
    if not re.fullmatch('M[0-9]+',model):raise ValueError('MODEL_ID_INVALID')
    layout=tributary_layout(project,model,structure,layout_data)
    rows=sorted([r for r in summary['instances'] if r['canonical_role']=='PURLIN_LOCAL'],key=lambda r:r['instance_name'])
    names=[r['instance_name'] for r in rows];groups=[r.get('connection_group') for r in rows]
    if not rows or len(set(names))!=len(rows) or len(set(groups))!=len(rows) or any(not g or not re.fullmatch('[A-Za-z0-9_]+',g) for g in groups):raise ValueError('PURLIN_GROUP_MISMATCH')
    lengths={r['instance_name']:float(r['geometry_info']['length']) for r in rows}
    if any(not math.isfinite(x) or x<=0 for x in lengths.values()):raise ValueError('INVALID_LOCAL_GEOMETRY_LENGTH')
    w=WorkbookValues(path);result=[]
    try:
        tasks='16组Abaqus任务';models='9套基准荷载';mr=w.unique_row(models,1,model)
        if (w.value(models,'B'+str(mr)),w.value(models,'C'+str(mr)),float(w.value(models,'D'+str(mr))))!=(site,kind,angle):raise ValueError('MODEL_METADATA_MISMATCH')
        for case,label,column,sign in [('POS','正风压+恒雪','M',1),('NEG','负风吸力','N',-1)]:
            candidates=[r for r in range(1,w.formulas[tasks].max_row+1) if w.formulas[tasks].cell(r,2).value==model and w.formulas[tasks].cell(r,5).value==label]
            if len(candidates)!=1:raise ValueError('CASE_TASK_MISSING_OR_DUPLICATE: '+case)
            row=candidates[0];job_id=w.value(tasks,'A'+str(row))
            if not re.fullmatch('J[0-9]+',job_id):raise ValueError('JOB_ID_INVALID')
            if (w.value(tasks,'C'+str(row)),float(w.value(tasks,'D'+str(row))))!=(site,angle):raise ValueError('JOB_MODEL_SITE_ANGLE_MISMATCH')
            q=float(w.value(tasks,'G'+str(row)));expected=float(w.value(models,column+str(mr)))*1000
            if not math.isfinite(q) or q*sign<=0 or not math.isclose(q,expected,rel_tol=1e-9):raise ValueError('CASE_VALUE_SIGN_OR_FORMULA_MISMATCH')
            direction_text=str(w.value(tasks,'H'+str(row)))
            if ('下压' if case=='POS' else '上拔') not in direction_text:raise ValueError('WORKBOOK_DIRECTION_CONFLICT')
            d=dict(layout)
            d.update(schema='step07-load-3',model_id=model,project_id=project,project_site=site,structure_type=structure,angle_deg=angle,job_id=job_id,case_id=case,load_case=label,
                source_workbook=str(path),source_workbook_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_sheet=tasks,source_cell='G'+str(row),source_direction=direction_text,formula_audit=list(w.used.values()),binding_source=binding_source,
                q_N_per_m=q,load_N_per_m=q,components=[dict(id='COMBINED',q_N_per_m=q,direction='PANEL_INWARD_NORMAL')],
                applied_instances=names,groups=groups,local_model_length_m=lengths,effective_load_length_m={n:layout['tributary_length_m'] for n in names},
                total_force_N=q*layout['tributary_length_m'],all_purlins_total_force_N=q*layout['tributary_length_m']*len(names),
                load_direction='SIGNED_PANEL_NORMAL',load_transfer_method='UNIFORM_UPPER_FLANGE_TRACTION_TO_EXISTING_TIE',create_step='STEP07_LOADING',
                engineering_status='SIMPLIFIED_TIE_BENCHMARK_PENDING_REVIEW',replace_verified_legacy_j13=False,
                warnings=['Signed q uses inward panel normal as positive; NEG reverses direction',layout.get('pending_confirmation','Layout from explicit confirmed project mapping'),
                'Tributary rule and simplified Tie are not refined continuous-purlin/bolt models','Mesh quality and solver Tie enforcement require independent review',
                'POS includes dead/snow scalar combination; NEG contains wind suction only; no added Gravity'])
            if angle<15:d['warnings'].append('Angle below 15 degrees borrows 15 degree coefficients; confirmation pending')
            result.append(d)
        return result
    finally:w.close()

def read_load_case(workbook,summary,job_id='J13',support_layout=None):
    for d in read_load_cases(workbook,summary):
        if d['job_id']==job_id:return d
    raise ValueError('CASE_NOT_YET_VALIDATED: '+job_id+' does not belong to project task pair')
