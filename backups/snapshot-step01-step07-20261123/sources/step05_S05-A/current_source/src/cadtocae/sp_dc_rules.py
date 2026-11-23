"""SP_DC data validation and ruleset composition; no angle-specific decisions."""
import copy
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from .column_axis import cct_placement_axis, cct_dot, cct_sub
from .column_hoop_tie import resolve_hoop
from .analysis_capability import is_hoop_member, hoop_band_review, GeometryReviewError
from .workbook import (load_dimension_complete_components, component_code_from_row,
                       _parsed_spec_for_export, section_kind_and_model_params,
                       _length_m_for_export, effective_model_policy)

DC_ROLES = ('INCLINED_BEAM','BRACE_FRONT','BRACE_REAR','COLUMN_FRONT','COLUMN_REAR','COLUMN_DOWN')
DC_RULES = ['BEAM_BRACE_TIE','COLUMN_BEAM_TIE','COLUMN_HOOP_TIE']
DC_CAPABILITY = 'SP_DC_FULL_CONNECTION_SETUP'


def normalized_components(path):
    """Use the existing exporter normalization in memory, including read-only scans."""
    result=[]
    for row in load_dimension_complete_components(path):
        parsed=_parsed_spec_for_export(row)
        kind,params=section_kind_and_model_params(parsed)
        policy,element=effective_model_policy(row)
        result.append(dict(part_name=row['abaqus_part_name'],component_code=component_code_from_row(row),
            section_kind=kind,section_params_m=params,model_policy=policy,element_type=element,
            length_m=_length_m_for_export(row,parsed),thickness_m=float(parsed.thickness_mm)/1000.,
            source='workbook.export_abaqus_json(selection=complete)',source_row=row))
    return result


def unique_member(summary,components,role):
    members=[m for m in summary['instances'] if (m.get('canonical_role') or m.get('component_code'))==role]
    if len(members)!=1:raise ValueError('Expected unique '+role)
    m=members[0]
    matches=[c for c in components if c['part_name']==m['part_name'] and c['component_code']==m['component_code']]
    if len(matches)!=1:raise ValueError('Missing/ambiguous component for '+role)
    g=copy.deepcopy(matches[0]);g.pop('source_row',None)
    if len([v for v in summary['instances'] if v['part_name']==m['part_name']])!=1:
        raise ValueError('Shared Part would affect other instances: '+m['part_name'])
    length=g['length_m']
    if not isinstance(length,(int,float)) or not math.isfinite(length) or length<=0:
        raise ValueError('Invalid length: '+role)
    if abs(length-m['geometry_info']['length'])>1.e-6 or g['section_kind']!=m['geometry_info']['section_kind']:
        raise ValueError('Workbook/summary geometry mismatch: '+role)
    axis=cct_placement_axis(m['placement'])
    origin=m['placement'].get('final_origin',m['placement']['translation'])
    if len(origin)!=3 or not all(math.isfinite(float(v)) for v in origin):raise ValueError('Invalid placement: '+role)
    return dict(role=role,instance_name=m['instance_name'],part_name=m['part_name'],component_geometry=g,
                origin=list(origin),axis_direction=list(axis),length_m=length)


