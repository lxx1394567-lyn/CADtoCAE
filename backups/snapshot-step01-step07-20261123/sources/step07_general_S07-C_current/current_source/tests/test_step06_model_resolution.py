import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from cadtocae.purlin_bolt_preset_runtime import resolve_step06_model
from cadtocae.connector_integration import integrated_source
from test_step06_connector_b1 import plan

class ExactModels(dict):
    def values(self):raise AssertionError('Must not search models')

class ModelResolutionTests(unittest.TestCase):
    def ns(self):
        result={'__name__':'test'};exec(integrated_source({},'unused'),result)
        return result
    def model(self,p):
        instances={p['source_instance']:NS(partName=p['source_part'],dependent=True),p['target_instance']:NS(partName=p['target_part'],dependent=True)}
        return NS(name=p['project_id'],rootAssembly=NS(instances=instances,features={'STEP05_RP_TEST':object()},sets={},surfaces={}),constraints={'STEP05_TIE_TEST':object()},sections={})
    def test_exact_not_prefix_case_or_instance_search(self):
        p=plan();formal=self.model(p)
        models=ExactModels({'Model-1':object(),p['project_id']:formal,p['project_id']+'-Copy':self.model(p),p['project_id']+'-origin':self.model(p)})
        self.assertIs(resolve_step06_model(NS(models=models),p['project_id']),formal)
        del models[p['project_id']]
        with self.assertRaisesRegex(ValueError,'TARGET_MODEL_NOT_FOUND.*Available Models'):
            resolve_step06_model(NS(models=models),p['project_id'])
        for name in ('',None,123,'  '):
            with self.assertRaisesRegex(ValueError,'INVALID_PROJECT_ID'):resolve_step06_model(NS(models=models),name)
    def test_b1_multiple_models_only_formal_regions(self):
        ns=self.ns();p=plan();formal=self.model(p)
        models=ExactModels({p['project_id']:formal,p['project_id']+'-Copy':self.model(p),p['project_id']+'-origin':self.model(p),'Model-1':object()})
        seen=[]
        ns['b1_resolve']=lambda instance,*args:(seen.append(instance) or [],{})
        with patch.dict('sys.modules',abaqusConstants=NS(ON=True)):
            context=ns['b1_preflight'](p,NS(models=models))
        self.assertIs(context[0],formal)
        self.assertEqual(seen,list(formal.rootAssembly.instances.values()))
    def test_missing_instance_and_duplicate_classification(self):
        ns=self.ns();p=plan();formal=self.model(p);mdb=NS(models={p['project_id']:formal})
        del formal.rootAssembly.instances[p['target_instance']]
        with self.assertRaisesRegex(ValueError,'STEP06_A_REQUIRED: INSTANCE_MISSING'):ns['b1_preflight'](p,mdb)
        formal.rootAssembly.instances[p['target_instance']]=object()
        formal.constraints['STEP06_COUPLING_P01_SUPPORT']=object()
        with self.assertRaisesRegex(ValueError,'EXISTING_STEP06_B_OBJECT'):ns['b1_preflight'](p,mdb)
    def test_sb_multiple_models_exact_target(self):
        ns=self.ns();p=plan();formal=self.model(p);items=[]
        formal.rootAssembly.instances={}
        for i in range(1,5):
            c=dict(p,connection_group='P%02d'%i,source_instance='PURLIN_SUPPORT_%02d'%i,target_instance='INCLINED_BEAM_01',connection_family='SUPPORT_BEAM',target_surface='INCLINED_BEAM_TOP_FLANGE',support_hole_id='PS_TO_BEAM',total_length_m=.025)
            formal.rootAssembly.instances[c['source_instance']]=NS(partName=c['source_part'],dependent=True)
            items.append(c)
        formal.rootAssembly.instances['INCLINED_BEAM_01']=NS(partName=p['target_part'],dependent=True)
        formal.sections['STEP06_CONNECTOR_SECTION_PURLIN_BOLT']=object()
        ns['validate_bolt_preset']=lambda x:None;ns['sb_prior_snapshot']=lambda *args:[]
        seen=[]
        def resolve(instance,*args):
            seen.append(instance);return [NS(index=len(seen))],{}
        ns['b1_resolve']=resolve
        models=ExactModels({p['project_id']:formal,p['project_id']+'-Copy':self.model(p),'Model-1':object()})
        with patch.dict('sys.modules',abaqusConstants=NS(ON=True,CARTESIAN='CARTESIAN',NONE='NONE')):
            contexts,keys,prior=ns['sb_preflight'](dict(project_id=p['project_id'],connections=items,support_purlin_connections=[]),NS(models=models))
        self.assertEqual(len(contexts),4)
        self.assertTrue(all(c[0] is formal for c in contexts))
        self.assertTrue(all(any(x is y for y in formal.rootAssembly.instances.values()) for x in seen))
