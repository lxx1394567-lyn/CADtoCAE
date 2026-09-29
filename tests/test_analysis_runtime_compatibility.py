"""Dedicated Abaqus coding-contract checks, separate from Python 3 correctness."""
import ast
import builtins
from pathlib import Path
from types import GeneratorType
import unittest
from unittest.mock import patch

from cadtocae.runtime_compatibility import assert_runtime_compatible, check_templates, RUNTIME_TEMPLATES
from cadtocae.beam_brace_tie import generate
from cadtocae.analysis_project import discover_project_folder
import test_analysis_beam_brace_tie as simple_fixture
import test_step05_analysis_setup as legacy_fixture


class RuntimeCompatibilityTests(unittest.TestCase):
    def fixture(self, cls):
        value = cls()
        self.addCleanup(value.doCleanups)
        value.setUp()
        return value

    def test_all_runtime_templates_have_no_generator_or_dict_comprehension(self):
        self.assertEqual(check_templates(), 14)
        for name in RUNTIME_TEMPLATES:
            source = (Path(__file__).resolve().parents[1]/'src/cadtocae'/name).read_text(encoding='utf-8')
            self.assertFalse(any(isinstance(n, ast.GeneratorExp) for n in ast.walk(ast.parse(source))), name)

    def test_rejects_all_forbidden_patterns_not_just_sum(self):
        patterns = ['sum(x for x in xs)', 'tuple(x for x in xs)', 'list(x for x in xs)',
                    'any(x for x in xs)', 'all(x for x in xs)', 'min(x for x in xs)',
                    'max(x for x in xs)', '{k: sum(x for x in xs) for k in ks}',
                    '(x for x in xs)', 'def lazy():\n    yield 1']
        for source in patterns:
            with self.subTest(source=source), self.assertRaises(ValueError):
                assert_runtime_compatible(source)

    def test_final_simple_generated_script(self):
        fixture = self.fixture(simple_fixture.PlannerTests)
        path = generate(discover_project_folder(fixture.root), fixture.config)['script']
        source = path.read_text(encoding='utf-8')
        assert_runtime_compatible(source, str(path))
        self.assertNotIn('area_before', source)
        self.assertNotIn('area_after', source)
        self.assertIn('Beam web patch area incomplete', source)

    def test_final_legacy_generated_script(self):
        fixture = self.fixture(legacy_fixture.AnalysisRuntimeTests)
        assert_runtime_compatible(fixture.source, str(fixture.paths['script']))

    def test_generator_refuses_runtime_regression_before_writing(self):
        fixture = self.fixture(simple_fixture.PlannerTests)
        files = discover_project_folder(fixture.root)
        original = Path.read_text
        def corrupt(path, *args, **kwargs):
            source = original(path, *args, **kwargs)
            if path.name == 'beam_brace_tie_runtime.py':
                source += '\ninvalid = sum(x for x in [1,2])\n'
            return source
        with patch.object(Path, 'read_text', corrupt):
            with self.assertRaisesRegex(ValueError, 'GeneratorExp'):
                generate(files, fixture.config)
        self.assertEqual(list((fixture.root/'step05_validation').glob('*_analysis_setup.py')), [])

    def test_model_execution_with_generator_rejecting_reducers(self):
        # Simulate the reported lazy-iterator incompatibility rather than relying
        # only on ordinary CPython builtins accepting generators.
        fixture = self.fixture(simple_fixture.RuntimeTests)
        def reducer(name):
            fn = getattr(builtins, name)
            def guarded(*args, **kwargs):
                for arg in args:
                    if isinstance(arg, GeneratorType):
                        raise TypeError("arg1; found 'generator', expecting a recognized type")
                return fn(*args, **kwargs)
            return guarded
        for name in ('sum','any','all','min','max','sorted'):
            fixture.runtime[name] = reducer(name)
        report = fixture.run_script()
        self.assertEqual(report['status'], 'SUCCESS')
        self.assertEqual(len(report['connections']), 2)
        self.assertEqual(len(report['partitions']), 8)

    def test_name_helper_python3_and_python2_unicode_branch(self):
        fixture = self.fixture(simple_fixture.RuntimeTests)
        helper = fixture.runtime['abaqus_name']
        self.assertEqual(helper(None), '')
        self.assertIs(type(helper('STEP05_REGION')), str)
        self.assertEqual(helper(b'STEP05_REGION'), 'STEP05_REGION')
        for value in ('\u4e2d\u6587', b'\xff'):
            with self.assertRaisesRegex(ValueError, 'ASCII'):
                helper(value)
        # Exercise exactly the branch Python 2 takes for JSON Unicode strings.
        fixture.runtime['unicode'] = str
        self.assertEqual(helper('STEP05_REGION'), b'STEP05_REGION')
        self.assertIs(type(helper('STEP05_REGION')), bytes)
        with self.assertRaisesRegex(ValueError, 'ASCII'):
            helper('\u4e2d\u6587')

    def test_json_names_cross_all_api_boundaries_and_reuse(self):
        import json
        fixture = self.fixture(simple_fixture.RuntimeTests)
        fixture.plan = json.loads(json.dumps(fixture.plan))
        calls = []
        helper = fixture.runtime['abaqus_name']
        class SafeName(str):
            pass
        def converted(value):
            calls.append(value)
            return SafeName(helper(value))
        fixture.runtime['abaqus_name'] = converted
        def guard(fn, keys):
            def checked(*args, **kwargs):
                for key in keys:
                    self.assertIs(type(kwargs[key]), SafeName)
                return fn(*args, **kwargs)
            return checked
        assembly = fixture.model.rootAssembly
        assembly.Set = guard(assembly.Set, ['name'])
        assembly.Surface = guard(assembly.Surface, ['name'])
        fixture.model.Tie = guard(fixture.model.Tie, ['name'])
        for part in fixture.parts:
            part.features.changeKey = guard(part.features.changeKey, ['fromName', 'toName'])
        result = fixture.run_script()
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(len(assembly.sets), 4)
        self.assertEqual(len(assembly.surfaces), 4)
        self.assertEqual(len(fixture.model.constraints), 2)
        self.assertEqual(fixture.run_script()['partitions'], [])
        for name in ('TEST', 'BEAM', 'FRONT', 'REAR', 'STEP05_TIE_BEAM_BRACE_FRONT'):
            self.assertIn(name, calls)

    def test_generated_name_audit_rejects_each_unsafe_api(self):
        fixture = self.fixture(simple_fixture.PlannerTests)
        source = generate(discover_project_folder(fixture.root), fixture.config)['script'].read_text(encoding='utf-8')
        assert_runtime_compatible(source)
        for original, broken in (
            ('Set(name=set_name', 'Set(name=name'),
            ('Surface(name=surf_name', "Surface(name=c['beam_region']"),
            ('Tie(name=tie_name', "Tie(name=c['tie']"),
            ('fromName=abaqus_name(datum.name)', 'fromName=datum.name'),
        ):
            self.assertIn(original, source)
            with self.assertRaisesRegex(ValueError, 'object name requires abaqus_name'):
                assert_runtime_compatible(source.replace(original, broken))
