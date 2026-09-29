"""Pure geometry shared by tests and the embedded Abaqus Python 2.7/3 runtime.

No Abaqus imports, numpy, or engineering coordinates are required here.
"""
import math


def finite(value):
    return not (math.isnan(value) or math.isinf(value))


def vector(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError('Expected a 3D vector')
    _runtime_values_19 = []
    for x in value:
        _runtime_values_19.append(float(x))
    result = tuple(_runtime_values_19)
    _runtime_match_20 = True
    for x in result:
        if not _runtime_match_20:
            break
        if not finite(x):
            _runtime_match_20 = False
    if not _runtime_match_20:
        raise ValueError('Nonfinite vector')
    return result


def add(a, b):
    _runtime_values_18 = []
    for i in range(3):
        _runtime_values_18.append(a[i] + b[i])
    return tuple(_runtime_values_18)


def sub(a, b):
    _runtime_values_17 = []
    for i in range(3):
        _runtime_values_17.append(a[i] - b[i])
    return tuple(_runtime_values_17)


def scale(a, s):
    _runtime_values_16 = []
    for x in a:
        _runtime_values_16.append(x * s)
    return tuple(_runtime_values_16)


def dot(a, b):
    _runtime_total_15 = 0
    for i in range(3):
        _runtime_total_15 += a[i] * b[i]
    return _runtime_total_15


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    length = norm(a)
    if length < 1.e-12:
        raise ValueError("Zero direction / degenerate frame")
    return scale(a, 1.0 / length)


def matvec(matrix, point):
    _runtime_values_14 = []
    for row in matrix:
        _runtime_values_14.append(dot(row, point))
    return tuple(_runtime_values_14)


def transpose(matrix):
    _runtime_values_12 = []
    for i in range(3):
        _runtime_values_13 = []
        for j in range(3):
            _runtime_values_13.append(matrix[j][i])
        _runtime_values_12.append(tuple(_runtime_values_13))
    return tuple(_runtime_values_12)


def transform(pose, point):
    return add(matvec(pose["rotation"], point), pose["translation"])


def inverse_point(pose, point):
    return matvec(transpose(pose["rotation"]), sub(point, pose["translation"]))


def fit_pose(local_points, global_points, tolerance):
    """Recover a proper rigid transform from corresponding dependent vertices.

    Use a well-spaced noncollinear triple, then verify EVERY correspondence.
    A topology mismatch or reflection cannot pass the complete residual check.
    """
    if len(local_points) != len(global_points) or len(local_points) < 3:
        raise ValueError('unsupported transform contract: vertex correspondence missing')
    first = local_points[0]
    second = max(range(1, len(local_points)), key=lambda i: norm(sub(local_points[i], first)))
    line = sub(local_points[second], first)
    third = max(range(1, len(local_points)), key=lambda i: norm(cross(line, sub(local_points[i], first))))

    def basis(points):
        x = unit(sub(points[second], points[0]))
        z = unit(cross(x, sub(points[third], points[0])))
        return (x, cross(z, x), z)
    local = basis(local_points)
    world = basis(global_points)
    _runtime_values_7 = []
    for i in range(3):
        _runtime_values_8 = []
        for j in range(3):
            _runtime_total_9 = 0
            for k in range(3):
                _runtime_total_9 += world[k][i] * local[k][j]
            _runtime_values_8.append(_runtime_total_9)
        _runtime_values_7.append(tuple(_runtime_values_8))
    rotation = tuple(_runtime_values_7)
    pose = {'rotation': rotation, 'translation': sub(global_points[0], matvec(rotation, first))}
    _runtime_values_10 = None
    for p, q in zip(local_points, global_points):
        _runtime_value_11 = norm(sub(transform(pose, p), q))
        if _runtime_values_10 is None or _runtime_value_11 > _runtime_values_10:
            _runtime_values_10 = _runtime_value_11
    if _runtime_values_10 is None:
        raise ValueError('max() arg is an empty sequence')
    residual = _runtime_values_10
    if residual > tolerance:
        raise ValueError('unsupported transform contract: nonrigid/mismatched geometry')
    pose['max_residual_m'] = residual
    return pose


def rotate_point(point, rotation):
    center = vector(rotation["axis_point"])
    axis = unit(vector(rotation["axis_direction"]))
    angle = float(rotation["angle_deg"])
    if not finite(angle):
        raise ValueError("Nonfinite rotation")
    angle = math.radians(angle)
    v = sub(point, center)
    result = add(add(scale(v, math.cos(angle)), scale(cross(axis, v), math.sin(angle))),
                 scale(axis, dot(axis, v)*(1.0-math.cos(angle))))
    return add(center, result)


def placement_candidates(placement):
    """Do not guess where legacy summary translation belongs among rotations.

    Enumerate possible insertions; ONLY runtime geometry can select a candidate.
    More than one insertion producing the same rigid transform is harmless.
    """
    if "translation" not in placement or "rotation_steps" not in placement:
        raise ValueError("unsupported transform contract: incomplete placement")
    translation = vector(placement["translation"])
    rotations = placement["rotation_steps"]
    if not isinstance(rotations, list) or len(rotations) > 8:
        raise ValueError("unsupported transform contract: rotation_steps")
    result = []
    for split in range(len(rotations)+1):
        def apply(point):
            for index in range(len(rotations)+1):
                if index == split:
                    point = add(point, translation)
                if index < len(rotations):
                    point = rotate_point(point, rotations[index])
            return point
        origin = apply((0., 0., 0.))
        columns = [sub(apply(v), origin) for v in ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))]
        result.append({"rotation": transpose(columns), "translation": origin, "translation_after_rotations": split})
    return result


