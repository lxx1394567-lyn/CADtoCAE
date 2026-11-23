"""Discover the four SP_SC assembly connections; never deduplicate by Part."""
from .connector_b1_plan import build_b1_plan, _one


def build_group_plan(holes, report, structure_type=None):
    members = [m for m in holes['instances'] if m.get('canonical_role') in ('PURLIN_SUPPORT','PURLIN_LOCAL')]
    groups = sorted(set([m.get('connection_group') for m in members]))
    if groups != ['P01','P02','P03','P04']:
        raise ValueError('INCOMPLETE_P01_P04_GROUPS: expected complete groups P01-P04')
    connections = []
    for group in groups:
        for role in ('PURLIN_SUPPORT','PURLIN_LOCAL'):
            m = _one([m for m in members if m['connection_group']==group and m['canonical_role']==role],group+' '+role)
            if m['instance_name'] != role+'_'+group[1:]:
                raise ValueError('Group instance mapping mismatch')
        connections.append(build_b1_plan(holes,report,group,structure_type))
    return dict(schema_version='step06-b-groups-v1',project_id=holes['project_id'],
                connections=connections,groups=groups,expected_connections=4)
