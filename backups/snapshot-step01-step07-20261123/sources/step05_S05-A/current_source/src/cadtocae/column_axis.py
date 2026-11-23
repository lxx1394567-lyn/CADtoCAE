"""Small shared axial arithmetic; also embedded verbatim in Abaqus Python 2.7."""
import math


def cct_dot(a, b):
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def cct_sub(a, b):
    return (a[0]-b[0],a[1]-b[1],a[2]-b[2])


def cct_unit(value):
    if len(value) != 3:
        raise ValueError('Invalid column axis')
    values = []
    for v in value:
        v = float(v)
        if math.isnan(v) or math.isinf(v):
            raise ValueError('Invalid column axis')
        values.append(v)
    length = math.sqrt(cct_dot(values,values))
    if length < 1.e-12:
        raise ValueError('Invalid column axis')
    return (values[0]/length,values[1]/length,values[2]/length)


def cct_placement_axis(placement):
    # Rotations determine direction independently of translation order. The
    # final origin is verified against actual Instance geometry at runtime.
    axis = (0.,0.,1.)
    steps = placement.get('rotation_steps') or []
    if not steps and placement.get('rotation_angle'):
        steps = [dict(axis_direction=placement['rotation_axis'],angle_deg=placement['rotation_angle'])]
    for step in steps:
        k = cct_unit(step['axis_direction'])
        angle = math.radians(float(step['angle_deg']))
        if math.isnan(angle) or math.isinf(angle):
            raise ValueError('Invalid column rotation')
        c,s = math.cos(angle),math.sin(angle)
        cross = (k[1]*axis[2]-k[2]*axis[1],k[2]*axis[0]-k[0]*axis[2],k[0]*axis[1]-k[1]*axis[0])
        along = cct_dot(k,axis)
        axis = (axis[0]*c+cross[0]*s+k[0]*along*(1.-c),
                axis[1]*c+cross[1]*s+k[1]*along*(1.-c),
                axis[2]*c+cross[2]*s+k[2]*along*(1.-c))
    axis = cct_unit(axis)
    explicit = placement.get('axis_direction')
    if explicit is not None:
        explicit = cct_unit(explicit)
        if steps and cct_dot(explicit,axis) < 1.-1.e-10:
            raise ValueError('Column axis_direction disagrees with placement rotations')
        axis = explicit
    return axis


def cct_axial_layout(members, tolerance=1.e-6):
    """Scalar coordinates are projections on the lower column's +local-Z axis."""
    common = cct_unit(members[1]['axis_direction'])
    anchor = members[1]['origin']
    ranges, offsets, signs = [], [], []
    for member in members:
        axis = cct_unit(member['axis_direction'])
        sign = cct_dot(axis,common)
        if abs(abs(sign)-1.) > 1.e-10:
            raise ValueError('COLUMN_COLUMN_TIE axes are not parallel')
        for station in (0.,member['length_m']):
            point = (member['origin'][0]+axis[0]*station,
                     member['origin'][1]+axis[1]*station,
                     member['origin'][2]+axis[2]*station)
            delta = cct_sub(point,anchor)
            projection = cct_dot(delta,common)
            radial = (delta[0]-common[0]*projection,delta[1]-common[1]*projection,delta[2]-common[2]*projection)
            if math.sqrt(cct_dot(radial,radial)) > tolerance:
                raise ValueError('COLUMN_COLUMN_TIE axes are not coaxial')
        start = cct_dot(member['origin'],common)
        end = start+sign*member['length_m']
        ranges.append([min(start,end),max(start,end)])
        offsets.append(start)
        signs.append(sign)
    overlap = [max(ranges[0][0],ranges[1][0]),min(ranges[0][1],ranges[1][1])]
    length = overlap[1]-overlap[0]
    if length <= tolerance:
        raise ValueError('COLUMN_COLUMN_TIE has no valid axial overlap')
    local, cuts = [], []
    for i in range(2):
        interval = sorted([(overlap[0]-offsets[i])/signs[i],(overlap[1]-offsets[i])/signs[i]])
        partitions = []
        for j in range(2):
            if abs(interval[j]) <= tolerance:
                interval[j] = 0.
            elif abs(interval[j]-members[i]['length_m']) <= tolerance:
                interval[j] = members[i]['length_m']
            else:
                partitions.append(interval[j])
        local.append(interval)
        cuts.append(partitions)
    return dict(common_axis=common,upper_global_range=ranges[0],lower_global_range=ranges[1],
                actual_overlap=overlap,overlap_length=length,local_overlaps=local,partitions=cuts)


def cct_same_interval(upper, lower, overlap, tolerance=1.e-6):
    for interval in (upper,lower):
        for i in range(2):
            if abs(interval[i]-overlap[i]) > tolerance:
                raise ValueError('COLUMN_COLUMN_TIE regions do not share the same overlap interval')
