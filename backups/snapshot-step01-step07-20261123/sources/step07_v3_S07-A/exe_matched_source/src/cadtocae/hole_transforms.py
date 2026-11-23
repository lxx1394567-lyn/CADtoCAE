"""Step04 orientation -> translation -> global-axis roll contract (Python 2.7)."""
import math


def _step04_xyz(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError('Invalid ' + label + ': expected XYZ')
    result = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError('Invalid ' + label)
        number = float(item)
        if math.isnan(number) or math.isinf(number):
            raise ValueError('Nonfinite ' + label)
        result.append(number)
    return tuple(result)


def _step04_unit(value):
    xyz = _step04_xyz(value, 'vector')
    length = math.sqrt(xyz[0]*xyz[0]+xyz[1]*xyz[1]+xyz[2]*xyz[2])
    if length < 1.e-12:
        raise ValueError('Zero rotation axis/vector')
    return (xyz[0]/length, xyz[1]/length, xyz[2]/length)


def _step04_contract(placement):
    translation = _step04_xyz(placement['translation'], 'placement.translation')
    steps = placement['rotation_steps']
    if not isinstance(steps, (list, tuple)):
        raise ValueError('rotation_steps must be a sequence')
    for step in steps:
        _step04_xyz(step['axis_point'], 'axis_point')
        _step04_unit(step['axis_direction'])
        angle = float(step['angle_deg'])
        if isinstance(step['angle_deg'], bool) or math.isnan(angle) or math.isinf(angle):
            raise ValueError('Invalid angle_deg')
    return translation, steps


def step04_placement_phases(placement):
    """Adapt step04-instance-plan-v1, matching Step04 _instance call order.

    Leading origin rotations orient the Part. The first global non-origin
    axis starts the post-translation phase, including every subsequent step.
    The 1e-12 threshold matches Step04's placement operation tolerance.
    """
    translation, steps = _step04_contract(placement)
    pre, post = [], []
    after_translation = False
    for step in steps:
        center = _step04_xyz(step['axis_point'], 'axis_point')
        if max(abs(center[0]), abs(center[1]), abs(center[2])) > 1.e-12:
            after_translation = True
        if after_translation:
            post.append(step)
        else:
            pre.append(step)
    return translation, pre, post


def _step04_rotate(value, step, direction_only=False, inverse=False):
    axis = _step04_unit(step['axis_direction'])
    center = (0.,0.,0.) if direction_only else _step04_xyz(step['axis_point'], 'axis_point')
    angle = math.radians(float(step['angle_deg']))
    if inverse:
        angle = -angle
    v = (value[0]-center[0], value[1]-center[1], value[2]-center[2])
    dot_value = axis[0]*v[0]+axis[1]*v[1]+axis[2]*v[2]
    cross_value = (axis[1]*v[2]-axis[2]*v[1], axis[2]*v[0]-axis[0]*v[2], axis[0]*v[1]-axis[1]*v[0])
    result = []
    for i in range(3):
        result.append(center[i]+v[i]*math.cos(angle)+cross_value[i]*math.sin(angle)+axis[i]*dot_value*(1.-math.cos(angle)))
    return tuple(result)


def step04_local_point_to_global(point, placement):
    translation, pre, post = step04_placement_phases(placement)
    result = _step04_xyz(point, 'local point')
    for step in pre:
        result = _step04_rotate(result, step)
    result = (result[0]+translation[0], result[1]+translation[1], result[2]+translation[2])
    for step in post:
        result = _step04_rotate(result, step)
    return result


def step04_local_vector_to_global(vector, placement):
    unused, pre, post = step04_placement_phases(placement)
    result = _step04_xyz(vector, 'local vector')
    for step in pre + post:
        result = _step04_rotate(result, step, direction_only=True)
    return _step04_unit(result)


def step04_global_point_to_local(point, placement):
    translation, pre, post = step04_placement_phases(placement)
    result = _step04_xyz(point, 'global point')
    for step in reversed(post):
        result = _step04_rotate(result, step, inverse=True)
    result = (result[0]-translation[0], result[1]-translation[1], result[2]-translation[2])
    for step in reversed(pre):
        result = _step04_rotate(result, step, inverse=True)
    return result


def step04_global_vector_to_local(vector, placement):
    unused, pre, post = step04_placement_phases(placement)
    result = _step04_xyz(vector, 'global vector')
    for step in list(reversed(post)) + list(reversed(pre)):
        result = _step04_rotate(result, step, direction_only=True, inverse=True)
    return _step04_unit(result)


def step04_validate_anchors(placement, anchors, tolerance=1.e-6, results=None):
    _step04_contract(placement)
    if not anchors:
        raise ValueError('SUMMARY_ANCHOR_MISSING: independent local/global assembly anchor required')
    if results is None:
        results = []
    for anchor in anchors:
        local = _step04_xyz(anchor['local_point'], 'anchor local point')
        expected = _step04_xyz(anchor['expected_global'], 'anchor expected global')
        actual = step04_local_point_to_global(local, placement)
        back = step04_global_point_to_local(actual, placement)
        residual, roundtrip = 0., 0.
        for i in range(3):
            residual += (actual[i]-expected[i])**2
            roundtrip += (back[i]-local[i])**2
        residual, roundtrip = math.sqrt(residual), math.sqrt(roundtrip)
        results.append(dict(name=anchor.get('name','anchor'), local_point=local, expected_global=expected,
                            actual_global=actual, error_m=residual, roundtrip_error_m=roundtrip))
        if residual > tolerance or roundtrip > tolerance:
            raise ValueError('SUMMARY_TRANSFORM_INCONSISTENT: %s anchor error %.12g m (tolerance %.12g m)' %
                             (anchor.get('name','anchor'), residual, tolerance))
    return results
