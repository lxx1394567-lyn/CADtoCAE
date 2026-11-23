"""Independent SUPPORT_BEAM input adapter; existing connector implementation is read-only."""
import json
from pathlib import Path
from .connector_b1_plan import fingerprint, _one, _near
from .connector_geometry import require_connector_structure, matched_hole_geometry, parallel_hole_axes, check_hole_coaxial
from .hole_transforms import step04_local_point_to_global as point, step04_local_vector_to_global as vector
from .hole_setup import _helpers
from .runtime_compatibility import assert_runtime_compatible
from .analysis_discovery import safe_project_id


def build_support_beam_geometry(holes, report, structure_type=None):
    if (report.get('status')!='SUCCESS' or report.get('project_id')!=holes['project_id']
            or report.get('plan_fingerprint')!=fingerprint(holes)):
        raise ValueError('Matching successful Step06-A report required')
    require_connector_structure(holes,structure_type)
    connections=[]
    beam=_one([m for m in holes['instances'] if m.get('canonical_role')=='INCLINED_BEAM'],'beam')
    if beam['instance_name']!='INCLINED_BEAM_01' or beam['component_geometry']['model_policy']!='SHELL':
        raise ValueError('Expected shell INCLINED_BEAM_01')
    height=beam['component_geometry']['section_params_m']['h_m']
    for group in ('P01','P02','P03','P04'):
        source=_one([h for h in holes['driving_holes'] if h['connection_group']==group and h['hole_id']=='PS_TO_BEAM'],group+' source')
        target=_one([h for h in report['inclined_beam'] if h['connection_group']==group],group+' target')
        derived=_one([h for h in holes['derived_holes'] if h['source_driving_hole_id']==source['driving_hole_id']],group+' derived')
        support=_one([m for m in holes['instances'] if m.get('connection_group')==group and m.get('canonical_role')=='PURLIN_SUPPORT'],group+' support')
        if (support['instance_name']!='PURLIN_SUPPORT_'+group[1:] or source['source_instance']!=support['instance_name']
                or source['source_part']!=support['part_name'] or source['leg']!='SHORT_LEG'
                or target['source_instance']!=support['instance_name'] or target['target_instance']!=beam['instance_name']
                or target['target_part']!=beam['part_name'] or derived['target_instance']!=beam['instance_name']
                or derived['target_part']!=beam['part_name'] or target['target_surface']!='INCLINED_BEAM_TOP_FLANGE'
                or target['feature_name']!='STEP06_HOLE_BEAM_'+group+'_FROM_SUPPORT'
                or target['normal_axis']!=1 or abs(target['plane_coordinate']-height)>1.e-6
                or abs(target['local_center'][1]-height)>1.e-6):
            raise ValueError('Support/Beam TOP_FLANGE semantic mismatch: '+group)
        width,length,circular=matched_hole_geometry(source,target)
        _near(point(source['local_center_m'],support['placement']),target['source_global_center'],'support center')
        _near(point(target['local_center'],beam['placement']),target['intersection_global'],'beam center')
        parallel_hole_axes(vector(source['local_axis'],support['placement']),target['global_hole_axis'],'bolt axis')
        if 'local_axis' in target:
            parallel_hole_axes(vector(target['local_axis'],beam['placement']),target['global_hole_axis'],'target axis')
        if not circular:
            parallel_hole_axes(vector(source['local_major_axis'],support['placement']),target['global_major_axis'],'major axis')
            if 'local_major_axis' in target:
                parallel_hole_axes(vector(target['local_major_axis'],beam['placement']),target['global_major_axis'],'target major axis')
        check_hole_coaxial(target['source_global_center'],target['intersection_global'],target['global_hole_axis'])
        connections.append(dict(project_id=holes['project_id'],connection_group=group,connection_family='SUPPORT_BEAM',
            source_instance=support['instance_name'],target_instance=beam['instance_name'],source_part=support['part_name'],
            target_part=beam['part_name'],rp_support=target['source_global_center'],rp_purlin=target['intersection_global'],
            bolt_axis=target['global_hole_axis'],slot_major_axis=target['global_major_axis'],width_m=width,total_length_m=length,hole_type=source['hole_type'],
            thickness_m=source['source_geometry']['t_m'],support_hole_id='PS_TO_BEAM',beam_hole_feature=target['feature_name'],
            target_surface='INCLINED_BEAM_TOP_FLANGE',connector_type='CARTESIAN',behavior_status='PRESET_FOR_WORKFLOW_VALIDATION'))
    return dict(project_id=holes['project_id'],connections=connections,support_purlin_connections=[],
                step06_a_fingerprint=fingerprint(holes),schema_version='step06-support-beam-v1')


def build_support_beam_plan(holes, report, prior, structure_type=None):
    plan = build_support_beam_geometry(holes, report, structure_type)
    previous=prior.get('support_purlin_connections',prior.get('connections',[]))
    if (prior.get('status')!='SUCCESS' or prior.get('project_id')!=holes['project_id']
            or sorted(c['connection_group'] for c in previous)!=['P01','P02','P03','P04']
            or any(c['status']!='SUCCESS' for c in previous)):
        raise ValueError('Four successful Support-Purlin connections required')
    plan['support_purlin_connections'] = previous
    return plan


def script_source(plan, report_path):
    root=Path(__file__).parent
    source='# -*- coding: utf-8 -*-\nimport math\n'
    source+=_helpers('analysis_geometry.py',{'add','sub','scale','dot','cross','norm','unit'})
    for name in ('connector_geometry.py','purlin_bolt_preset_runtime.py','connector_b1_runtime.py','connector_groups_runtime.py','support_beam_connector_runtime.py'):
        source+=(root/name).read_text(encoding='utf-8')+'\n'
    source+='PLAN=json.loads(%r)\n'%json.dumps(plan,sort_keys=True,allow_nan=False)
    source+='REPORT_PATH=json.loads(%r)\n'%json.dumps(str(report_path))
    source+="if __name__=='__main__':\n    from abaqus import mdb\n    execute_support_beam(PLAN,mdb,REPORT_PATH)\n"
    assert_runtime_compatible(source)
    return source


def generate(folder,project):
    safe_project_id(project);folder=Path(folder).resolve(strict=True)
    def read(suffix):return json.loads((folder/(project+suffix)).read_text(encoding='utf-8-sig'))
    plan=build_support_beam_plan(read('_step06_plan.json'),read('_step06_hole_report.json'),read('_step06_b_connector_report.json'),read('_assembly_summary.json').get('structure_type'))
    output=folder/(project+'_step06_b_support_beam_connector_setup.py')
    if output.is_symlink():raise ValueError('Output cannot be symlink')
    output.write_text(script_source(plan,folder/(project+'_step06_b_connector_report.json')),encoding='utf-8')
    return output
