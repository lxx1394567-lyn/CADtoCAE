"""SP_DC Part-once inheritance audit; workbook schema and geometry unchanged."""
from .hole_plan import _instances, _role
from .hole_transforms import step04_local_point_to_global, step04_local_vector_to_global, _step04_rotate
import copy
import math


def _close(a,b,tol=1.e-9):
    return len(a)==len(b) and all(abs(x-y)<=tol for x,y in zip(a,b))


def expand_standard_prototype(summary,catalog,plan):
    """Only a single explicitly filled Part can be a standard source.

    Multiple filled Parts retain their independent patterns. No union/inference
    from hole suffixes. Missing/ambiguous pair metadata blocks inheritance.
    """
    active={h['part_name'] for h in plan['driving_holes']}
    if len(active)!=1 or len(catalog)==1:return
    if len(catalog)!=2:raise ValueError('SPDC_PROTOTYPE_AMBIGUOUS: expected one unique A/B prototype pair')
    source=next(iter(active));target=next(p for p in catalog if p!=source)
    if any(h['part_name']==target for h in plan['disabled_holes']):
        raise ValueError('SPDC_PROTOTYPE_AMBIGUOUS: target has explicit disabled rows')
    a,b=catalog[source],catalog[target]
    if a['geometry']!=b['geometry'] or a['component'].get('section_params_m')!=b['component'].get('section_params_m'):
        raise ValueError('SPDC_PROTOTYPE_GEOMETRY_MISMATCH: '+source+' / '+target)
    members={m['instance_name']:m for m in _instances(summary) if _role(m)=='HOOP'}
    pairs=summary.get('hoop_groups') or []
    if not pairs:raise ValueError('SPDC_PROTOTYPE_SYMMETRY_UNCONFIRMED: summary.hoop_groups required')
    used=set();groups=set();evidence=[]
    probes=((0.,0.,0.),(.1,0.,0.),(0.,.1,0.),(0.,0.,.1))
    for pair in pairs:
        group=pair['group_id'];an,bn=pair['instance_a'],pair['instance_b']
        if group in groups or an in used or bn in used or an==bn:
            raise ValueError('SPDC_PROTOTYPE_AMBIGUOUS: duplicate group/half mapping')
        ma,mb=members.get(an),members.get(bn)
        if not ma or not mb or ma['part_name']!=source or mb['part_name']!=target or pair['part_a']!=source or pair['part_b']!=target:
            raise ValueError('SPDC_PROTOTYPE_MAPPING_MISMATCH: '+group)
        if ma['connection_group']!=group or mb['connection_group']!=group:
            raise ValueError('SPDC_PROTOTYPE_MAPPING_MISMATCH: '+group)
        rot=pair['pair_rotation']
        angle=float(rot['angle_deg'])
        if not math.isfinite(angle) or abs(abs(angle)%360.-180.)>1.e-7:
            raise ValueError('SPDC_PROTOTYPE_SYMMETRY_UNCONFIRMED: expected half-turn')
        for local in probes:
            ga=step04_local_point_to_global(local,ma['placement'])
            gb=step04_local_point_to_global(local,mb['placement'])
            if not _close(_step04_rotate(ga,rot),gb):
                raise ValueError('SPDC_PROTOTYPE_SYMMETRY_UNCONFIRMED: '+group)
        holes=[]
        for h in plan['driving_holes']:
            ga=step04_local_point_to_global(h['local_center_m'],ma['placement'])
            gb=step04_local_point_to_global(h['local_center_m'],mb['placement'])
            expected=_step04_rotate(ga,rot)
            if not _close(gb,expected):raise ValueError('SPDC_PROTOTYPE_GLOBAL_HOLE_MISMATCH: '+group)
            holes.append(dict(hole_id=h['hole_id'],source_global_center=ga,target_global_center=gb,
                              source_global_axis=step04_local_vector_to_global(h['local_axis'],ma['placement']),
                              target_global_axis=step04_local_vector_to_global(h['local_axis'],mb['placement']),
                              symmetry_error_m=math.dist(gb,expected)))
        evidence.append(dict(group_id=group,source_instance=an,target_instance=bn,
            source_placement=ma['placement'],target_placement=mb['placement'],pair_rotation=rot,holes=holes))
        groups.add(group);used.update((an,bn))
    if used!=set(members):raise ValueError('SPDC_PROTOTYPE_MAPPING_INCOMPLETE')
    for hole in list(plan['driving_holes']):
        h=copy.deepcopy(hole);h['part_name']=target
        refs=catalog[target]['referencing_instances']
        h['shared_part_info'].update(part_name=target,referencing_instances=refs,expected_affected_instances=refs,
            shared_part=len(refs)>1,execution_policy='MODIFY_SHARED_PART_ONCE' if len(refs)>1 else 'MODIFY_PART_ONCE')
        plan['driving_holes'].append(h)
    plan['prototype_inheritance']=dict(source_part=source,target_part=target,local_mapping='IDENTITY',
        geometry_parameters_match=True,pairs=evidence,actual_geometry_validation='REQUIRED_BEFORE_MUTATION')


def add_part_inheritance_plan(summary, catalog, plan):
    expand_standard_prototype(summary,catalog,plan)
    members=[]
    for m in _instances(summary):
        if _role(m)!='HOOP':continue
        group=m.get('connection_group')
        if not group:raise ValueError('SPDC_HOOP_GROUP_MAPPING_MISSING: '+m['instance_name'])
        # Part identity always comes from the summary, never a numeric suffix.
        members.append(dict(group_id=group,instance_name=m['instance_name'],part_name=m['part_name'],
                            half_id=m.get('half_id') or m['instance_name'].rsplit('_',1)[-1]))
        # Explicit instance-specific requests cannot be merged into a shared Part.
        if any(m.get(k) for k in ('hole_pattern_override','requires_instance_isolation')):
            raise ValueError('PART_PATTERN_VARIATION_REQUIRES_ISOLATION: '+m['instance_name']+' '+m['part_name'])
    patterns=[]
    for part in sorted(catalog):
        refs=sorted(m['instance_name'] for m in members if m['part_name']==part)
        if refs!=sorted(catalog[part]['referencing_instances']):raise ValueError('SPDC_HOOP_REFERENCE_MISMATCH: '+part)
        holes=[h for h in plan['driving_holes'] if h['part_name']==part]
        patterns.append(dict(part_name=part,hole_pattern=holes,referencing_instances=refs,
                             expected_cut_features=len(holes)))
    counts=dict(unique_hoop_parts=len(patterns),unique_part_cut_count=len(plan['driving_holes']),
                hoop_group_count=len({m['group_id'] for m in members}),half_instance_count=len(members),
                assembly_instance_hole_count=sum(p['expected_cut_features']*len(p['referencing_instances']) for p in patterns))
    plan.update(spdc_part_schema='spdc-part-inheritance-v1',part_patterns=patterns,instance_mapping=members,expected_counts=counts)
    return plan
