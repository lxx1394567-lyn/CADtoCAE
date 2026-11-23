import copy,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as N,ModuleType
from unittest.mock import patch
from cadtocae.hoop_brace_setup import hoop_brace_source
from test_step06_dp_hoop_brace import build,fixture


class OptionalPurlinReportTests(unittest.TestCase):
    def setUp(self):
        self.ns={'__name__':'test'}
        exec(hoop_brace_source(build(fixture()),'unused'),self.ns)
        self.constants=ModuleType('abaqusConstants')
        for key in ('KINEMATIC','ON','OFF'):setattr(self.constants,key,key)
        self.ns['validate_bolt_preset']=lambda section:None
        self.model=N(sections={'STEP06_CONNECTOR_SECTION_PURLIN_BOLT':N()},constraints={})
        a=N(features={},sets={},referencePoints={},datums={},sectionAssignments=[],connectorOrientations=[])
        self.model.rootAssembly=a;edges={}
        a.getFeatureEdges=lambda name:edges[name]
        a.getCoordinates=lambda entity:entity.position
        self.names=[]
        for group in ('P01','P02','P03','P04'):
            for names in (self.ns['b1_names'](group),self.ns['sb_names'](group)):
                self.names.append(names)
                for key in ('rp_support','rp_purlin','wire','orientation'):
                    name=names[key];a.features[name]=N(id=len(a.features)+1,suppressed=False)
                for key in ('rp_support','rp_purlin'):
                    name=names[key];rp=N(position=(len(a.referencePoints),0,0))
                    a.referencePoints[a.features[name].id]=rp;a.sets[name]=N(referencePoints=[rp])
                for key,rp in (('support_coupling','rp_support'),('purlin_coupling','rp_purlin')):
                    self.model.constraints[names[key]]=N(couplingType='KINEMATIC',u1='ON',u2='ON',u3='ON',ur1='OFF',ur2='OFF',ur3='OFF',controlPoint=(names[rp],),suppressed=False)
                wire=names['wire'];edges[wire]=[N(index=len(edges))];a.sets[wire]=N(edges=edges[wire])
                a.sectionAssignments.append(N(region=(wire,),sectionName='STEP06_CONNECTOR_SECTION_PURLIN_BOLT'))
                datum=N(axis1=N(direction=(1,0,0)),axis2=N(direction=(0,1,0)),axis3=N(direction=(0,0,1)))
                a.datums[a.features[names['orientation']].id]=datum
                a.connectorOrientations.append(N(region=(wire,),localCsys1=datum))

    def validate(self):
        with patch.dict(sys.modules,abaqusConstants=self.constants):
            return self.ns['validate_existing_purlin_connectors'](self.model)

    def test_live_counts_and_optional_missing_report(self):
        live=self.validate()
        self.assertEqual([live[k] for k in ('rp_count','coupling_count','wire_count')],[16,16,8])
        with tempfile.TemporaryDirectory() as tmp:
            r=dict(purlin_prerequisite=live,warnings=[])
            self.ns['dp_hb_optional_audit'](dict(project_id='P',optional_audit_path=str(Path(tmp)/'missing.json')),r)
            self.assertEqual(r['purlin_report_audit_status'],'MISSING')
            self.assertIn('PURLIN_REPORT_MISSING',r['warnings'][0])

    def test_present_report_audit_and_conflict_warning(self):
        live=self.validate()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'report.json';prior=dict(live,project_id='P',status='SUCCESS')
            for project,expected in (('P','PASS'),('WRONG','INVALID')):
                prior['project_id']=project;path.write_text(json.dumps(prior))
                r=dict(purlin_prerequisite=live,warnings=[])
                self.ns['dp_hb_optional_audit'](dict(project_id='P',purlin_report_path=str(path)),r)
                self.assertEqual(r['purlin_report_audit_status'],expected)

    def test_missing_live_objects_fail(self):
        a=self.model.rootAssembly
        for repo,key in ((a.features,self.names[0]['wire']),(a.sets,self.names[1]['rp_support']),
                         (a.features,self.names[2]['orientation']),(self.model.constraints,self.names[3]['support_coupling'])):
            old=repo.pop(key)
            with self.assertRaisesRegex(ValueError,'PURLIN_CONNECTORS_REQUIRED'):self.validate()
            repo[key]=old

    def test_wrong_dof_section_or_orientation_assignment_fail(self):
        c=self.model.constraints[self.names[0]['support_coupling']];c.ur1='ON'
        with self.assertRaisesRegex(ValueError,'PURLIN_CONNECTORS_REQUIRED'):self.validate()
        c.ur1='OFF';a=self.model.rootAssembly
        a.sectionAssignments[0].sectionName='WRONG'
        with self.assertRaisesRegex(ValueError,'PURLIN_CONNECTORS_REQUIRED'):self.validate()
        a.sectionAssignments[0].sectionName='STEP06_CONNECTOR_SECTION_PURLIN_BOLT'
        a.connectorOrientations.pop()
        with self.assertRaisesRegex(ValueError,'PURLIN_CONNECTORS_REQUIRED'):self.validate()
