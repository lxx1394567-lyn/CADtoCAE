# Standalone Python 2.7 runtime. DATA supplied by the desktop generator.
import math


def text(value):
    try:
        text_type = unicode
    except NameError:
        text_type = str
    return value if isinstance(value, text_type) else value.decode('utf-8')


def lookup(repo, name):
    matches = [key for key in repo.keys() if text(key) == text(name)]
    if len(matches) != 1:
        raise ValueError('Expected unique %r; available keys: %r' % (name, list(repo.keys())))
    return repo[matches[0]]


def sub(a, b):
    _runtime_values_16 = []
    for x, y in zip(a, b):
        _runtime_values_16.append(x - y)
    return tuple(_runtime_values_16)


def dot(a, b):
    _runtime_total_15 = 0
    for x, y in zip(a, b):
        _runtime_total_15 += x * y
    return _runtime_total_15


def unit(v):
    length = math.sqrt(dot(v, v))
    if length < 1e-10:
        raise ValueError('Degenerate geometry direction')
    _runtime_values_14 = []
    for x in v:
        _runtime_values_14.append(x / length)
    return tuple(_runtime_values_14)


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def section_center(instance, name):
    region = lookup(instance.sets, name)
    _runtime_values_11 = []
    for edge in region.edges:
        for i in edge.getVertices():
            _runtime_values_11.append(i)
    ids = sorted(set(_runtime_values_11))
    if not ids:
        raise ValueError('Validated beam section Set is empty: ' + name)
    points = [instance.vertices[i].pointOn[0] for i in ids]
    _runtime_values_12 = []
    for i in range(3):
        _runtime_total_13 = 0
        for p in points:
            _runtime_total_13 += p[i]
        _runtime_values_12.append(_runtime_total_13 / len(points))
    return tuple(_runtime_values_12)


def select_lower_flange(beam, width):
    """Select actual Assembly face using validated sections, width and gravity.

    No instance transform or plane construction: all vertices are world geometry.
    """
    lo = section_center(beam, 'STEP05_BEAM_C_MINUS_80')
    hi = section_center(beam, 'STEP05_BEAM_C_PLUS_80')
    axis = unit(sub(hi, lo))
    if abs(math.sqrt(dot(sub(hi, lo), sub(hi, lo))) - 0.16) > 1e-06:
        raise ValueError('Validated C +/-80 section separation is not 0.160 m')
    transverse = unit(cross((0.0, 0.0, 1.0), axis))
    height = unit(cross(axis, transverse))
    _runtime_values_4 = None
    for v in beam.vertices:
        _runtime_value_5 = dot(v.pointOn[0], height)
        if _runtime_values_4 is None or _runtime_value_5 < _runtime_values_4:
            _runtime_values_4 = _runtime_value_5
    if _runtime_values_4 is None:
        raise ValueError('min() arg is an empty sequence')
    floor = _runtime_values_4
    matches = []
    for face in beam.faces:
        points = [beam.vertices[i].pointOn[0] for i in face.getVertices()]
        if len(points) != 4:
            continue
        if abs(dot(unit(face.getNormal()), height)) < 1.0 - 1e-06:
            continue
        _runtime_match_6 = False
        for p in points:
            if _runtime_match_6:
                break
            if abs(dot(p, height) - floor) > 1e-06:
                _runtime_match_6 = True
        if _runtime_match_6:
            continue
        _runtime_values_7 = None
        for p in points:
            _runtime_value_8 = dot(p, transverse)
            if _runtime_values_7 is None or _runtime_value_8 > _runtime_values_7:
                _runtime_values_7 = _runtime_value_8
        if _runtime_values_7 is None:
            raise ValueError('max() arg is an empty sequence')
        _runtime_values_9 = None
        for p in points:
            _runtime_value_10 = dot(p, transverse)
            if _runtime_values_9 is None or _runtime_value_10 < _runtime_values_9:
                _runtime_values_9 = _runtime_value_10
        if _runtime_values_9 is None:
            raise ValueError('min() arg is an empty sequence')
        span = _runtime_values_7 - _runtime_values_9
        stations = [dot(sub(p, lo), axis) for p in points]
        if abs(span - width) < 1e-06 and abs(min(stations)) < 1e-06 and (abs(max(stations) - 0.16) < 1e-06):
            matches.append(face)
    if len(matches) != 1:
        raise ValueError('Expected one full-width lower flange face between validated C sections; found %d' % len(matches))
    return matches[0]


