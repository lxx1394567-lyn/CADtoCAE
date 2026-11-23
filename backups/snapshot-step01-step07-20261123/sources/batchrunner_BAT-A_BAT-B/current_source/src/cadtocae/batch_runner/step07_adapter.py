"""Bindings for the inspected CURRENT_MDB_IN_PLACE interface; no modelling."""
import ast
import json
from pathlib import Path
from .executor import digest
from .matching import legal_candidates, validate_file


def inspect_plan(project, stage, plan):
    if (plan.get('schema') != 'step07-inplace-1' or
        plan.get('execution_mode') != 'CURRENT_MDB_IN_PLACE' or
        plan.get('stage') != stage.number - 4 or
        plan.get('project_id') != project.prefix or plan.get('model_name') != project.prefix):
        raise ValueError('Unsupported Step07 interface/stage/project; regenerate current in-place PY')
    summary = plan['assembly_summary']
    if summary.get('project_id') != project.prefix or summary.get('model_name') != project.prefix:
        raise ValueError('Step07 embedded Assembly project mismatch')
    contract = dict(kind='report', model=project.prefix, step07=plan['stage'],
                    instances=[x['instance_name'] for x in summary['instances']],
                    parts=[], step07_plan=plan)
    stage.embedded_inputs.append('INPLACE_PLAN')
    stage.inputs.append(dict(path='', relative='upstream_hole_report.json', source_name='runtime_report.json',
                             required=True, found=False, role='runtime', from_stage=4))
    missing = False
    if stage.number == 9:
        raw = plan.get('load_config_path')
        if not raw:
            stage.reasons.append('Missing Load configuration: regenerate Load PY with project load workbook')
            return contract, True
        path = Path(raw)
        if not path.is_absolute():
            path = Path(stage.script).parent / path
        # The embedded path is authoritative; a fallback is exact-name only.
        if not path.is_file():
            candidates = legal_candidates(Path(project.folder), path.name)
            if len(candidates) > 1:
                raise ValueError('Conflicting Load inputs: '+str(candidates))
            if candidates:
                path = candidates[0]
        item = dict(path=str(path.resolve()), relative='step07_load_input.json', required=True,
                    found=path.is_file(), role='runtime')
        stage.inputs.append(item)
        if not item['found']:
            stage.reasons.append('Missing required Load JSON: '+str(path))
            missing = True
        else:
            item['validation'] = validate_file(path, project.prefix)
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            if data.get('project_id') != project.prefix:
                raise ValueError('Load JSON must explicitly identify this project')
            if digest(path) != plan.get('load_config_sha256'):
                raise ValueError('Load JSON changed: regenerate Load PY from workbook; embedded SHA-256 differs')
    return contract, missing


def adapt_inplace(source):
    """Retain original runtime and entry; replace only I/O configuration and capture report."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    edits = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'INPLACE_PLAN' for t in node.targets):
            addition = ("\nINPLACE_PLAN['logs_dir'] = os.path.abspath('step07_logs')\n"
                        "INPLACE_PLAN['output_dir'] = os.getcwd()\n"
                        "with open('upstream_hole_report.json') as _batch_h: INPLACE_PLAN['hole_report'] = json.load(_batch_h)\n"
                        "if INPLACE_PLAN['stage'] == 5: INPLACE_PLAN['load_config_path'] = os.path.abspath('step07_load_input.json')\n")
            edits.append((node.end_lineno, node.end_lineno, addition))
        if isinstance(node, ast.If) and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'u7_run' for n in ast.walk(node)):
            edits.append((node.lineno-1, node.end_lineno,
                          "if __name__ == '__main__':\n    _batch_step07_result = u7_run(INPLACE_PLAN)\n    with open('runtime_report.json', 'w') as _batch_r: json.dump(_batch_step07_result, _batch_r)\n"))
    if len(edits) != 2:
        raise ValueError('Unsupported Step07 entry point; expected INPLACE_PLAN and u7_run')
    for start, end, replacement in sorted(edits, reverse=True):
        lines[start:end] = [replacement]
    return ''.join(lines)
