"""Desktop-only lint for text which will execute in Abaqus/CAE 2020.

This checks the runtime coding contract, not the installed Abaqus kernel/API.
Never inline this Python 3 build-time module into a generated CAE script.
"""
import ast
from pathlib import Path

RUNTIME_TEMPLATES = (
    'analysis_geometry.py', 'analysis_runtime.py', 'beam_brace_tie_runtime.py',
    'partition_validation_minimal.py', 'brace_partition_validation_minimal.py',
    'brace_extend_face_validation.py', 'brace_extend_face_replay_validation.py',
    'column_column_tie_runtime.py',
    'column_axis.py',
    'column_hoop_tie_runtime.py',
    'tie_preflight_runtime.py',
    'column_beam_coupling_runtime.py',
    'column_beam_tie_runtime.py', 'sp_dc_runtime.py',
)


def assert_runtime_compatible(source, filename='<generated>'):
    tree = ast.parse(source, filename=filename)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.GeneratorExp, ast.DictComp, ast.Yield, ast.YieldFrom)):
            violations.append('%s:%d %s' % (filename, node.lineno, type(node).__name__))
    if violations:
        raise ValueError('Abaqus runtime requires explicit loops; forbidden lazy/comprehension pattern:\n'+
                         '\n'.join(sorted(violations)))
    if any(isinstance(n, ast.FunctionDef) and n.name in ('abaqus_name', 'cct_partition', 'cht_rename') for n in tree.body):
        assert_object_names(tree, filename)
    return tree


def assert_object_names(tree, filename):
    """Guard the formal executor's explicit API-boundary name conversions."""
    for function in tree.body:
        if not isinstance(function, ast.FunctionDef):
            continue
        safe = set()
        for node in ast.walk(function):
            if isinstance(node, ast.Assign):
                value = node.value
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'abaqus_name':
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            safe.add(target.id)
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ('Set', 'Surface', 'Tie', 'changeKey'):
                continue
            for keyword in node.keywords:
                if keyword.arg not in ('name', 'fromName', 'toName'):
                    continue
                value = keyword.value
                converted = (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                             and value.func.id == 'abaqus_name')
                if not converted and not (isinstance(value, ast.Name) and value.id in safe):
                    raise ValueError('%s:%d Abaqus object name requires abaqus_name' % (filename, node.lineno))


def check_templates():
    root = Path(__file__).parent
    for filename in RUNTIME_TEMPLATES:
        assert_runtime_compatible((root/filename).read_text(encoding='utf-8'), filename)
    return len(RUNTIME_TEMPLATES)
