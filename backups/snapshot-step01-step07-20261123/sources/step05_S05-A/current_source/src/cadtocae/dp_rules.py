"""DP semantic planner: scoped inputs and shared connection algorithms."""
import math
from collections import defaultdict

from .analysis_capability import is_hoop_member
from .analysis_defaults import DEFAULT_SP_SC_ANALYSIS_CONFIG
from .analysis_project import validate_project_files
from .beam_brace_tie import build_plan
from .column_beam_coupling import resolve_face_coupling
from .column_hoop_tie import resolve_hoop
from .column_axis import cct_dot
from .analysis_geometry import rotate_point
from .main_frame_assembly import _read_named_points
from .sp_dc_rules import unique_member
from .workbook import (load_dimension_complete_components, component_code_from_row,
                       _parsed_spec_for_export, section_kind_and_model_params,
                       _length_m_for_export, effective_model_policy)
from copy import deepcopy

DP_ROLES = ('INCLINED_BEAM','BRACE_FRONT','BRACE_REAR','COLUMN_FRONT','COLUMN_REAR')
DP_POINTS = ('B','C','D','E','CF0','CF1','CR0','CR1')
DP_RULES = ['BEAM_BRACE_TIE','COLUMN_HOOP_TIE','COLUMN_BEAM_COUPLING']
DP_CAPABILITY = 'DP_FULL_CONNECTION_SETUP'


def default_dp_config():
    result = {key:deepcopy(DEFAULT_SP_SC_ANALYSIS_CONFIG[key]) for key in DP_RULES}
    result['COLUMN_BEAM_COUPLING']['beam_half_length_mm'] = 50.
    return result


def selected_components(files, summary):
    members = [m for m in summary['instances'] if m.get('canonical_role',m.get('component_code')) in DP_ROLES or is_hoop_member(m)]
    parts = {m['part_name'] for m in members}
    result = []
    for row in load_dimension_complete_components(files.components):
        if row.get('abaqus_part_name') not in parts:
            continue  # Clamp properties are not inputs to this ruleset.
        parsed = _parsed_spec_for_export(row)
        kind,params = section_kind_and_model_params(parsed)
        policy,element = effective_model_policy(row)
        thickness = parsed.thickness_mm
        if thickness is None or not math.isfinite(float(thickness)) or thickness <= 0:
            raise ValueError('Missing/invalid thickness for '+row['abaqus_part_name'])
        result.append(dict(part_name=row['abaqus_part_name'],component_code=component_code_from_row(row),
                           section_kind=kind,section_params_m=params,model_policy=policy,element_type=element,
                           length_m=_length_m_for_export(row,parsed),thickness_m=float(thickness)/1000.,
                           source='workbook.export_abaqus_json(selection=complete)'))
    return result


def dp_requirements(summary,points):
    missing = dict(roles=[],points=[],hoop_groups=[])
    for role in DP_ROLES:
        matches = [m for m in summary['instances'] if (m.get('canonical_role') or m.get('component_code'))==role]
        if len(matches)!=1: missing['roles'].append(role+' (requires unique instance)')
    for key in DP_POINTS:
        a,b = summary.get('assembly_points',{}).get(key),points.get(key)
        valid = lambda v: isinstance(v,(list,tuple)) and len(v)==3 and all(type(x) in (int,float) and math.isfinite(x) for x in v)
        if not valid(a) or not valid(b):missing['points'].append(key)
        elif max(abs(x-y) for x,y in zip(a,b))>1.e-6:missing['points'].append(key+' (coordinate/summary mismatch)')
    groups = defaultdict(list)
    for member in summary['instances']:
        if is_hoop_member(member):groups[member.get('connection_group')].append(member)
    metadata = summary.get('hoop_groups',[])
    for record in metadata:
        if record.get('group_id') not in groups:
            missing['hoop_groups'].append(str(record.get('group_id'))+' has no HOOP instances')
    columns = {m['instance_name']:m for m in summary['instances'] if m.get('canonical_role') in ('COLUMN_FRONT','COLUMN_REAR')}
    assigned = []
    if len(groups)<2:missing['hoop_groups'].append('At least two complete HOOP groups required')
    for gid,halves in groups.items():
        records=[g for g in metadata if g.get('group_id')==gid]
        if not gid or sorted(h.get('pair_member') or h['instance_name'].rsplit('_',1)[-1] for h in halves)!=['A','B']:
            missing['hoop_groups'].append(str(gid)+' requires unique A/B pair')
        if len(records)!=1 or records[0].get('column_instance') not in columns:
            missing['hoop_groups'].append(str(gid)+' missing/ambiguous column_instance mapping')
        else:
            g=records[0];assigned.append(g['column_instance'])
            if {g.get('instance_a'),g.get('instance_b')}!={h['instance_name'] for h in halves}:
                missing['hoop_groups'].append(str(gid)+' summary A/B instance mapping mismatch')
    for name in columns:
        if name not in assigned:missing['hoop_groups'].append('No HOOP group mapped to '+name)
    return missing