def brace_targets(brace):
    if not len(brace.faces) or len(brace.cells):
        raise ValueError('Expected BRACE_FRONT shell faces')
    return brace.faces[:]


def run(mdb, data, ON):
    print('STEP05 BRACE EXTEND FACE VALIDATION')
    assembly = lookup(mdb.models, data['model']).rootAssembly
    beam = lookup(assembly.instances, data['beam_instance'])
    brace = lookup(assembly.instances, data['brace_instance'])
    name = 'STEP05_BRACE_FRONT_EXTEND_BEAM_FACE'
    _runtime_match_1 = False
    for key in assembly.features.keys():
        if _runtime_match_1:
            break
        if text(key) == name:
            _runtime_match_1 = True
    if _runtime_match_1:
        raise ValueError('Validation feature already exists; inspect it or restore the pre-validation assembly')
    extend = select_lower_flange(beam, data['beam_width'])
    brace_targets(brace)
    print('beam lower flange face index = %d; pointOn = %r' % (extend.index, extend.pointOn))
    print('brace target face indices = %r' % [face.index for face in brace.faces])
    before = (len(brace.faces), len(brace.edges))
    _runtime_total_2 = 0
    for face in brace.faces:
        _runtime_total_2 += face.getSize(printResults=False)
    area = _runtime_total_2
    print('brace faces before = %d; brace edges before = %d' % before)
    created, independent, mesh_removed = (False, False, False)
    try:
        if brace.dependent == ON:
            assembly.makeIndependent(instances=(brace,))
            independent = True
            assembly.regenerate()
        beam = lookup(assembly.instances, data['beam_instance'])
        brace = lookup(assembly.instances, data['brace_instance'])
        extend = select_lower_flange(beam, data['beam_width'])
        try:
            feature = assembly.PartitionFaceByExtendFace(faces=brace_targets(brace), extendFace=extend)
        except Exception as exc:
            if not len(brace.elements):
                raise
            print('Partition failed with brace mesh present: %s; clearing only brace instance mesh and retrying once' % exc)
            assembly.deleteMesh(regions=(brace,))
            mesh_removed = True
            beam = lookup(assembly.instances, data['beam_instance'])
            brace = lookup(assembly.instances, data['brace_instance'])
            feature = assembly.PartitionFaceByExtendFace(faces=brace_targets(brace), extendFace=select_lower_flange(beam, data['beam_width']))
        assembly.features.changeKey(fromName=feature.name, toName=name)
        assembly.regenerate()
        brace = lookup(assembly.instances, data['brace_instance'])
        if len(brace.faces) <= before[0] or len(brace.edges) <= before[1]:
            raise ValueError('Extend-face partition did not modify BRACE_FRONT geometry')
        _runtime_total_3 = 0
        for face in brace.faces:
            _runtime_total_3 += face.getSize(printResults=False)
        after_area = _runtime_total_3
        if abs(after_area - area) > max(1e-12, area * 1e-06):
            raise ValueError('Unexpected shell area change')
        created = True
    finally:
        brace = lookup(assembly.instances, data['brace_instance'])
        print('brace faces after = %d; brace edges after = %d' % (len(brace.faces), len(brace.edges)))
        print('partition created = %s; brace made independent = %s; mesh removed = %s' % (created, independent, mesh_removed))
        print('Material removed = False; Tie created = False')
        print('Inspect BRACE_FRONT in Assembly; this is an Assembly feature, not a Part feature')


if __name__ == '__main__':
    from abaqus import mdb
    from abaqusConstants import ON
    run(mdb, DATA, ON)
