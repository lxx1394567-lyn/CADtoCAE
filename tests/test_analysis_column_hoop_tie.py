import contextlib
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from cadtocae.column_hoop_tie import resolve_hoop, build_hoop_plan, hoop_enabled
from cadtocae.runtime_compatibility import assert_runtime_compatible
from cadtocae.beam_brace_tie import generate
from cadtocae.analysis_project import discover_project_folder
import test_analysis_column_column_tie as cc
import test_analysis_beam_brace_tie as bb


def inputs(code='HOOP'):
    summary,components=cc.inputs()
    for label,angle in (('A',0),('B',180)):
        summary['instances'].append(dict(component_code=code,canonical_role='HOOP',part_name='P_HOOP',
            instance_name='HOOP_01_'+label,connection_group='HOOP_01',
            placement=dict(translation=[0.,0.,1.26],rotation_steps=[],rotation_angle=angle,rotation_axis=[0.,0.,1.])))
    components.append(dict(component_code=code,part_name='P_HOOP',section_kind='HOOP_BAND',model_policy='SOLID',thickness_m=.006,
        section_params_m=dict(width_m=.08,inner_radius_m=.0885)))
    return summary,components


class CurvedFace:
    def __init__(self,index,radius,lo,hi,half,vids,origin=(0,0,0),instance='',normal_sign=1,flat=False):
        self.index,self.instanceName=index,instance
        self.r,self.lo,self.hi,self.half=radius,lo,hi,half
        self.ids,self.origin,self.normal_sign,self.flat=vids,origin,normal_sign,flat
        y0,y1=(-radius,radius) if half==0 else ((0,radius) if half==1 else (-radius,0))
        self.box={'low':(-radius,y0,origin[2]+lo),'high':(radius,y1,origin[2]+hi)}
        self.radial=(1,0,0) if half==0 else (0,half,0)
        self.pointOn=((origin[0]+radius*self.radial[0],origin[1]+radius*self.radial[1],origin[2]+(lo+hi)/2),self.radial)
    def getVertices(self): return self.ids
    def getSize(self,printResults=False): return (2 if self.half==0 else 1)*math.pi*self.r*(self.hi-self.lo)
    def getCurvature(self,point): return {'curvature1':0.,'curvature2':0. if self.flat else 1./self.r}
    def getNormal(self,point): return tuple(self.normal_sign*x for x in self.radial)
    def getCentroid(self):
        y=0 if self.half==0 else self.half*2*self.r/math.pi
        return ((self.origin[0],self.origin[1]+y,self.origin[2]+(self.lo+self.hi)/2),)


class Pipe(cc.Pipe):
    def __init__(self,member):
        super().__init__(member)
        self.split=None
    @property
    def vertices(self): return self.make_vertices((0,0,0))
    def make_vertices(self,origin):
        return [NS(pointOn=((origin[0]+sign*self.member['radius_m'],origin[1],origin[2]+z),))
                for z in self.stations for sign in (1,-1)]
    def make_faces(self,origin,instance,axis=None):
        faces=cc.Faces()
        for j,(lo,hi) in enumerate(zip(self.stations,self.stations[1:])):
            halves=(1,-1) if self.split and lo>=self.split[0]-1.e-6 and hi<=self.split[1]+1.e-6 else (0,)
            for half in halves:
                ids=(2*j,2*j+1,2*j+2,2*j+3) if half else (2*j,2*j+2)
                faces.append(CurvedFace(len(faces),self.member['radius_m'],lo,hi,half,ids,origin,instance,self.sign))
        return faces
    def DatumPointByCoordinate(self,coords):
        f=self.feature('Point',coords=coords)
        self.datums[f.id]=f
        return f
    def DatumPlaneByThreePoints(self,point1,point2,point3):
        # Verify the requested plane is the observed A/B (XZ) boundary.
        self.asserted_plane=tuple(p.coords for p in (point1,point2,point3))
        assert abs(point3.coords[1])<1.e-6
        f=self.feature('HalfPlane')
        self.datums[f.id]=f
        return f
    def PartitionFaceByDatumPlane(self,datumPlane,faces):
        if hasattr(datumPlane,'offset'):
            return super().PartitionFaceByDatumPlane(datumPlane,faces)
        self.split=(min(f.lo for f in faces),max(f.hi for f in faces))
        return self.feature('HalfPartition')