def build_dp_plan(files, config=None):
    summary = validate_project_files(files)
    if summary['structure_type']!='DP':raise ValueError('DP ruleset requires DP summary')
    points,_ = _read_named_points(files.coordinate)
    missing = dp_requirements(summary,points)
    if any(missing.values()):raise ValueError('DP missing requirements: '+str(missing))
    config = config or default_dp_config()
    if config != default_dp_config():raise ValueError('DP v1 requires the validated fixed configuration')
    components = selected_components(files,summary)
    geometry = {}
    for role in DP_ROLES:
        member=unique_member(summary,components,role)
        g=member['component_geometry'];kind='PIPE' if role.startswith('COLUMN_') else 'C_CHANNEL'
        if g['section_kind']!=kind or g['model_policy']!='SHELL':raise ValueError('Unsupported DP geometry: '+role)
        if kind=='C_CHANNEL':
            params=g['section_params_m']
            if any(not math.isfinite(params[k]) or params[k]<=0 for k in ('h_m','b_m','lip_m','t_m')) or params['lip_m']>=params['h_m']/2. or abs(g['thickness_m']-params['t_m'])>1.e-6:
                raise ValueError('Invalid C_CHANNEL section: '+role)
        geometry[member['part_name']]=g
    plan=build_plan(files,config,normalized_geometry=geometry)
    couplings=[resolve_face_coupling(summary,components,role,config['COLUMN_BEAM_COUPLING']) for role in ('COLUMN_FRONT','COLUMN_REAR')]
    for i,rule in enumerate(couplings):
        diagnostic=points['CF1' if i==0 else 'CR1']
        rule['control_point_diagnostic']=dict(coordinate=list(diagnostic),delta=[a-b for a,b in zip(rule['rp_coordinate'],diagnostic)])
        for other in couplings[:i]+plan['connections']:
            if max(rule['beam_range'][0],other['beam_range'][0]) < min(rule['beam_range'][1],other['beam_range'][1])-1.e-9:
                raise ValueError('DP beam coupling patches overlap another connection region')
    groups=[]
    for meta in sorted(summary['hoop_groups'],key=lambda g:g['group_id']):
        gid=meta['group_id']
        if not gid or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_' for c in gid):
            raise ValueError('Unsafe HOOP group_id')
        column=next(m for m in summary['instances'] if m['instance_name']==meta['column_instance'])
        role=column.get('canonical_role') or column['component_code']
        subset=deepcopy(dict(summary,instances=[m for m in summary['instances'] if not is_hoop_member(m) or m.get('connection_group')==gid]))
        # DP's horizontal A/B flip occurs AFTER translation. Step04 explicitly
        # publishes that operation as pair_rotation; translation alone is not
        # the B half's final extrusion origin.
        if meta.get('pair_transform_rule')=='DP_ASYMMETRIC_HORIZONTAL_FLIP':
            half=next(m for m in subset['instances'] if m['instance_name']==meta['instance_b'])
            rotation=meta.get('pair_rotation')
            steps=half['placement'].get('rotation_steps',[])
            if not rotation or not steps or steps[-1]!=rotation:
                raise ValueError('DP HOOP post-rotation contract mismatch: '+gid)
            half['placement']['final_origin']=list(rotate_point(half['placement']['translation'],rotation))
        group=resolve_hoop(subset,components,column_role=role)
        col=group['column'];start=cct_dot(col['origin'],col['axis_direction'])
        if group['expected_hoop_band'][0]<start-1.e-6 or group['expected_hoop_band'][1]>start+col['length_m']+1.e-6:
            raise ValueError(gid+' axial band exceeds '+role+' range')
        col['partition_namespace']=gid
        for previous in groups:
            if previous['column']['instance_name']==col['instance_name'] and max(previous['expected_overlap'][0],group['expected_overlap'][0])<min(previous['expected_overlap'][1],group['expected_overlap'][1])-1.e-6:
                raise ValueError('Overlapping HOOP groups on '+role)
        for half in group['halves']:
            tail=gid+'_'+half['label']
            half.update(column_region='STEP05_REGION_'+role+'_'+tail,hoop_region='STEP05_REGION_'+tail+'_'+role,
                        tie='STEP05_TIE_'+role+'_'+tail)
        groups.append(group)
    ties=[c['tie'] for c in plan['connections']]+[h['tie'] for g in groups for h in g['halves']]
    rps=[c['rp_name'] for c in couplings];names=[t['coupling'] for c in couplings for t in c['targets']]
    plan.update(structure_type='DP',ruleset='DP',supported_rules=DP_RULES,column_beam_couplings=couplings,
                column_hoop_groups=groups,warnings=list(summary.get('warnings',[])),
                expected_constraints=dict(ties=ties,tie_count=len(ties),reference_points=len(rps),rp_names=rps,
                                          couplings=len(names),coupling_names=names))
    plan['source_files']['analysis_config']='DEFAULT_DP_ANALYSIS_CONFIG'
    return plan
