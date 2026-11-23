import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from openpyxl import load_workbook

from cadtocae.hole_workbooks import create_hole_workbook, read_project_hole_workbook, HOOP_HEADERS_V1
from cadtocae.hoop_hole_plan import unique_hoop_parts, build_hoop_hole_plan
from cadtocae.hole_profiles import is_round_profile, is_slot_profile, hole_area, hoop_boundary_probes
from cadtocae.hole_plan import build_step06_a_plan
from test_step06_project_tables import add_hoop, complete
from test_step06_derived import fixture_a


def hoop_fixture():
    summary,components,_ = fixture_a()
    add_hoop(summary,components)
    components[-1]['section_params_m'].update(left_extension_m=.14,right_extension_m=.20,width_m=.12)
    return summary,components,unique_hoop_parts(summary,components)


def hole(side='LEFT', number=1, kind='ROUND', distance=40., z=40., direction='PLATE_LENGTH'):
    return dict(part_name='PART_HOOP',hole_id='HOOP_%s_%02d'%(side,number),end_reference=side,
                distance_from_end_mm=distance,distance_from_side_mm=z,hole_type=kind,
                width_mm=16.,slot_total_length_mm=30. if kind=='SLOT' else None,
                slot_major_axis=direction if kind=='SLOT' else None,enabled=True)


class HoleV2PlanTests(unittest.TestCase):
    def setUp(self):
        self.summary,self.components,self.catalog=hoop_fixture()
    def plan(self,rows):return build_hoop_hole_plan(self.catalog,rows)

    def test_round_slot_both_axes_and_round_equivalent(self):
        for kind,direction in [('ROUND',None),('SLOT','PLATE_LENGTH'),('SLOT','BAND_WIDTH')]:
            rows=[hole(kind=kind,direction=direction),hole('RIGHT',kind=kind,direction=direction)]
            hs=self.plan(rows)['driving_holes']
            for h in hs:
                self.assertEqual(h['width_m'],.016)
                self.assertEqual(h['total_length_m'],.016 if kind=='ROUND' else .030)
                self.assertEqual(is_round_profile(h),kind=='ROUND')
                self.assertEqual(is_slot_profile(h),kind=='SLOT')
                self.assertEqual(h['local_center'],h['local_center_m'])
                self.assertEqual(h['local_axis'],(0.,1.,0.))
                self.assertEqual(h['shared_part_info']['execution_policy'],'MODIFY_SHARED_PART_ONCE')
                self.assertEqual('diameter_m' in h,kind=='ROUND')
        row=hole(kind='SLOT');row['slot_total_length_mm']=16.
        h=self.plan([row])['driving_holes'][0]
        self.assertTrue(is_round_profile(h));self.assertFalse(is_slot_profile(h))
        self.assertEqual(len(set(p for p,n in hoop_boundary_probes(h))),12)
        self.assertAlmostEqual(hole_area(h),math.pi*.008**2)

    def test_unequal_counts_zero_side_and_asymmetric_centers(self):
        for left,right in [(2,1),(1,3),(0,2),(0,0)]:
            rows=[hole(side,n,z=20.+30.*(n-1)) for side,count in [('LEFT',left),('RIGHT',right)] for n in range(1,count+1)]
            hs=self.plan(rows)['driving_holes'];self.assertEqual(len(hs),left+right)
            g=self.catalog['PART_HOOP']['geometry']
            self.assertNotEqual(g['left_straight_length_m'],g['right_straight_length_m'])
            for h in hs:
                self.assertAlmostEqual(h['local_center'][0],g['left_end_x_m']+.04 if h['end_reference']=='LEFT' else g['right_end_x_m']-.04)

    def test_boundaries_rejected_for_both_slot_axes(self):
        flat=self.catalog['PART_HOOP']['geometry']['left_straight_length_m']*1000.
        for direction,key,value in [('PLATE_LENGTH','distance_from_end_mm',flat-14.),('PLATE_LENGTH','distance_from_end_mm',14.),
                                    ('BAND_WIDTH','distance_from_side_mm',14.),('BAND_WIDTH','distance_from_side_mm',106.)]:
            row=hole(kind='SLOT',direction=direction);row[key]=value
            with self.subTest(key=key,value=value),self.assertRaisesRegex(ValueError,'crosses'):self.plan([row])

    def test_overlap_all_profiles_crossing_and_touching(self):
        for a,b in [('ROUND','ROUND'),('ROUND','SLOT'),('SLOT','SLOT')]:
            for separation in (0.,8.,16.):
                with self.subTest(a=a,b=b,separation=separation),self.assertRaisesRegex(ValueError,'HOOP_HOLE_OVERLAP'):
                    self.plan([hole(kind=a),hole(number=2,kind=b,z=40.+separation)])
        self.plan([hole(kind='SLOT'),hole(number=2,kind='ROUND',z=70.)])
        with self.assertRaisesRegex(ValueError,'HOOP_HOLE_OVERLAP'):
            self.plan([hole(kind='SLOT'),hole(number=2,kind='SLOT',direction='BAND_WIDTH')])

    def test_legacy_ids_and_duplicate_canonical_id(self):
        a=hole();a['hole_id']='HOOP_LEFT';a['diameter_mm']=a.pop('width_mm')
        h=self.plan([a])['driving_holes'][0]
        self.assertEqual(h['hole_id'],'HOOP_LEFT_01');self.assertEqual(h['width_m'],h['total_length_m'])
        with self.assertRaisesRegex(ValueError,'duplicate'):self.plan([a,hole()])

    def test_invalid_slot_direction_size_and_disabled(self):
        for changes in [dict(slot_total_length_mm=15.),dict(slot_major_axis=None),dict(width_mm=0.),dict(width_mm=float('nan'))]:
            row=hole(kind='SLOT');row.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.plan([row])
        row=hole();row.update(enabled=False,width_mm=None,distance_from_end_mm=None)
        self.assertFalse(self.plan([row])['driving_holes'])

    def test_parts_have_independent_patterns(self):
        add_hoop(self.summary,self.components,'SECOND','HOOP_ASSEMBLY_2')
        self.catalog=unique_hoop_parts(self.summary,self.components)
        other=hole('RIGHT',kind='SLOT');other['part_name']='SECOND'
        self.assertEqual(len(self.plan([hole(),hole(number=2,z=80.),other])['driving_holes']),3)


