from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import load_workbook
from cadtocae.hole_projects import scan_projects,generate_batch,generate_hole_tables,project_details
from cadtocae.hole_workbooks import (create_hole_workbook,read_project_hole_workbook,
    SUPPORT_SHEET,HOOP_SHEET,SUPPORT_HEADERS,HOOP_HEADERS,SUFFIX,META_SHEET,project_id_from_filename)
from cadtocae.hoop_hole_plan import hoop_geometry,unique_hoop_parts,build_hoop_hole_plan
from test_step06_discovery import project_files,hole_table,chinese_rows


def add_hoop(summary,components,part='PART_HOOP',code='HOOP'):
    components.append(dict(part_name=part,component_code=code,section_kind='HOOP_BAND',model_policy='SOLID',
        section_params_m=dict(diameter_m=.3,width_m=.08,t_m=.006,left_extension_m=.109,
                              right_extension_m=.109,transition_fillet_m=.01)))
    for i in range(1,3):
        for side in ('A','B'):
            summary['instances'].append(dict(instance_name='%s_%02d_%s'%(code,i,side),part_name=part,
                component_code=code,canonical_role='HOOP',placement=dict(translation=[0,0,i],rotation_steps=[])))


def complete(path):
    wb=load_workbook(path)
    s=wb[SUPPORT_SHEET]
    for row,corner,total in ((4,60,40),(5,21,25)):
        for col,value in ((5,corner),(6,25),(9,12),(10,total)):s.cell(row,col,value)
    for row in range(4,wb[HOOP_SHEET].max_row+1):
        for col,value in ((5,50),(6,40),(8,16)):wb[HOOP_SHEET].cell(row,col,value)
    wb.save(path);wb.close()


class ProjectTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.components=project_files(self.root)
        self.summary_path=self.root/'TEST_STEP06_assembly_summary.json'
        self.summary=json.loads(self.summary_path.read_text(encoding='utf-8'))
        add_hoop(self.summary,self.components);self.save_summary()
        def export(source,target,selection):
            self.assertEqual(selection,'complete');target.write_text(json.dumps({'components':self.components}),encoding='utf-8');return target
        self.enterContext(patch('cadtocae.hole_projects.export_abaqus_json',side_effect=export))
        self.path=self.root/('TEST_STEP06'+SUFFIX)
    def save_summary(self):self.summary_path.write_text(json.dumps(self.summary),encoding='utf-8')
    def scan(self):return scan_projects(self.root)
    def create(self):return generate_hole_tables(self.scan())
    def ready(self):self.create();complete(self.path);return self.scan()

    def test_missing_incomplete_complete_and_generated_status(self):
        self.assertEqual(self.scan()['projects'][0]['status'],'MISSING_TABLE')
        result=self.create();self.assertEqual(result['table_counts']['created'],1)
        self.assertEqual(result['projects'][0]['status'],'NEEDS_INPUT')
        complete(self.path)
        scan=self.scan();self.assertEqual(scan['projects'][0]['status'],'READY',scan)
        result=generate_batch(scan);self.assertEqual(result['generation_counts']['succeeded'],1,result)
        self.assertEqual(self.scan()['projects'][0]['status'],'GENERATED')
        plan=json.loads((self.root/'TEST_STEP06_step06_plan.json').read_text(encoding='utf-8'))
        self.assertTrue(plan['hoop_hole_plan']['runtime_enabled'])
        self.assertEqual(len(plan['hoop_hole_plan']['driving_holes']),2)
        self.assertFalse((self.root/'TEST_STEP06_step06_hole_report.json').exists())

    def test_two_sheets_no_user_project_or_group_part_locked(self):
        self.create();wb=load_workbook(self.path);self.addCleanup(wb.close)
        self.assertEqual([s.title for s in wb if s.sheet_state=='visible'],[SUPPORT_SHEET,HOOP_SHEET])
        self.assertEqual(wb[META_SHEET].sheet_state,'hidden')
        self.assertEqual(tuple(c.value for c in wb[SUPPORT_SHEET][3]),SUPPORT_HEADERS)
        self.assertEqual(tuple(c.value for c in wb[HOOP_SHEET][3]),HOOP_HEADERS)
        self.assertNotIn('项目编号',SUPPORT_HEADERS);self.assertNotIn('连接组',SUPPORT_HEADERS)
        self.assertTrue(wb[HOOP_SHEET]['B4'].protection.locked)
        self.assertTrue(wb[HOOP_SHEET].protection.sheet)
        self.assertFalse(wb[HOOP_SHEET]['E4'].protection.locked)
        self.assertIsNone(wb[HOOP_SHEET]['E4'].value)
        self.assertEqual(wb[HOOP_SHEET].max_row,5)

    def test_existing_workbook_preserved_exactly(self):
        self.ready();before=self.path.read_bytes()
        result=self.create();self.assertEqual(result['table_counts']['preserved'],1)
        self.assertEqual(result['table_events'][0]['message'],'Existing hole table preserved.')
        self.assertEqual(before,self.path.read_bytes())

    def test_exclusive_create_race_preserves_new_existing_file(self):
        original=Path.open
        def race(path,mode='r',*args,**kwargs):
            if path==self.path and mode=='xb':
                with original(path,'wb') as stream:stream.write(b'user workbook')
            return original(path,mode,*args,**kwargs)
        with patch.object(Path,'open',race):
            result=create_hole_workbook(self.root,'TEST_STEP06',self.summary,self.components)
        self.assertEqual(result['status'],'PRESERVED');self.assertEqual(self.path.read_bytes(),b'user workbook')

    def test_multiple_projects_get_separate_workbooks(self):
        project_files(self.root,'OTHER')
        result=self.create();self.assertEqual(result['table_counts']['created'],2)
        self.assertTrue((self.root/('OTHER'+SUFFIX)).is_file())
        complete(self.path)
        rows={r['project_id']:r for r in self.scan()['projects']}
        self.assertEqual(rows['TEST_STEP06']['status'],'READY')
        self.assertEqual(rows['OTHER']['status'],'NEEDS_INPUT')

    def test_multiple_unique_hoop_parts_each_has_two_rows(self):
        add_hoop(self.summary,self.components,'PART_HOOP_2','HOOP_ASSEMBLY_2');self.save_summary()
        self.ready();row=self.scan()['projects'][0]
        holes=row['plan']['hoop_hole_plan']['driving_holes'];self.assertEqual(len(holes),4)
        self.assertEqual({h['part_name'] for h in holes},{'PART_HOOP','PART_HOOP_2'})
        for h in holes:self.assertEqual(len(h['shared_part_info']['referencing_instances']),4)

    def test_shared_hoop_one_definition_per_side_and_centers(self):
        row=self.ready()['projects'][0];holes=row['plan']['hoop_hole_plan']['driving_holes']
        self.assertEqual(len(holes),2)
        for h,x in zip(holes,[-.215,.215]):
            self.assertAlmostEqual(h['local_center_m'][0],x)
            self.assertEqual(h['local_center_m'][1:],(.003,.04))
            self.assertEqual(h['local_axis'],(0.,1.,0.))
            self.assertEqual(h['shared_part_info']['execution_policy'],'MODIFY_SHARED_PART_ONCE')

    def test_legacy_warns_without_fallback(self):
        old=self.root/'Step06_螺栓孔定位表_中文版.xlsx';hole_table(old,chinese_rows())
        before=old.read_bytes();row=self.scan()['projects'][0]
        self.assertEqual(row['status'],'MISSING_TABLE')
        self.assertIn('LEGACY_AGGREGATE_TABLE',' '.join(row['warnings']))
        self.create();self.assertEqual(old.read_bytes(),before)

    def test_invalid_schema_filename_identity_and_formula_rejected(self):
        self.ready();before=self.path.read_bytes()
        for case in ('schema','identity','formula','unknown_part','wrong_end'):
            with self.subTest(case=case):
                self.path.write_bytes(before);wb=load_workbook(self.path)
                if case=='schema':wb[HOOP_SHEET].title='错误'
                elif case=='identity':wb[META_SHEET]['B2']='OTHER'
                elif case=='formula':wb[HOOP_SHEET]['E4']='=50'
                elif case=='unknown_part':wb[HOOP_SHEET]['B4']='UNKNOWN'
                elif case=='missing_row':wb[HOOP_SHEET].delete_rows(5)
                else:wb[HOOP_SHEET]['D4']='右端'
                wb.save(self.path);wb.close()
                self.assertEqual(self.scan()['projects'][0]['status'],'NEEDS_REVIEW')

    def test_filename_primary_parser(self):
        self.assertEqual(project_id_from_filename(self.path),'TEST_STEP06')
        for filename in ('wrong.xlsx',SUFFIX,'CON'+SUFFIX):
            with self.subTest(filename=filename),self.assertRaises(ValueError):project_id_from_filename(filename)

    def test_office_roundtrip_without_metadata_keeps_values_and_ready(self):
        from openpyxl.packaging.core import DocumentProperties
        self.ready();wb=load_workbook(self.path)
        values={s:list(wb[s].values) for s in (SUPPORT_SHEET,HOOP_SHEET)}
        del wb[META_SHEET]
        wb.properties=DocumentProperties()
        wb.custom_doc_props.props=[]
        wb.defined_names.clear()
        wb.save(self.path);wb.close()
        row=self.scan()['projects'][0]
        self.assertEqual(row['status'],'READY',row)
        self.assertIn('Workbook metadata missing; filename identity used.',row['warnings'])
        wb=load_workbook(self.path)
        try:self.assertEqual(values,{s:list(wb[s].values) for s in values})
        finally:wb.close()

    def test_office_properties_never_override_filename(self):
        self.ready();wb=load_workbook(self.path)
        wb.properties.subject='Office rewrote subject';wb.properties.identifier='OTHER'
        wb.save(self.path);wb.close()
        row=self.scan()['projects'][0]
        self.assertEqual(row['status'],'READY',row)
        self.assertNotIn('Workbook metadata missing; filename identity used.',row['warnings'])

    def test_metadata_conflict_has_explicit_reason(self):
        self.ready();wb=load_workbook(self.path);wb[META_SHEET]['B2']='OTHER';wb.save(self.path);wb.close()
        row=self.scan()['projects'][0]
        self.assertEqual(row['status'],'NEEDS_REVIEW')
        self.assertEqual(row['first_blocking_reason'],'Workbook metadata conflicts with filename identity')

    def test_orphan_workbook_is_reported_not_silently_ignored(self):
        self.ready();(self.root/('ORPHAN'+SUFFIX)).write_bytes(self.path.read_bytes())
        rows={r['project_id']:r for r in self.scan()['projects']}
        self.assertEqual(rows['TEST_STEP06']['status'],'READY')
        self.assertEqual(rows['ORPHAN']['status'],'NEEDS_REVIEW')
        self.assertIn('does not match any scanned project',rows['ORPHAN']['first_blocking_reason'])

    def test_missing_metadata_does_not_hide_missing_dimensions_or_bad_headers(self):
        self.create();wb=load_workbook(self.path);del wb[META_SHEET];wb.save(self.path);wb.close()
        row=self.scan()['projects'][0]
        self.assertEqual(row['status'],'NEEDS_INPUT')
        self.assertIn('distance_from_angle_corner_mm',row['first_blocking_reason'])
        self.assertIn('Workbook metadata missing; filename identity used.',row['warnings'])
        wb=load_workbook(self.path);wb[SUPPORT_SHEET]['E3']='wrong';wb.save(self.path);wb.close()
        row=self.scan()['projects'][0]
        self.assertEqual(row['status'],'NEEDS_REVIEW')
        self.assertIn('headers',row['first_blocking_reason'])

    def test_disabled_hoop_needs_no_dimensions(self):
        self.ready();wb=load_workbook(self.path)
        for r in (4,5):
            wb[HOOP_SHEET].cell(r,11,'否')
            for c in (5,6,8):wb[HOOP_SHEET].cell(r,c).value=None
        wb.save(self.path);wb.close()
        row=self.scan()['projects'][0];self.assertEqual(row['status'],'READY')
        self.assertEqual(len(row['plan']['hoop_hole_plan']['disabled_holes']),2)

    def test_missing_component_and_bad_support_geometry(self):
        self.ready();self.components[0]['section_params_m']['leg_a_m']=.065
        self.assertIn('free-edge',self.scan()['projects'][0]['first_blocking_reason'])
        (self.root/'TEST_STEP06_components.xlsx').unlink()
        self.assertIn('components',self.scan()['projects'][0]['first_blocking_reason'])

    def test_recursive_outputs_and_selected_generation(self):
        self.ready();child=self.root/'child';child.mkdir();project_files(child,'CHILD')
        scan=scan_projects(self.root,True);generate_hole_tables(scan);complete(child/('CHILD'+SUFFIX))
        self.assertEqual(len(self.scan()['projects']),1)
        scan=scan_projects(self.root,True)
        selected=generate_batch(scan,{(str(child),'CHILD')})
        self.assertEqual(selected['generation_counts']['succeeded'],1)
        self.assertTrue((child/'CHILD_step06_plan.json').exists())
        self.assertFalse((self.root/'CHILD_step06_plan.json').exists())

    def test_changed_input_blocks_stale_generation(self):
        scan=self.ready();wb=load_workbook(self.path);wb[SUPPORT_SHEET]['E4']=61;wb.save(self.path);wb.close()
        self.assertEqual(generate_batch(scan)['generation_counts']['failed'],1)

    def test_changed_table_during_read_rejected(self):
        self.ready()
        from cadtocae.hole_workbooks import read_project_hole_workbook as original
        def change(*args):
            result=original(*args);wb=load_workbook(self.path);wb[SUPPORT_SHEET]['E4']=61;wb.save(self.path);wb.close();return result
        with patch('cadtocae.hole_workbooks.read_project_hole_workbook',side_effect=change):
            self.assertIn('changed while reading',self.scan()['projects'][0]['first_blocking_reason'])

    def test_atomic_pair_rollback(self):
        generate_batch(self.ready());paths=[self.root/('TEST_STEP06'+s) for s in ('_step06_plan.json','_step06_hole_setup.py')]
        before=[p.read_bytes() for p in paths]
        import os
        original=os.replace
        def fail(src,dst):
            if Path(src).parent.name.startswith('.step06-tmp-') and Path(dst)==paths[1]:raise OSError('publish failed')
            return original(src,dst)
        with patch('cadtocae.hole_setup.os.replace',side_effect=fail):
            self.assertEqual(generate_batch(self.scan())['generation_counts']['failed'],1)
        self.assertEqual(before,[p.read_bytes() for p in paths])


