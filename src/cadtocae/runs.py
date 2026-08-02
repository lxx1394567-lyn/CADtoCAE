from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


RUN_SUBDIRS = ("workbooks", "json", "abaqus_scripts", "reports", "previews", "logs")


@dataclass(frozen=True)
class RunPaths:
    root: Path
    workbooks: Path
    json: Path
    abaqus_scripts: Path
    reports: Path
    previews: Path
    logs: Path
    manifest: Path
    outputs_root: Path


def _safe_project_code(project_code: str) -> str:
    cleaned = []
    for char in project_code.strip():
        if char.isalnum() or char in ("_", "-"):
            cleaned.append(char)
        else:
            cleaned.append("_")
    return "".join(cleaned) or "PV_SUPPORT"


def _unique_timestamp_dir(base: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = base / stamp
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        candidate = base / ("%s_%03d" % (stamp, index))
        if not candidate.exists():
            return candidate
    raise RuntimeError("Cannot allocate a unique run directory under %s" % base)


def create_run_paths(
    project_code: str = "SP_SC_ANG20",
    outputs_root: str | Path = "outputs",
    run_dir: str | Path | None = None,
) -> RunPaths:
    outputs = Path(outputs_root)
    if run_dir:
        if str(run_dir).strip().lower() == "latest":
            latest = outputs / "latest_run_manifest.json"
            if not latest.exists():
                raise FileNotFoundError("latest run manifest not found: %s" % latest)
            latest_payload = json.loads(latest.read_text(encoding="utf-8"))
            root = Path(latest_payload["run_dir"])
        else:
            root = Path(run_dir)
    else:
        root = _unique_timestamp_dir(outputs / ("%s_runs" % _safe_project_code(project_code)))

    paths = {name: root / name for name in RUN_SUBDIRS}
    root.mkdir(parents=True, exist_ok=True)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    return RunPaths(
        root=root,
        workbooks=paths["workbooks"],
        json=paths["json"],
        abaqus_scripts=paths["abaqus_scripts"],
        reports=paths["reports"],
        previews=paths["previews"],
        logs=paths["logs"],
        manifest=root / "manifest.json",
        outputs_root=outputs,
    )


def _path_text(path: str | Path | None) -> str | None:
    if path is None:
        return None
    return str(Path(path).resolve())


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _merge_outputs(manifest: dict[str, Any], outputs: dict[str, Any]) -> None:
    manifest.setdefault("outputs", {})
    for category, value in outputs.items():
        if isinstance(value, dict):
            manifest["outputs"].setdefault(category, {})
            manifest["outputs"][category].update(value)
        else:
            manifest["outputs"][category] = value


def update_manifest(
    paths: RunPaths,
    project_code: str,
    stage: str,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    update_latest: bool = True,
) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    manifest = _load_manifest(paths.manifest)
    if not manifest:
        manifest = {
            "project_code": project_code,
            "project_prefix": project_code,
            "created_at": now,
            "run_dir": _path_text(paths.root),
            "tool": "CADtoCAE",
            "outputs": {},
            "stages": {},
            "warnings": [],
            "errors": [],
        }

    manifest["updated_at"] = now
    manifest["project_code"] = project_code
    manifest["project_prefix"] = project_code
    manifest["run_dir"] = _path_text(paths.root)
    if metadata:
        manifest.setdefault("metadata", {}).update(metadata)
    if outputs:
        _merge_outputs(manifest, outputs)
    if warnings:
        manifest.setdefault("warnings", []).extend(warnings)
    if errors:
        manifest.setdefault("errors", []).extend(errors)

    manifest.setdefault("stages", {})[stage] = {
        "updated_at": now,
        "inputs": inputs or {},
        "outputs": outputs or {},
        "warnings": warnings or [],
        "errors": errors or [],
    }

    paths.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if update_latest:
        try:
            root_resolved = paths.root.resolve()
            outputs_resolved = paths.outputs_root.resolve()
            root_resolved.relative_to(outputs_resolved)
            should_update_latest = True
        except ValueError:
            should_update_latest = False
        if should_update_latest:
            latest = paths.outputs_root / "latest_run_manifest.json"
            latest.parent.mkdir(parents=True, exist_ok=True)
            latest.write_text(
                json.dumps(
                    {
                        "project_code": project_code,
                        "project_prefix": project_code,
                        "updated_at": now,
                        "run_dir": _path_text(paths.root),
                        "manifest": _path_text(paths.manifest),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
    return manifest
