"""Python 2.7/3 compatible code executed ONLY by Abaqus/CAE noGUI."""
from __future__ import print_function
import json
import os
import traceback
import sys
# Abaqus loads additional Part methods on module import, including RemoveFaces.
# Restore the kernel API registrations that the interactive CAE session provides.
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

def report_errors(value):
    if isinstance(value, dict):
        if value.get('errors'):
            raise RuntimeError('Runtime report contains errors: ' + repr(value['errors']))
        for child in value.values():
            report_errors(child)
    elif isinstance(value, list):
        for child in value:
            report_errors(child)

def run():
    with open('job.json', 'r') as handle:
        job = json.load(handle)
    contract = job['contract']
    try:
        if job['previous']:
            abaqus.openMdb(pathName=native(job['previous']))
        else:
            abaqus.Mdb()
        namespace = {'__name__': '__main__', '__file__': os.path.abspath('stage.py')}
        with open('stage.py', 'rb') as handle:
            code = compile(handle.read(), 'stage.py', 'exec')
        eval(code, namespace, namespace)
        model = abaqus.mdb.models[native(contract['model'])]
        for raw_name in contract.get('parts', []):
            name = native(raw_name)
            if name not in model.parts:
                raise RuntimeError('Missing expected Part: ' + name)
            part = model.parts[name]
            if not len(part.cells) and not len(part.faces):
                raise RuntimeError('Empty expected Part: ' + name)
        for step_name in contract.get('steps', []):
            if native(step_name) not in model.steps:
                raise RuntimeError('Missing expected analysis step: ' + step_name)
        for raw_name in contract.get('instances', []):
            name = native(raw_name)
            if name not in model.rootAssembly.instances:
                raise RuntimeError('Missing expected Instance: ' + name)
        if contract['kind'] == 'parts':
            result = namespace.get('_batch_parts_result')
            if result is None or result[1]:
                raise RuntimeError('Part creation returned failures or missing result: ' + repr(result))
        if contract['kind'] in ('report', 'assembly'):
            with open('runtime_report.json', 'r') as handle:
                report = json.load(handle)
            if contract.get('step07') and report.get('status') == 'REVIEW_REQUIRED':
                abaqus.mdb.saveAs(pathName=os.path.abspath('review_only.cae'))
                raise RuntimeError('REVIEW_REQUIRED: '+repr(report.get('mesh_acceptance', {}).get('review_reasons', [])))
            if contract['kind'] == 'report' and (report.get('status') != 'SUCCESS' or report.get('overall_status', 'SUCCESS') != 'SUCCESS'):
                raise RuntimeError('Runtime report did not succeed: '+str(report.get('status'))+'; '+str(report.get('mesh_acceptance', {})))
            report_errors(report)
            if contract['kind'] == 'assembly':
                for entry in report.get('beam_station_validation', {}).values():
                    if entry.get('error_m', 0) > 1.0e-6:
                        raise RuntimeError('Assembly beam station validation failed')
        model.rootAssembly.regenerate()
        abaqus.mdb.saveAs(pathName=os.path.abspath('checkpoint.cae'))
        abaqus.mdb.close()
        abaqus.openMdb(pathName=os.path.abspath('checkpoint.cae'))
        model = abaqus.mdb.models[native(contract['model'])]
        for raw_name in contract.get('parts', []):
            name = native(raw_name)
            if name not in model.parts:
                raise RuntimeError('Saved model lost Part: ' + name)
        for step_name in contract.get('steps', []):
            if native(step_name) not in model.steps:
                raise RuntimeError('Missing expected analysis step: ' + step_name)
        for raw_name in contract.get('instances', []):
            name = native(raw_name)
            if name not in model.rootAssembly.instances:
                raise RuntimeError('Saved model lost Instance: ' + name)
        if contract.get('step07'):
            from step07_verify import verify_step07
            def compare(name, actual, expected):
                if actual != expected: raise RuntimeError(name+': '+repr(actual)+' != '+repr(expected))
            def near(name, actual, expected):
                if abs(actual-expected) > max(abs(expected)*1.e-4, 1.e-12): raise RuntimeError(name)
            verify_step07(model, {str(contract['step07']+4): report}, compare, near)
        evidence = dict(token=job['token'], status='SUCCESS', model=contract['model'],
                        parts=len(model.parts), instances=len(model.rootAssembly.instances))
        abaqus.mdb.close()
        with open('receipt.json', 'w') as handle:
            json.dump(evidence, handle)
    except BaseException:
        with open('worker_error.txt', 'w') as handle:
            handle.write(traceback.format_exc())
        raise

if __name__ == '__main__':
    run()
