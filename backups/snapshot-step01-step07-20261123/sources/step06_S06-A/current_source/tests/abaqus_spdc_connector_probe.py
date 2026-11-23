from abaqus import openMdb
from abaqusConstants import *
import part,assembly,interaction,section
import json,traceback
result={}
try:
    mdb=openMdb(pathName='input.cae')
    ns={'__name__':'probe'}
    execfile('runtime.py',ns)
    # Packaged GUI smoke uses relocated inputs. Use the original matching Plan
    # for this completed CAE; do not weaken fingerprints for relocated files.
    with open('actual_connector_plan.json') as h:plan=json.load(h)
    m=mdb.models[str(plan['project_id'])]
    before=ns['integrated_step05_state'](m)
    r=ns['execute_integrated_connectors'](plan,mdb,'connector_report.json')
    assert r['status']=='SUCCESS'
    assert ns['integrated_step05_state'](m)==before
    cs=[c for n,c in m.constraints.items() if n.startswith('STEP06_COUPLING_')]
    assert len(cs)==16
    for c in cs:
        assert c.couplingType==KINEMATIC
        assert (c.u1,c.u2,c.u3,c.ur1,c.ur2,c.ur3)==(ON,ON,ON,OFF,OFF,OFF)
    assert len(r['support_purlin_connections'])==4
    assert len(r['support_beam_connections'])==4
    result.update(status='SUCCESS',report=r,step05='PASS')
except Exception:
    result.update(status='FAILED',error=traceback.format_exc())
with open('result.json','w') as h:json.dump(result,h,indent=2)
