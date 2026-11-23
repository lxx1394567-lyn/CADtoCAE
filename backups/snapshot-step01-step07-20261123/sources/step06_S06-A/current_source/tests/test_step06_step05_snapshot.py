import unittest
from pathlib import Path
from types import SimpleNamespace as NS


class FeatureError(Exception):pass


class Feature:
    __members__ = ['sketch', 'path', 'edges', 'faces', 'references']
    id = 42
    suppressed = False

    def __getattr__(self, name):
        if name in self.__members__:
            raise FeatureError('Feature does not have path '+name)
        raise AttributeError(name)

    def __str__(self):
        raise AssertionError('Kernel object serialization is forbidden')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.ns={}
        path=Path(__file__).parents[1]/'src/cadtocae/connector_integration_runtime.py'
        exec(path.read_text(encoding='utf-8'),self.ns)
        self.snapshot=self.ns['integrated_step05_state']
        self.model=NS(constraints={'STEP05_DP_TIE':Feature(),'STEP05_DP_COUPLING':Feature()},
                      rootAssembly=NS(features={'STEP05_DP_RP':Feature()}))

    def test_optional_properties_never_accessed(self):
        feature=self.model.rootAssembly.features['STEP05_DP_RP']
        with self.assertRaises(FeatureError):getattr(feature,'sketch')
        self.assertEqual(self.snapshot(self.model)['features'],[('STEP05_DP_RP',42,False)])

    def test_deleted_feature_constraint_and_changed_id_detected(self):
        before=self.snapshot(self.model)
        feature=self.model.rootAssembly.features.pop('STEP05_DP_RP')
        self.assertNotEqual(before,self.snapshot(self.model))
        self.model.rootAssembly.features['STEP05_DP_RP']=feature
        feature.id=43
        self.assertNotEqual(before,self.snapshot(self.model))
        feature.id=42
        del self.model.constraints['STEP05_DP_TIE']
        self.assertNotEqual(before,self.snapshot(self.model))
        self.model.constraints.clear()
        with self.assertRaisesRegex(ValueError,'STEP05_REQUIRED'):self.snapshot(self.model)

    def test_suppression_changes_detected_for_both_repositories(self):
        before=self.snapshot(self.model)
        for obj in (self.model.constraints['STEP05_DP_TIE'],self.model.rootAssembly.features['STEP05_DP_RP']):
            obj.suppressed=True
            self.assertNotEqual(before,self.snapshot(self.model))
            obj.suppressed=False
            self.assertEqual(before,self.snapshot(self.model))

    def test_step06_objects_do_not_change_snapshot(self):
        before=self.snapshot(self.model)
        self.model.constraints['STEP06_COUPLING_P01_SUPPORT']=Feature()
        self.model.rootAssembly.features['STEP06_RP_P01_SUPPORT']=Feature()
        self.assertEqual(before,self.snapshot(self.model))

    def test_suppression_method_and_safe_fallbacks(self):
        safe=self.ns['safe_suppressed']
        self.assertTrue(safe(NS(isSuppressed=lambda:True,suppressed=False)))
        class Fallback:
            suppressed=True
            def isSuppressed(self):raise FeatureError('not applicable')
        self.assertTrue(safe(Fallback()))
        class Unavailable:
            def __getattr__(self,name):raise FeatureError('not applicable')
        self.assertFalse(safe(Unavailable()))
