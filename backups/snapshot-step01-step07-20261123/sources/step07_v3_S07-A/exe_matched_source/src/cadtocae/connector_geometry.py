"""Shared SP_SC connector hole contracts; compatible with Abaqus Python 2.7."""
import math

PROFILE_TOL = 1.e-9


def require_sp_sc(holes, structure_type=None):
    value = structure_type if structure_type is not None else holes.get('structure_type')
    if value != 'SP_SC':
        raise ValueError('UNSUPPORTED_STRUCTURE_TYPE: expected SP_SC, got '+str(value))


def connector_profile(hole):
    kind=hole.get('hole_type','SLOT')
    if kind not in ('SLOT','ROUND'):raise ValueError('UNSUPPORTED_HOLE_PROFILE: '+str(kind))
    width=hole.get('width_m');length=hole.get('total_length_m')
    if (isinstance(width,bool) or isinstance(length,bool) or not isinstance(width,(int,float))
            or not isinstance(length,(int,float))):raise ValueError('UNSUPPORTED_HOLE_PROFILE: numeric dimensions required')
    if math.isnan(width) or math.isinf(width) or math.isnan(length) or math.isinf(length) or width<=0. or length<=0.:
        raise ValueError('UNSUPPORTED_HOLE_PROFILE: positive finite dimensions required')
    if length < width-PROFILE_TOL:raise ValueError('UNSUPPORTED_HOLE_PROFILE: length below width')
    circular=abs(length-width)<=PROFILE_TOL
    if kind=='ROUND' and not circular:raise ValueError('UNSUPPORTED_HOLE_PROFILE: ROUND length differs from diameter')
    return width, length, circular


def matched_hole_geometry(source,target):
    sw,sl,sc=connector_profile(source);tw,tl,tc=connector_profile(target)
    if abs(sw-tw)>PROFILE_TOL or abs(sl-tl)>PROFILE_TOL or sc!=tc:
        raise ValueError('HOLE_GEOMETRY_MISMATCH: source/target dimensions differ')
    if not sc and source['hole_type']!=target['hole_type']:
        raise ValueError('HOLE_GEOMETRY_MISMATCH: source/target profiles differ')
    return sw,sl,sc


def parallel_hole_axes(a,b,label):
    if len(a)!=3 or len(b)!=3:raise ValueError('HOLE_GEOMETRY_MISMATCH: '+label)
    if any([math.isnan(x) or math.isinf(x) for x in list(a)+list(b)]):raise ValueError('HOLE_GEOMETRY_MISMATCH: '+label)
    an=math.sqrt(sum([x*x for x in a]));bn=math.sqrt(sum([x*x for x in b]))
    if an<1.e-12 or bn<1.e-12:raise ValueError('HOLE_GEOMETRY_MISMATCH: zero '+label)
    cosine=sum([x*y for x,y in zip(a,b)])/(an*bn)
    if abs(abs(cosine)-1.)>1.e-8:raise ValueError('HOLE_GEOMETRY_MISMATCH: nonparallel '+label)


def check_hole_coaxial(a,b,axis):
    d=[y-x for x,y in zip(a,b)]
    n=math.sqrt(sum([v*v for v in axis]))
    if n<1.e-12:raise ValueError('SOURCE_TARGET_HOLE_NOT_COAXIAL: zero axis')
    c=(d[1]*axis[2]-d[2]*axis[1],d[2]*axis[0]-d[0]*axis[2],d[0]*axis[1]-d[1]*axis[0])
    if math.sqrt(sum([v*v for v in c]))/n>1.e-6:
        raise ValueError('SOURCE_TARGET_HOLE_NOT_COAXIAL')
