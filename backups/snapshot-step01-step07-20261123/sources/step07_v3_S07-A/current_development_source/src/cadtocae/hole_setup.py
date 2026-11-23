"""Generate self-contained Step06 CAE scripts and publish an atomic output pair."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from .analysis_discovery import identity, linked, safe_project_id
from .runtime_compatibility import assert_runtime_compatible


def _helpers(filename, names):
    """Reuse only pure helper functions, never the Step05 Tie executor."""
    source = (Path(__file__).parent/filename).read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            selected.append("".join(lines[node.lineno-1:node.end_lineno]))
    if len(selected) != len(names):
        raise ValueError("Missing reusable runtime helper: "+filename)
    return "\n\n".join(selected)+"\n"


def script_source(plan, report_path):
    encoded = json.dumps(plan, ensure_ascii=True, sort_keys=True, allow_nan=False)
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    source = "# -*- coding: utf-8 -*-\n# CADtoCAE Step06 Hole Setup\nimport math\n"
    source += _helpers("beam_brace_tie_runtime.py", {"is_numeric_triple", "point3", "vector3", "abaqus_name"})
    source += _helpers("analysis_runtime.py", {"_s5_repository_text", "_s5_repository_key", "resolve_repository_item"})
    source += (Path(__file__).parent/"hole_runtime.py").read_text(encoding="utf-8")
    entry = 'execute_hole_setup'
    if plan.get('runtime_mode') == 'STEP06_A':
        source += _helpers('analysis_geometry.py', {'add','sub','scale','dot','cross','norm','unit'})
        source += (Path(__file__).parent/'hole_transforms.py').read_text(encoding='utf-8-sig')
        source += (Path(__file__).parent/'hole_derived_runtime.py').read_text(encoding='utf-8-sig')
        entry = 'execute_step06_a'
        if plan.get('hoop_hole_plan',{}).get('runtime_enabled'):
            source += (Path(__file__).parent/'hoop_hole_runtime.py').read_text(encoding='utf-8-sig')
            entry = 'execute_step06_with_hoop'
    source += "\nPLAN = json.loads(%r)\n" % encoded
    source += "REPORT_PATH = json.loads(%r)\n" % json.dumps(str(report_path), ensure_ascii=True)
    source += "if __name__ == '__main__':\n    from abaqus import mdb\n    %s(PLAN, mdb, REPORT_PATH, %r)\n" % (entry, fingerprint)
    assert_runtime_compatible(source, "step06_hole_setup.py")
    return source


def write_hole_setup(plan, folder, input_identity=None):
    folder = Path(folder).resolve(strict=True)
    project = plan["project_id"]
    safe_project_id(project)
    if not folder.is_dir():
        raise ValueError("Project folder required")
    paths = {"plan":folder/(project+"_step06_plan.json"), "script":folder/(project+"_step06_hole_setup.py")}
    report = folder/(project+"_step06_hole_report.json")
    source = script_source(plan, report)
    for path in list(paths.values())+[report]:
        if path.exists() and (linked(path) or not path.is_file()):
            raise ValueError("Expected a regular output file: "+str(path))
    lock = folder/("."+project+"_step06_generation.lock")
    with lock.open("x", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    try:
        with tempfile.TemporaryDirectory(prefix=".step06-tmp-", dir=folder) as temporary:
            stage = Path(temporary)
            (stage/paths["plan"].name).write_text(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            (stage/paths["script"].name).write_text(source, encoding="utf-8")
            for value, expected in (input_identity or {}).items():
                if linked(Path(value)) or identity(Path(value)) != expected:
                    raise ValueError("Input changed before publication: "+value)
            backup = stage/"previous"
            backup.mkdir()
            replaced = []
            try:
                for path in paths.values():
                    if path.exists():
                        if linked(path) or not path.is_file():
                            raise ValueError("Output changed before publication: "+str(path))
                        shutil.copy2(path, backup/path.name)
                    os.replace(stage/path.name, path)
                    replaced.append(path)
            except Exception:
                for path in reversed(replaced):
                    if (backup/path.name).exists():
                        os.replace(backup/path.name, path)
                    else:
                        path.unlink()
                raise
    finally:
        lock.unlink()
    return paths