class HoopBoundsTests(unittest.TestCase):
    def setUp(self):
        self.summary={'instances':[]};self.components=[];add_hoop(self.summary,self.components)
        self.catalog=unique_hoop_parts(self.summary,self.components)
        self.rows=[dict(part_name='PART_HOOP',hole_id='HOOP_'+side,end_reference=side,hole_type='ROUND',
                       distance_from_end_mm=50,distance_from_side_mm=40,diameter_mm=16,enabled=True)
                   for side in ('LEFT','RIGHT')]
    def test_edges_fillet_arc_nonpositive_and_nonfinite(self):
        for key,value in [('distance_from_end_mm',8),('distance_from_side_mm',8),('distance_from_side_mm',72),
                          ('distance_from_end_mm',100),('distance_from_end_mm',150),('diameter_mm',0),
                          ('diameter_mm',float('nan'))]:
            rows=deepcopy(self.rows);rows[0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):build_hoop_hole_plan(self.catalog,rows)
    def test_exact_tangent_is_rejected_as_well_as_crossing(self):
        flat=self.catalog['PART_HOOP']['geometry']['left_straight_length_m']
        self.rows[0]['distance_from_end_mm']=(flat-.008)*1000.
        with self.assertRaisesRegex(ValueError,'fillet'):build_hoop_hole_plan(self.catalog,self.rows)
    def test_geometry_matches_corrected_step02_tangent(self):
        g=self.catalog['PART_HOOP']['geometry']
        self.assertAlmostEqual(g['straight_tangent_x_m'],(.15*(.15+2*(.01+.006)))**.5)
        self.assertAlmostEqual(g['left_end_x_m'],-.265)
    def test_bad_kind_policy_rf_and_unknown_dimensions(self):
        for changes in ({'section_kind':'ANGLE'},{'model_policy':'SHELL'}, {'section_params_m':{}},
                        {'section_params_m':dict(self.components[0]['section_params_m'],transition_fillet_m=-.1)}):
            c=dict(self.components[0],**changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):hoop_geometry(c)
    def test_ambiguous_component_mapping_rejected(self):
        self.components.append(deepcopy(self.components[0]))
        with self.assertRaisesRegex(ValueError,'unique component'):unique_hoop_parts(self.summary,self.components)
