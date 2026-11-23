import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from cadtocae.bolt_coupling_update_runtime import bolt_coupling_names, update_bolt_couplings


class Coupling:
    def __init__(self):
        self.couplingType='DISTRIBUTING';self.u1=self.u2=self.u3=True
        self.ur1=self.ur2=self.ur3=True;self.suppressed=False
        self.controlPoint=('original-rp',);self.surface=('original-hole',);self.calls=0
    def setValues(self,**kwargs):
        self.calls+=1
        if getattr(self,'fail_once',False):
            self.fail_once=False
            raise ValueError('injected')
        self.__dict__.update(kwargs)


class BoltRuleTests(unittest.TestCase):
    def run_update(self,model):
        constants=NS(ON=True,OFF=False,KINEMATIC='KINEMATIC')
        with tempfile.TemporaryDirectory() as folder,patch.dict('sys.modules',abaqusConstants=constants,interaction=NS()):
            return update_bolt_couplings(NS(models={'model':model}),str(Path(folder)/'report.json'),'model')

    def model(self):
        return NS(constraints={name:Coupling() for name in bolt_coupling_names()},
                  sections={'K':(5.e8,2.e8,2.e8)},loads={'preload':1234},orientations={'axes':[(1,0,0)]})

    def test_all_sixteen_existing_and_preserve_other_data(self):
        m=self.model();before=copy.deepcopy((m.sections,m.loads,m.orientations))
        report=self.run_update(m)
        self.assertEqual(report['updated_couplings'],16)
        for c in m.constraints.values():
            self.assertEqual((c.couplingType,c.u1,c.u2,c.u3,c.ur1,c.ur2,c.ur3),('KINEMATIC',True,True,True,False,False,False))
            self.assertEqual(c.controlPoint,('original-rp',));self.assertEqual(c.surface,('original-hole',))
        self.assertEqual(before,(m.sections,m.loads,m.orientations))

    def test_missing_last_target_zero_mutation(self):
        m=self.model();del m.constraints[bolt_coupling_names()[-1]]
        with self.assertRaisesRegex(ValueError,'Missing'):self.run_update(m)
        self.assertTrue(all(c.calls==0 for c in m.constraints.values()))

    def test_rollback(self):
        m=self.model();m.constraints[bolt_coupling_names()[3]].fail_once=True
        with self.assertRaisesRegex(ValueError,'injected'):self.run_update(m)
        self.assertTrue(all(c.couplingType=='DISTRIBUTING' and c.ur1 for c in m.constraints.values()))

    def test_step05_not_selected(self):
        m=self.model();m.constraints['STEP05_COUPLING']=Coupling();self.run_update(m)
        self.assertEqual(m.constraints['STEP05_COUPLING'].calls,0)


if __name__=='__main__':unittest.main()
