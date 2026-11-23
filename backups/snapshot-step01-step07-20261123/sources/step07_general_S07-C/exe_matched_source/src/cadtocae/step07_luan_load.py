"""Luan POS adapter: original supplier workbook plus explicitly confirmed layout.
No Pingtang defaults and no inference for other projects.
"""
import hashlib
import math
import copy
from pathlib import Path
from .step07_load_input import WorkbookValues
from .step07_tributary import tributary_layout

def read_luan_pos(workbook,summary,mapping):
    project='SP_DC_ANG19_LUANLUANLUAN-T0203'
    if summary['project_id']!=project or summary['model_name']!=project or summary['structure_type']!='SP_DC' or mapping.get('confirmed') is not True or mapping.get('project_id')!=project:
        raise ValueError('LUAN_CONFIRMED_MAPPING_REQUIRED')
    inputs=dict(mapping['confirmed_inputs']);angle=float(inputs['angle_deg'])
    if not 15<=angle<=20:raise ValueError('ANGLE_OUTSIDE_CONFIRMED_INTERPOLATION')
    path=Path(workbook).resolve(strict=True);w=WorkbookValues(path)
    try:
        layout_input=copy.deepcopy(mapping['support_layout'])
        if 'Step07_POS' in w.formulas.sheetnames:
            sheet='Step07_POS';values={}
            for row in range(5,w.formulas[sheet].max_row+1):
                key=w.formulas[sheet].cell(row,1).value
                if key in list(inputs)+['project_id','case_id','purlin_length_m','support_count','spacing_1_m','spacing_2_m','spacing_3_m','cantilever_left_m','cantilever_right_m','support_index','mu15','mu20']:
                    if key in values:raise ValueError('DUPLICATE_INPUT_KEY: '+key)
                    values[key]=w.value(sheet,'C'+str(row))
            if values.get('project_id')!=project or values.get('case_id')!='POS':raise ValueError('INPUT_WORKBOOK_IDENTITY_MISMATCH')
            for key in inputs:
                if key not in values:raise ValueError('MISSING_INPUT: '+key)
                inputs[key]=float(values[key])
                if not math.isfinite(inputs[key]) or inputs[key]<=0:raise ValueError('INVALID_INPUT: '+key)
            angle=inputs['angle_deg']
            if not 15<=angle<=20 or abs(angle-float(mapping['actual_angle_deg']))>1e-8:raise ValueError('MODEL_ANGLE_MISMATCH')
            for key in ('purlin_length_m','support_count','cantilever_left_m','cantilever_right_m','support_index'):layout_input[key]=values[key]
            if layout_input['support_count']!=4 or layout_input['support_index'] not in (0,3):raise ValueError('THIS_TEMPLATE_REQUIRES_FOUR_SUPPORTS_AND_END_FRAME')
            layout_input['support_index']=int(layout_input['support_index']);layout_input['support_count']=int(layout_input['support_count'])
            layout_input['support_spacing_m']=[float(values['spacing_%d_m'%i]) for i in (1,2,3)]
            layout_input['support_position']='LEFT' if layout_input['support_index']==0 else 'RIGHT'
            wind_reference=inputs['basic_wind_kPa']*inputs['height_factor']*inputs['gust_factor']*inputs['wind_factor']*inputs['terrain_factor']
            mu15=float(values['mu15']);mu20=float(values['mu20'])
            if not (0<mu15<float('inf') and 0<mu20<float('inf')):raise ValueError('INVALID_SHAPE_COEFFICIENT')
        else:
            sheet='风荷载组合'
            if w.value(sheet,'C4')!=inputs['basic_wind_kPa'] or w.value(sheet,'B16')!=inputs['terrain_factor']:raise ValueError('SOURCE_WIND_PARAMETERS_CHANGED')
            wind_reference=float(w.value(sheet,'H26'))
            expected=inputs['basic_wind_kPa']*inputs['height_factor']*inputs['gust_factor']*inputs['wind_factor']*inputs['terrain_factor']
            if abs(wind_reference-expected)>1e-9:raise ValueError('WORKBOOK_WIND_REFERENCE_MISMATCH')
            mu15=float(w.value(sheet,'I25'));mu20=float(w.value(sheet,'J25'))
        mu=mu15+(mu20-mu15)*(angle-15)/5
        width=inputs['module_length_m']/2
        dead=inputs['module_mass_kg']*inputs['gravity_N_per_kg']/(inputs['module_length_m']*inputs['module_width_m'])/1000
        components=[dict(id='WIND',q_N_per_m=wind_reference*mu*width*1000,direction='PANEL_INWARD_NORMAL'),dict(id='DEAD',q_N_per_m=inputs['dead_factor']*dead*width*1000,direction='GLOBAL_DOWN'),dict(id='SNOW',q_N_per_m=inputs['snow_factor']*inputs['snow_combination_factor']*inputs['snow_shape_factor']*inputs['snow_kPa']*width*1000,direction='GLOBAL_DOWN')]
        q=sum(x['q_N_per_m'] for x in components)
        layout=tributary_layout(project,'LUAN19','SP_DC',layout_input)
        rows=sorted([x for x in summary['instances'] if x['canonical_role']=='PURLIN_LOCAL'],key=lambda x:x['instance_name'])
        if len(rows)!=4 or len(set(x['connection_group'] for x in rows))!=4:raise ValueError('CONFIRMED_FOUR_PURLINS_REQUIRED')
        names=[x['instance_name'] for x in rows];d=dict(layout)
        d.update(schema='step07-load-4',project_site='六安',angle_deg=angle,job_id='END_POS',case_id='POS',load_case='正风压+恒载+雪载（2x14端部榀）',source_workbook=str(path),source_workbook_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_sheet=sheet,source_cell=('C5:C31' if sheet=='Step07_POS' else 'H26,I25,J25'),formula_audit=list(w.used.values()),binding_source=mapping['source'],confirmed_inputs=inputs,interpolated_shape_coefficient=mu,module_dead_kPa=dead,tributary_width_m=width,
            q_N_per_m=q,load_N_per_m=q,components=[dict(id='COMBINED',q_N_per_m=q,direction='PANEL_INWARD_NORMAL')],vector_components=components,
            applied_instances=names,groups=[x['connection_group'] for x in rows],local_model_length_m={x['instance_name']:float(x['geometry_info']['length']) for x in rows},effective_load_length_m={n:layout['tributary_length_m'] for n in names},
            total_force_N=q*layout['tributary_length_m'],all_purlins_total_force_N=q*layout['tributary_length_m']*len(names),scalar_force_note='Sum of component magnitudes, NOT vector norm. Actual vectors/norms are calculated from CAE panel normal.',
            load_direction='WIND_NORMAL_DEAD_SNOW_VERTICAL',load_transfer_method='UNIFORM_UPPER_FLANGE_TRACTION_TO_EXISTING_TIE',create_step='STEP07_LOADING',engineering_status='SIMPLIFIED_TIE_BENCHMARK_PENDING_REVIEW',replace_verified_legacy_j13=False,
            warnings=['Explicit input workbook/confirmed parameters override supplier hardcoded snow combination; see confirmed_inputs and formula_audit','End tributary = adjacent half span + cantilever; see explicit layout. Not continuous purlin reaction analysis','Wind normal; dead and snow global vertical. Scalar sum is not vector magnitude','NEG disabled for this confirmed case','Mesh quality, 564 unmatched Tie nodes in prior solve and material grade remain separate engineering checks'])
        return [d]
    finally:w.close()
