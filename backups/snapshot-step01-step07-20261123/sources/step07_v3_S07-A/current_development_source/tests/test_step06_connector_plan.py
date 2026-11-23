from dataclasses import replace
import json
import unittest

from cadtocae.connector_plan import build_connector_plan, PROPERTY_FAMILIES
from cadtocae.hole_inputs import normalize_hole_rows
from cadtocae.hole_plan import build_hole_plan
from test_step06_hole_inputs import input_rows
from test_step06_hole_plan import fixture


class ConnectorPlanTests(unittest.TestCase):
    def setUp(self):
        summary,components=fixture()
        self.holes=build_hole_plan(summary,normalize_hole_rows(input_rows()),components)

    def test_two_intents_no_stiffness_or_runtime_objects(self):
        plan=build_connector_plan(self.holes)
        self.assertEqual(len(plan.connections),2)
        self.assertEqual({p.connector_property for p in plan.connections},{'PURLIN_BOLT'})
        self.assertTrue(all(p.behavior_status=='NOT_CALIBRATED' for p in plan.connections))
        self.assertEqual(PROPERTY_FAMILIES,('PURLIN_BOLT','HOOP_BOLT'))
        payload=json.dumps(plan.to_dict(),allow_nan=False)
        for name in ('stiffness','CutExtrude','ReferencePoint','WirePolyLine'):self.assertNotIn(name,payload)

    def test_stable_connector_id(self):
        names={p.connector_id for p in build_connector_plan(self.holes).connections}
        self.assertEqual(names,{'STEP06_CONNECTOR_P01_PS_TO_PURLIN','STEP06_CONNECTOR_P01_PS_TO_BEAM'})

    def test_missing_derived_hole_rejected(self):
        with self.assertRaises(ValueError):build_connector_plan(replace(self.holes,derived_holes=()))

    def test_inconsistent_target_rejected(self):
        wrong=replace(self.holes.derived_holes[0],hole_diameter_m=.3)
        with self.assertRaises(ValueError):
            build_connector_plan(replace(self.holes,derived_holes=(wrong,self.holes.derived_holes[1])))
