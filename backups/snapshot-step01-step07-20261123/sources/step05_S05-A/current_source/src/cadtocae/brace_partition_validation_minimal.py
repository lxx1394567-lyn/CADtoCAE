# Standalone Python 2.7 compatible runtime. DATA is written by the generator.
def lookup(repo, name):
    try:
        text_type = unicode
    except NameError:
        text_type = str
    def text(value):
        return value if isinstance(value, text_type) else value.decode('utf-8')
    keys = [key for key in repo.keys() if text(key) == text(name)]
    if len(keys) != 1:
        raise ValueError('Expected unique %r; available: %r' % (name, list(repo.keys())))
    return repo[keys[0]]


def run(mdb, data):
    print('STEP05 BRACE PARTITION VALIDATION')
    for label, key in (('brace part', 'brace'), ('beam lower flange plane global point', 'point_global'), ('beam lower flange plane global normal', 'normal_global'), ('brace cut plane local point', 'point_local'), ('brace cut plane local normal', 'normal_local')):
        print('%s = %r' % (label, data[key]))
    model = lookup(mdb.models, data['model'])
    part = lookup(model.parts, data['brace'])
    prefix = 'STEP05_DATUM_BRACE_FRONT_BEAM'
    cut_name = 'STEP05_PARTITION_BRACE_FRONT_BEAM'
    set_name = 'STEP05_SET_BRACE_FRONT_BEAM_CUT'
    reserved = [prefix, cut_name, set_name] + [prefix + '_P%d' % i for i in range(3)]
    for repo in (part.features, part.sets):
        _runtime_match_1 = False
        for key in repo.keys():
            if _runtime_match_1:
                break
            if key in reserved:
                _runtime_match_1 = True
        if _runtime_match_1:
            raise ValueError('Brace validation objects already exist; restore the pre-brace model before retry')
    before = (len(part.faces), len(part.edges))
    _runtime_total_2 = 0
    for f in part.faces:
        _runtime_total_2 += f.getSize(printResults=False)
    area_before = _runtime_total_2
    print('faces before partition = %d; edges before partition = %d' % before)
    created = False
    mesh_removed = False
    try:
        points = []
        for i, coords in enumerate(data['datum_points']):
            feature = part.DatumPointByCoordinate(coords=tuple(coords))
            points.append(part.datums[feature.id])
            part.features.changeKey(fromName=feature.name, toName=prefix + '_P%d' % i)
        plane = part.DatumPlaneByThreePoints(point1=points[0], point2=points[1], point3=points[2])
        plane_id = plane.id
        part.features.changeKey(fromName=plane.name, toName=prefix)
        try:
            feature = part.PartitionFaceByDatumPlane(datumPlane=part.datums[plane_id], faces=part.faces[:])
        except Exception as exc:
            if not len(part.elements):
                raise
            print('Partition failed with brace mesh present: %s; deleting only brace mesh and retrying once' % exc)
            part.deleteMesh()
            mesh_removed = True
            feature = part.PartitionFaceByDatumPlane(datumPlane=part.datums[plane_id], faces=part.faces[:])
        part.features.changeKey(fromName=feature.name, toName=cut_name)
        model.rootAssembly.regenerate()
        after = (len(part.faces), len(part.edges))
        if after[0] <= before[0] or after[1] <= before[1]:
            raise ValueError('BRACE_FRONT partition did not intersect shell geometry')
        _runtime_total_3 = 0
        for f in part.faces:
            _runtime_total_3 += f.getSize(printResults=False)
        area_after = _runtime_total_3
        if abs(area_after - area_before) > max(1e-12, area_before * 1e-06):
            raise ValueError('Shell area changed unexpectedly')
        edges = part.edges[0:0]
        p, n = (data['point_local'], data['normal_local'])
        for edge in part.edges:
            vertices = [part.vertices[i].pointOn[0] for i in edge.getVertices()]
            _runtime_condition_4 = len(vertices) == 2
            if _runtime_condition_4:
                _runtime_match_5 = True
                for v in vertices + [edge.pointOn[0]]:
                    if not _runtime_match_5:
                        break
                    _runtime_total_6 = 0
                    for i in range(3):
                        _runtime_total_6 += (v[i] - p[i]) * n[i]
                    if not abs(_runtime_total_6) < 1e-06:
                        _runtime_match_5 = False
                _runtime_condition_4 = _runtime_match_5
            if _runtime_condition_4:
                edges = edges + part.edges[edge.index:edge.index + 1]
        if not len(edges):
            raise ValueError('BRACE_FRONT partition did not intersect shell geometry')
        part.Set(name=set_name, edges=edges)
        model.rootAssembly.regenerate()
        created = True
    finally:
        print('faces after partition = %d; edges after partition = %d' % (len(part.faces), len(part.edges)))
        print('partition created = %s' % created)
        print('mesh removed = %s' % mesh_removed)
        print('remesh_required = %s' % (mesh_removed or len(part.faces) != before[0]))
        print('Material removed = False\nTie created = False')


if __name__ == '__main__':
    from abaqus import mdb
    run(mdb, DATA)
