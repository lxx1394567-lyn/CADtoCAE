import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace as NS
from cadtocae.spdc_hoop_inputs import add_part_inheritance_plan
from cadtocae.hoop_hole_plan import unique_hoop_parts,build_hoop_hole_plan
from cadtocae.hole_workbooks import create_hole_workbook,read_project_hole_workbook,HOOP_HEADERS,SUFFIX
from cadtocae.hole_setup import script_source
from test_step06_project_tables import add_hoop,complete
from test_step06_discovery import project_files
from test_step06_hoop_runtime import HoopPart
import test_step06_derived as base


def fixture():
    s={'structure_type':'SP_DC','instances':[]};c=[]
    add_hoop(s,c,'PART_A');c.append(dict(c[0],part_name='PART_B'));s['instances']=[]
    for g in range(1,4):
        for half in ('A','B'):
            s['instances'].append(dict(instance_name='HOOP_%02d_%s'%(g,half),connection_group='HOOP_%02d'%g,
                canonical_role='HOOP',component_code='HOOP',part_name='PART_'+half,placement=dict(translation=[0,0,g],rotation_steps=[])))
    rows=[]
    for part,n in (('PART_A','01'),('PART_B','02')):
        for end in ('LEFT','RIGHT'):
            rows.append(dict(part_name=part,hole_id='HOOP_'+end+'_'+n,end_reference=end,distance_from_end_mm=30 if n=='01' else 70,
                distance_from_side_mm=40,hole_type='ROUND',width_mm=16 if n=='01' else 18,slot_total_length_mm=None,slot_major_axis=None,enabled=True))
    return s,c,rows


def build(s,c,r):
    catalog=unique_hoop_parts(s,c)
    return add_part_inheritance_plan(s,catalog,build_hoop_hole_plan(catalog,r))


def prototype_fixture():
    s,c,r=fixture()
    for row in r:row['part_name']='PART_A'
    s['hoop_groups']=[]
    for g in range(1,4):
        rotation=dict(axis_point=[0,0,g],axis_direction=[0,0,1],angle_deg=180.)
        s['hoop_groups'].append(dict(group_id='HOOP_%02d'%g,instance_a='HOOP_%02d_A'%g,instance_b='HOOP_%02d_B'%g,
            part_a='PART_A',part_b='PART_B',pair_rotation=rotation))
        s['instances'][2*g-1]['placement']['rotation_steps']=[rotation]
    return s,c,r


