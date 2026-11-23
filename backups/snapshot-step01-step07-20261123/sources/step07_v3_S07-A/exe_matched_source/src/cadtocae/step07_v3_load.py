"""Explicit V3 D1 interface; legacy workbooks never enter this adapter."""
import hashlib
import math
import json
import re
import zipfile
from pathlib import Path
import openpyxl
from .step07_tributary import tributary_layout

SCHEMA = 'V3_D1_POS_1'

def v3_values(path):
    if not zipfile.is_zipfile(path):return None
    w=openpyxl.load_workbook(path,read_only=True,data_only=False)
    try:
        if 'Step07_POS' not in w.sheetnames:return None
        schemas=[r[2].value for r in w['Step07_POS'].iter_rows(min_row=5) if r[0].value=='schema_version']
        if not schemas:return None
        if schemas!=[SCHEMA]:raise ValueError('V3_SCHEMA_MISSING_OR_DUPLICATE')
        rows={};cells={}
        for row in w['Step07_POS'].iter_rows(min_row=5):
            key=row[0].value
            if not isinstance(key,str) or not key:continue
            if key in rows:raise ValueError('DUPLICATE_INPUT_KEY: '+key)
            rows[key]=row[2].value;cells[key]=row[2].coordinate
        if rows.get('schema_version')!=SCHEMA:return None
        # Inputs must be literal: no stale/absent formula cache can become zero.
        for key,value in rows.items():
            if isinstance(value,str) and value.startswith('='):raise ValueError('V3_INPUT_FORMULA_NOT_ALLOWED: '+key)
        return rows,cells
    finally:w.close()

def v3_calculate(v):
    def num(k,positive=True):
        x=v.get(k)
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or (positive and x<=0):raise ValueError('V3_INVALID_INPUT: '+k)
        return float(x)
    required={'combination_id':'D1','case_id':'POS','structure_type':'SP_DC','ground_category':'B','self_weight_mode':'CAE_GRAVITY','snow_reference_area':'HORIZONTAL','unit_system':'N-m-Pa'}
    for k,x in required.items():
        if v.get(k)!=x:raise ValueError('V3_UNSUPPORTED_SETTING: '+k)
    n=num('support_count');index=num('support_index',False)
    if n!=int(n) or index!=int(index):raise ValueError('V3_NONINTEGER_SUPPORT')
    n=int(n);index=int(index)
    if v.get('spacing_list_m'):
        spacing=json.loads(v['spacing_list_m'])
    else:spacing=[num('spacing_%d_m'%i) for i in range(1,n)]
    if not isinstance(spacing,list) or len(spacing)!=n-1:raise ValueError('V3_SPACING_COUNT')
    for i,x in enumerate(spacing,1):
        old=v.get('spacing_%d_m'%i)
        if old is not None and abs(float(old)-x)>1e-9:raise ValueError('V3_SPACING_FIELDS_CONFLICT')
    project=v['project_id'];model=v['model_id']
    if not re.fullmatch('[A-Za-z0-9_-]+',model):raise ValueError('INVALID_MODEL_ID')
    layout=tributary_layout(project,model,'SP_DC',dict(project_id=project,model_id=model,structure_type='SP_DC',support_count=n,support_index=index,support_spacing_m=spacing,support_position='SINGLE' if n==1 else ('LEFT' if index==0 else 'RIGHT' if index==n-1 else 'MIDDLE'),purlin_length_m=num('loaded_coverage_length_m'),cantilever_left_m=num('cantilever_left_m',False),cantilever_right_m=num('cantilever_right_m',False)))
    if abs(layout['tributary_length_m']-num('expected_tributary_length_m'))>1e-9:raise ValueError('V3_EXPECTED_TRIBUTARY_MISMATCH')
    if num('purlin_length_m')<num('loaded_coverage_length_m'):raise ValueError('STEEL_LENGTH_LESS_THAN_COVERAGE')
    if num('wind_reduction_factor')!=1 or num('terrain_factor')!=1:raise ValueError('V3_SCOPE_OR_TERRAIN_REVIEW_REQUIRED')
    if abs(num('gravity_N_per_kg')-9.81)>1e-9:raise ValueError('V3_REQUIRES_GRAVITY_9_81')
    if num('height_factor')!=1:raise ValueError('V3_HEIGHT_FACTOR_REQUIRES_NEW_REVIEW')
    angle=num('angle_deg');b=num('tributary_width_m');g=num('gravity_N_per_kg')
    if not 0<angle<90:raise ValueError('INVALID_ANGLE')
    if abs(b-num('module_length_m')/2)>1e-9:raise ValueError('V3_TRIBUTARY_WIDTH')
    factors=(num('dead_factor'),num('wind_factor'),num('snow_factor')*num('snow_combination_factor'))
    if any(abs(a-bb)>1e-9 for a,bb in zip(factors,(1.3,1.5,1.05))):raise ValueError('V3_REQUIRES_D1_FACTORS')
    beta=None if v.get('gust_factor') is None else num('gust_factor')
    pending=[]
    if beta is None:pending.append('gust_factor')
    height=v.get('wind_height_m')
    if height is None or v.get('height_confirmation')!='CONFIRMED':pending.append('height_and_flat_terrain_confirmation')
    elif not 0<float(height)<=10 or v.get('flat_terrain')!='YES':raise ValueError('HEIGHT_FACTOR_CONDITION_NOT_MET')
    for key in ('beta_basis','model_binding_confirmation','units_confirmation','mass_inventory_confirmation'):
        if not v.get(key) or v[key]=='PENDING':pending.append(key)
    if v.get('model_binding_confirmation') not in ('CONFIRMED','PENDING'):raise ValueError('INVALID_BINDING_CONFIRMATION')
    status=v.get('parameter_status')
    if status not in ('PENDING_DESIGN','CONFIRMED_DESIGN','TRIAL_ONLY'):raise ValueError('INVALID_PARAMETER_STATUS')
    if status=='CONFIRMED_DESIGN' and pending:raise ValueError('FALSE_DESIGN_CONFIRMATION: '+str(pending))
    # Trial inputs explicitly acknowledge assumptions; no unconfirmed live model is approved.
    if status=='TRIAL_ONLY' and (beta is None or v.get('trial_acknowledgement')!='SOFTWARE_TEST_ONLY'):raise ValueError('TRIAL_ACKNOWLEDGEMENT_REQUIRED')
    G=num('module_mass_kg')*g/(num('module_length_m')*num('module_width_m'))
    Wcoef=num('basic_wind_kPa')*1000*num('overall_shape_factor')*num('height_factor')
    S=num('snow_kPa')*1000*num('snow_shape_factor')*math.cos(math.radians(angle))
    L=layout['tributary_length_m'];A=b*L
    forces={'DEAD':G*A*factors[0],'WIND':None if beta is None else Wcoef*beta*A*factors[1],'SNOW':S*A*factors[2]}
    vector=None if beta is None else [forces['WIND']*math.sin(math.radians(angle)),0.,-forces['WIND']*math.cos(math.radians(angle))-forces['DEAD']-forces['SNOW']]
    return dict(layout=layout,pending=pending,engineering_status='TEST_ONLY' if status=='TRIAL_ONLY' else ('PENDING_DESIGN' if pending or status=='PENDING_DESIGN' else 'DESIGN_INPUT_CONFIRMED_NOT_MODEL_ACCEPTED'),standard_area_N_m2=dict(DEAD=G,WIND=None if beta is None else Wcoef*beta,SNOW=S),wind_standard_coefficient_N_m2=Wcoef,area_m2=A,forces_N=forces,reference_vector_N=vector,four_purlin_reference_vector_N=None if vector is None else [4*x for x in vector],gravity_z_m_s2=-factors[0]*g,tributary_length_m=L)

