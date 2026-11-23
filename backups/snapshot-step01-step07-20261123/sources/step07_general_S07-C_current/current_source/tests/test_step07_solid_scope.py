import unittest
from cadtocae.step07_mesh_rules import MESH_RULES
class SolidScopeTests(unittest.TestCase):
 def test_only_luan_project_override(self):
  p='SP_DC_ANG19_LUANLUANLUAN-T0203'
  self.assertEqual(set(MESH_RULES['project_hoop_uniform_sizes']),{p})
  self.assertEqual(MESH_RULES['project_hoop_uniform_sizes'][p],{'HOOP_01':.008,'HOOP_02':.008,'HOOP_03':.008})
  self.assertEqual(MESH_RULES['project_support_uniform_sizes'],{p:.008})
 def test_other_roles_and_quality_unchanged(self):
  self.assertEqual(MESH_RULES['sizes']['HOOP'],.015)
  self.assertEqual(MESH_RULES['sizes']['PURLIN_SUPPORT'],.01)
  self.assertEqual(MESH_RULES['shape_warning'],.05)
  self.assertEqual(MESH_RULES['sizes']['INCLINED_BEAM'],.08)
