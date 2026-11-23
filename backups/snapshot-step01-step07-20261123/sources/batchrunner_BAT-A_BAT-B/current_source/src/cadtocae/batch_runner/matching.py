"""Deterministic read discovery and binding, never fuzzy or newest-file selection."""
import ast
import hashlib
import json
from pathlib import Path, PureWindowsPath
import zipfile

LEGAL_DIRS = ('', 'inputs', 'json', 'reports', '过程文件/调试文件')
READERS = {'open', 'load_workbook', 'read_excel', 'read_text', 'read_bytes', 'exists', 'isfile'}

def legal_candidates(folder, name):
    folder = Path(folder).resolve()
    result = []
    for relative in LEGAL_DIRS:
        path = folder / relative / name
        resolved = path.resolve()
        if folder in resolved.parents and path.is_file() and not path.is_symlink():
            if resolved not in result:
                result.append(resolved)
    return result

def validate_file(path, prefix):
    path = Path(path)
    if path.suffix.lower() == '.json':
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(data, dict):
            project = data.get('project')
            identities = [data.get('project_id'), data.get('model_name')]
            if isinstance(project, dict):
                identities += [project.get('project_id'), project.get('model_name')]
            elif isinstance(project, str):
                identities.append(project)
            if any(value and value != prefix for value in identities):
                raise ValueError('JSON project identity mismatch: ' + str(path))
        return 'JSON valid; declared project identity matches or identity is filename-only'
    if path.suffix.lower() == '.xlsx':
        with zipfile.ZipFile(path) as workbook:
            if '[Content_Types].xml' not in workbook.namelist() or workbook.testzip():
                raise ValueError('Invalid XLSX container: ' + str(path))
        return 'XLSX container valid (not a business-schema validation)'
    return 'Readable file'

def evaluate(node, env):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.Subscript):
        return evaluate(node.value, env)[evaluate(node.slice, env)]
    if isinstance(node, ast.BinOp):
        left, right = evaluate(node.left, env), evaluate(node.right, env)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Div):
            return str(Path(left) / right)
    if isinstance(node, ast.Attribute) and node.attr == 'parent':
        return str(Path(evaluate(node.value, env)).parent)
    if isinstance(node, ast.Call):
        name = ast.unparse(node.func)
        args = [evaluate(x, env) for x in node.args]
        if name in ('Path', 'str'):
            return str(args[0])
        if name in ('os.path.join',):
            return str(Path(args[0]).joinpath(*args[1:]))
        if name in ('os.path.dirname',):
            return str(Path(args[0]).parent)
        if name in ('os.path.abspath',):
            return str(Path(args[0]).resolve())
        if name == 'json.loads':
            return json.loads(args[0])
        if isinstance(node.func, ast.Attribute) and node.func.attr in ('resolve', 'absolute'):
            return str(Path(evaluate(node.func.value, env)).resolve())
    raise ValueError('Unresolved expression')

