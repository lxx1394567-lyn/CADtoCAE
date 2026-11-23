"""Folder mapping, Chinese schemas, capability and transactional publication."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from cadtocae.hole_inputs import CHINESE_HEADERS, read_hole_table, normalize_records, normalize_hole_rows
from cadtocae.hole_plan import build_hole_plan
from cadtocae.hole_projects import scan_projects, generate_batch, project_details
from test_step06_hole_inputs import input_rows
from test_step06_hole_plan import fixture


def chinese_rows(project=None):
    return [[project,'P01','檩托','PS_TO_PURLIN','局部檩条','长肢',60,25,'起始端','长圆孔',12,40,'沿长肢方向','是',''],
            [project,'P01','檩托','PS_TO_BEAM','斜梁','短肢',21,25,'起始端','长圆孔',12,25,'沿檩托长度方向','是','']]


def hole_table(path, rows):
    wb=Workbook(); sheet=wb.active;sheet.title='螺栓孔定位表'
    sheet.append(CHINESE_HEADERS)
    for row in rows:sheet.append(row)
    wb.create_sheet('字段说明').append(['说明'])
    wb.save(path);wb.close()


def project_files(folder, project='TEST_STEP06'):
    summary,components=fixture();summary.update(project_id=project,model_name=project,structure_type='SP_SC')
    (folder/(project+'_assembly_summary.json')).write_text(json.dumps(summary),encoding='utf-8')
    wb=Workbook();wb.active.append(['Components fixture; exporter mocked in discovery unit tests'])
    wb.save(folder/(project+'_components.xlsx'));wb.close()
    return components


class ShapeTests(unittest.TestCase):
    def rows(self, changes=None):
        rows=input_rows()
        for row in rows:row.update(hole_type='SLOT',slot_total_length_mm=25,slot_major_axis='PART_LENGTH')
        if changes:rows[0].update(changes)
        return rows

    def test_round_and_slot(self):
        self.assertEqual(normalize_hole_rows(input_rows())[0].hole_type,'ROUND')
        row=normalize_hole_rows(self.rows())[0]
        self.assertEqual((row.hole_diameter_mm,row.slot_total_length_mm),(14.,25.))

    def test_bad_slot_dimensions_axis_and_round_conflicts(self):
        for changes in ({'slot_total_length_mm':12},{'slot_total_length_mm':-1},{'hole_diameter_mm':0},
                        {'slot_major_axis':'global X'},{'hole_type':'SQUARE'},{'hole_type':'ROUND'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):normalize_hole_rows(self.rows(changes))

    def test_equal_width_length_allowed(self):
        self.assertEqual(normalize_hole_rows(self.rows({'slot_total_length_mm':14}))[0].slot_total_length_mm,14)

    def test_slot_envelope_and_major_axis(self):
        summary,components=fixture()
        rows=self.rows({'slot_total_length_mm':90})
        with self.assertRaisesRegex(ValueError,'end-edge'):build_hole_plan(summary,normalize_hole_rows(rows),components)
        rows=self.rows({'slot_total_length_mm':100,'slot_major_axis':'LEG_DIRECTION'})
        with self.assertRaises(ValueError):build_hole_plan(summary,normalize_hole_rows(rows),components)

    def test_p02_plan_only_is_supported(self):
        summary,components=fixture();rows=input_rows()
        for m in list(summary['instances'][:2]):summary['instances'].append(dict(deepcopy(m),connection_group='P02',instance_name=m['instance_name'].replace('01','02')))
        rows += [dict(r,connection_group='P02') for r in input_rows()]
        plan=build_hole_plan(summary,normalize_hole_rows(rows),components)
        self.assertEqual(len(plan.driving_holes),4);self.assertEqual(plan.benchmark_scope,'P01')

    def test_confirmed_chinese_workbook_read_only(self):
        path=Path(__file__).resolve().parents[1]/'examples/Step06_螺栓孔定位表_中文版.xlsx'
        records=read_hole_table(path);rows=normalize_records(records,'TEST_STEP06')
        self.assertEqual(len(rows),2)
        self.assertEqual([(r.hole_type,r.hole_diameter_mm,r.slot_total_length_mm) for r in rows],[('SLOT',12,40),('SLOT',12,25)])
        self.assertEqual([r.slot_major_axis for r in rows],['LEG_DIRECTION','PART_LENGTH'])
