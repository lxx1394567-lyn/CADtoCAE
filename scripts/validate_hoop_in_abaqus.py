# -*- coding: utf-8 -*-
"""Abaqus 2020 validation of Step02 solids and unchanged Step04 HOOP placement.

Run: abaqus cae noGUI=<this file> -- --cases <cases.json> --report <report.json>
Cases contain name, runner, assembly, component, pairs, and groups. Runner and
assembly are freshly generated scripts; only their definitions are loaded.
No input CAE is opened or saved. --cae optionally saves the validation models.
"""
from __future__ import print_function

import argparse
import __builtin__ as builtin
import codecs
import json
import imp
import math
import os
import sys
import traceback

from abaqus import mdb
from abaqusConstants import *
import regionToolset

def definitions(path, final_call):
    with codecs.open(path, 'r', 'utf-8') as stream:
        source = stream.read().replace('\r\n', '\n')
    head, separator, tail = source.rpartition('\n' + final_call + '\n')
    if not separator or tail.strip():
        raise ValueError('Unexpected generated script entry point: ' + path)
    scope = {'__file__': path, '__name__': 'hoop_validation_definitions'}
    eval(compile(head.encode('utf-8'), path, 'exec'), scope)
    return scope


def distance(a, b):
    return math.sqrt(builtin.sum((x-y)**2 for x, y in zip(a, b)))


def check(value, message):
    if not value:
        raise AssertionError(message)


def arc_middle(segment):
    c, a, b = segment['center'], segment['start'], segment['end']
    first = math.atan2(a[1]-c[1], a[0]-c[0])
    last = math.atan2(b[1]-c[1], b[0]-c[0])
    sweep = (last-first) % (2*math.pi)
    if segment['direction'] == 'CLOCKWISE':
        sweep -= 2*math.pi
    radius = distance(a, c)
    angle = first+sweep/2
    return (c[0]+radius*math.cos(angle), c[1]+radius*math.sin(angle))


def area_integral(segment):
    a, b = segment['start'], segment['end']
    if segment['kind'] == 'LINE':
        return a[0]*b[1]-b[0]*a[1]
    c = segment['center']
    first = math.atan2(a[1]-c[1], a[0]-c[0])
    last = math.atan2(b[1]-c[1], b[0]-c[0])
    sweep = (last-first) % (2*math.pi)
    if segment['direction'] == 'CLOCKWISE':
        sweep -= 2*math.pi
    return c[0]*(b[1]-a[1])-c[1]*(b[0]-a[0])+distance(a,c)**2*sweep


