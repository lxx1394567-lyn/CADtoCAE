# -*- coding: utf-8 -*-
"""Standalone, case-specific Part-local kernel experiment; Python 2.7 compatible.

No Analysis Runtime or instance transformation is used.
"""
MODEL = 'SP_SC_ANG28_1042110101170S-T0204'
BEAM = 'P_SP_SC_ANG28_INCLINED_BEAM'
BRACE = 'P_SP_SC_ANG28_BRACE_FRONT'
C = 0.336
MINUS = 0.256
PLUS = 0.416
TOL = 1.e-6


def text(value):
    try:
        text_type = unicode
    except NameError:
        text_type = str
    return value if isinstance(value, text_type) else value.decode('utf-8')


def lookup(repo, name):
    keys = [key for key in repo.keys() if text(key) == text(name)]
    if len(keys) != 1:
        raise ValueError('Expected unique %r; available keys: %r' % (name, list(repo.keys())))
    return repo[keys[0]]


def edges_at(part, station):
    selected = part.edges[0:0]
    for edge in part.edges:
        points = [part.vertices[i].pointOn[0] for i in edge.getVertices()]
        _runtime_condition_6 = len(points) == 2
        if _runtime_condition_6:
            _runtime_match_7 = True
            for p in points + [edge.pointOn[0]]:
                if not _runtime_match_7:
                    break
                if not abs(p[2] - station) <= TOL:
                    _runtime_match_7 = False
            _runtime_condition_6 = _runtime_match_7
        if _runtime_condition_6:
            selected = selected + part.edges[edge.index:edge.index + 1]
    return selected


def run(mdb, XYPLANE):
    model = lookup(mdb.models, MODEL)
    part = lookup(model.parts, BEAM)
    mesh_removed = False
    remesh_required = False
    print('STEP05 MINIMAL PARTITION VALIDATION')
    print('Model = %s; Beam Part = %s' % (MODEL, BEAM))
    print('C = %.3f; C-80mm = %.3f; C+80mm = %.3f m' % (C, MINUS, PLUS))
    if not len(part.faces) or len(part.cells):
        raise ValueError('Expected shell beam faces for PartitionFaceByDatumPlane')
    z = [v.pointOn[0][2] for v in part.vertices]
    if not z or not min(z) < MINUS < PLUS < max(z):
        raise ValueError('Both stations must lie inside the Part local Z extent')
    names = ('STEP05_BEAM_C_MINUS_80', 'STEP05_BEAM_C_PLUS_80')
    reserved = list(names) + [n + s for n in names for s in ('_PLANE', '_PARTITION')]
    reserved.append('STEP05_BEAM_LOCAL_YMIN_PATCH_CANDIDATE')
    for repo in (part.features, part.sets):
        _runtime_match_1 = False
        for key in repo.keys():
            if _runtime_match_1:
                break
            if text(key) in reserved:
                _runtime_match_1 = True
        if _runtime_match_1:
            raise ValueError('Minimal validation objects already exist; use a fresh pre-validation model')
    try:
        for name, offset in zip(names, (MINUS, PLUS)):
            datum = part.DatumPlaneByPrincipalPlane(principalPlane=XYPLANE, offset=offset)
            datum_id = datum.id
            part.features.changeKey(fromName=datum.name, toName=name + '_PLANE')
            try:
                feature = part.PartitionFaceByDatumPlane(datumPlane=part.datums[datum_id], faces=part.faces[:])
            except Exception as exc:
                if not len(part.elements):
                    raise
                print('Partition failed with beam mesh present: %s; removing only beam mesh and retrying once' % exc)
                part.deleteMesh()
                mesh_removed = True
                remesh_required = True
                feature = part.PartitionFaceByDatumPlane(datumPlane=part.datums[datum_id], faces=part.faces[:])
            remesh_required = True
            part.features.changeKey(fromName=feature.name, toName=name + '_PARTITION')
            print('Partition completed at local Z = %.3f m' % offset)
        for name, offset in zip(names, (MINUS, PLUS)):
            selected = edges_at(part, offset)
            if not len(selected):
                raise ValueError('No section edges found at %.3f' % offset)
            part.Set(name=name, edges=selected)
            print('Created %s; edges = %d' % (name, len(selected)))
        model.rootAssembly.regenerate()
        try:
            _runtime_values_2 = None
            for v in part.vertices:
                _runtime_value_3 = v.pointOn[0][1]
                if _runtime_values_2 is None or _runtime_value_3 < _runtime_values_2:
                    _runtime_values_2 = _runtime_value_3
            if _runtime_values_2 is None:
                raise ValueError('min() arg is an empty sequence')
            ymin = _runtime_values_2
            candidate = part.faces[0:0]
            for face in part.faces:
                points = [part.vertices[i].pointOn[0] for i in face.getVertices()]
                _runtime_condition_4 = points
                if _runtime_condition_4:
                    _runtime_match_5 = True
                    for p in points:
                        if not _runtime_match_5:
                            break
                        if not (abs(p[1] - ymin) <= TOL and MINUS - TOL <= p[2] <= PLUS + TOL):
                            _runtime_match_5 = False
                    _runtime_condition_4 = _runtime_match_5
                if _runtime_condition_4:
                    candidate = candidate + part.faces[face.index:face.index + 1]
            if len(candidate):
                part.Set(name='STEP05_BEAM_LOCAL_YMIN_PATCH_CANDIDATE', faces=candidate)
                print('Local Y-min patch candidate created; confirm lower flange manually, physical side NOT inferred')
            else:
                print('WARNING: no reliable local flange candidate; beam partitions remain available')
        except Exception as exc:
            print('WARNING: optional patch selection skipped: %s' % exc)
        try:
            brace = lookup(model.parts, BRACE)
            ends = [v.pointOn[0][2] for v in brace.vertices]
            print('Brace local Z endpoints: %r' % ([min(ends), max(ends)],))
            print('WARNING: no explicit C-to-local-end mapping in current inputs; STEP05_BRACE_FRONT_END_C not created')
        except Exception as exc:
            print('WARNING: optional brace check skipped: %s' % exc)
        model.rootAssembly.regenerate()
        print('BEAM PARTITION VALIDATION COMPLETE; inspect both named edge sets')
    finally:
        print('mesh_removed = %s' % mesh_removed)
        print('remesh_required = %s' % remesh_required)
        print('Material removed = False; no final mesh generated')


if __name__ == '__main__':
    from abaqus import mdb
    from abaqusConstants import XYPLANE
    run(mdb, XYPLANE)
