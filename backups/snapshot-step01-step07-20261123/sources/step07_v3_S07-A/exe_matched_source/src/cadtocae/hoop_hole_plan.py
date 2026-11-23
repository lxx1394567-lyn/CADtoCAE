"""HOOP input planning; no CAE API calls or model mutations in this module.

Coordinates mirror Step02's corrected explicit tangent-chain profile (main,
scripts/make_cae_runner.py: _hoop_band_dimensions/_hoop_band_profile_geometry).
The older offset-profile implementation is deliberately not imported.
"""
from dataclasses import asdict, dataclass
import math

from .analysis_capability import is_hoop_member, match_hoop_component
from .hole_inputs import positive_number
from .hole_plan import _instances

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
                left_straight_length_m=-xmin-tangent,right_straight_length_m=xmax-tangent)


def unique_hoop_parts(summary, components):
    members = _instances(summary)
    result = {}
    for m in members:
        if not is_hoop_member(m):
            continue
        part = m['part_name']
        if part in result:
            continue
        c = match_hoop_component(m, components)
        references = [r for r in members if r['part_name']==part]
        if any(not is_hoop_member(r) for r in references):
            raise ValueError('Mixed canonical roles reference HOOP Part '+part)
        if any(r.get('dependent') is False for r in references):
            raise ValueError('Independent HOOP instance requires review: '+part)
        for r in references:
            match_hoop_component(r,components)
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
    diameter_m: float
    local_center_m: tuple
    local_axis: tuple
    shared_part_info: dict
    validation_status: str
    coordinate_convention: str = CONVENTION
    runtime_status: str = 'CUT_PENDING_RUNTIME_PREFLIGHT'


def build_hoop_hole_plan(catalog, rows):
    holes, disabled, seen = [], [], set()
    expected = {(part,h) for part in catalog for h in ('HOOP_LEFT','HOOP_RIGHT')}
    for row in rows:
        part, hole = row['part_name'],row['hole_id']
        key = (part,hole)
        if key not in expected or key in seen:
            raise ValueError('Unknown/duplicate HOOP Part or hole ID: '+str(key))
        seen.add(key)
        end = 'LEFT' if hole=='HOOP_LEFT' else 'RIGHT'
        if row['end_reference'] != end or row['hole_type'] != 'ROUND':
            raise ValueError('HOOP_LEFT/RIGHT requires matching end and ROUND')
        if not row['enabled']:
            disabled.append(dict(part_name=part,hole_id=hole))
            continue
        distance, side, diameter = [positive_number(row.get(k),k)/1000. for k in
                                   ('distance_from_end_mm','distance_from_side_mm','diameter_mm')]
        g = catalog[part]['geometry']; radius = diameter/2.
        flat = g['left_straight_length_m'] if end=='LEFT' else g['right_straight_length_m']
        tolerance = 1.e-12
        if distance <= radius+tolerance or side <= radius+tolerance or side+radius >= g['width_m']-tolerance:
            raise ValueError(part+'/'+hole+': hole crosses end/width edge')
        if distance+radius >= flat-tolerance:
            raise ValueError(part+'/'+hole+': hole enters transition fillet / arc region')
        x = g['left_end_x_m']+distance if end=='LEFT' else g['right_end_x_m']-distance
        refs = catalog[part]['referencing_instances']
        shared = dict(part_name=part,referencing_instances=refs,shared_part=len(refs)>1,
                      hole_pattern_identical=True,requires_instance_isolation=False,
                      execution_policy='MODIFY_SHARED_PART_ONCE' if len(refs)>1 else 'MODIFY_PART_ONCE',
                      expected_affected_instances=refs)
        holes.append(asdict(HoopDrivingHoleSpec(part,hole,end,distance,side,'ROUND',diameter,
                       (x,g['thickness_m']/2.,side),(0.,1.,0.),shared,'VALIDATED_INPUT')))
    if seen != expected:
        raise ValueError('Missing HOOP Part hole rows: '+str(sorted(expected-seen)))
    return dict(runtime_enabled=True,coordinate_convention=CONVENTION,
                driving_holes=holes,disabled_holes=disabled,
                part_geometry={p:c['geometry'] for p,c in catalog.items()})
