import contextlib
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from analysis_fake_cae import Repository
from cadtocae.column_column_tie import resolve_columns, read_column_config, build_column_plan
from cadtocae.column_axis import cct_axial_layout, cct_same_interval
from cadtocae.runtime_compatibility import assert_runtime_compatible
from cadtocae.beam_brace_tie import generate
from cadtocae.analysis_project import discover_project_folder
import test_analysis_beam_brace_tie as beam_fixture


def inputs(overlap=.55):
    members, components = [], []
    for role, length, origin, diameter in (
        ('COLUMN_UP', 2.506, (0.,0.,1.6-overlap), .168),
        ('COLUMN_DOWN', 1.6, (0.,0.,0.), .177),
    ):
        members.append(dict(component_code=role,part_name='P_'+role,instance_name=role+'_01',
            geometry_info={'length':length},placement=dict(translation=origin,rotation_steps=[],rotation_angle=None)))
        components.append(dict(component_code=role,part_name='P_'+role,length_m=length,section_kind='PIPE',
            model_policy='SHELL',thickness_m=.0045,section_params_m={'od_m':diameter,'t_m':.0045}))
    return {'instances':members},components


class Faces(list):
    def __getitem__(self,key):
        result=super().__getitem__(key)
        return Faces(result) if isinstance(key,slice) else result
    def __add__(self,other):
        return Faces(list(self)+list(other))
    def getBoundingBox(self):
        return dict(low=tuple(min(f.box['low'][i] for f in self) for i in range(3)),
                    high=tuple(max(f.box['high'][i] for f in self) for i in range(3)))


def perpendicular(axis):
    other=(0.,1.,0.) if abs(axis[1]) < .9 else (1.,0.,0.)
    v=(other[1]*axis[2]-other[2]*axis[1],other[2]*axis[0]-other[0]*axis[2],other[0]*axis[1]-other[1]*axis[0])
    length=math.sqrt(sum(x*x for x in v))
    return tuple(x/length for x in v)


class Cylinder:
    def __init__(self,index,radius,lo,hi,origin,sign,instance,axis):
        self.index,self.instanceName=index,instance
        center=tuple(origin[i]+axis[i]*(lo+hi)/2. for i in range(3))
        ext=tuple(abs(axis[i])*(hi-lo)/2.+radius*math.sqrt(max(0.,1.-axis[i]**2)) for i in range(3))
        self.box=dict(low=tuple(center[i]-ext[i] for i in range(3)),high=tuple(center[i]+ext[i] for i in range(3)))
        self.radial=perpendicular(axis)
        self.pointOn=(tuple(center[i]+radius*self.radial[i] for i in range(3)),)
        self.radius,self.lo,self.hi,self.sign=radius,lo,hi,sign
    def getCurvature(self,point):
        return {'curvature1':0.,'curvature2':1./self.radius}
    def getNormal(self,point):
        return tuple(self.sign*v for v in self.radial)
    def getVertices(self):
        return (self.index,self.index+1)
    def getSize(self,printResults=False):
        return 2*math.pi*self.radius*(self.hi-self.lo)


class Pipe:
    def __init__(self,member):
        self.name=member['part_name']
        self.member=member
        self.stations=[0.,member['length_m']]
        self.cells=[]
        self.elements=[1]
        self.features=Repository()
        self.datums={}
        self.sign=1
        self.deleted=False
    @property
    def faces(self):
        return self.make_faces((0.,0.,0.),'')
    @property
    def vertices(self):
        return [NS(pointOn=((self.member['radius_m'],0.,z),)) for z in self.stations]
    def make_faces(self,origin,instance,axis=(0.,0.,1.)):
        return Faces(Cylinder(i,self.member['radius_m'],lo,hi,origin,self.sign,instance,axis)
                     for i,(lo,hi) in enumerate(zip(self.stations,self.stations[1:])))
    def deleteMesh(self):
        self.deleted=True
        self.elements=[]
    def feature(self,prefix,**kw):
        f=NS(id=len(self.features)+1,name=prefix+str(len(self.features)+1),**kw)
        self.features[f.name]=f
        return f
    def DatumPlaneByPrincipalPlane(self,principalPlane,offset):
        assert principalPlane=='XYPLANE'
        f=self.feature('Datum',offset=offset)
        self.datums[f.id]=f
        return f
    def PartitionFaceByDatumPlane(self,datumPlane,faces):
        self.stations.append(datumPlane.offset)
        self.stations.sort()
        return self.feature('Partition')


