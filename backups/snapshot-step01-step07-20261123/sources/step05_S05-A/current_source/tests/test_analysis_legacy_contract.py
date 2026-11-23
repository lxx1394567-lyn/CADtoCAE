"""Pin the checkpoint's default SC/DC runtime AST, excluding only DP branches.

This is stronger than excluding changed files from a local byte-hash check:
every original statement and literal must survive after specializing the new
optional modes to their legacy defaults. No Git checkout or private input needed.
"""
import ast
import hashlib
from pathlib import Path
import unittest


class LegacyDefaults(ast.NodeTransformer):
    def visit_FunctionDef(self,node):
        if node.name in ('cpl_verify_face_station','prepare_face_coupling','cpl_face_selections'):
            return None
        if node.name=='execute' and node.args.args[-1].arg=='prepared':
            node.args.args=node.args.args[:-2];node.args.defaults=node.args.defaults[:-2]
        return self.generic_visit(node)

    def visit_Assign(self,node):
        if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('face_mode','expected_status'):
            return None
        return self.generic_visit(node)

    def visit_If(self,node):
        text=ast.unparse(node.test)
        if text in ('face_mode','geometry_only',"report.get('report_key')"):
            result=[]
            for statement in node.orelse:
                transformed=self.visit(statement)
                if isinstance(transformed,list):result.extend(transformed)
                elif transformed is not None:result.append(transformed)
            return result
        return self.generic_visit(node)

    def visit_IfExp(self,node):
        if isinstance(node.test,ast.Name) and node.test.id=='face_mode':return self.visit(node.orelse)
        return self.generic_visit(node)

    def visit_Name(self,node):
        if node.id=='expected_status':return ast.Constant(value='SUCCESS')
        return node


def legacy_ast(source):
    return ast.dump(LegacyDefaults().visit(ast.parse(source)),include_attributes=False)


class LegacyContractTests(unittest.TestCase):
    def test_default_runtime_matches_checkpoint_ast(self):
        # SHA256 of AST at ff322e1, generated once from that checkpoint.
        expected = {'beam_brace_tie_runtime.py': 'f76594f4f6922dd342da3c8c49749fc7c6d419db9ea2c3e0ae145ce205376b4d', 'column_beam_coupling_runtime.py': '728ace800c4d9689fb5f4b543bc2256a94a239d00adad1f6fa281db99f3e32df'}
        for filename,digest in expected.items():
            source=(Path(__file__).resolve().parents[1]/'src/cadtocae'/filename).read_text(encoding='utf-8')
            self.assertEqual(hashlib.sha256(legacy_ast(source).encode()).hexdigest(),digest,filename)