class HoleV2WorkbookTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.summary,self.components,_=hoop_fixture();self.project=self.summary['project_id']
        self.path=Path(create_hole_workbook(self.root,self.project,self.summary,self.components)['path'])
    def read(self):return read_project_hole_workbook(self.path,self.project,self.summary,self.components)

    def test_v2_blank_dimensions_schema_dropdowns_and_preservation(self):
        wb=load_workbook(self.path);self.addCleanup(wb.close)
        self.assertEqual(wb['_STEP06_META']['B1'].value,'step06-project-hole-table-v2')
        for sheet in ('檩托孔位','抱箍孔位'):
            self.assertIn('孔宽/直径 (mm)',[c.value for c in wb[sheet][3]])
            self.assertNotIn('孔径 (mm)',[c.value for c in wb[sheet][3]])
        for row in (4,5):
            for col in (5,6,8,9):self.assertIsNone(wb['抱箍孔位'].cell(row,col).value)
        self.assertTrue(wb['抱箍孔位']['B4'].protection.locked)
        choices=' '.join(str(v.formula1) for v in wb['抱箍孔位'].data_validations.dataValidation)
        self.assertIn('圆孔,长圆孔',choices);self.assertIn('沿直板长度方向,沿抱箍宽度方向',choices)
        before=self.path.read_bytes();self.assertEqual(create_hole_workbook(self.root,self.project,self.summary,self.components)['status'],'PRESERVED')
        self.assertEqual(before,self.path.read_bytes())

    def test_v1_adapter_and_v2_have_identical_geometry(self):
        complete(self.path);v2=self.read()
        wb=load_workbook(self.path);s=wb['抱箍孔位'];s.delete_cols(9,2)
        for i,h in enumerate(HOOP_HEADERS_V1,1):s.cell(3,i,h)
        s['C4']='HOOP_LEFT';s['C5']='HOOP_RIGHT';wb['檩托孔位']['I3']='孔径 (mm)'
        wb['_STEP06_META']['B1']='step06-project-hole-table-v1';wb.save(self.path);wb.close()
        before=self.path.read_bytes();v1=self.read()
        self.assertEqual(v1[0],v2[0]);self.assertEqual(v1[1]['driving_holes'],v2[1]['driving_holes'])
        self.assertEqual(v1[1]['workbook_schema'],'v1 compatible');self.assertEqual(before,self.path.read_bytes())

    def test_all_added_rows_read_and_round_support(self):
        complete(self.path);wb=load_workbook(self.path)
        s=wb['抱箍孔位'];s.append(['抱箍','PART_HOOP','HOOP_LEFT_02','左端',40,85,'长圆孔',16,30,'沿直板长度方向','是',''])
        for r in (4,5):
            wb['檩托孔位'].cell(r,8,'圆孔')
            for c in (10,11):wb['檩托孔位'].cell(r,c).value=None
        wb.save(self.path);wb.close()
        rows,hp=self.read();self.assertEqual(len(hp['driving_holes']),3)
        plan=build_step06_a_plan(self.summary,rows,self.components)
        for h in plan['driving_holes']:
            self.assertEqual(h['hole_type'],'ROUND');self.assertEqual(h['width_m'],h['total_length_m']);self.assertIsNone(h['local_major_axis'])

    def test_slot_missing_values_and_schema_not_silently_accepted(self):
        complete(self.path);wb=load_workbook(self.path);wb['抱箍孔位']['G4']='长圆孔';wb.save(self.path);wb.close()
        with self.assertRaisesRegex(ValueError,'slot_total_length_mm'):self.read()
        wb=load_workbook(self.path);wb['抱箍孔位']['G3']='UNKNOWN';wb.save(self.path);wb.close()
        with self.assertRaisesRegex(ValueError,'headers'):self.read()