class Instance:
    def __init__(self,part):
        self.part=part
        self.name=part.member['instance_name']
        self.partName=part.name
        self.dependent='ON'
    @property
    def faces(self):
        return self.part.make_faces(self.part.member['origin'],self.name,self.part.member['axis_direction'])
    @property
    def vertices(self):
        m=self.part.member
        axis=m['axis_direction']
        radial=perpendicular(axis)
        return [NS(pointOn=(tuple(m['origin'][i]+axis[i]*z+radial[i]*m['radius_m'] for i in range(3)),)) for z in self.part.stations]


class ColumnTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report=Path(self.tmp.name)/'report.json'
        self.runtime={'__name__':'test','json':json}
        root=Path(__file__).resolve().parents[1]/'src/cadtocae'
        for name in ('beam_brace_tie_runtime.py','column_axis.py','column_column_tie_runtime.py'):
            source=(root/name).read_text(encoding='utf-8')
            assert_runtime_compatible(source)
            exec(source,self.runtime)
        self.prepare()

    def prepare(self,overlap=.55,source=None):
        self.rule=resolve_columns(*(source or inputs(overlap)))
        self.plan=dict(model_name='TEST',column_column_tie=self.rule)
        self.parts=[Pipe(m) for m in self.rule['members']]
        self.a=NS(instances={p.member['instance_name']:Instance(p) for p in self.parts},sets={},surfaces={},regenerate=lambda:None)
        def aset(name,faces):
            self.assertIs(type(name),str)
            self.a.sets[name]=NS(name=name,faces=faces)
        def surf(name,**kwargs):
            self.assertIs(type(name),str)
            side='SIDE1' if 'side1Faces' in kwargs else 'SIDE2'
            faces=next(iter(kwargs.values()))
            self.a.surfaces[name]=NS(name=name,faces=faces,sides=[side]*len(faces))
        self.a.Set,self.a.Surface=aset,surf
        self.model=NS(parts={p.name:p for p in self.parts},rootAssembly=self.a,constraints={})
        def tie(**kwargs):
            self.assertIs(type(kwargs['name']),str)
            self.model.constraints[kwargs['name']]=NS(**kwargs)
        self.model.Tie=tie
        self.mdb=NS(models={'TEST':self.model})
        self.report.write_text(json.dumps({'status':'SUCCESS','fingerprint':'beam','remesh_required':False,'connections':['FRONT','REAR']}))

    def run_rule(self,previous=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.runtime['execute_column'](self.plan,self.mdb,str(self.report),'column',previous,'XYPLANE','ON','COMPUTED')

    def test_partitions_regions_master_slave_and_reuse(self):
        r=self.run_rule()
        self.assertEqual(r['status'],'SUCCESS')
        self.assertAlmostEqual(r['partitions'][0]['station'],.55)
        self.assertAlmostEqual(r['partitions'][1]['station'],1.05)
        self.assertEqual(r['COLUMN_UP']['shell_side'],'SIDE1')
        self.assertEqual(r['COLUMN_DOWN']['shell_side'],'SIDE2')
        tie=self.model.constraints['STEP05_TIE_COLUMN_UP_DOWN']
        self.assertEqual(tie.master.name,'STEP05_SURF_COLUMN_DOWN_UP')
        self.assertEqual(tie.slave.name,'STEP05_SURF_COLUMN_UP_DOWN')
        self.assertEqual((tie.positionToleranceMethod,tie.adjust,tie.tieRotations,tie.thickness),('COMPUTED','ON','ON','ON'))
        self.assertEqual(set(self.a.sets),{'STEP05_REGION_COLUMN_UP_DOWN','STEP05_REGION_COLUMN_DOWN_UP'})
        self.assertEqual(len(r['mesh_removed']),2)
        self.assertFalse(r['material_removed'])
        repeated=self.run_rule(r)
        self.assertFalse(repeated['tie_created'])
        self.assertEqual(repeated['partitions'],[])
        self.assertEqual(len(self.model.constraints),1)
        saved=json.loads(self.report.read_text())
        self.assertEqual(saved['connections'],['FRONT','REAR'])
        self.assertEqual(saved['fingerprint'],'beam')

    def test_normals_reversed_resolve_physical_sides(self):
        for part in self.parts: part.sign=-1
        r=self.run_rule()
        self.assertEqual(r['COLUMN_UP']['shell_side'],'SIDE2')
        self.assertEqual(r['COLUMN_DOWN']['shell_side'],'SIDE1')

    def test_real_ang28_full_overlap_and_matching_selected_ranges(self):
        self.prepare(.55)
        self.assertEqual(self.rule['actual_overlap'],[1.05,1.6])
        self.assertAlmostEqual(self.rule['overlap_length'],.55)
        self.assertEqual(self.rule['members'][0]['interval'],[0.,.55])
        self.assertEqual(self.rule['members'][1]['interval'],[1.05,1.6])
        r=self.run_rule()
        self.assertEqual(r['ranges']['selected_upper_range'],[1.05,1.6])
        self.assertEqual(r['ranges']['selected_lower_range'],[1.05,1.6])

    def test_noncoaxial_rejected(self):
        self.parts[0].member['origin'][0]=.01
        with self.assertRaisesRegex(ValueError,'not coaxial'): self.run_rule()

    def test_no_overlap_or_touching_rejected(self):
        for overlap in (-.1,0.,.0000005):
            with self.assertRaisesRegex(ValueError,'has no valid axial overlap'):
                resolve_columns(*inputs(overlap))

    def test_rotated_translated_coaxial_columns_use_common_axis(self):
        summary,components=inputs()
        angle=math.radians(28.)
        axis=(math.sin(angle),0.,math.cos(angle))
        anchor=(2.,-3.,4.)
        for member in summary['instances']:
            z=member['placement']['translation'][2]
            member['placement']['translation']=[anchor[i]+axis[i]*z for i in range(3)]
            member['placement']['rotation_steps']=[dict(axis_direction=(0.,1.,0.),axis_point=(0.,0.,0.),angle_deg=28.)]
        self.prepare(source=(summary,components))
        r=self.run_rule()
        base=sum(a*b for a,b in zip(anchor,axis))
        self.assertAlmostEqual(r['ranges']['actual_overlap'][0],base+1.05)
        self.assertAlmostEqual(r['ranges']['actual_overlap'][1],base+1.6)
        self.assertAlmostEqual(r['partitions'][0]['station'],.55)
        self.assertAlmostEqual(r['partitions'][1]['station'],1.05)
        self.assertEqual(r['COLUMN_UP']['shell_side'],'SIDE1')
        self.assertEqual(r['COLUMN_DOWN']['shell_side'],'SIDE2')

    def test_antiparallel_local_axes_convert_each_station(self):
        summary,components=inputs()
        summary['instances'][0]['placement']['axis_direction']=[0.,0.,-1.]
        summary['instances'][0]['placement']['translation']=[0.,0.,3.556]
        self.prepare(source=(summary,components))
        r=self.run_rule()
        self.assertAlmostEqual(self.rule['members'][0]['interval'][0],1.956)
        self.assertEqual(self.rule['members'][0]['interval'][1],2.506)
        self.assertAlmostEqual(r['partitions'][0]['station'],1.956)
        self.assertAlmostEqual(r['ranges']['selected_upper_range'][0],1.05)
        self.assertAlmostEqual(r['ranges']['selected_upper_range'][1],1.6)

    def test_contained_pipe_skips_ends_and_partitions_both_interior_boundaries(self):
        summary,components=inputs()
        components[0]['length_m']=.3
        summary['instances'][0]['geometry_info']['length']=.3
        summary['instances'][0]['placement']['translation']=[0.,0.,1.1]
        self.prepare(source=(summary,components))
        self.assertEqual(self.rule['members'][0]['partitions'],[])
        r=self.run_rule()
        self.assertEqual(len(r['partitions']),2)
        self.assertEqual([p['part'] for p in r['partitions']],['P_COLUMN_DOWN']*2)
        self.assertAlmostEqual(r['partitions'][0]['station'],1.1)
        self.assertAlmostEqual(r['partitions'][1]['station'],1.4)
        self.assertFalse(self.parts[0].deleted)
        self.assertEqual(self.parts[0].features,{})
        self.assertEqual(len(self.parts[1].features),4)

    def test_partition_helper_does_not_create_natural_end_datums(self):
        p=self.parts[0]
        for z in (0.,p.member['length_m']):
            self.runtime['cct_partition'](p,z,'XYPLANE',{})
        self.assertEqual(p.features,{})
        self.assertFalse(p.deleted)

    def test_selected_range_mismatch_rejected_before_regions_and_tie(self):
        original=self.runtime['cct_faces']
        def incorrect(*args):
            faces,side,ids,interval=original(*args)
            if args[2]['role']=='COLUMN_UP': interval[1]-=.01
            return faces,side,ids,interval
        self.runtime['cct_faces']=incorrect
        with self.assertRaisesRegex(ValueError,'regions do not share the same overlap interval'):
            self.run_rule()
        self.assertEqual(self.a.sets,{})
        self.assertEqual(self.a.surfaces,{})
        self.assertEqual(self.model.constraints,{})

    def test_interval_tolerance_and_no_automatic_expansion(self):
        cct_same_interval([1.05,1.6],[1.05+1.e-7,1.6],[1.05,1.6])
        with self.assertRaisesRegex(ValueError,'same overlap interval'):
            cct_same_interval([1.05,1.6],[1.05,1.59],[1.05,1.6])

    def test_runtime_drift_from_summary_rejected(self):
        inst=self.a.instances['COLUMN_UP_01']
        original=inst.part
        other=Pipe(dict(original.member,origin=[0.,0.,1.06]))
        inst.part=other
        with self.assertRaisesRegex(ValueError,'placement differs'):
            self.run_rule()
        self.assertFalse(any(p.features for p in self.parts))

    def test_flat_face_and_whole_column_not_selected(self):
        p=self.parts[0]
        p.stations=[0.,.55,p.member['length_m']]
        inst=Instance(p)
        faces=inst.faces
        faces[0].getCurvature=lambda point:{'curvature1':0.,'curvature2':0.}
        with self.assertRaisesRegex(ValueError,'No cylindrical'):
            self.runtime['cct_faces'](p,NS(faces=faces,vertices=inst.vertices),p.member,self.rule['common_axis'])
        selected,side,ids,interval=self.runtime['cct_faces'](p,inst,p.member,self.rule['common_axis'])
        self.assertEqual(ids,[0])
        self.assertEqual(len(selected),1)

    def test_invalid_normal_fails(self):
        p=self.parts[0]
        p.stations=[0.,.55,p.member['length_m']]
        faces=Instance(p).faces
        faces[0].getNormal=lambda point:(0.,0.,1.)
        with self.assertRaisesRegex(ValueError,'physical shell side'):
            self.runtime['cct_faces'](p,NS(faces=faces),p.member,self.rule['common_axis'])

    def test_shell_pointon_normal_payload_is_not_passed_as_coordinate(self):
        p=self.parts[0]
        p.stations=[0.,.55,p.member['length_m']]
        faces=Instance(p).faces
        faces[0].pointOn=(faces[0].pointOn[0]+(1.,0.,0.),)
        curvature=faces[0].getCurvature
        def checked(point):
            self.assertEqual(len(point),3)
            return curvature(point)
        faces[0].getCurvature=checked
        self.assertEqual(self.runtime['cct_faces'](p,NS(faces=faces,vertices=Instance(p).vertices),p.member,self.rule['common_axis'])[2],[0])

    def test_conflicting_tie_fails(self):
        r=self.run_rule()
        self.model.constraints[self.rule['tie']].adjust='OFF'
        with self.assertRaisesRegex(ValueError,'Conflicting column Tie'): self.run_rule(r)

    def test_conflicting_fingerprint_fails(self):
        r=self.run_rule()
        r['fingerprint']='other'
        with self.assertRaisesRegex(ValueError,'conflict policy FAIL'): self.run_rule(r)

    def test_nonparallel_or_non_pipe_and_bad_lengths_rejected(self):
        summary,components=inputs()
        summary['instances'][0]['placement']['rotation_angle']=10
        summary['instances'][0]['placement']['rotation_axis']=[0.,1.,0.]
        with self.assertRaisesRegex(ValueError,'not parallel'): resolve_columns(summary,components)
        summary,components=inputs()
        components[0]['section_kind']='C_CHANNEL'
        with self.assertRaisesRegex(ValueError,'PIPE shell'): resolve_columns(summary,components)
        components[0]['section_kind']='PIPE'
        components[0]['length_m']=-1
        with self.assertRaises(ValueError): resolve_columns(summary,components)

    def test_workbook_schema_and_enabled(self):
        for value, expected in ((True,True),(False,False),('TRUE',True),('FALSE',False)):
            sheet=NS(values=[('rule_id','enabled'),('COLUMN_COLUMN_TIE',value)])
            wb=type('Book',(),{'sheetnames':['Column_Tie_Config'], '__getitem__':lambda self,key:sheet,'close':lambda self:None})()
            with patch('cadtocae.column_column_tie.load_workbook',return_value=wb):
                self.assertEqual(read_column_config('unused')['enabled'],expected)
        for value in (0,-1,None,'=TRUE','100',float('nan')):
            sheet=NS(values=[('rule_id','enabled'),('COLUMN_COLUMN_TIE',value)])
            wb=type('Book',(),{'sheetnames':['Column_Tie_Config'], '__getitem__':lambda self,key:sheet,'close':lambda self:None})()
            with patch('cadtocae.column_column_tie.load_workbook',return_value=wb),self.assertRaises(ValueError):
                read_column_config('unused')

    def test_old_length_schema_is_rejected(self):
        sheet=NS(values=[('column_tie_length_mm',),(100,)])
        wb=type('Book',(),{'sheetnames':['Column_Tie_Config'], '__getitem__':lambda self,key:sheet,'close':lambda self:None})()
        with patch('cadtocae.column_column_tie.load_workbook',return_value=wb),self.assertRaisesRegex(ValueError,'rule_id, enabled'):
            read_column_config('unused')

    def test_disabled_rule_does_not_require_column_inputs(self):
        with patch('cadtocae.column_column_tie.read_column_config',return_value={'enabled':False}):
            self.assertIsNone(build_column_plan(None,'unused'))

    def test_combined_generated_script_preserves_beam_functions(self):
        import ast
        fixture=beam_fixture.PlannerTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        with patch('cadtocae.beam_brace_tie.build_column_plan',return_value=self.rule):
            path=generate(discover_project_folder(fixture.root),fixture.config)['script']
        source=path.read_text(encoding='utf-8')
        assert_runtime_compatible(source)
        root=Path(__file__).resolve().parents[1]/'src/cadtocae'
        original=ast.parse((root/'beam_brace_tie_runtime.py').read_text(encoding='utf-8'))
        actual={n.name:ast.dump(n) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
        for node in original.body:
            if isinstance(node,ast.FunctionDef): self.assertEqual(actual[node.name],ast.dump(node))
        self.assertLess(source.rfind('    execute(PLAN'),source.rfind('    execute_column(PLAN'))
        self.assertNotIn('RemoveFace',source)
        self.assertNotIn('CutExtrude',source)

    def test_runtime_non_ascii_names_fail(self):
        self.plan['model_name']='\u4e2d\u6587'
        with self.assertRaisesRegex(ValueError,'ASCII'): self.run_rule()
