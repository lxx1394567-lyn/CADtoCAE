"""Step06-only binding of component geometry to authoritative summary Parts."""
from copy import deepcopy
import math
from .analysis_capability import is_hoop_family

ROLES = ('PURLIN_SUPPORT','PURLIN_LOCAL','INCLINED_BEAM','HOOP')


def role_of(record):
    code = record.get('component_code')
    return record.get('canonical_role') or ('HOOP' if is_hoop_family(code) else code)


def resolve_hole_component(member, components):
    role, part = role_of(member), member['part_name']
    exact = [c for c in components if c.get('part_name',c.get('abaqus_part_name')) == part]
    candidates = exact
    method = 'EXACT_PART'
    if not exact:
        candidates = [c for c in components if c.get('component_code') == member.get('component_code')]
        method = 'UNIQUE_COMPONENT_CODE'
        if not candidates and role != 'HOOP':
            candidates = [c for c in components if role_of(c) == role]
            method = 'UNIQUE_CANONICAL_ROLE'
    if len(candidates) != 1:
        raise ValueError('Components match: FAIL; requires unique component geometry for '+role+
                         '; summary Part='+part+'; candidates='+str([c.get('part_name') for c in candidates]))
    source = candidates[0]
    if role_of(source) != role:
        raise ValueError('Components match: FAIL; canonical role conflict for '+part)
    kind,policy = {'PURLIN_SUPPORT':('ANGLE','SOLID'),'PURLIN_LOCAL':('C_CHANNEL','SHELL'),
                   'INCLINED_BEAM':('C_CHANNEL','SHELL'),'HOOP':('HOOP_BAND','SOLID'),
                   'BRACE_FRONT':('C_CHANNEL','SHELL'),'BRACE_REAR':('C_CHANNEL','SHELL')}[role]
    info = member.get('geometry_info') or {}
    if source.get('section_kind') != kind or source.get('model_policy') != policy or info.get('section_kind',kind) != kind:
        raise ValueError('Components match: FAIL; section/model policy conflict for '+part)
    if not source.get('section_params_m'):
        raise ValueError('Components match: FAIL; component section geometry missing for '+part)
    if role != 'HOOP':
        length,reported = source.get('length_m'),info.get('length')
        if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in (length,reported)):
            raise ValueError('Components match: FAIL; invalid component/summary length for '+part)
        if abs(length-reported)>1.e-9:
            raise ValueError('Workbook/summary length mismatch: '+part)
    result = deepcopy(source)
    # Only the in-memory geometry binding changes. Neither input file is rewritten.
    result['part_name'] = part
    return result, dict(role=role,instance_name=member['instance_name'],connection_group=member.get('connection_group'),
                        actual_part_name=part,component_part_name=source.get('part_name'),method=method,
                        components_match='PASS')


def mapping_diagnostics(summary, components):
    results=[]
    for role in ROLES:
        members=[m for m in summary.get('instances',[]) if role_of(m)==role]
        if not members:continue
        entry=dict(role=role,instances_found=[m['instance_name'] for m in members],
                   actual_part_names=sorted(set(m['part_name'] for m in members)),components_match='PASS',bindings=[],errors=[])
        for member in members:
            try:
                _,binding=resolve_hole_component(member,components)
                entry['bindings'].append(binding)
            except ValueError as exc:
                entry['components_match']='FAIL';entry['errors'].append(str(exc))
        results.append(entry)
    return results


def mapping_text(entry):
    return ('Role: '+entry['role']+'; Instances found: '+', '.join(entry['instances_found'])+
            '; Actual Part names: '+str(entry['actual_part_names'])+'; Components match: '+entry['components_match']+
            ('; '+ '; '.join(entry['errors']) if entry['errors'] else ''))
