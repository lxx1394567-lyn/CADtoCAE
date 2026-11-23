"""Shared hole-profile geometry, usable in generators and Abaqus Python 2.7."""
import math
import re

HOLE_PROFILE_TOL = 1.e-9


def hole_dimensions(hole):
    kind = hole.get('hole_type')
    width = hole.get('width_m', hole.get('diameter_m'))
    length = hole.get('total_length_m', width if kind == 'ROUND' else None)
    for value in (width, length):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value) or math.isinf(value) or value <= 0.:
            raise ValueError('Invalid hole width / total length')
    if kind not in ('ROUND', 'SLOT') or length < width-HOLE_PROFILE_TOL:
        raise ValueError('Invalid hole profile: total length must be >= width')
    if kind == 'ROUND' and abs(length-width) > HOLE_PROFILE_TOL:
        raise ValueError('ROUND total length must equal diameter')
    return width, width if abs(length-width) <= HOLE_PROFILE_TOL else length


def is_round_profile(hole):
    width, length = hole_dimensions(hole)
    return hole['hole_type'] == 'ROUND' or abs(length-width) <= HOLE_PROFILE_TOL


def is_slot_profile(hole):
    width, length = hole_dimensions(hole)
    return length > width+HOLE_PROFILE_TOL


def hoop_hole_id(value):
    if value in ('HOOP_LEFT', 'HOOP_RIGHT'):
        return value+'_01'
    if not isinstance(value, type(u'')) and not isinstance(value, str):
        raise ValueError('Invalid HOOP hole ID')
    if not re.match(r'^HOOP_(LEFT|RIGHT)_[0-9]{2,}$', value) or int(value.rsplit('_',1)[1]) <= 0:
        raise ValueError('Invalid HOOP hole ID: '+value)
    return value


def hoop_profile(hole):
    width, length = hole_dimensions(hole)
    major = hole.get('local_major_axis')
    if is_slot_profile(hole) and tuple(major or ()) not in ((1.,0.,0.), (0.,0.,1.)):
        raise ValueError('HOOP SLOT requires PLATE_LENGTH or BAND_WIDTH')
    major = tuple(major) if major is not None else (1.,0.,0.)
    if major not in ((1.,0.,0.), (0.,0.,1.)):
        raise ValueError('Invalid HOOP local major axis')
    r, h = width/2., (length-width)/2.
    return r, h, (major[0], major[2])


def hole_area(hole):
    width, length = hole_dimensions(hole)
    return math.pi*width*width/4.+width*(length-width)


def hole_perimeter(hole):
    width, length = hole_dimensions(hole)
    return math.pi*width+2.*(length-width)


def hoop_boundary_probes(hole):
    """Return X/Z offsets and outward profile normals, away from seams."""
    r,h,u = hoop_profile(hole)
    v = (-u[1],u[0])
    result = []
    if is_round_profile(hole):
        for i in range(12):
            a = 2.*math.pi*(i+.5)/12.
            n = (math.cos(a), math.sin(a))
            result.append(((r*n[0],r*n[1]),n))
    else:
        for sign in (-1.,1.):
            for fraction in (-.5,.5):
                result.append(((h*fraction*u[0]+sign*r*v[0],h*fraction*u[1]+sign*r*v[1]),(sign*v[0],sign*v[1])))
            for i in range(4):
                a = -math.pi/2.+math.pi*(i+.5)/4.
                n = (sign*math.cos(a)*u[0]+math.sin(a)*v[0],sign*math.cos(a)*u[1]+math.sin(a)*v[1])
                result.append(((sign*h*u[0]+r*n[0],sign*h*u[1]+r*n[1]),n))
    return result


def validate_hoop_bounds(hole, geometry, tolerance=1.e-12):
    r,h,u = hoop_profile(hole)
    center = hole['local_center_m']
    end = hole['end_reference']
    if end not in ('LEFT','RIGHT') or not hoop_hole_id(hole['hole_id']).startswith('HOOP_'+end+'_'):
        raise ValueError('HOOP Part-local end reference mismatch')
    low,high = ((geometry['left_end_x_m'],-geometry['straight_tangent_x_m']) if end=='LEFT'
                else (geometry['straight_tangent_x_m'],geometry['right_end_x_m']))
    ex,ez = r+h*abs(u[0]),r+h*abs(u[1])
    if center[0]-ex <= low+tolerance or center[0]+ex >= high-tolerance:
        raise ValueError('HOOP profile crosses free edge / transition fillet / arc')
    if center[2]-ez <= tolerance or center[2]+ez >= geometry['width_m']-tolerance:
        raise ValueError('HOOP profile crosses width edge')


def _hole_segment(hole):
    r,h,u = hoop_profile(hole)
    c = hole['local_center_m']
    return (c[0]-h*u[0],c[2]-h*u[1]),(c[0]+h*u[0],c[2]+h*u[1]),r


def _hole_point_segment_distance(p,a,b):
    d = (b[0]-a[0],b[1]-a[1])
    length2 = d[0]*d[0]+d[1]*d[1]
    t = max(0.,min(1.,((p[0]-a[0])*d[0]+(p[1]-a[1])*d[1])/length2)) if length2 else 0.
    return math.hypot(p[0]-a[0]-t*d[0],p[1]-a[1]-t*d[1])


def validate_hoop_overlap(holes):
    # Major axes are X or Z; an axis-aligned segment intersection is exact here.
    for i,a in enumerate(holes):
        p,q,ra = _hole_segment(a)
        for b in holes[i+1:]:
            if a['part_name'] != b['part_name']:
                continue
            x,y,rb = _hole_segment(b)
            overlaps = all([max(min(p[k],q[k]),min(x[k],y[k])) <= min(max(p[k],q[k]),max(x[k],y[k])) for k in (0,1)])
            distance = 0. if overlaps else min(_hole_point_segment_distance(p,x,y),_hole_point_segment_distance(q,x,y),
                                               _hole_point_segment_distance(x,p,q),_hole_point_segment_distance(y,p,q))
            if distance <= ra+rb+HOLE_PROFILE_TOL:
                raise ValueError('HOOP_HOLE_OVERLAP: '+a['hole_id']+' / '+b['hole_id'])
