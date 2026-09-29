"""SP_SC v1 defaults, passed through the existing analysis input validators."""
from collections.abc import Mapping
from copy import deepcopy
from types import SimpleNamespace

CONFIG_ID = 'DEFAULT_SP_SC_ANALYSIS_CONFIG'
DEFAULT_SP_SC_ANALYSIS_CONFIG = {
    'BEAM_BRACE_TIE': dict(enabled=True,beam_half_length_mm=50,brace_end_length_mm=50,
                           beam_shell_side='SIDE2',brace_shell_side='SIDE2'),
    'COLUMN_COLUMN_TIE': dict(enabled=True),
    'COLUMN_HOOP_TIE': dict(enabled=True),
    'COLUMN_BEAM_COUPLING': dict(enabled=True,column_top_length_mm=50,coupling_type='DISTRIBUTING',
                                u1=True,u2=True,u3=True,ur1=True,ur2=True,ur3=True),
}


def default_analysis_config():
    return deepcopy(DEFAULT_SP_SC_ANALYSIS_CONFIG)


DC_CONFIG_ID = 'DEFAULT_SP_DC_ANALYSIS_CONFIG'
DEFAULT_SP_DC_ANALYSIS_CONFIG = {
    'BEAM_BRACE_TIE': deepcopy(DEFAULT_SP_SC_ANALYSIS_CONFIG['BEAM_BRACE_TIE']),
    'COLUMN_BEAM_TIE': dict(enabled=True,beam_half_length_mm=50,column_top_length_mm=50),
    'COLUMN_HOOP_TIE': dict(enabled=True),
}


def family_analysis_config(structure):
    if structure == 'SP_SC':return default_analysis_config()
    if structure == 'SP_DC':return deepcopy(DEFAULT_SP_DC_ANALYSIS_CONFIG)
    raise ValueError('Unsupported structure: '+str(structure))


def open_analysis_config(value, loader, sheet, rule, fields, **options):
    """Expose in-memory values using the SAME row schema as the legacy reader.

    No Excel file is constructed. Explicit legacy workbook paths still use the
    original loader. Validation and engineering resolvers remain shared.
    """
    if not isinstance(value,Mapping):return loader(value,**options)
    class ConfigView:
        sheetnames=[sheet] if rule in value else []
        def __getitem__(self,key):
            if key!=sheet or rule not in value:raise KeyError(key)
            data=dict(value[rule],rule_id=rule)
            rows=[tuple(fields),tuple(data.get(field) for field in fields)]
            return SimpleNamespace(values=rows,iter_rows=lambda values_only=True:iter(rows))
        def close(self):pass
    return ConfigView()
