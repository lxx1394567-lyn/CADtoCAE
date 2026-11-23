"""Read-only model inspection, executed by a separate Abaqus Python 2.7/3 process.
Never runs a modelling script, regenerates, saves, or alters the database.
"""
from __future__ import print_function
import json
import sys
import traceback
import abaqus
import part
import assembly
import interaction
import section
import material
import mesh
import sketch
import step
import load
import connectorBehavior


def native(value):
    if sys.version_info[0] < 3 and isinstance(value, unicode):
        return value.encode(sys.getfilesystemencoding() or 'mbcs')
    return value


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            for item in walk(child):
                yield item
    elif isinstance(value, list):
        for child in value:
            for item in walk(child):
                yield item


def geometry(model):
    return {name: dict(volume=sum([c.getSize(printResults=False) for c in p.cells]),
                       area=sum([f.getSize(printResults=False) for f in p.faces]),
                       faces=len(p.faces), cells=len(p.cells)) for name, p in model.parts.items()}


def verify(job, result):
    checks = result['checks']
    def check(name, actual, expected):
        ok = actual == expected
        checks.append(dict(name=name, actual=actual, expected=expected, status='PASSED' if ok else 'FAILED'))
        if not ok:
            raise RuntimeError('%s: expected %r, got %r' % (name, expected, actual))
    def close_enough(name, actual, expected):
        # CAD kernel roundoff; scales with reported area/volume, not object counts.
        tolerance = max(abs(expected)*1.e-4, 1.e-12)
        checks.append(dict(name=name, actual=actual, expected=expected, tolerance=tolerance,
                           status='PASSED' if abs(actual-expected) <= tolerance else 'FAILED'))
        if abs(actual-expected) > tolerance:
            raise RuntimeError('%s differs from the stage report' % name)
    def feature(p, name):
        name = native(name)
        check('feature '+name, name in p.features, True)
        check('active '+name, bool(p.features[name].isSuppressed()), False)
    baseline = None
    if job.get('baseline'):
        abaqus.openMdb(pathName=native(job['baseline']))
        baseline = geometry(abaqus.mdb.models[native(job['model'])])
        abaqus.mdb.close()
    abaqus.openMdb(pathName=native(job['path']))
    check('model identity', native(job['model']) in abaqus.mdb.models, True)
    model = abaqus.mdb.models[native(job['model'])]
    a = model.rootAssembly
    result.update(model=job['model'], description=model.description, parts=len(model.parts), instances=len(a.instances), geometry=geometry(model))
    for name in job['parts']:
        name = native(name)
        check('Part '+name, name in model.parts, True)
        check('nonempty Part '+name, bool(len(model.parts[name].faces) or len(model.parts[name].cells)), True)
    for name in job['instances']:
        check('Instance '+name, native(name) in a.instances, True)
    for name in job['steps']:
        check('analysis step '+name, native(name) in model.steps, True)
    reports = job['reports']
    if '3' in reports:
        constraints = set()
        for item in walk(reports['3']):
            if isinstance(item.get('tie'), (str, type(u''))):
                constraints.add(item['tie'])
            if item.get('name', '').startswith('STEP05_COUPLING_'):
                constraints.add(item['name'])
            if item.get('part') and item.get('name', '').startswith('STEP05_'):
                feature(model.parts[native(item['part'])], item['name'])
        check('Analysis report supplies named constraints', bool(constraints), True)
        for name in sorted(constraints):
            check('Analysis constraint '+name, native(name) in model.constraints, True)
            check('active Analysis constraint '+name, bool(model.constraints[native(name)].suppressed), False)
    if '4' in reports:
        r = reports['4']
        removed = {}
        names = set()
        def hole(pname, fname, amount, metric):
            key = (pname, fname)
            if key in names:
                return
            names.add(key)
            feature(model.parts[native(pname)], fname)
            removed[(pname, metric)] = removed.get((pname, metric), 0.0) + amount
        for item in r['support']['created_hole_details']:
            hole(item['part'], item['name'], item['removed_volume_m3'], 'volume')
        for item in r['purlin_local'] + r['inclined_beam']:
            if (item['target_part'], item['feature_name']) not in names:
                hole(item['target_part'], item['feature_name'], item['removed_area_m2'], 'area')
        for item in r['hoop_validation']['parts']:
            for h in item['holes']:
                hole(item['part_name'], h['feature_name'], h['removed_volume'], 'volume')
            close_enough('Hoop saved volume '+item['part_name'], result['geometry'][item['part_name']]['volume'], item['post_regenerate_volume'])
            for inst in item['instance_inheritance']:
                isolated = {x['instance']: x['new_part'] for x in reports.get('5', {}).get('isolated_parts', [])}
                check('Hoop instance Part '+inst['instance_name'], a.instances[native(inst['instance_name'])].partName, isolated.get(inst['instance_name'], inst['part_name']))
        check('Hole feature count from report', len(names), r['created_holes'])
        check('Hole geometry baseline available', baseline is not None, True)
        for (pname, metric), amount in sorted(removed.items()):
            close_enough('Hole removed '+metric+' '+pname, baseline[pname][metric]-result['geometry'][pname][metric], amount)
        result['holes'] = len(names)
    from step07_verify import verify_step07
    verify_step07(model, reports, check, close_enough)
    abaqus.mdb.close()


def run():
    with open('verify_job.json') as handle:
        job = json.load(handle)
    result = dict(token=job['token'], status='FAILED', checks=[], path=job['path'])
    try:
        verify(job, result)
        result['status'] = 'PASSED'
    except BaseException:
        result['error'] = traceback.format_exc()
    with open('verification.json', 'w') as handle:
        json.dump(result, handle, indent=2)

if __name__ == '__main__':
    run()