def verify(case):
    runner = definitions(case['runner'], 'create_parts()')
    assembly = definitions(case['assembly'], 'main()')
    item = case['component']
    profile = runner['_hoop_band_profile_geometry'](item)
    dims = profile['dimensions']
    w, t, r = dims['width_m'], dims['thickness_m'], dims['inner_radius_m']
    model = mdb.Model(name=str(case['name']))
    part = runner['_create_solid_part'](model, item)
    check(len(part.cells) == 1, 'Expected one solid cell')
    part.checkGeometry()
    boundary = builtin.sum(area_integral(s) for s in profile['inner']) - builtin.sum(area_integral(s) for s in profile['outer'])
    boundary += t*(dims['right_end_x_m']-dims['left_end_x_m'])
    expected_volume = abs(boundary)*w/2
    volume = part.getMassProperties(relativeAccuracy=HIGH)['volume']
    # Kernel mass integration is numerical; compare at 0.001% relative tolerance.
    check(abs(volume-expected_volume) < expected_volume*1e-5,
          'Solid volume %.12g vs analytic %.12g' % (volume, expected_volume))
    radii = []
    for edge in part.edges:
        try:
            radii.append(edge.getRadius())
        except Exception:
            pass
    for radius in (r, r+t, dims['inner_chain_bend_radius_m'], dims['outer_chain_bend_radius_m']):
        if radius > 0:
            check(any(abs(value-radius)<1e-9 for value in radii), 'Missing circular edge radius %g' % radius)
    # Every explicit profile segment must exist as an actual extruded face.
    for chain in (profile['inner'], profile['outer']):
        for s in chain:
            xy = arc_middle(s) if s['kind']=='ARC' else tuple((a+b)/2 for a,b in zip(s['start'],s['end']))
            face = part.faces.findAt(coordinates=xy+(w/2,))
            check(face is not None, 'Missing extruded face')
    old_model = mdb.Model(name=str(case['name'])+'_legacy')
    old_part = legacy._create_solid_part(dict(globals()), old_model, item)
    check(abs(old_part.getMassProperties(relativeAccuracy=HIGH)['volume']-volume)<volume*1e-9, 'Entry point mismatch')
    contacts = []
    for pair, group in zip(case['pairs'], case['groups']):
        for member in pair:
            assembly['_instance'](model, member)
        instances = [model.rootAssembly.instances[str(m['instance_name'])] for m in pair]
        center = tuple(group['center'])
        # Matching cylindrical reference column, only for this isolated HOOP test.
        column_name = str(group['group_id'])+'_COLUMN'
        sketch = model.ConstrainedSketch(name=column_name, sheetSize=4*r)
        sketch.CircleByCenterPerimeter(center=(0,0), point1=(r,0))
        column = model.Part(name=column_name, dimensionality=THREE_D, type=DEFORMABLE_BODY)
        column.BaseSolidExtrude(sketch=sketch, depth=2*w)
        model.rootAssembly.Instance(name=column_name, part=column, dependent=ON)
        model.rootAssembly.translate(instanceList=(column_name,), vector=(center[0],center[1],center[2]-w))
        column_instance = model.rootAssembly.instances[column_name]
        model.rootAssembly.regenerate()
        for side in (0, -1):
            s = profile['inner'][side]
            local = ((s['start'][0]+s['end'][0])/2, 0.0, w/2)
            point = tuple(assembly['_transform_member'](local, pair[0]))
            faces = [inst.faces.findAt(coordinates=point) for inst in instances]
            normals = [face.getNormal(point=point) for face in faces]
            check(builtin.sum(a*b for a,b in zip(*normals)) < -0.999999, 'Mating face normals not opposed')
            contacts.append(list(point))
        for inst, member in zip(instances, pair):
            for degrees in (45,90,135):
                angle = math.radians(degrees)
                local = (r*math.cos(angle), r*math.sin(angle), w/2)
                point = tuple(assembly['_transform_member'](local, member))
                hoop_face = inst.faces.findAt(coordinates=point)
                column_face = column_instance.faces.findAt(coordinates=point)
                check(builtin.sum(a*b for a,b in zip(hoop_face.getNormal(point=point), column_face.getNormal(point=point))) < -0.999999,
                      'Hoop/column contact normals not opposed')
    return {'name':case['name'], 'status':'PASS', 'dimensions':dims, 'volume_m3':volume,
            'analytic_volume_m3':expected_volume, 'edge_radii_m':radii,
            'pair_count':len(case['pairs']), 'mating_face_sample_points':contacts}


def main():
    global legacy
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--cae')
    parser.add_argument('--legacy-script', required=True)
    arguments = sys.argv[sys.argv.index('--cases'):]
    args = parser.parse_args(arguments)
    legacy = imp.load_source('hoop_legacy', args.legacy_script)
    with open(args.cases) as stream:
        cases = json.load(stream)
    results = []
    for case in cases:
        try:
            results.append(verify(case))
        except Exception:
            results.append({'name':case['name'], 'status':'FAIL', 'traceback':traceback.format_exc()})
        print(json.dumps(results[-1]))
    with open(args.report, 'w') as stream:
        json.dump(results, stream, indent=2)
    if args.cae:
        mdb.saveAs(pathName=os.path.abspath(args.cae))
    check(all(result['status']=='PASS' for result in results), 'HOOP validation failed; see report')


if __name__ == '__main__':
    main()
