"""HOOP input planning; no CAE API calls or model mutations in this module.

Coordinates mirror Step02's corrected explicit tangent-chain profile (main,
scripts/make_cae_runner.py: _hoop_band_dimensions/_hoop_band_profile_geometry).
The older offset-profile implementation is deliberately not imported.
"""
from dataclasses import asdict, dataclass
import math

from .analysis_capability import is_hoop_member
from .hole_component_resolution import resolve_hole_component
from .hole_inputs import positive_number
from .hole_plan import _instances
from .hole_profiles import hoop_hole_id, hole_dimensions, validate_hoop_bounds, validate_hoop_overlap

CONVENTION = 'STEP02_HOOP_INNER_PROFILE_Y0_MATERIAL_POSITIVE_Y'


def hoop_geometry(component):
    if component.get('section_kind') != 'HOOP_BAND' or component.get('model_policy') != 'SOLID':
        raise ValueError('HOOP requires SOLID HOOP_BAND geometry')
    p = component.get('section_params_m') or {}
    d, w, t, left, right = [positive_number(p.get(k), k) for k in
                          ('diameter_m','width_m','t_m','left_extension_m','right_extension_m')]
    rf = p.get('transition_fillet_m', 0.)
    if isinstance(rf, bool) or not isinstance(rf,(int,float)) or not math.isfinite(rf) or rf < 0:
        raise ValueError('transition_fillet_m must be finite and nonnegative')
    ri, ro = d/2., d/2.+t
    for name, expected in (('inner_radius_m',ri),('outer_radius_m',ro)):
        if name in p and abs(positive_number(p[name],name)-expected) > 1.e-9:
            raise ValueError('Inconsistent HOOP '+name)
    tangent = math.sqrt(ri*(ri+2.*(rf+t)))
    xmin, xmax = -ro-left, ro+right
    if min(-xmin,xmax)-tangent <= max(ro,left,right,rf+t)*1.e-10:
        raise ValueError('HOOP RF leaves no straight ear plate')
    return dict(convention=CONVENTION, section_kind='HOOP_BAND', model_policy='SOLID', width_m=w, thickness_m=t,
                left_end_x_m=xmin,right_end_x_m=xmax,straight_tangent_x_m=tangent,
                left_straight_length_m=-xmin-tangent,right_straight_length_m=xmax-tangent,
                left_transition_boundary_x_m=-tangent,right_transition_boundary_x_m=tangent)


def unique_hoop_parts(summary, components):
    members = _instances(summary)
    result = {}
    for m in members:
        if not is_hoop_member(m):
            continue
        part = m['part_name']
        if part in result:
            continue
        c = resolve_hole_component(m, components)[0]
        references = [r for r in members if r['part_name']==part]
        if any(not is_hoop_member(r) for r in references):
            raise ValueError('Mixed canonical roles reference HOOP Part '+part)
        if any(r.get('dependent') is False for r in references):
            raise ValueError('Independent HOOP instance requires review: '+part)
        for r in references:
            resolve_hole_component(r,components)
        result[part] = dict(component=c,geometry=hoop_geometry(c),
                            referencing_instances=sorted(r['instance_name'] for r in references))
    return result


@dataclass(frozen=True)
class HoopDrivingHoleSpec:
    part_name: str
    hole_id: str
    end_reference: str
    distance_from_end_m: float
    distance_from_side_m: float
    hole_type: str
    width_m: float
    total_length_m: float
    local_center_m: tuple
    local_axis: tuple
    local_major_axis: tuple | None
    shared_part_info: dict
    validation_status: str
    coordinate_convention: str = CONVENTION
    runtime_status: str = 'CUT_PENDING_RUNTIME_PREFLIGHT'


def build_hoop_hole_plan(catalog, rows):
    holes, disabled, seen = [], [], set()
    for row in rows:
        part, hole = row['part_name'],hoop_hole_id(row['hole_id'])
        key = (part,hole)
        if part not in catalog or key in seen:
            raise ValueError('Unknown/duplicate HOOP Part or hole ID: '+str(key))
        seen.add(key)
        end = 'LEFT' if hole.startswith('HOOP_LEFT_') else 'RIGHT'
        if row['end_reference'] != end or row['hole_type'] not in ('ROUND','SLOT'):
            raise ValueError('HOOP hole requires matching end and ROUND/SLOT')
        if not row['enabled']:
            disabled.append(dict(part_name=part,hole_id=hole))
            continue
        distance, side = [positive_number(row.get(k),k)/1000. for k in
                          ('distance_from_end_mm','distance_from_side_mm')]
        width = positive_number(row.get('width_mm',row.get('diameter_mm')),'width_mm')/1000.
        length_input = row.get('slot_total_length_mm')
        length = width if row['hole_type']=='ROUND' and length_input in (None,'') else positive_number(length_input,'slot_total_length_mm')/1000.
        width,length = hole_dimensions(dict(hole_type=row['hole_type'],width_m=width,total_length_m=length))
        direction = row.get('slot_major_axis')
        axes = {'PLATE_LENGTH':(1.,0.,0.),'BAND_WIDTH':(0.,0.,1.)}
        if row['hole_type']=='SLOT' and direction not in axes:
            raise ValueError('HOOP SLOT major axis required: PLATE_LENGTH or BAND_WIDTH')
        if direction not in (None,'') and direction not in axes:
            raise ValueError('Invalid HOOP major axis')
        major = axes.get(direction)
        g = catalog[part]['geometry']
        x = g['left_end_x_m']+distance if end=='LEFT' else g['right_end_x_m']-distance
        refs = catalog[part]['referencing_instances']
        shared = dict(part_name=part,referencing_instances=refs,shared_part=len(refs)>1,
                      hole_pattern_identical=True,requires_instance_isolation=False,
                      execution_policy='MODIFY_SHARED_PART_ONCE' if len(refs)>1 else 'MODIFY_PART_ONCE',
                      expected_affected_instances=refs)
        spec = asdict(HoopDrivingHoleSpec(part,hole,end,distance,side,row['hole_type'],width,length,
                       (x,g['thickness_m']/2.,side),(0.,1.,0.),major,shared,'VALIDATED_INPUT'))
        spec['local_center'] = spec['local_center_m']
        if row['hole_type']=='ROUND':spec['diameter_m']=width  # Legacy read-only compatibility.
        validate_hoop_bounds(spec,g)
        holes.append(spec)
    validate_hoop_overlap(holes)
    return dict(runtime_enabled=True,coordinate_convention=CONVENTION,
                driving_holes=holes,disabled_holes=disabled,
                part_geometry={p:c['geometry'] for p,c in catalog.items()})