def read_v3_d1(path,summary):
    data=v3_values(path)
    if data is None:raise ValueError('NOT_V3_WORKBOOK')
    v,cells=data;calc=v3_calculate(v);project=v['project_id']
    if summary['project_id']!=project or summary['model_name']!=v['target_model'] or v['target_model']!=project or summary['structure_type']!='SP_DC':raise ValueError('V3_PROJECT_MODEL_BINDING_MISMATCH')
    rows=sorted([r for r in summary['instances'] if r['canonical_role']=='PURLIN_LOCAL'],key=lambda r:r['instance_name'])
    if len(rows)!=4 or len(set(x['connection_group'] for x in rows))!=4:raise ValueError('V3_FOUR_PURLIN_MAPPING_REQUIRED')
    L=calc['tributary_length_m'];components=[dict(id=k,q_N_per_m=None if force is None else force/L,direction='PANEL_INWARD_NORMAL' if k=='WIND' else 'GLOBAL_DOWN') for k,force in calc['forces_N'].items()]
    d=dict(calc['layout']);d.update(schema='step07-v3-d1',project_id=project,model_id=v['model_id'],case_id='POS',job_id=v['model_id']+'_'+v['configuration_id']+'_D1',create_step='STEP07_LOADING',angle_deg=float(v['angle_deg']),source_workbook=str(Path(path).resolve()),source_workbook_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),source_sheet='Step07_POS',source_cells=cells,inputs=v,calculation=calc,engineering_status=calc['engineering_status'],pending_design_parameters=calc['pending'],components=components,vector_components=components,applied_instances=[r['instance_name'] for r in rows],groups=[r['connection_group'] for r in rows],local_model_length_m={r['instance_name']:float(r['geometry_info']['length']) for r in rows},steel_purlin_length_m=float(v['purlin_length_m']),load_direction='WIND_NORMAL_DEAD_SNOW_VERTICAL',load_transfer_method='THREE_UNIFORM_UPPER_FLANGE_TRACTIONS_PLUS_STEEL_GRAVITY',warnings=['V3 D1 only; snow projected once; component mass excludes steel Gravity','Actual material density, units and modeled mass inventory must be verified before live execution','Three configurations require corresponding geometry; no geometry is generated from this Excel','Local traction force/moment equivalence is not continuous-purlin reaction verification'])
    if v['configuration_id']=='2x7':d['warnings'].append('V3 right cantilever 0.978 gives 8.057 m vs reference 8.058 m; 1 mm pending. Selected left tributary remains 4.029 m.')
    return [d]
