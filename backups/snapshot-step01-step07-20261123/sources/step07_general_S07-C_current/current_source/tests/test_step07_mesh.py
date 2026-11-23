import json,math,tempfile,unittest,sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from cadtocae.step07_mesh_setup import generate_stage3
from cadtocae.step07_mesh_desktop import scan_mesh_projects,validate_accepted
from cadtocae.step07_mesh_rules import MESH_RULES
from cadtocae import step07_mesh_runtime as rt
rt.math=math

class MeshTests(unittest.TestCase):
    def fixture(self,p):
        project='DP_ANG14_FULL_ID';summary=p/(project+'_assembly_summary.json')
        summary.write_text(json.dumps(dict(project_id=project,model_name=project,instances=[dict(instance_name='i')],structure_type='DP')))
        (p/'CAE_Results').mkdir();source=p/'CAE_Results'/(project+'_step07_02_v2.cae');source.write_bytes(b'accepted')
        return summary,source
    def test_discovery_excludes_backups_requires_explicit_version(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);summary,source=self.fixture(p)
            source.with_name('DP_ANG14_FULL_ID_step07_02_v3_session_input.cae').write_bytes(b'backup')
            source.with_name('DP_ANG14_FULL_ID_step07_02_v3.cae').write_bytes(b'candidate')
            scan=scan_mesh_projects(p);row=scan['projects'][0]
            self.assertEqual(len(row['files']['stage2_candidates']),2);self.assertNotIn('cae',row['files'])
            self.assertEqual(validate_accepted(row,source),str(source))
            with self.assertRaises(ValueError):validate_accepted(row,source.with_name('DP_ANG14_FULL_ID_step07_02_v3_session_input.cae'))
    def test_generation_flat_protected_and_default_current_session(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);summary,source=self.fixture(p)
            first=generate_stage3(summary,source,p);second=generate_stage3(summary,source,p)
            self.assertTrue(first['script'].endswith('_step07_03_mesh.py'));self.assertTrue(second['script'].endswith('_mesh_v2.py'))
            self.assertEqual(Path(first['plan']['manual_working_copy']).read_bytes(),b'accepted')
            self.assertFalse(Path(first['plan']['output_cae']).exists());self.assertEqual(first['plan']['execution_mode'],'CURRENT_SESSION_DEBUG')
            self.assertEqual(source.read_bytes(),b'accepted')
    def test_duplicate_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);self.fixture(p);other=p/'other';other.mkdir();self.fixture(other)
            self.assertTrue(all(not r['ready'] for r in scan_mesh_projects(p)['projects']))
    def test_quality_fails_closed_but_retains_warning(self):
        constants=NS(ANALYSIS_CHECKS='analysis',ASPECT_RATIO='aspect',SHAPE_FACTOR='shape')
        data={'failedElements':[],'warningElements':[NS(label=42)],'naElements':[],'numElements':1}
        p=NS(name='part',verifyMeshQuality=lambda **kw:data if kw['criterion']=='analysis' else {'failedElements':[]})
        with patch.dict(sys.modules,{'abaqusConstants':constants}):
            result=rt.m3_quality(p,{'mesh_rules':MESH_RULES});self.assertEqual(result['analysis']['warningElements'],[42])
            data['failedElements']=[NS(label=1)]
            with self.assertRaisesRegex(ValueError,'QUALITY_FAILED'):rt.m3_quality(p,{'mesh_rules':MESH_RULES})
            data['failedElements']=[];data['naElements']=[NS(label=1)]
            with self.assertRaisesRegex(ValueError,'NOT_EVALUATED'):rt.m3_quality(p,{'mesh_rules':MESH_RULES})
    def test_region_resolution_avoids_repository_contains(self):
        class Repo(dict):
            def __contains__(self,key):raise AssertionError('Unsafe Abaqus repository contains')
        a=NS(sets=Repo(),surfaces=Repo({'surface':42}))
        self.assertEqual(rt.m3_region(a,('surface',)),42)
        with self.assertRaisesRegex(ValueError,'MISSING'):rt.m3_region(a,('missing',))
    def test_existing_mesh_requires_review_and_is_not_destroyed(self):
        constants=NS(**{k:k for k in ('STANDARD','C3D10','S4R','S3','TET','FREE','QUAD_DOMINATED','FINER','ADVANCING_FRONT','FIXED','SWEEP','QUAD','STRUCTURED')})
        p=NS(name='existing',cells=[],nodes=[1],elements=[NS(type='S4R')],getUnmeshedRegions=lambda:None)
        def forbidden(**kw):raise AssertionError('Existing mesh must not be reseeded')
        p.seedPart=forbidden;p.generateMesh=forbidden
        with patch.dict(sys.modules,{'abaqusConstants':constants,'mesh':NS()}),patch.object(rt,'m3_quality',return_value={}),patch.object(rt,'m3_mesh_digest',return_value='unchanged'):
            with self.assertRaisesRegex(ValueError,'PROVENANCE_REVIEW'):rt.m3_mesh_part(p,{}, {'mesh_rules':MESH_RULES},{})
    def test_optimization_rejects_stage3_input(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);summary,source=self.fixture(p)
            old=source.with_name('DP_ANG14_FULL_ID_step07_03.cae');old.write_bytes(b'old mesh')
            with self.assertRaisesRegex(ValueError,'Step07-02'):generate_stage3(summary,old,p)
    def test_unrelated_short_edges_not_refined(self):
        part=NS(faces=[])
        assembly=NS(sets={'GENERAL_SHORT_EDGE':NS()},surfaces={},instances={})
        model=NS(rootAssembly=assembly,constraints={},parts={'beam':part})
        data={'beam':{'roles':['INCLINED_BEAM'],'surface_area_m2':1.}}
        self.assertEqual(rt.m3_refinements(model,{'mesh_rules':MESH_RULES},data),{'beam':{}})

if __name__=='__main__':unittest.main()

class SpatialRegionTests(unittest.TestCase):
    def test_spatial_membership_detects_moved_region_not_index_changes(self):
        rt.json=json
        class Edge:
            instanceName=''
            index=4
            pointOn=((.5,0.,0.),)
            def getSize(self,**kw):return 1.
            def getVertices(self):return (0,1)
        e=Edge();region=NS(faces=[],edges=[e],vertices=[],referencePoints=[])
        a=NS(sets={'connection':region},surfaces={},instances={},vertices=[NS(pointOn=((0.,0.,0.),)),NS(pointOn=((1.,0.,0.),))])
        m=NS(rootAssembly=a,parts={})
        baseline=rt.m3_spatial_regions(m)
        e.index=99
        self.assertEqual(rt.m3_spatial_regions(m),baseline)
        e.pointOn=((.5,.1,0.),)
        self.assertNotEqual(rt.m3_spatial_regions(m),baseline)
        region.edges=[]
        self.assertNotEqual(rt.m3_spatial_regions(m),baseline)