def source_reads(tree, script, embedded):
    env = dict(embedded, __file__=str(script))
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                env[node.targets[0].id] = evaluate(node.value, env)
            except (ValueError, KeyError, TypeError, IndexError):
                pass
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
        if name not in READERS:
            continue
        mode = next((kw.value for kw in node.keywords if kw.arg == 'mode'), node.args[1] if name == 'open' and len(node.args)>1 else ast.Constant('r'))
        try:
            mode = evaluate(mode, env)
        except (ValueError, KeyError, TypeError):
            mode = None
        if name == 'open' and isinstance(mode, str) and any(c in mode for c in 'wax'):
            continue
        is_check = name in ('exists', 'isfile')
        receiver = name in ('read_text', 'read_bytes') or (is_check and not node.args and isinstance(node.func, ast.Attribute))
        arg = node.func.value if receiver else (node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg in ('file','filename','io')), None))
        if arg is None:
            continue
        local_env = dict(env)
        ancestor = parents.get(node)
        while ancestor is not None:
            if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                shadows = {n.id for n in ast.walk(ancestor) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
                shadows.update(a.arg for a in ancestor.args.args)
                for key in shadows:
                    local_env.pop(key, None)
                break
            ancestor = parents.get(ancestor)
        try:
            value = evaluate(arg, local_env)
        except (ValueError, KeyError, TypeError, IndexError):
            value = None
        yield node, arg, value, receiver, mode, is_check

def auto_match(project, stage, tree, embedded):
    folder = Path(project.folder)
    stage.contract.setdefault('read_bindings', [])
    missing = False
    reads = list(source_reads(tree, Path(stage.script), embedded))
    references = {}
    for call, arg, reference, receiver, mode, is_check in reads:
        if is_check:
            continue
        expression = ast.unparse(arg)
        # Audited generated runtimes read their own freshly redirected report.
        if stage.contract['kind'] != 'custom' and expression in ('REPORT', 'REPORT_PATH', 'report_path', 'path'):
            continue
        if stage.contract.get('integrated_hole_report') and expression in ("plan['hole_report_path']", "PLAN['hole_report_path']"):
            continue
        if not isinstance(reference, str) or mode is None or (isinstance(mode, str) and '+' in mode):
            stage.reasons.append('Unresolved runtime read at line %d: %s; explicit compatible input interface required' % (call.lineno, expression))
            continue
        basename = PureWindowsPath(reference).name
        existing = next((i for i in stage.inputs if i['role']=='runtime' and (i['relative']==reference or i.get('original_reference')==reference)), None)
        if existing:
            item = existing
        else:
            item = dict(path=str(folder/basename), relative='inputs/'+hashlib.sha256(reference.encode()).hexdigest()[:16]+Path(basename).suffix,
                        required=True, found=False, role='runtime', original_reference=reference,
                        expected=[str(folder/d/basename) for d in LEGAL_DIRS], from_stage=None)
            stage.inputs.append(item)
            if not basename.startswith(project.prefix+'_'):
                stage.reasons.append('Runtime input does not have exact project prefix: ' + reference)
                continue
            if basename.endswith('_report.json'):
                stage.reasons.append('Historical report cannot be used as input without an explicit upstream producer: ' + reference)
                continue
            candidates = legal_candidates(folder, basename)
            item['candidates'] = [str(p) for p in candidates]
            if len(candidates) > 1:
                item['validation'] = 'CONFLICT'
                stage.reasons.append('Multiple exact input candidates: ' + ', '.join(item['candidates']))
                continue
            if candidates:
                item.update(path=str(candidates[0]), found=True)
        if item.get('from_stage') is not None:
            item['validation'] = 'WAITING_UPSTREAM'
        elif not item['found']:
            if item['required']:
                missing = True
                item['validation'] = 'MISSING_INPUT'
                stage.reasons.append('Missing required input: '+str(item['path']))
            else:
                item['validation'] = 'OPTIONAL_ABSENT'
        else:
            try:
                item['validation'] = validate_file(item['path'], project.prefix)
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                item['validation'] = str(exc)
                stage.reasons.append(str(exc))
        binding = dict(line=arg.lineno, column=arg.col_offset, end_line=arg.end_lineno, end_column=arg.end_col_offset,
                       relative=item['relative'], original=expression, receiver=receiver)
        stage.contract['read_bindings'].append(binding)
        references[reference] = item['relative']
    for call, arg, reference, receiver, mode, is_check in reads:
        if is_check and isinstance(reference, str) and reference in references:
            stage.contract['read_bindings'].append(dict(line=arg.lineno,column=arg.col_offset,end_line=arg.end_lineno,end_column=arg.end_col_offset,relative=references[reference],original=ast.unparse(arg),receiver=receiver))
    if not stage.contract['read_bindings']:
        stage.contract.pop('read_bindings')
    return missing

def bind_reads(source, bindings):
    """Replace only statically validated read arguments, preserving all algorithm bodies."""
    lines = source.encode('utf-8').splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1]+len(line))
    raw = b''.join(lines)
    for binding in sorted(bindings, key=lambda b:(b['line'],b['column']), reverse=True):
        start = offsets[binding['line']-1]+binding['column']
        end = offsets[binding['end_line']-1]+binding['end_column']
        value = ascii(binding['relative'])
        if binding['receiver']:
            value = '__import__("pathlib").Path(%s)' % value
        raw = raw[:start]+value.encode()+raw[end:]
    return raw.decode('utf-8')


def external_plan(tree, script, prefix, embedded):
    """Recognize the exact PLAN = json.load(open(...)) report-script interface."""
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='PLAN' for t in node.targets)):
            continue
        if not (isinstance(node.value, ast.Call) and ast.unparse(node.value.func)=='json.load'):
            continue
        descendant_ids = {id(n) for n in ast.walk(node.value)}
        for call, arg, reference, receiver, mode, is_check in source_reads(tree, script, embedded):
            if id(call) in descendant_ids and isinstance(reference, str):
                name=PureWindowsPath(reference).name
                candidates=legal_candidates(Path(script).parent,name)
                if name.startswith(prefix+'_') and len(candidates)==1:
                    validate_file(candidates[0],prefix)
                    return True,json.loads(candidates[0].read_text(encoding='utf-8-sig'))
        return True,None
    return False,None
