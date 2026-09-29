import unittest
from pathlib import Path
import tempfile
from openpyxl import Workbook

from cadtocae.analysis_defaults import default_analysis_config
from cadtocae.beam_brace_tie import read_tie_config
from cadtocae.column_column_tie import read_column_config
from cadtocae.column_hoop_tie import hoop_enabled
from cadtocae.column_beam_coupling import read_coupling_config


class DefaultConfigTests(unittest.TestCase):
    def test_same_validators_and_values_as_validated_workbook(self):
        # Snapshot of the validated workbook; no local input files required.
        sheets = {
            'Tie_Config': [('rule_id', 'enabled', 'beam_half_length_mm', 'brace_end_length_mm', 'beam_shell_side', 'brace_shell_side'),
                           ('BEAM_BRACE_TIE', True, 50, 50, 'SIDE2', 'SIDE2')],
            'Column_Tie_Config': [('rule_id', 'enabled'), ('COLUMN_COLUMN_TIE', True)],
            'Column_Hoop_Tie_Config': [('rule_id', 'enabled'), ('COLUMN_HOOP_TIE', True)],
            'Coupling_Config': [('rule_id', 'enabled', 'column_top_length_mm', 'coupling_type', 'u1', 'u2', 'u3', 'ur1', 'ur2', 'ur3'),
                                ('COLUMN_BEAM_COUPLING', True, 50, 'DISTRIBUTING', True, True, True, True, True, True)],
        }
        with tempfile.TemporaryDirectory() as folder:
            legacy = Path(folder) / 'analysis.xlsx'
            workbook = Workbook()
            workbook.remove(workbook.active)
            for name, rows in sheets.items():
                sheet = workbook.create_sheet(name)
                for row in rows:
                    sheet.append(row)
            workbook.save(legacy)
            workbook.close()
            for reader in (read_tie_config,read_column_config,hoop_enabled,read_coupling_config):
                with self.subTest(reader=reader.__name__):
                    self.assertEqual(reader(default_analysis_config()),reader(legacy))

    def test_same_validation_rejects_invalid_internal_values(self):
        config=default_analysis_config();config['BEAM_BRACE_TIE']['beam_half_length_mm']=-50
        with self.assertRaises(ValueError):read_tie_config(config)
        config=default_analysis_config();config['COLUMN_BEAM_COUPLING']['u2']=False
        with self.assertRaises(ValueError):read_coupling_config(config)

    def test_defaults_are_isolated_per_project(self):
        one=default_analysis_config();one['COLUMN_BEAM_COUPLING']['ur3']=False
        self.assertTrue(default_analysis_config()['COLUMN_BEAM_COUPLING']['ur3'])
