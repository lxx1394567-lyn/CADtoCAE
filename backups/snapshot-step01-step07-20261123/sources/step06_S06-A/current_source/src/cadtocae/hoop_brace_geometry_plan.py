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


def build_hoop_geometry_plan(summary, holes, components, groups, mapping, half_selection=None):
    halves=half_selection or {'FRONT':'A','REAR':'A'}
    if set(halves)!=set(('FRONT','REAR')) or any(x not in ('A','B') for x in halves.values()):
        raise ValueError('Invalid explicit hoop half selection')
    members=summary['instances'];hp=holes['hoop_hole_plan'];connections=[]
    for side in ('FRONT','REAR'):
        group=groups[side];half=halves[side]
        name=group.get('instance_'+half.lower())
        hoop=unique([m for m in members if m.get('canonical_role')=='HOOP' and
                     m.get('connection_group')==group['group_id'] and
                     (m['instance_name']==name if name else m['instance_name'].endswith('_'+half))],
                    'DP_HOOP_GROUP_MAPPING_AMBIGUOUS: half '+side)
        brace=unique([m for m in members if m.get('canonical_role')=='BRACE_'+side], 'DP_BRACE_MAPPING_AMBIGUOUS')
        component=resolve_hole_component(brace,components)[0]
        height=component['section_params_m']['h_m']
        start=point((0.,height/2.,0.),brace['placement']);brace_axis=unit(vector((0.,0.,1.),brace['placement']))
        thickness=hp['part_geometry'][hoop['part_name']]['thickness_m']
        if not 0.<thickness<float('inf'):raise ValueError('Invalid HOOP thickness')
        candidates=[]
        for hole in hp['driving_holes']:
            if hole['part_name']!=hoop['part_name'] or hole.get('enabled') is False:continue
            width,length,circular=connector_profile(hole)
            center=point(hole['local_center_m'],hoop['placement']);axis=unit(vector(hole['local_axis'],hoop['placement']))
            delta=sub(start,center);distance=norm(sub(delta,scale(axis,dot(delta,axis))))
            usages=[hole.get(k) for k in ('connection_target','hole_usage')]
            semantic=any(str(x).upper() in (side,'BRACE_'+side,brace['instance_name']) for x in usages if x)
            assigned=any(str(x).upper() in ('FRONT','REAR','BRACE_FRONT','BRACE_REAR','BRACE_FRONT_01','BRACE_REAR_01') for x in usages if x)
            candidates.append(dict(hole=hole,center=center,axis=axis,distance=distance,semantic=semantic,
                                   assigned=assigned,width=width,length=length))
        options=[c for c in candidates if c['semantic']] or [c for c in candidates if not c['assigned']]
        options.sort(key=lambda c:c['distance'])
        if not options or (len(options)>1 and (options[0]['semantic'] or abs(options[1]['distance']-options[0]['distance'])<=TOL)):
            raise ValueError('DP_HOOP_BRACE_HOLE_AMBIGUOUS: '+side)
        selected=options[0];hole=selected['hole'];center=selected['center'];axis=selected['axis']
        brace_rp,sign_evidence=choose_brace_rp(center,axis,thickness,brace['placement'],height)
        major=hole.get('local_major_axis') or (1.,0.,0.)
        connections.append(dict(side=side,hoop_group=group['group_id'],hoop_half=half,
            hoop_instance=hoop['instance_name'],hoop_part=hoop['part_name'],selected_hole_id=hole['hole_id'],
            hoop_hole_id=hole['hole_id'],hole_type=hole['hole_type'],width_m=selected['width'],total_length_m=selected['length'],
            hoop_rp_global=center,brace_rp_global=brace_rp,rp_distance_m=norm(sub(brace_rp,center)),
            hoop_thickness_m=thickness,bolt_axis=axis,hole_major_axis=unit(vector(major,hoop['placement'])),
            brace_axis=brace_axis,brace_instance=brace['instance_name'],brace_part=brace['part_name'],
            brace_placement=brace['placement'],brace_web_height_m=height,brace_start_global=start,
            brace_region='BRACE_START_50MM_WEB',brace_station_m=[0.,.05],
            hole_selection_evidence=dict(method='SEMANTIC' if selected['semantic'] else 'UNIQUE_PROJECTED_START_DISTANCE',
                candidates=[dict(hole_id=c['hole']['hole_id'],projected_distance_m=c['distance']) for c in candidates],
                side_candidates=sign_evidence),group_mapping_evidence=mapping[side]))
    return dict(project_id=summary['project_id'],structure_type='DP',schema_version='step06-dp-hoop-brace-v1',
        front_hoop_group=groups['FRONT']['group_id'],rear_hoop_group=groups['REAR']['group_id'],
        brace_hoop_half='A' if halves=={'FRONT':'A','REAR':'A'} else 'EXPLICIT',
        hoop_half_for_brace_front=halves['FRONT'],hoop_half_for_brace_rear=halves['REAR'],
        connections=connections,group_mapping_evidence=mapping,connector_section='STEP06_CONNECTOR_SECTION_HOOP_BOLT',
        expected_rps=4,expected_couplings=4,expected_wires=2,expected_connectors=2,
        parameter_source='TEMPORARY_PRESET',behavior_status='PRESET_FOR_WORKFLOW_VALIDATION',
        stiffness_n_m=[5.e8,2.e8,2.e8],**version_fields(),**preload_record())