def column_beam_plan(summary,components,config):
    for key in ('beam_half_length_mm','column_top_length_mm'):
        if type(config.get(key)) not in (int,float) or not math.isfinite(config[key]) or config[key]<=0:
            raise ValueError('Expected positive '+key)
    beam=unique_member(summary,components,'INCLINED_BEAM')
    half=config['beam_half_length_mm']/1000.;end=config['column_top_length_mm']/1000.
    result=dict(rule_id='COLUMN_BEAM_TIE',beam=beam,columns=[],connections=[],partitions={beam['part_name']:[]})
    for role in ('COLUMN_FRONT','COLUMN_REAR'):
        column=unique_member(summary,components,role)
        for member in (column,beam):
            g=member['component_geometry']
            if g['section_kind']!='C_CHANNEL' or g['model_policy']!='SHELL':
                raise ValueError('COLUMN_BEAM_TIE requires C_CHANNEL shell: '+member['role'])
        if abs(column['axis_direction'][2]-1.)>1.e-6:raise ValueError('Expected upright column: '+role)
        top=[column['origin'][i]+column['axis_direction'][i]*column['length_m'] for i in range(3)]
        station=cct_dot(cct_sub(top,beam['origin']),beam['axis_direction'])
        interval=[station-half,station+half]
        if not 0<interval[0]<interval[1]<beam['length_m'] or not 0<end<column['length_m']:
            raise ValueError('COLUMN_BEAM_TIE partition outside Part')
        for other in result['connections']:
            if max(interval[0],other['beam_range'][0])<min(interval[1],other['beam_range'][1]):
                raise ValueError('COLUMN_BEAM_TIE patches overlap')
        suffix=role.replace('COLUMN_','')
        result['columns'].append(column)
        result['partitions'][column['part_name']]=[column['length_m']-end]
        result['partitions'][beam['part_name']].extend(interval)
        result['connections'].append(dict(id='BEAM_COLUMN_'+suffix,column=column['instance_name'],beam=beam['instance_name'],
            column_part=column['part_name'],beam_part=beam['part_name'],column_top=top,station_m=station,
            column_range=[column['length_m']-end,column['length_m']],beam_range=interval,
            column_region='STEP05_REGION_COLUMN_'+suffix+'_BEAM',beam_region='STEP05_REGION_BEAM_COLUMN_'+suffix,
            tie='STEP05_TIE_BEAM_COLUMN_'+suffix,master=column['instance_name'],slave=beam['instance_name']))
    return result


def hoop_group_plans(summary,components):
    groups=defaultdict(list)
    for m in summary['instances']:
        if is_hoop_member(m):groups[m.get('connection_group')].append(m)
    if not groups:raise ValueError('Missing complete HOOP group')
    plans=[]
    for group,halves in groups.items():
        if not group or not isinstance(group,str):raise ValueError('Missing HOOP group_id')
        labels=[h.get('pair_member') or h['instance_name'].rsplit('_',1)[-1] for h in halves]
        if sorted(labels)!=['A','B']:raise ValueError('Incomplete HOOP A/B group: '+group)
        subset=dict(summary,instances=[m for m in summary['instances'] if not is_hoop_member(m)]+halves)
        rule=resolve_hoop(subset,components)
        # Group identity supplies stable names; axial sorting must not rename groups.
        if any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_' for c in group):
            raise ValueError('Unsafe HOOP group_id: '+group)
        rule['column']['partition_namespace']=group
        for half in rule['halves']:
            tail=group+'_'+half['label']
            half.update(column_region='STEP05_REGION_COLUMN_DOWN_'+tail,
                        hoop_region='STEP05_REGION_'+tail+'_COLUMN_DOWN',tie='STEP05_TIE_COLUMN_DOWN_'+tail)
        plans.append(rule)
    plans.sort(key=lambda r:(r['expected_hoop_band'][0],r['group_id']))
    for a,b in zip(plans,plans[1:]):
        if a['expected_overlap'][1]>b['expected_overlap'][0]+1.e-6:
            raise ValueError('Overlapping HOOP axial bands require review')
    issues=[issue for rule in plans if (issue:=hoop_band_review(rule)) is not None]
    if issues:raise GeometryReviewError(issues,plans)
    return plans


def input_warnings(summary,components,points):
    warnings=[]
    for c in components:
        role=c['component_code'];row=c.get('source_row',{})
        if role in ('COLUMN_FRONT','COLUMN_REAR'):
            warnings.append(role+' is '+c['section_kind']+' '+c['model_policy'])
            if c['model_policy']=='SHELL' and c['element_type'].startswith('C3D'):
                warnings.append(role+': SHELL model policy conflicts with Excel element label '+c['element_type']+'; final mesh not performed')
        if role=='COLUMN_DOWN' and c['section_kind']=='PIPE' and row.get('截面类型') not in ('圆管','圆钢管','PIPE'):
            warnings.append('COLUMN_DOWN legacy derived fields differ; normalized PIPE uses current specification '+str(row.get('规格')))
    if 'REAR_BRACE_LENGTH' in points:
        warnings.append('Rear brace length diagnostic = %.6f mm' % (points['REAR_BRACE_LENGTH'][2]*1000.))
    if 'COLUMN_TOP_LINE_ANGLE' in points:
        warnings.append('Column-top line angle diagnostic = %.9f degrees' % points['COLUMN_TOP_LINE_ANGLE'][2])
    return warnings
