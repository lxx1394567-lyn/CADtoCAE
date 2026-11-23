"""One connector, consuming the successful Step06-A plan/report without hole edits."""
import hashlib
import json
import math
from .connector_geometry import require_connector_structure, matched_hole_geometry, parallel_hole_axes, check_hole_coaxial
from .hole_transforms import step04_local_point_to_global, step04_local_vector_to_global


def fingerprint(plan):
    return hashlib.sha256(json.dumps(plan, ensure_ascii=True, sort_keys=True,
                                    allow_nan=False).encode('utf-8')).hexdigest()


def _one(values, label):
    if len(values) != 1:
        raise ValueError('INCOMPLETE_P01_P04_GROUPS: Expected exactly one ' + label)
    return values[0]


def _near(a, b, label):
    if len(a) != 3 or len(b) != 3 or not all([not (math.isnan(float(v)) or math.isinf(float(v))) for v in list(a)+list(b)]):
        raise ValueError('Invalid ' + label)
    if math.sqrt(sum([(float(x)-float(y))**2 for x,y in zip(a,b)])) > 1.e-6:
        raise ValueError('Step06-A data mismatch: ' + label)


def build_b1_plan(holes, report, group="P01", structure_type=None):
    if (report.get('status') != 'SUCCESS' or report.get('project_id') != holes['project_id']
            or report.get('plan_fingerprint') != fingerprint(holes)):
        raise ValueError('Matching SUCCESS Step06-A report required')
    require_connector_structure(holes,structure_type)
    source = _one([h for h in holes['driving_holes'] if h['connection_group'] == group
                   and h['hole_id'] == 'PS_TO_PURLIN'], 'P01 driving hole')
    target = _one([h for h in report['purlin_local'] if h['connection_group'] == group],
                  'P01 derived result')
    derived = _one([h for h in holes['derived_holes']
                    if h['source_driving_hole_id'] == source['driving_hole_id']], 'linked derived hole')
    if (derived['target_instance'] != target['target_instance']
            or derived['target_part'] != target['target_part']
            or derived['target_role'] != 'PURLIN_LOCAL'):
        raise ValueError('Derived hole/report linkage mismatch')
    if (source['source_instance'] != 'PURLIN_SUPPORT_'+group[1:]
            or target['source_instance'] != source['source_instance']
            or target['target_instance'] != 'PURLIN_LOCAL_'+group[1:]):
        raise ValueError('B1 instance contract mismatch')
    width,length,circular = matched_hole_geometry(source,target)
    members = dict([(m['instance_name'],m) for m in holes['instances']])
    a = members[source['source_instance']]; b = members[target['target_instance']]
    _near(step04_local_point_to_global(source['local_center_m'],a['placement']),
          target['source_global_center'],'support center')
    _near(step04_local_point_to_global(target['local_center'],b['placement']),
          target['intersection_global'],'purlin center')
    parallel_hole_axes(step04_local_vector_to_global(source['local_axis'],a['placement']),
                       target['global_hole_axis'],'bolt axis')
    if 'local_axis' in target:
        parallel_hole_axes(step04_local_vector_to_global(target['local_axis'],b['placement']),target['global_hole_axis'],'target axis')
    if not circular:
        parallel_hole_axes(step04_local_vector_to_global(source['local_major_axis'],a['placement']),
                           target['global_major_axis'],'major axis')
        if 'local_major_axis' in target:
            parallel_hole_axes(step04_local_vector_to_global(target['local_major_axis'],b['placement']),target['global_major_axis'],'target major axis')
    check_hole_coaxial(target['source_global_center'],target['intersection_global'],target['global_hole_axis'])
    if a['part_name'] != source['source_part'] or b['part_name'] != target['target_part']:
        raise ValueError('B1 part contract mismatch')
    return dict(schema_version='step06-b1-connector-v1',project_id=holes['project_id'],
                connection_group=group,connection_family='PURLIN_BOLT',
                step06_a_fingerprint=fingerprint(holes),
                source_driving_hole_id=source['driving_hole_id'],
                target_derived_hole_id=derived['derived_hole_id'],
                source_instance=a['instance_name'],target_instance=b['instance_name'],
                source_part=a['part_name'],target_part=b['part_name'],
                rp_support=target['source_global_center'],rp_purlin=target['intersection_global'],
                bolt_axis=target['global_hole_axis'],slot_major_axis=target['global_major_axis'],
                width_m=width,total_length_m=length,hole_type=source['hole_type'],thickness_m=source['source_geometry']['t_m'],
                connector_type='CARTESIAN',behavior_status='PRESET_FOR_WORKFLOW_VALIDATION')
