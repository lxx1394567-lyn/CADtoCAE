"""Shared Step05 semantic matching and geometry capability diagnostics."""
import re
from .workbook import component_code_from_row, _parsed_spec_for_export, section_kind_and_model_params


def is_hoop_family(code):
    return isinstance(code,str) and re.fullmatch(r'HOOP(?:_(?:ASSEMBLY_)?[0-9]+)?',code) is not None


def is_hoop_member(member):
    return member.get('canonical_role')=='HOOP' or is_hoop_family(member.get('component_code'))


def match_hoop_component(member,components):
    """Never mutate source records or resolve ambiguous Parts using code aliases."""
    part=member['part_name']
    matches=[c for c in components if c.get('part_name',c.get('abaqus_part_name'))==part]
    if len(matches)!=1:
        raise ValueError('HOOP component mapping requires unique exact part_name: '+part+'; matches='+str(len(matches)))
    component=matches[0]
    code=component.get('component_code') or component_code_from_row(component)
    if not is_hoop_member(member) or not is_hoop_family(code):
        raise ValueError('Non-HOOP component family for '+part+': '+str(code))
    kind=component.get('section_kind')
    if kind is None:kind=section_kind_and_model_params(_parsed_spec_for_export(component))[0]
    if kind!='HOOP_BAND':raise ValueError('Expected HOOP_BAND geometry for '+part+'; got '+str(kind))
    return component


def hoop_mapping(member,component):
    return dict(raw_component_code=member.get('component_code'),canonical_role='HOOP',
                component_record_code=component.get('component_code') or component_code_from_row(component),
                part_name=member['part_name'],instance_name=member['instance_name'])


def hoop_band_review(rule):
    column=rule['column'];axis=column['axis_direction'];origin=column['origin']
    start=sum(a*b for a,b in zip(origin,axis));end=start+column['length_m']
    low,high=rule['expected_hoop_band'];overlap=rule['expected_overlap']
    if low>=start-1.e-6 and high<=end+1.e-6:return None
    group=rule['group_id']
    reason=group+' axial band exceeds COLUMN_DOWN range.'
    details=(reason+'\nCOLUMN_DOWN: %.3f-%.3f m\n%s: %.3f-%.3f m\n'
             'Actual overlap: %.3f-%.3f m\nOverlap length: %.3f m\n'
             'Action required: Verify column length / hoop position or define partial-overlap Tie rule.'
             % (start,end,group,low,high,overlap[0],overlap[1],overlap[1]-overlap[0]))
    return dict(group_id=group,reason=reason,details=details,column_range=[start,end],
                hoop_band=[low,high],actual_overlap=overlap,overlap_length=overlap[1]-overlap[0])


class GeometryReviewError(ValueError):
    def __init__(self,issues,groups):
        super().__init__('\n\n'.join(i['details'] for i in issues))
        self.issues=issues
        self.groups=groups


def first_blocking_reason(row):
    if row.get('first_blocking_reason'):return row['first_blocking_reason']
    if row.get('errors'):return row['errors'][0]
    for category,values in row.get('missing_requirements',{}).items():
        if values:return category+': '+str(values[0])
    return ''
