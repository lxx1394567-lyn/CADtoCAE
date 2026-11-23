import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from cadtocae.purlin_bolt_preset_runtime import validate_bolt_preset,apply_bolt_preset,bolt_preset_metadata


class PresetTests(unittest.TestCase):
    def section(self):
        s=NS(translationalType='CARTESIAN',rotationalType='NONE',behaviorOptions=[])
        s.setValues=lambda **kw:s.__dict__.update(kw)
        return s

    def modules(self):
        return patch.dict('sys.modules',abaqusConstants=NS(CARTESIAN='CARTESIAN',NONE='NONE',LINEAR='LINEAR',UNCOUPLED='UNCOUPLED'),
                          connectorBehavior=NS(ConnectorElasticity=lambda **kw:NS(**kw)))

    def test_exact_three_translational_uncoupled_components(self):
        with self.modules():
            s=self.section();apply_bolt_preset(s);validate_bolt_preset(s)
        self.assertEqual(s.behaviorOptions[0].components,(1,2,3))
        self.assertEqual(s.behaviorOptions[0].table,((5.e8,2.e8,2.e8),))

    def test_existing_values_replaced_by_one_option(self):
        with self.modules():
            s=self.section();s.behaviorOptions=[object(),object()];apply_bolt_preset(s)
            self.assertEqual(len(s.behaviorOptions),1)

    def test_rotational_type_rejected_without_mutation(self):
        with self.modules():
            s=self.section();s.rotationalType='CARDAN'
            with self.assertRaises(ValueError):apply_bolt_preset(s)
            self.assertEqual(s.behaviorOptions,[])

    def test_wrong_coupling_or_stiffness_rejected(self):
        with self.modules():
            for field,value in [('coupling','COUPLED'),('components',(1,2,3,4)),('table',((1.,2.,3.),))]:
                s=self.section();apply_bolt_preset(s);setattr(s.behaviorOptions[0],field,value)
                with self.assertRaises(ValueError):validate_bolt_preset(s)

    def test_temporary_parameter_metadata(self):
        self.assertEqual(bolt_preset_metadata()['parameter_source'],'TEMPORARY_PRESET')
        self.assertEqual(bolt_preset_metadata()['behavior_status'],'PRESET_FOR_WORKFLOW_VALIDATION')
