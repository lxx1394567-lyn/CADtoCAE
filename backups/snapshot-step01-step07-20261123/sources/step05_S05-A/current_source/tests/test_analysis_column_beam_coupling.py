import contextlib
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from analysis_fake_cae import Part,Instance,Repository,DynamicStation
import test_analysis_column_column_tie as cc
import test_analysis_beam_brace_tie as bb
from cadtocae.column_beam_coupling import resolve_coupling,read_coupling_config,FIELDS
from cadtocae.beam_brace_tie import generate
from cadtocae.analysis_project import discover_project_folder
from cadtocae.runtime_compatibility import assert_runtime_compatible


def config():
    return dict(zip(FIELDS,('COLUMN_BEAM_COUPLING',True,50.,'DISTRIBUTING',True,True,True,True,True,True)))


class CouplingTests(unittest.TestCase):
    def setUp(self):
        self.base=cc.ColumnTests();self.addCleanup(self.base.doCleanups);self.base.setUp()
        self.runtime=self.base.runtime
        self.source=(Path(__file__).resolve().parents[1]/'src/cadtocae/column_beam_coupling_runtime.py').read_text()
        exec(self.source,self.runtime)
        summary,components=cc.inputs()
        summary['instances'].append(dict(component_code='INCLINED_BEAM',instance_name='BEAM',part_name='BEAM',
            geometry_info={'length':2.},placement=dict(translation=[0,0,0],rotation_steps=[])))
        components.append(dict(component_code='INCLINED_BEAM',part_name='BEAM',length_m=2.,section_kind='C_CHANNEL',
            model_policy='SHELL',section_params_m={'h_m':.09,'b_m':.05},thickness_m=.002))
        self.inputs=(summary,components)
        self.rule=resolve_coupling(summary,components,[0,0,1.],1.,config())
        self.plan=dict(model_name='TEST',column_beam_coupling=self.rule)
        class Pipe(cc.Pipe):
            @property
            def edges(self):
                return [NS(index=i,pointOn=((self.member['radius_m'],0,z),),getVertices=lambda i=i:(i,),
                           getSize=lambda printResults=False:2*math.pi*self.member['radius_m']) for i,z in enumerate(self.stations)]
        class PipeInstance(cc.Instance):
            @property
            def edges(self):
                return [NS(index=e.index,instanceName=self.name,pointOn=self.vertices[e.index].pointOn,
                           getVertices=e.getVertices,getSize=e.getSize) for e in self.part.edges]
        class BeamPart(Part):
            def DatumPlaneByPrincipalPlane(self,principalPlane,offset):
                return self.feature('DatumPlane',NS(point=(0,0,offset),normal=(0,0,1)))
        class BeamInstance(Instance):
            @property
            def edges(self):
                return [NS(index=e.index,instanceName=self.name,pointOn=(self.mapped(e.pointOn[0]),),
                           getVertices=e.getVertices,getSize=e.getSize) for e in self.part.edges]
        self.cp=Pipe(self.rule['column']);self.ci=PipeInstance(self.cp)
        self.bp=BeamPart('BEAM',.05,.09,.015,2.,(1.,))
        self.bp.sets={'SET_BEAM_SEC_F':DynamicStation(self.bp,1.)}
        self.bi=BeamInstance('BEAM',self.bp,((1,0,0),(0,1,0),(0,0,1)),(0,0,0))
        self.a=self.base.a;self.model=self.base.model
        self.model.parts[self.cp.name]=self.cp;self.model.parts['BEAM']=self.bp
        self.a.instances[self.ci.name]=self.ci;self.a.instances['BEAM']=self.bi
        self.a.features=Repository();self.a.referencePoints={}
        self.a.Set=lambda name,**kw:self.a.sets.update({name:NS(**kw)})
        self.a.Surface=lambda name,side1Edges:self.a.surfaces.update({name:NS(edges=side1Edges,sides=['SIDE1'])})
        def rp(point):
            index=900+len(self.a.referencePoints)
            self.a.referencePoints[index]=NS(coordinate=tuple(point))
            f=NS(id=index,name='RP-auto');self.a.features[f.name]=f
            return f
        self.a.ReferencePoint=rp
        self.a.getCoordinates=lambda entity:entity.coordinate
        def coupling(**kw):
            self.assertTrue(kw['surface'].edges)
            self.assertEqual(len(kw['controlPoint'].referencePoints),1)
            self.model.constraints[kw['name']]=NS(**kw)
        self.model.Coupling=coupling

    def prepare(self):
        return self.runtime['prepare_coupling_geometry'](self.plan,self.base.mdb,str(self.base.report),'XYPLANE','ON')

    def run_rule(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.runtime['execute_coupling'](self.prepare(),'ON','OFF','DISTRIBUTING','WHOLE_SURFACE','UNIFORM')

    def test_rp_two_couplings_existing_ties_and_repeat(self):
        names=['STEP05_TIE_BEAM_BRACE_FRONT','STEP05_TIE_BEAM_BRACE_REAR','STEP05_TIE_COLUMN_UP_DOWN',
               'STEP05_TIE_COLUMN_DOWN_HOOP_A','STEP05_TIE_COLUMN_DOWN_HOOP_B']
        originals={name:object() for name in names};self.model.constraints.update(originals)
        r=self.run_rule()
        self.assertEqual(r['reference_point']['coordinate'],[0.,0.,3.556])
        self.assertEqual(r['semantic_mapping']['STEP05_RP_COLUMN_UP'],900)
        self.assertTrue(r['reused_step04_f_set'])
        self.assertEqual([t['target_type'] for t in r['targets']],['EDGE','EDGE'])
        a=self.model.constraints['STEP05_COUPLING_COLUMN_UP'];b=self.model.constraints['STEP05_COUPLING_BEAM_F']
        self.assertIs(a.controlPoint,b.controlPoint);self.assertIsNot(a.surface,b.surface)
        for c in (a,b):
            self.assertEqual(c.couplingType,'DISTRIBUTING')
            for dof in FIELDS[4:]:self.assertEqual(getattr(c,dof),'ON')
        repeated=self.run_rule()
        self.assertFalse(repeated['reference_point']['created'])
        self.assertFalse(any(c['created'] for c in repeated['couplings']))
        self.assertEqual(len(self.a.referencePoints),1);self.assertEqual(len(self.model.constraints),7)
        for name in names:self.assertIs(self.model.constraints[name],originals[name])
        self.assertFalse(self.cp.deleted);self.assertNotIn('deleteMesh',self.bp.mutations)

    def test_missing_set_reuses_existing_f_geometry(self):
        self.bp.sets={}
        r=self.run_rule();self.assertFalse(r['reused_step04_f_set']);self.assertEqual(r['partitions'],[])

    def test_missing_f_partition_deletes_only_beam_mesh(self):
        self.bp.__init__('BEAM',.05,.09,.015,2.)
        r=self.run_rule()
        self.assertEqual(r['mesh_removed'],['BEAM']);self.assertEqual(r['remesh_required_parts'],['BEAM'])
        self.assertEqual(len(r['partitions']),1);self.assertFalse(self.cp.deleted)

    def test_invalid_f_set_fails_without_mutation(self):
        self.bp.sets['SET_BEAM_SEC_F']=NS(edges=[])
        with self.assertRaisesRegex(ValueError,'differs'):self.prepare()
        self.assertFalse(self.cp.deleted);self.assertNotIn('deleteMesh',self.bp.mutations)

    def test_missing_f_with_existing_constraints_fails_clean(self):
        self.bp.__init__('BEAM',.05,.09,.015,2.)
        self.model.constraints['OLD']=object()
        with self.assertRaisesRegex(ValueError,'clean Step02'):self.prepare()
        self.assertNotIn('deleteMesh',self.bp.mutations)

    def test_wrong_f_global_coordinate(self):
        self.rule['f_point'][2]+=.1
        with self.assertRaisesRegex(ValueError,'global F station'):self.run_rule()
        self.assertEqual(self.a.referencePoints,{})

    def test_conflicting_rp_position(self):
        self.run_rule();self.a.referencePoints[900].coordinate=(0,0,0)
        with self.assertRaisesRegex(ValueError,'RP position'):self.run_rule()
        self.assertEqual(len(self.a.referencePoints),1)

    def test_conflicting_coupling_dof(self):
        self.run_rule();self.model.constraints['STEP05_COUPLING_BEAM_F'].ur2='OFF'
        with self.assertRaisesRegex(ValueError,'parameter'):self.run_rule()

    def test_conflicting_surface(self):
        self.run_rule();self.a.surfaces['STEP05_SURF_BEAM_F'].edges=[]
        with self.assertRaisesRegex(ValueError,'edge Surface'):self.run_rule()

    def test_tilted_column_top_uses_axis(self):
        summary,components=self.inputs
        member=summary['instances'][0];member['placement']['axis_direction']=[.6,0,.8]
        r=resolve_coupling(summary,components,[0,0,1],1.,config())
        self.assertAlmostEqual(r['rp_coordinate'][0],.6*2.506)
        self.assertAlmostEqual(r['rp_coordinate'][2],1.05+.8*2.506)

    def test_ambiguous_roles_and_station_fail(self):
        summary,components=self.inputs
        with self.assertRaisesRegex(ValueError,'outside'):resolve_coupling(summary,components,[0,0,0],5,config())
        summary['instances'].append(summary['instances'][0])
        with self.assertRaisesRegex(ValueError,'unique'):resolve_coupling(summary,components,[0,0,0],1,config())

    def test_runtime_no_native_mesh_access(self):
        import ast
        assert_runtime_compatible(self.source)
        calls={n.func.attr for n in ast.walk(ast.parse(self.source)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
        self.assertFalse(calls & {'Tie','getNodes','generateMesh','PartitionFaceByExtendFace'})

    def test_generated_order_and_frozen_modules(self):
        fixture=bb.PlannerTests();self.addCleanup(fixture.doCleanups);fixture.setUp()
        with patch('cadtocae.beam_brace_tie.build_coupling_plan',return_value=self.rule):
            source=generate(discover_project_folder(fixture.root),fixture.config)['script'].read_text()
        self.assertLess(source.rfind('coupling_context = prepare_coupling_geometry'),source.rfind('    execute(PLAN'))
        self.assertLess(source.rfind('tie_batch.finish(REPORT)'),source.rfind('    execute_coupling('))
        assert_runtime_compatible(source)

    def test_config_default_length_and_fixed_dofs(self):
        row=list(config().values());row[2]=None
        sheet=NS(values=[FIELDS,tuple(row)])
        class Book:
            sheetnames=['Coupling_Config']
            def __getitem__(self,key):return sheet
            def close(self):pass
        with patch('cadtocae.column_beam_coupling.load_workbook',return_value=Book()):
            self.assertEqual(read_coupling_config('unused')['column_top_length_mm'],50.)
            row[5]=False;sheet.values=[FIELDS,tuple(row)]
            with self.assertRaisesRegex(ValueError,'six DOFs'):read_coupling_config('unused')

    def test_config_missing_sheet_is_disabled(self):
        with patch('cadtocae.column_beam_coupling.load_workbook',return_value=NS(sheetnames=[],close=lambda:None)):
            self.assertIsNone(read_coupling_config('unused'))