class SPDCPartTests(unittest.TestCase):
    def test_standard_prototype_four_rows_eight_cuts_twentyfour_holes(self):
        s,c,r=prototype_fixture();p=build(s,c,r)
        self.assertEqual(p['expected_counts'],dict(unique_hoop_parts=2,unique_part_cut_count=8,hoop_group_count=3,half_instance_count=6,assembly_instance_hole_count=24))
        self.assertEqual([len(x['hole_pattern']) for x in p['part_patterns']],[4,4])
        for pair in p['prototype_inheritance']['pairs']:
            for h in pair['holes']:
                self.assertLess(h['symmetry_error_m'],1e-9)
                a,b=h['source_global_center'],h['target_global_center']
                self.assertAlmostEqual(a[0],-b[0]);self.assertAlmostEqual(a[1],-b[1]);self.assertAlmostEqual(a[2],b[2])
        # Source rows remain one four-hole pattern, not repeated per group.
        self.assertEqual(len(r),4)

    def test_prototype_rejects_geometry_and_symmetry_ambiguity(self):
        for mode in ('geometry','translation','rotation','group','part','missing','disabled'):
            s,c,r=prototype_fixture()
            if mode=='geometry':c[1]['section_params_m']=dict(c[1]['section_params_m'],t_m=.007)
            if mode=='translation':s['instances'][1]['placement']['translation']=[.01,0,1]
            if mode=='rotation':s['hoop_groups'][0]['pair_rotation']['angle_deg']=90
            if mode=='group':s['hoop_groups'][0]['group_id']='HOOP_99'
            if mode=='part':s['hoop_groups'][0]['part_b']='NOT_PART_B'
            if mode=='missing':s['hoop_groups'].pop()
            if mode=='disabled':r.append(dict(r[0],part_name='PART_B',enabled=False))
            with self.assertRaisesRegex(ValueError,'SPDC_PROTOTYPE'):build(s,c,r)

    def test_original_four_rows_inherit_all_groups(self):
        s,c,r=fixture();p=build(s,c,r)
        self.assertEqual(p['expected_counts'],dict(unique_hoop_parts=2,unique_part_cut_count=4,hoop_group_count=3,half_instance_count=6,assembly_instance_hole_count=12))
        self.assertEqual([len(p['hole_pattern']) for p in p['part_patterns']],[2,2])
        self.assertEqual(len(p['instance_mapping']),6)

    def test_hole_suffix_never_selects_group_or_half(self):
        s,c,r=fixture();r[0]['hole_id']='HOOP_LEFT_99';p=build(s,c,r)
        self.assertEqual(p['expected_counts']['assembly_instance_hole_count'],12)
        self.assertEqual(p['driving_holes'][0]['shared_part_info']['referencing_instances'],['HOOP_01_A','HOOP_02_A','HOOP_03_A'])

    def test_unequal_multi_holes_mixed_profiles(self):
        s,c,r=fixture();r.append(dict(r[0],hole_id='HOOP_LEFT_02',distance_from_end_mm=70,hole_type='SLOT',slot_total_length_mm=25,slot_major_axis='BAND_WIDTH'))
        p=build(s,c,r);self.assertEqual(p['expected_counts']['unique_part_cut_count'],5)
        self.assertEqual(p['expected_counts']['assembly_instance_hole_count'],15)

    def test_variation_requires_isolation(self):
        s,c,r=fixture();s['instances'][2]['hole_pattern_override']={'width_mm':18}
        with self.assertRaisesRegex(ValueError,'PART_PATTERN_VARIATION_REQUIRES_ISOLATION'):build(s,c,r)

    def test_duplicate_unknown_overlap_invalid_size(self):
        for mode in ('duplicate','unknown','overlap','size'):
            s,c,r=fixture()
            if mode=='duplicate':r.append(dict(r[0]))
            if mode=='unknown':r[0]['part_name']='FAKE'
            if mode=='overlap':r.append(dict(r[0],hole_id='HOOP_LEFT_02'))
            if mode=='size':r[0]['width_mm']=-1
            with self.assertRaises(ValueError):build(s,c,r)

    def test_existing_schema_and_four_rows_roundtrip(self):
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);c=project_files(root);s=json.loads((root/'TEST_STEP06_assembly_summary.json').read_text())
            hs,hc,_=fixture();s['instances'].extend(hs['instances']);s['structure_type']='SP_DC';c.extend(hc)
            create_hole_workbook(root,'TEST_STEP06',s,c);path=root/('TEST_STEP06'+SUFFIX)
            w=load_workbook(path);self.assertEqual(tuple(x.value for x in w['抱箍孔位'][3]),HOOP_HEADERS);self.assertEqual(w['抱箍孔位'].max_row,7);w.close()
            complete(path);before=path.read_bytes();_,p=read_project_hole_workbook(path,'TEST_STEP06',s,c)
            self.assertEqual(p['expected_counts']['assembly_instance_hole_count'],12)
            create_hole_workbook(root,'TEST_STEP06',s,c);self.assertEqual(before,path.read_bytes())

    def runtime(self,mixed=False):
        b=base.Step06ATests();b.setUp();self.addCleanup(b.doCleanups);s,c,r=fixture()
        if mixed:r[2].update(hole_type='SLOT',slot_total_length_mm=25,slot_major_axis='BAND_WIDTH')
        hp=build(s,c,r);b.plan['hoop_hole_plan']=json.loads(json.dumps(hp))
        for part in hp['part_geometry']:b.parts[part]=HoopPart(part,hp['part_geometry'][part])
        for m in s['instances']:b.assembly.instances[m['instance_name']]=NS(partName=m['part_name'],dependent=True,pose=copy.deepcopy(m['placement']))
        ns={'__name__':'test'};exec(script_source(b.plan,b.path),ns)
        return b,ns

    def run_all(self,b,ns):
        with contextlib.redirect_stdout(io.StringIO()):return ns['execute_step06_with_hoop'](b.plan,b.mdb,str(b.path),'test')

    def test_runtime_round_slot_and_counts(self):
        for mixed in (False,True):
            b,ns=self.runtime(mixed);r=self.run_all(b,ns)['hoop_validation']
            self.assertEqual(r['status'],'SUCCESS');self.assertEqual(r['unique_part_cut_count'],4);self.assertEqual(r['assembly_instance_hole_count'],12)
            self.assertEqual([g['actual_holes'] for g in r['groups']],[4,4,4])
            for p in r['parts']:
                self.assertEqual(p['actual_cut_features'],2)
                for key in ('volume_validation','cut_geometry_status','assembly_inheritance_status'):self.assertEqual(p[key],'PASS')

    def test_runtime_reference_dependent_count_and_pattern_guards(self):
        for mode in ('independent','missing','count','pattern'):
            b,ns=self.runtime()
            if mode=='independent':b.assembly.instances['HOOP_03_A'].dependent=False
            if mode=='missing':b.assembly.instances.pop('HOOP_03_A')
            if mode=='count':b.plan['hoop_hole_plan']['expected_counts']['assembly_instance_hole_count']=4
            if mode=='pattern':b.plan['hoop_hole_plan']['part_patterns'][0]['hole_pattern'].pop()
            with self.assertRaises(ValueError):self.run_all(b,ns)
            b.unchanged();self.assertFalse(b.parts['PART_A'].cut_calls)