class Instance(cc.Instance):
    @property
    def vertices(self): return self.part.make_vertices(self.part.member['origin'])


class Hoop:
    def __init__(self,label):
        self.name='HOOP_01_'+label
        self.partName='P_HOOP'
        self.dependent='ON'
        self.vertices=[]
        self.faces=cc.Faces()
        half=1 if label=='A' else -1
        for radius,flat,normal in ((.0885,False,-1),(.0945,False,1),(.0885,True,-1)):
            ids=[]
            for z in (1.26,1.34):
                for x in (radius,-radius):
                    ids.append(len(self.vertices))
                    self.vertices.append(NS(pointOn=((x,0,z),)))
            self.faces.append(CurvedFace(len(self.faces),radius,1.26,1.34,half,ids,instance=self.name,normal_sign=normal,flat=flat))


class HoopTests(unittest.TestCase):
    def setUp(self):
        self.base=cc.ColumnTests()
        self.addCleanup(self.base.doCleanups)
        self.base.setUp()
        self.runtime=self.base.runtime
        source=(Path(__file__).resolve().parents[1]/'src/cadtocae/column_hoop_tie_runtime.py').read_text(encoding='utf-8')
        assert_runtime_compatible(source)
        exec(source,self.runtime)
        self.rule=resolve_hoop(*inputs())
        self.plan=dict(self.base.plan,column_hoop_tie=self.rule)
        self.model=self.base.model
        self.a=self.base.a
        self.pipe=Pipe(self.base.rule['members'][1])
        self.model.parts[self.pipe.name]=self.pipe
        self.a.instances['COLUMN_DOWN_01']=Instance(self.pipe)
        self.model.parts['P_HOOP']=NS(cells=[1],features={},elements=[1])
        for label in ('A','B'): self.a.instances['HOOP_01_'+label]=Hoop(label)

    def prepare(self,previous=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.runtime['prepare_hoop'](self.plan,self.base.mdb,str(self.base.report),'hoop',previous,'XYPLANE','ON')
    def finish(self,ctx):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.runtime['execute_hoop'](ctx,'ON','COMPUTED')

    def test_real_pair_band_partitions_two_ties_and_reuse(self):
        ctx=self.prepare()
        self.assertEqual(ctx['overlap'],[1.26,1.34])
        self.assertAlmostEqual(ctx['report']['overlap_length'],.08)
        self.assertEqual(self.pipe.stations,[0,1.26,1.34,1.6])
        self.assertEqual(self.pipe.split,(1.26,1.34))
        r=self.finish(ctx)
        self.assertEqual(r['status'],'SUCCESS')
        self.assertEqual(len(self.model.constraints),2)
        records=r['connections']
        self.assertEqual(len(records),2)
        self.assertFalse(set(records[0]['column_face_ids']) & set(records[1]['column_face_ids']))
        for rec,label in zip(records,('A','B')):
            self.assertEqual(rec['tie'],'STEP05_TIE_COLUMN_DOWN_HOOP_'+label)
            self.assertEqual(rec['master'],'COLUMN_DOWN_01')
            self.assertEqual(rec['component_mapping']['canonical_role'],'HOOP')
            self.assertEqual(rec['component_mapping']['raw_component_code'],'HOOP')
            self.assertEqual(rec['slave'],'HOOP_01_'+label)
            self.assertEqual(rec['master_physical_side'],'OUTER')
            self.assertEqual(rec['slave_physical_side'],'INNER')
            tie=self.model.constraints[rec['tie']]
            self.assertEqual(tie.master.name,'STEP05_SURF_COLUMN_DOWN_HOOP_'+label)
            self.assertEqual(tie.slave.name,'STEP05_SURF_HOOP_'+label+'_COLUMN_DOWN')
            self.assertEqual(rec['hoop_face_ids'],[0])
        self.assertFalse(r['material_removed'])
        self.assertEqual(self.model.parts['P_HOOP'].features,{})
        self.assertEqual(self.model.parts['P_HOOP'].elements,[1])
        repeat=self.finish(self.prepare(r))
        self.assertFalse(any(c['created'] for c in repeat['connections']))
        self.assertEqual(repeat['partitions'],[])

    def test_all_five_ties_with_frozen_beam_and_column_executors(self):
        beam=bb.RuntimeTests()
        self.addCleanup(beam.doCleanups)
        beam.setUp()
        self.model.parts.update(beam.model.parts)
        self.a.instances.update(beam.model.rootAssembly.instances)
        self.base.mdb.models['TEST']=self.model
        plan=dict(beam.plan,column_column_tie=self.base.rule,column_hoop_tie=self.rule)
        self.plan=plan
        self.rule_before=json.loads(json.dumps(self.base.rule))
        original_surface=self.a.Surface
        def nameless_surface(**kwargs):
            result=original_surface(**kwargs)
            surface=self.a.surfaces[kwargs['name']]
            if hasattr(surface,'name'): del surface.name
            return result
        self.a.Surface=nameless_surface
        exec((Path(__file__).resolve().parents[1]/'src/cadtocae/tie_preflight_runtime.py').read_text(),self.runtime)
        previous={}
        for repeat in (False,True):
            batch=self.runtime['Step05TieBatch']()
            with contextlib.redirect_stdout(io.StringIO()):
                self.runtime['execute'](plan,self.base.mdb,str(self.base.report),'beam','XYPLANE','ON','COMPUTED',batch)
            ctx=self.prepare(previous.get('column_hoop_tie'))
            with contextlib.redirect_stdout(io.StringIO()):
                self.runtime['execute_column'](plan,self.base.mdb,str(self.base.report),'column',previous.get('column_column_tie'),'XYPLANE','ON','COMPUTED',batch)
            with contextlib.redirect_stdout(io.StringIO()):
                self.runtime['execute_hoop'](ctx,'ON','COMPUTED',batch)
                if not repeat: self.assertEqual(self.model.constraints,{})
                def no_native_mesh():
                    self.fail('Preflight must not query mesh nodes before final remeshing')
                for model,parameters in batch.entries:
                    for face in parameters['slave'].faces:
                        face.getNodes=no_native_mesh
                batch.finish(str(self.base.report))
            self.assertEqual(len(self.model.constraints),5)
            for name in ('STEP05_TIE_COLUMN_UP_DOWN','STEP05_TIE_COLUMN_DOWN_HOOP_A','STEP05_TIE_COLUMN_DOWN_HOOP_B'):
                self.assertNotIn('COLUMN_DOWN_01', {f.instanceName for f in self.model.constraints[name].slave.faces})
            previous=json.loads(self.base.report.read_text())
            self.assertEqual(previous['overall_status'],'SUCCESS')
            self.assertEqual(previous['slave_preflight']['checked_ties'],5)
            for check in previous['slave_preflight']['geometry_checks']:
                self.assertNotEqual(check['slave_instance'],'COLUMN_DOWN_01')
                self.assertEqual(check['node_level_check'],'skipped')
                self.assertEqual(check['slave_region'],batch.region_records[(id(self.model),check['tie'])]['slave_surface_name'])
            self.assertEqual(previous['column_column_tie']['COLUMN_DOWN']['physical_side'],'INNER')
            self.assertEqual(previous['column_column_tie']['COLUMN_UP']['physical_side'],'OUTER')
            self.assertNotEqual(previous['column_column_tie']['COLUMN_DOWN']['shell_side'],previous['column_hoop_tie']['column_shell_side'])
            self.assertEqual(previous['column_column_tie']['ranges']['actual_overlap'],[1.05,1.6])
        self.assertEqual(json.loads(json.dumps(self.base.rule)),self.rule_before)

    def test_family_code_and_same_group_resolution(self):
        self.assertEqual(resolve_hoop(*inputs('HOOP_ASSEMBLY_1'))['group_id'],'HOOP_01')
        summary,components=inputs()
        summary['instances'][-1]['connection_group']='HOOP_02'
        with self.assertRaisesRegex(ValueError,'one complete HOOP group'): resolve_hoop(summary,components)

    def test_ambiguous_extra_hoop_fails(self):
        summary,components=inputs()
        summary['instances'].append(dict(summary['instances'][-1]))
        with self.assertRaisesRegex(ValueError,'one complete HOOP group'): resolve_hoop(summary,components)

    def test_nonoverlap_fails_before_mesh_change(self):
        for label in ('A','B'):
            h=self.a.instances['HOOP_01_'+label]
            for v in h.vertices: v.pointOn=((v.pointOn[0][0],0,v.pointOn[0][2]+2),)
        with self.assertRaisesRegex(ValueError,'has no valid axial overlap'): self.prepare()
        self.assertFalse(self.pipe.deleted)
        self.assertEqual(self.model.constraints,{})

    def test_different_hoop_bands_fail(self):
        h=self.a.instances['HOOP_01_B']
        for v in h.vertices: v.pointOn=((v.pointOn[0][0],0,v.pointOn[0][2]+.01),)
        with self.assertRaisesRegex(ValueError,'axial bands differ'): self.prepare()
        self.assertFalse(self.pipe.deleted)

    def test_outer_and_ear_faces_rejected(self):
        h=self.a.instances['HOOP_01_A']
        ids,_=self.runtime['cht_inner'](h,self.rule['halves'][0],self.rule['column'],[1.26,1.34])
        self.assertEqual(ids,[0])
        h.faces[0].normal_sign=1
        with self.assertRaisesRegex(ValueError,'No unique cylindrical'): self.prepare()

    def test_nonopposite_hoops_rejected(self):
        self.a.instances['HOOP_01_B'].faces[0].half=1
        with self.assertRaisesRegex(ValueError,'not opposite'): self.prepare()

    def test_duplicate_slaves_and_incomplete_union_rejected(self):
        with self.assertRaisesRegex(ValueError,'column master regions overlap'):
            self.runtime['cht_disjoint']([1],[1],[1,2])
        with self.assertRaisesRegex(ValueError,'complete column band'):
            self.runtime['cht_disjoint']([1],[2],[1,2,3])

    def test_pairing_ambiguity_rejected(self):
        ctx=self.prepare()
        inst=self.a.instances['COLUMN_DOWN_01']
        ids=self.runtime['cht_band_ids'](self.pipe,ctx['column']['interval'])
        with self.assertRaisesRegex(ValueError,'Ambiguous HOOP A/B'):
            self.runtime['cht_halves'](inst,ids,ctx['column'],ctx['normal'],[(0,0,1.3),(0,0,1.3)])

    def test_shell_side_uses_frozen_resolver_with_reversed_normal(self):
        self.pipe.sign=-1
        result=self.finish(self.prepare())
        self.assertEqual(result['column_shell_side'],'SIDE2')

    def test_partition_natural_ends_skipped(self):
        for z in (0.,1.6): self.runtime['cht_axial_cut'](self.pipe,z,'XYPLANE',{})
        self.assertFalse(self.pipe.features)
        self.assertFalse(self.pipe.deleted)

    def test_existing_column_tie_requires_clean_model_before_new_partitions(self):
        self.model.constraints['STEP05_TIE_COLUMN_UP_DOWN']=NS()
        with self.assertRaisesRegex(ValueError,'clean Step02'): self.prepare()
        self.assertFalse(self.pipe.deleted)

    def test_noop_half_cut_cannot_create_constraints(self):
        old=self.pipe.PartitionFaceByDatumPlane
        def noop(datumPlane,faces):
            if hasattr(datumPlane,'offset'): return old(datumPlane,faces)
            return self.pipe.feature('Noop')
        self.pipe.PartitionFaceByDatumPlane=noop
        ctx=self.prepare()
        with self.assertRaisesRegex(ValueError,'Ambiguous column half'): self.finish(ctx)
        self.assertEqual(self.model.constraints,{})

    def test_conflicting_tie_fails(self):
        r=self.finish(self.prepare())
        self.model.constraints['STEP05_TIE_COLUMN_DOWN_HOOP_A'].adjust='OFF'
        with self.assertRaisesRegex(ValueError,'Conflicting HOOP Tie'): self.finish(self.prepare(r))

    def test_hoop_partial_overlap_does_not_modify_solid(self):
        column=dict(self.rule['column'])
        with self.assertRaisesRegex(ValueError,'no HOOP modification'):
            self.runtime['cht_inner'](self.a.instances['HOOP_01_A'],self.rule['halves'][0],column,[1.28,1.34])

    def test_disabled_workbook_keeps_legacy_path(self):
        with patch('cadtocae.column_hoop_tie.hoop_enabled',return_value=False):
            self.assertIsNone(build_hoop_plan(None,'unused'))

    def test_boolean_only_schema_no_dimensions(self):
        for value,expected in ((True,True),(False,False),('TRUE',True),('FALSE',False)):
            sheet=NS(values=[('rule_id','enabled'),('COLUMN_HOOP_TIE',value)])
            wb=type('Book',(),{'sheetnames':['Column_Hoop_Tie_Config'],'__getitem__':lambda self,key:sheet,'close':lambda self:None})()
            with patch('cadtocae.column_hoop_tie.load_workbook',return_value=wb):
                self.assertEqual(hoop_enabled('unused'),expected)

    def test_tilted_column_uses_actual_radial_vertex_for_local_plane(self):
        summary,components=cc.inputs()
        angle=math.radians(28)
        axis=(math.sin(angle),0.,math.cos(angle))
        for m in summary['instances']:
            z=m['placement']['translation'][2]
            m['placement']['translation']=[axis[i]*z for i in range(3)]
            m['placement']['axis_direction']=axis
        member=cc.resolve_columns(summary,components)['members'][1]
        part=cc.Pipe(member)
        inst=cc.Instance(part)
        n=self.runtime['cht_local_normal'](part,inst,member,(0.,1.,0.))
        self.assertAlmostEqual(n[0],0.)
        self.assertAlmostEqual(n[1],1.)
        self.assertAlmostEqual(n[2],0.)

    def test_pairing_follows_geometry_not_face_order(self):
        ctx=self.prepare()
        inst=self.a.instances['COLUMN_DOWN_01']
        ids=self.runtime['cht_band_ids'](self.pipe,ctx['column']['interval'])
        normal=ctx['normal']
        centers=[(0.,.056,1.3),(0.,-.056,1.3)]
        paired=self.runtime['cht_halves'](inst,list(reversed(ids)),ctx['column'],normal,centers)
        self.assertGreater(self.runtime['point3'](inst.faces[paired[0][0]].getCentroid())[1],0)
        self.assertLess(self.runtime['point3'](inst.faces[paired[1][0]].getCentroid())[1],0)

    def test_generated_script_preserves_frozen_functions_and_geometry_order(self):
        import ast
        fixture=bb.PlannerTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        with patch('cadtocae.beam_brace_tie.build_column_plan',return_value=self.base.rule),patch('cadtocae.beam_brace_tie.build_hoop_plan',return_value=self.rule):
            source=generate(discover_project_folder(fixture.root),fixture.config)['script'].read_text(encoding='utf-8')
        assert_runtime_compatible(source)
        functions={n.name:ast.dump(n) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
        for name in ('beam_brace_tie_runtime.py','column_column_tie_runtime.py','column_axis.py'):
            path=Path(__file__).resolve().parents[1]/'src/cadtocae'/name
            for node in ast.parse(path.read_text(encoding='utf-8')).body:
                if isinstance(node,ast.FunctionDef): self.assertEqual(functions[node.name],ast.dump(node))
        self.assertLess(source.rfind('    hoop_context = prepare_hoop'),source.rfind('    execute_column'))
        self.assertLess(source.rfind('    execute_column'),source.rfind('    execute_hoop'))
        self.assertLess(source.rfind('    execute_hoop'),source.rfind('    tie_batch.finish(REPORT)'))
        for forbidden in ('RemoveFace','CutExtrude','PartitionFaceByExtendFace','_s5_pose'):
            self.assertNotIn(forbidden,source)