def verify_pose_contract(pose, placement, points, tolerance):
    candidates = placement_candidates(placement)
    _runtime_values_5 = []
    for p in candidates:
        _runtime_match_6 = True
        for x in points:
            if not _runtime_match_6:
                break
            if not norm(sub(transform(p, x), transform(pose, x))) <= tolerance:
                _runtime_match_6 = False
        if _runtime_match_6:
            _runtime_values_5.append(p)
    matches = _runtime_values_5
    if not matches:
        raise ValueError('unsupported transform contract: summary does not match actual pose')
    return [p['translation_after_rotations'] for p in matches]


def patch_limits(station, half_length, length, tolerance):
    _runtime_match_3 = True
    for v in (station, half_length, length):
        if not _runtime_match_3:
            break
        if not finite(float(v)):
            _runtime_match_3 = False
    _runtime_condition_4 = not _runtime_match_3
    if not _runtime_condition_4:
        _runtime_condition_4 = half_length <= tolerance
    if _runtime_condition_4:
        raise ValueError('Invalid patch dimensions')
    low, high = (station - half_length, station + half_length)
    if low <= tolerance or high >= length - tolerance:
        raise ValueError('Patch boundaries must stay inside beam length')
    return (low, high)


def shell_outer_plane(point, normal, outward, thickness, offset_type, offset):
    """Reference geometry = midsurface + offset*thickness*positive normal.

    Physical SIDE1 = reference + (0.5-offset)*t*n;
    physical SIDE2 = reference + (-0.5-offset)*t*n.
    """
    normal, outward = unit(normal), unit(outward)
    alignment = dot(normal, outward)
    if abs(alignment) < 1.0-1.e-6:
        raise ValueError("Cannot uniquely determine physical side")
    if not finite(thickness) or thickness <= 0:
        raise ValueError("Invalid shell thickness")
    if offset_type == "MIDDLE_SURFACE":
        offset = 0.0
    elif offset_type == "TOP_SURFACE":
        offset = 0.5
    elif offset_type == "BOTTOM_SURFACE":
        offset = -0.5
    elif offset_type != "SINGLE_VALUE":
        raise ValueError("Unsupported shell offset interpretation: " + offset_type)
    if not finite(offset):
        raise ValueError("Invalid shell offset")
    sign = 1.0 if alignment > 0 else -1.0
    distance = (sign*0.5-offset)*thickness
    return {"point": add(point, scale(normal, distance)), "normal": outward,
            "physical_side": "SIDE1" if sign > 0 else "SIDE2", "thickness_m": thickness,
            "offset_fraction": offset, "offset_type": offset_type,
            "reference_to_physical_signed_m": distance,
            "offset_interpretation": "physical = reference + (side_sign/2 - offset_fraction) * thickness * positive_normal"}


def plane_intersection(points, point, normal, tolerance):
    """Intersection of a convex planar face polygon and a plane; no mutation."""
    found = []
    distances = [dot(sub(p, point), normal) for p in points]
    _runtime_match_1 = True
    for value in distances:
        if not _runtime_match_1:
            break
        if not abs(value) <= tolerance:
            _runtime_match_1 = False
    if _runtime_match_1:
        raise ValueError('Ambiguous coplanar brace face')
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        da, db = (distances[i], distances[(i + 1) % len(points)])
        if abs(da) <= tolerance:
            found.append(a)
        if da < -tolerance and db > tolerance or (db < -tolerance and da > tolerance):
            found.append(add(a, scale(sub(b, a), da / (da - db))))
    unique = []
    for candidate in found:
        _runtime_match_2 = False
        for p in unique:
            if _runtime_match_2:
                break
            if norm(sub(candidate, p)) <= tolerance:
                _runtime_match_2 = True
        if not _runtime_match_2:
            unique.append(candidate)
    if len(unique) not in (0, 1, 2):
        raise ValueError('Unsupported nonconvex/multiple brace intersection')
    return unique if len(unique) == 2 and norm(sub(unique[0], unique[1])) > tolerance else []
