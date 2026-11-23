import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest

from cadtocae.beam_brace_tie_runtime import abaqus_name, item, text, surface_key
from cadtocae.runtime_compatibility import assert_runtime_compatible


class SlavePreflightTests(unittest.TestCase):
    def setUp(self):
        self.namespace = dict(abaqus_name=abaqus_name, item=item, text=text, json=json, surface_key=surface_key)
        self.source = (Path(__file__).resolve().parents[1]/'src/cadtocae/tie_preflight_runtime.py').read_text()
        exec(self.source, self.namespace)
        self.batch = self.namespace['Step05TieBatch']()
        self.model = NS(constraints={}, rootAssembly=NS(surfaces={}, instances={}, regenerate=lambda: None))
        self.model.Tie = lambda **kw: self.model.constraints.update({kw['name']: NS(**kw)})

    def surface(self, name, instance='HOOP_A', face=0, nodes=()):
        value = NS(faces=[NS(instanceName=instance, index=face,
            getNodes=lambda: [NS(label=n) for n in nodes])])
        self.model.rootAssembly.surfaces[name] = value
        return value

    def stage(self, name, slave, master=None):
        slave_name='EMPTY'
        for key,value in self.model.rootAssembly.surfaces.items():
            if value is slave: slave_name=key
        instance=slave.faces[0].instanceName if slave.faces else 'UNSPECIFIED'
        self.batch.stage(self.model, master_surface_name='MASTER', slave_surface_name=slave_name,
            master_instance='COLUMN_DOWN', slave_instance=instance, name=name, slave=slave, master=master,
            positionToleranceMethod='COMPUTED', adjust='ON', tieRotations='ON', thickness='ON')

    def test_same_face_different_side_and_name_fails_before_any_tie(self):
        self.stage('TIE_A', self.surface('SURF_A'))
        self.stage('TIE_B', self.surface('SURF_B'))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            path.write_text(json.dumps(dict(status='PENDING_TIE_PREFLIGHT', connections=[dict(tie='TIE_A',tie_present=False)])))
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError,
                    'same slave geometry.*instance=HOOP_A.*TIE_A, TIE_B.*SURF_A, SURF_B'):
                self.batch.finish(str(path))
            self.assertEqual(self.model.constraints, {})
            self.assertEqual(json.loads(path.read_text())['overall_status'], 'FAILED')
            self.assertFalse(json.loads(path.read_text())['connections'][0]['tie_present'])

    def test_node_check_skipped_even_when_mesh_exists(self):
        self.model.rootAssembly.instances['HOOP_A']=NS(nodes=[1,2,3])
        self.stage('A',self.surface('A',face=0,nodes=(4,5)))
        self.stage('B',self.surface('B',face=1,nodes=(5,6)))
        self.assertEqual(self.batch.check(),2)
        for record in self.batch.diagnostics:
            self.assertTrue(record['mesh_available'])
            self.assertEqual(record['node_level_check'],'skipped')

    def test_no_native_mesh_creates_ties_without_getnodes_or_remesh(self):
        def forbidden(*args,**kwargs):
            self.fail('No native mesh: node access or premature meshing attempted')
        for name,face in (('FRONT',0),('REAR',3)):
            surface=self.surface(name,'INCLINED_BEAM',face)
            surface.faces[0].getNodes=forbidden
            self.stage(name,surface)
        self.model.rootAssembly.instances['INCLINED_BEAM']=NS(nodes=[],generateMesh=forbidden)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            path.write_text(json.dumps(dict(status='PENDING_TIE_PREFLIGHT')))
            self.batch.finish(str(path))
            report=json.loads(path.read_text())
        self.assertEqual(len(self.model.constraints),2)
        self.assertEqual(report['slave_preflight']['status'],'SUCCESS')
        for record in report['slave_preflight']['geometry_checks']:
            self.assertFalse(record['mesh_available'])
            self.assertEqual(record['node_level_check'],'skipped')
            self.assertEqual(record['slave_region'],record['tie'])

    def test_explicit_names_and_objects_are_separate(self):
        slave=self.surface('SEMANTIC_SLAVE','HOOP_A',8)
        self.stage('TIE_A',slave)
        record=self.batch.region_records[(id(self.model),'TIE_A')]
        self.assertIs(record['slave_surface'],slave)
        self.assertEqual(record['slave_surface_name'],'SEMANTIC_SLAVE')
        self.assertEqual(record['slave_face_ids'],[8])
        self.assertEqual(record['slave_instance'],'HOOP_A')
        self.assertNotIn('slave_surface_name',self.batch.entries[0][1])

    def test_existing_surface_key_without_name_attribute(self):
        slave=self.surface('SEMANTIC_SLAVE')
        self.assertFalse(hasattr(slave,'name'))
        self.assertEqual(surface_key(self.model.rootAssembly,slave),'SEMANTIC_SLAVE')
        self.assertEqual(surface_key(self.model.rootAssembly,('SEMANTIC_SLAVE',)),'SEMANTIC_SLAVE')

    def test_no_mesh_geometry_conflict_still_fails(self):
        def no_mesh(): raise RuntimeError('The instance does not contain a native mesh.')
        for name in ('A','B'):
            surface=self.surface(name)
            surface.faces[0].getNodes=no_mesh
            self.stage(name,surface)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError,'face id=0'):
            self.batch.check()

    def test_same_indices_different_instances_and_shared_master_allowed(self):
        master=self.surface('MASTER','COLUMN_DOWN')
        self.stage('A',self.surface('A','HOOP_A'),master)
        self.stage('B',self.surface('B','HOOP_B'),master)
        self.assertEqual(self.batch.check(),2)

    def test_distinct_faces_same_instance_allowed(self):
        self.stage('A',self.surface('A',face=0))
        self.stage('B',self.surface('B',face=3))
        self.assertEqual(self.batch.check(),2)

    def test_existing_unplanned_tie_is_checked(self):
        slave=self.surface('OLD')
        self.model.constraints['OLD_TIE']=NS(slave=('OLD',),positionToleranceMethod='COMPUTED')
        self.stage('NEW',slave)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError,'multiple Tie'):
            self.batch.check()

    def test_reuse_not_counted_twice(self):
        slave=self.surface('A')
        self.model.constraints['A']=NS(slave=slave,positionToleranceMethod='COMPUTED')
        self.stage('A',slave)
        self.assertEqual(self.batch.check(),1)

    def test_empty_region_fails_closed(self):
        self.stage('A',NS(name='EMPTY',faces=[]))
        with self.assertRaisesRegex(ValueError,'empty/unsupported'):
            self.batch.check()

    def test_runtime_compatibility(self):
        assert_runtime_compatible(self.source)
        import ast
        for node in ast.walk(ast.parse(self.source)):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                self.assertNotIn(node.func.attr,('getNodes','getElements','getElementFaces','getConnectivity','generateMesh'))
            if isinstance(node,ast.Attribute):
                self.assertNotEqual(node.attr,'name')

    def test_formal_surface_region_name_assumptions_do_not_return(self):
        import ast
        root=Path(__file__).resolve().parents[1]/'src/cadtocae'
        for filename in ('beam_brace_tie_runtime.py','column_column_tie_runtime.py','column_hoop_tie_runtime.py'):
            for node in ast.walk(ast.parse((root/filename).read_text(encoding='utf-8'))):
                if isinstance(node,ast.Attribute) and node.attr=='name':
                    self.assertIsInstance(node.value,ast.Name)
                    self.assertIn(node.value.id,('part','p','bp','datum','feature'))
