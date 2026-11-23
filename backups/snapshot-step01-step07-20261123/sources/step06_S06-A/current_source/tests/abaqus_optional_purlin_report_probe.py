from abaqus import openMdb
from abaqusConstants import *
import part,assembly,interaction,section
import json,traceback
result={}
try:
    mdb=openMdb(pathName='input.cae')
    ns={'__name__':'probe'};execfile('runtime.py',ns)
    plan=ns['PLAN'];m=mdb.models[str(plan['project_id'])]
    result['live']=ns['validate_existing_purlin_connectors'](m)
    prior=dict(result['live'],project_id=plan['project_id'],status='SUCCESS')
    with open('audit.json','w') as h:json.dump(prior,h)
    before=ns['bg_state'](m)
    for audit in ('audit.json','missing.json'):
        test=dict(plan,optional_audit_path=audit)
        audit_report=dict(purlin_prerequisite=result['live'],warnings=[])
        ns['dp_hb_optional_audit'](test,audit_report)
        assert audit_report['purlin_report_audit_status']==('PASS' if audit=='audit.json' else 'MISSING')
        wire='STEP06_WIRE_P01_PURLIN_BOLT'
        m.rootAssembly.features.changeKey(fromName=wire,toName='HIDDEN_TEST_WIRE')
        hidden=ns['bg_state'](m)
        try:
            ns['execute_hoop_brace'](test,mdb,'negative.json')
            raise AssertionError('Missing live wire accepted')
        except ValueError as error:
            assert 'PURLIN_CONNECTORS_REQUIRED' in str(error)
            assert ns['bg_state'](m)==hidden
        finally:m.rootAssembly.features.changeKey(fromName='HIDDEN_TEST_WIRE',toName=wire)
    assert ns['bg_state'](m)==before
    result['report_exists_and_missing_negative_live_tests']='PASS'
    result['report']=ns['execute_hoop_brace'](plan,mdb,'report.json')
    assert result['report']['purlin_report_audit_status']=='MISSING'
    mdb.close()
    mdb=openMdb(pathName='input.cae')
    present=ns['execute_hoop_brace'](dict(plan,optional_audit_path='audit.json'),mdb,'present_report.json')
    assert present['status']=='SUCCESS' and present['purlin_report_audit_status']=='PASS'
    result['present_report_execution']='PASS'
    result['status']='SUCCESS'
except Exception:result.update(status='FAILED',error=traceback.format_exc())
with open('result.json','w') as h:json.dump(result,h,indent=2)
