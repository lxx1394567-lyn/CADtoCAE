"""SP_SC ANG18 HOOP/Brace input adapter; no geometry/model mutation.

The SP_SC ANG18 engineering rule explicitly selects half A for both braces.
"""
import math
from .hole_transforms import step04_local_point_to_global as point
from .hole_transforms import step04_local_vector_to_global as vector


def hoop_brace_candidates(summary, hole_plan):
    if not summary['project_id'].startswith('SP_SC_ANG18_'):
        raise ValueError('HOOP_BRACE_SCOPE: SP_SC ANG18 only')
    members = {m['instance_name']: m for m in summary['instances']}
    hoop = hole_plan['hoop_hole_plan']
    result = {}
    for side, role in (('FRONT', 'BRACE_FRONT'), ('REAR', 'BRACE_REAR')):
        brace = members[role + '_01']
        start = point((0., 0., 0.), brace['placement'])
        web = point((0., 0., .025), brace['placement'])
        brace_axis = vector((0., 0., 1.), brace['placement'])
        candidates = []
        for name in ('HOOP_01_A',):
            member = members[name]
            geometry = hoop['part_geometry'][member['part_name']]
            thickness = geometry['thickness_m']
            if abs(thickness - .005) > 1.e-9:
                raise ValueError('HOOP_BRACE_SCOPE: expected 5 mm HOOP thickness')
            for hole in hoop['driving_holes']:
                if hole['part_name'] != member['part_name']:
                    continue
                if hole['hole_type'] != 'ROUND' or abs(hole['diameter_m'] - .016) > 1.e-9:
                    raise ValueError('HOOP_BRACE_SCOPE: expected 16 mm round hole')
                center = point(hole['local_center_m'], member['placement'])
                axis = vector(hole['local_axis'], member['placement'])
                if math.hypot(axis[0], axis[2]) > 1.e-6:
                    raise ValueError('HOOP_BOLT_AXIS_NOT_GLOBAL_Y')
                if (side == 'FRONT' and center[0] >= 0.) or (side == 'REAR' and center[0] <= 0.):
                    continue
                delta_y = web[1] - center[1]
                if delta_y >= -1.e-6:
                    raise ValueError('HOOP_BRACE_Y_SIGN_AMBIGUOUS')
                sign = -1.  # Explicit ANG18 A-half -> brace convention.
                brace_rp = (center[0], center[1] + sign * thickness, center[2])
                candidates.append(dict(side=side, hoop_group='HOOP_01', hoop_instance=name,
                    hoop_hole_id=hole['hole_id'], hoop_part=member['part_name'],
                    brace_instance=brace['instance_name'], brace_part=brace['part_name'],
                    hoop_rp_global=center, brace_rp_global=brace_rp,
                    delta_xyz=(0., sign * thickness, 0.), rp_distance=thickness,
                    hoop_thickness=thickness, bolt_axis=axis, brace_axis=brace_axis,
                    brace_web_global_y=web[1], distance_to_web=abs(delta_y),
                    start_xz_distance=math.hypot(center[0]-start[0],center[2]-start[2]),
                    brace_station_m=[0., .05], brace_region_semantic='BRACE_START_50MM_WEB'))
        if not candidates:
            raise ValueError('HOOP_BRACE_MAPPING_MISSING: ' + side)
        result[side] = candidates
    return result


def build_hoop_brace_plan(summary, hole_plan, half_selection=None):
    choices = half_selection or {'FRONT':'A','REAR':'A'}
    if choices != {'FRONT':'A','REAR':'A'}:
        raise ValueError('SP_SC ANG18 benchmark requires explicit A/A rule')
    candidates = hoop_brace_candidates(summary, hole_plan)
    connections = []
    for side in ('FRONT', 'REAR'):
        options = candidates[side]
        expected_hole = 'HOOP_LEFT' if side == 'FRONT' else 'HOOP_RIGHT'
        options = [c for c in options if c['hoop_instance']=='HOOP_01_A' and c['hoop_hole_id']==expected_hole]
        if len(options) != 1:
            raise ValueError('HOOP_BRACE_MAPPING_MISMATCH: '+side)
        c=options[0]
        if abs(c['delta_xyz'][1]+.005)>1.e-9:
            raise ValueError('HOOP_BRACE_Y_DIRECTION_MISMATCH')
        member=next(m for m in summary['instances'] if m['instance_name']==c['brace_instance'])
        c['brace_placement']=member['placement']
        connections.append(options[0])
    return dict(project_id=summary['project_id'],schema_version='step06-hoop-brace-v1',
                front_hoop_half='A',rear_hoop_half='A',brace_hoop_half='A',
                hoop_half_for_brace_front='A',hoop_half_for_brace_rear='A',
                front_hoop_hole='HOOP_LEFT',rear_hoop_hole='HOOP_RIGHT',
                connections=connections,connector_section='STEP06_CONNECTOR_SECTION_HOOP_BOLT',
                parameter_source='TEMPORARY_PRESET',behavior_status='PRESET_FOR_WORKFLOW_VALIDATION',
                stiffness_n_m=[5.e8,2.e8,2.e8])
