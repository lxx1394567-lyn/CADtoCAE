"""Generate standalone A2 scripts without requiring Abaqus in the build process."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .analysis_inputs import read_analysis_inputs
from .analysis_rules import build_analysis_plan
from .runtime_compatibility import assert_runtime_compatible


def generate_analysis_setup(summary_path, input_path, output_dir):
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8-sig"))
    plan = build_analysis_plan(summary, read_analysis_inputs(input_path))
    return write_analysis_setup(plan.to_dict(), output_dir)


def write_analysis_setup(payload, output_dir):
    """Write an already validated plan; no inputs or execution reports overwritten."""
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, allow_nan=False)
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    output = Path(output_dir).resolve()
    project_id = payload["project"]["project_id"]
    # Never allow user project identifiers to escape the selected output directory.
    if any(char in project_id for char in '/\\<>:"|?*') or project_id in (".", ".."):
        raise ValueError("Unsafe project_id for output filename")
    output.mkdir(parents=True, exist_ok=True)
    script_path = output / (project_id + "_analysis_setup.py")
    report_path = output / (project_id + "_analysis_setup_report.json")
    plan_path = output / (project_id + "_analysis_plan.json")
    source = Path(__file__).parent
    script = "# -*- coding: utf-8 -*-\n# CADtoCAE Step05 A2: partitions and regions only.\n"
    script += (source / "analysis_geometry.py").read_text(encoding="utf-8") + "\n"
    script += (source / "analysis_runtime.py").read_text(encoding="utf-8") + "\n"
    script += "\nPLAN = json.loads(%r)\n" % encoded
    script += "REPORT_PATH = json.loads(%r)\n" % json.dumps(str(report_path).replace("\\", "/"), ensure_ascii=True)
    script += "PLAN_FINGERPRINT = %r\n" % fingerprint
    script += "\nif __name__ == '__main__':\n    from abaqus import mdb\n    execute_analysis(PLAN, mdb, REPORT_PATH, PLAN_FINGERPRINT)\n"
    assert_runtime_compatible(script, str(script_path))
    compile(script, str(script_path), "exec")
    script_path.write_text(script, encoding="utf-8")
    plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return {"script": script_path, "plan": plan_path, "runtime_report": report_path}
