"""Conservative static contracts; generation inputs are distinct from runtime inputs."""
import ast
import json
import re
from pathlib import Path
from .matching import auto_match, LEGAL_DIRS, validate_file, external_plan, legal_candidates

PROVENANCE = (
    ('_components.xlsx',), ('_coordinate.xlsx', '_coordinate_formula_simple_fixed.xlsx', '_assembly_summary.json'),
    ('_analysis_plan.json',), ('_step06_plan.json', '_螺栓孔定位表.xlsx'),
    (), (), (), (), (),
)

def values(tree):
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            value = node.value
            try:
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and isinstance(value.func.value, ast.Name) and value.func.value.id == 'json' and value.func.attr == 'loads':
                    result[node.targets[0].id] = json.loads(ast.literal_eval(value.args[0]))
                else:
                    result[node.targets[0].id] = ast.literal_eval(value)
            except (ValueError, TypeError, IndexError, json.JSONDecodeError):
                pass
    return result

def local_file(folder, name):
    path = (folder / name).resolve()
    if folder not in path.parents or Path(name).is_absolute() or ':' in name:
        raise ValueError('Input must stay inside project directory: ' + name)
    return path

def check(project):
    folder = Path(project.folder)
    manifest_path = folder / (project.prefix + '_batchrunner.json')
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
            if not isinstance(manifest, dict) or manifest.get('project') != project.prefix:
                raise ValueError('Manifest project must exactly match prefix')
        except (ValueError, OSError) as exc:
            project.conflicts.append(str(exc))
    project.inventory = [dict(path=str(p.resolve()), role='historical_report' if p.name.endswith('_report.json') else 'script' if p.suffix == '.py' else 'source_or_plan')
                         for d in LEGAL_DIRS for p in (folder/d).glob(project.prefix+'_*') if p.is_file()]
    ready = not project.conflicts
    for stage in project.stages:
        if not stage.script:
            ready = False
            continue
        missing_input = False
        try:
            import hashlib
            source_bytes = Path(stage.script).read_bytes()
            stage.inspected_source_sha256 = hashlib.sha256(source_bytes).hexdigest()
            source = source_bytes.decode('utf-8-sig')
            tree = ast.parse(source)
            embedded = values(tree)
            external, external_payload = external_plan(tree, Path(stage.script), project.prefix, embedded)
            if external_payload is not None:
                embedded['PLAN'] = external_payload
            stage.embedded_inputs = [name for name in ('COMPONENTS_JSON','ASSEMBLY_DATA','PLAN') if name in embedded and not (name=='PLAN' and external)]
            config = manifest.get('stages', {}).get(str(stage.number), {})
            contract = {'model': project.prefix, 'kind': 'custom', 'parts': [], 'instances': []}
            if stage.number == 1 and 'COMPONENTS_JSON' in embedded:
                payload = json.loads(embedded['COMPONENTS_JSON'])
                contract.update(kind='parts', model=embedded.get('MODEL_NAME'), parts=[c['part_name'] for c in payload['components']])
            elif stage.number == 2 and 'ASSEMBLY_DATA' in embedded:
                data = embedded['ASSEMBLY_DATA']
                contract.update(kind='assembly', model=data['meta'].get('model_name'), instances=[x.get('instance_id') or x.get('instance_name') for x in data.get('instance_plan', [])])
                if data.get('errors'):
                    stage.reasons.append('Embedded assembly preflight errors: ' + str(data['errors']))
            elif stage.number >= 5 and 'INPLACE_PLAN' in embedded:
                from .step07_adapter import inspect_plan
                contract, missing_input = inspect_plan(project, stage, embedded['INPLACE_PLAN'])
            elif stage.number >= 3 and 'PLAN' in embedded:
                plan = embedded['PLAN']
                identity = plan.get('project_id') or plan.get('project', {}).get('project_id')
                if identity != project.prefix:
                    stage.reasons.append('Embedded PLAN project mismatch')
                contract.update(kind='report')
                if plan.get('model_name', project.prefix) != project.prefix:
                    stage.reasons.append('Embedded PLAN model mismatch')
            elif stage.number >= 3 and external and any(k in embedded for k in ('REPORT','REPORT_PATH')):
                contract.update(kind='report')
            elif not config.get('validation'):
                stage.reasons.append('Unknown runtime interface: declare validation in project manifest')
            if contract['model'] != project.prefix:
                stage.reasons.append('Model name does not match project prefix')
            if config.get('validation'):
                contract.update(config['validation'])
                if contract.get('model') != project.prefix:
                    stage.reasons.append('Validation model must match project prefix')
            if contract['kind'] == 'custom' and not (contract.get('parts') or contract.get('instances')):
                stage.reasons.append('Custom script requires expected parts or instances')
            contract['outputs'] = config.get('outputs', [])
            for output in contract['outputs']:
                local_file(folder, output)
            stage.contract = contract
            if contract['kind'] == 'parts' and not contract['parts']:
                stage.reasons.append('Empty component plan')
            if contract['kind'] == 'assembly' and not contract['instances']:
                stage.reasons.append('Empty or unsupported assembly instance plan')
            declared = {x['path']: x for x in config.get('inputs', [])}
            for name, item in declared.items():
                path = local_file(folder, name)
                from_stage = item.get('from_stage')
                if from_stage is not None:
                    if not isinstance(from_stage, int) or not 1 <= from_stage < stage.number:
                        raise ValueError('from_stage must precede this stage')
                    producer = manifest.get('stages', {}).get(str(from_stage), {})
                    if name not in producer.get('outputs', []):
                        raise ValueError('Upstream output not declared: ' + name)
                required = item.get('required', True)
                stage.inputs.append(dict(path=str(path), relative=name, required=required, found=path.is_file(), role='runtime', from_stage=from_stage))
                if required and from_stage is None and not path.is_file():
                    missing_input = True
                    stage.reasons.append('Missing required input: ' + str(path))
            if not contract.get('step07'):
                missing_input = auto_match(project, stage, tree, embedded) or missing_input
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and (getattr(node.func, 'id', '') == 'open' or getattr(node.func, 'attr', '') == 'open') and node.args:
                    try:
                        output_name = ast.literal_eval(node.args[0])
                        mode_node = next((kw.value for kw in node.keywords if kw.arg == 'mode'), node.args[1] if len(node.args)>1 else ast.Constant('r'))
                        mode = ast.literal_eval(mode_node)
                        if isinstance(output_name, str) and isinstance(mode, str) and any(c in mode for c in 'wax+'):
                            local_file(folder, output_name)
                    except (ValueError, TypeError) as exc:
                        if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and 'Input must stay' in str(exc):
                            stage.reasons.append('Unsafe literal output path: ' + node.args[0].value)
                if isinstance(node, ast.Call) and getattr(node.func, 'attr', '') in ('saveAs', 'openMdb'):
                    args = list(node.args) + [kw.value for kw in node.keywords if kw.arg == 'pathName']
                    for arg in args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            try:
                                local_file(folder, arg.value)
                            except ValueError:
                                stage.reasons.append('Unsafe hardcoded CAE path: ' + arg.value)
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.match(r'^(?:[A-Za-z]:[\\/]|\\\\|/)', node.value):
                    stage.warnings.append('Hardcoded path (review read/write use): ' + node.value[:240])
            for suffix in PROVENANCE[stage.number-1]:
                path = folder / (project.prefix + suffix)
                candidates = legal_candidates(folder, path.name)
                if len(candidates)>1:
                    stage.warnings.append('Optional generation source conflict (not a runtime requirement): '+', '.join(str(p) for p in candidates))
                for candidate in candidates or [path]:
                    stage.inputs.append(dict(path=str(candidate), relative=path.name, required=False, found=candidate.is_file(), role='generation', validation='OPTIONAL_CONFLICT' if len(candidates)>1 else 'OPTIONAL_FOUND' if candidate.is_file() else 'OPTIONAL_ABSENT'))
            for item in stage.inputs:
                if item.get('from_stage') is not None:
                    item['validation'] = 'WAITING_UPSTREAM'
                elif item['role'] == 'generation':
                    item.setdefault('validation', 'OPTIONAL_FOUND' if item['found'] else 'OPTIONAL_ABSENT')
            if stage.embedded_inputs:
                stage.warnings.append('Embedded data: changes to generation-only JSON/Excel require regenerating the PY; only runtime reads invalidate execution.')
            stage.outputs = ['checkpoint.cae'] + (['runtime_report.json'] if contract['kind'] in ('report', 'assembly') else []) + contract.get('outputs', [])
            if manifest_path.exists():
                stage.inputs.append(dict(path=str(manifest_path), relative=manifest_path.name, required=True, found=True, role='config'))
            if any(ord(c) > 127 or c.isspace() for c in str(folder)):
                stage.warnings.append('Unicode/space path: isolated ASCII worker filenames; Abaqus installation compatibility still required')
        except (ValueError, TypeError, KeyError, OSError, SyntaxError) as exc:
            stage.reasons.append('Cannot inspect script/manifest: ' + str(exc))
        if not ready:
            stage.reasons.append('Predecessor unavailable or project conflict')
        stage.reasons.extend(project.conflicts)
        stage.status = 'MISSING_INPUT' if missing_input else 'BLOCKED' if stage.reasons else 'READY'
        ready = stage.status == 'READY'
    return project
