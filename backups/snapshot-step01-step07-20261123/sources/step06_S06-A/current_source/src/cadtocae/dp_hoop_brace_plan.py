"""DP hoop/brace mapping from summary associations and actual hole profiles."""
import math
from .analysis_geometry import add, sub, scale, dot, cross, norm, unit
from .hole_transforms import step04_local_point_to_global as point
from .hole_transforms import step04_global_point_to_local as inverse
from .hole_transforms import step04_local_vector_to_global as vector
from .hole_component_resolution import resolve_hole_component
from .connector_geometry import connector_profile
from .step06_version import version_fields, preload_record

TOL = 1.e-6


def unique(items, error):
    if len(items) != 1:
        raise ValueError(error)
    return items[0]


def patch_distance(position, placement, height):
    p = inverse(position, placement)
    return math.sqrt(p[0]**2 + (p[1]-max(0.,min(height,p[1])))**2 +
                     (p[2]-max(0.,min(.05,p[2])))**2)


def choose_brace_rp(center, axis, thickness, placement, height):
    axis = unit(axis)
    options = [(patch_distance(add(center,scale(axis,sign*thickness)),placement,height),sign)
               for sign in (-1.,1.)]
    options.sort()
    if abs(options[1][0]-options[0][0]) <= TOL:
        raise ValueError('DP_BRACE_RP_SIDE_AMBIGUOUS')
    return add(center,scale(axis,options[0][1]*thickness)), options


def resolve_groups(summary):
    members=summary['instances'];groups=summary.get('hoop_groups',[])
    if not groups:
        # Group identity is semantic connection_group, never numeric order.
        ids=sorted(set(m['connection_group'] for m in members if m.get('canonical_role')=='HOOP' and m.get('connection_group')))
        groups=[dict(group_id=g) for g in ids if g]
    resolved={};evidence={}
    for side in ('FRONT','REAR'):
        column=unique([m for m in members if m.get('canonical_role')=='COLUMN_'+side],
                      'DP_HOOP_GROUP_MAPPING_AMBIGUOUS: column '+side)
        def semantic(g):
            values=[g.get('column_instance'),g.get('column_role'),g.get('brace_role')]
            return any(v in (column['instance_name'],'COLUMN_'+side,side,'BRACE_'+side) for v in values)
        explicit=[g for g in groups if semantic(g)]
        method='SUMMARY_COLUMN_ASSOCIATION'
        if explicit:
            g=unique(explicit,'DP_HOOP_GROUP_MAPPING_AMBIGUOUS: '+side)
            if g.get('column_instance',column['instance_name'])!=column['instance_name']:
                raise ValueError('DP_HOOP_GROUP_MAPPING_AMBIGUOUS: conflicting association')
        else:
            origin=point((0.,0.,0.),column['placement']);axis=unit(vector((0.,0.,1.),column['placement']))
            matches=[]
            for candidate in groups:
                # Never override an explicit association to the other column.
                if any(candidate.get(k) for k in ('column_instance','column_role','brace_role')):continue
                center=candidate.get('center')
                if center is None:
                    a=unique([m for m in members if m.get('connection_group')==candidate['group_id'] and
                              m.get('canonical_role')=='HOOP' and m['instance_name'].endswith('_A')],
                             'DP_HOOP_GROUP_MAPPING_AMBIGUOUS: A half')
                    center=point((0.,0.,0.),a['placement'])
                if norm(cross(sub(center,origin),axis))<=TOL:matches.append(candidate)
            g=unique(matches,'DP_HOOP_GROUP_MAPPING_AMBIGUOUS: '+side)
            method='UNIQUE_COLUMN_AXIS_MATCH'
        resolved[side]=g
        evidence[side]=dict(method=method,column_instance=column['instance_name'],group_id=g['group_id'])
    if resolved['FRONT']['group_id']==resolved['REAR']['group_id']:
        raise ValueError('DP_HOOP_GROUP_MAPPING_AMBIGUOUS: same front/rear group')
    return resolved,evidence


def build_dp_hoop_brace_plan(summary, holes, components, half_selection=None):
    if summary.get('structure_type')!='DP' or summary['project_id']!=holes['project_id']:
        raise ValueError('DP_HOOP_BRACE_SCOPE')
    from .hoop_brace_geometry_plan import build_hoop_geometry_plan
    groups,mapping=resolve_groups(summary)
    return build_hoop_geometry_plan(summary,holes,components,groups,mapping,half_selection)
