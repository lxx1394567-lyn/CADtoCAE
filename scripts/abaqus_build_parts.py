# -*- coding: utf-8 -*-
"""Abaqus noGUI entry point for material-table-driven Part creation.

Run inside Abaqus:
    abaqus cae noGUI=scripts/abaqus_build_parts.py -- --json outputs/abaqus_components.json --cae outputs/SP_SC.cae

Run without Abaqus for validation:
    python scripts/abaqus_build_parts.py --json outputs/abaqus_components.json --dry-run --report outputs/parts_report.json
"""

from __future__ import print_function

import argparse
import codecs
import json
import os
import sys


try:
    unicode
except NameError:
    unicode = str


def _ascii(value):
    if value is None:
        return ""
    if isinstance(value, unicode):
        return value.encode("ascii")
    return str(value)


def _argv_after_abaqus_separator(argv):
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return argv[1:]


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Create Abaqus Parts from photovoltaic support components.")
    parser.add_argument("--json", required=True, help="Input JSON exported by prepare_abaqus_inputs.py.")
    parser.add_argument("--cae", default="outputs/generated_parts.cae", help="Output CAE path, only used inside Abaqus.")
    parser.add_argument("--model-name", default="PV_SUPPORT_PARTS", help="Abaqus model name.")
    parser.add_argument("--report", default="outputs/parts_report.json", help="Dry-run or generation report path.")
    parser.add_argument("--dry-run", action="store_true", help="Validate input and write a report without Abaqus.")
    return parser.parse_args(_argv_after_abaqus_separator(argv))


def load_components(path):
    with codecs.open(path, "r", "utf-8") as handle:
        payload = json.load(handle)
    return payload.get("components", [])


def _float_or_none(value):
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _ensure_parent(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent)


def build_report_rows(components):
    rows = []
    seen = set()
    for component in components:
        name = component.get("part_name") or ""
        issues = []
        if not name:
            issues.append("part_name missing")
        if name in seen:
            issues.append("duplicate part_name")
        seen.add(name)
        if any(ord(char) > 127 for char in name):
            issues.append("part_name contains non-ASCII")
        if component.get("model_policy") == "SHELL" and component.get("thickness_m") in (None, ""):
            issues.append("shell thickness missing")
        if component.get("model_policy") in ("SHELL", "SOLID") and component.get("length_m") in (None, ""):
            if component.get("section_kind") not in ("HOOP_BAND",):
                issues.append("length missing")
        rows.append(
            {
                "part_name": name,
                "component_name": component.get("component_name"),
                "model_policy": component.get("model_policy"),
                "element_type": component.get("element_type"),
                "section_kind": component.get("section_kind"),
                "material": component.get("material", {}).get("material_grade"),
                "issues": issues,
            }
        )
    return rows


def write_report(path, rows):
    _ensure_parent(path)
    with codecs.open(path, "w", "utf-8") as handle:
        json.dump({"parts": rows}, handle, ensure_ascii=False, indent=2)
    return path


def _import_abaqus():
    try:
        from abaqus import mdb
        from abaqusConstants import C3D8R, DEFORMABLE_BODY, OFF, S4R, STANDARD, THREE_D, UNIFORM
        import mesh
        import regionToolset
    except Exception as exc:
        raise RuntimeError("Abaqus Python modules are unavailable. Use --dry-run outside Abaqus: %s" % exc)
    return {
        "mdb": mdb,
        "C3D8R": C3D8R,
        "DEFORMABLE_BODY": DEFORMABLE_BODY,
        "OFF": OFF,
        "S4R": S4R,
        "STANDARD": STANDARD,
        "THREE_D": THREE_D,
        "UNIFORM": UNIFORM,
        "mesh": mesh,
        "regionToolset": regionToolset,
    }


def _ensure_model(api, model_name):
    mdb = api["mdb"]
    model_key = _ascii(model_name)
    if model_key in mdb.models:
        return mdb.models[model_key]
    return mdb.Model(name=model_key)


def _ensure_material(model, material):
    mat_name = _ascii(material.get("abaqus_name") or "MAT_MANUAL_CHECK")
    if mat_name in model.materials:
        return mat_name
    mat = model.Material(name=mat_name)
    elastic_modulus = material.get("elastic_modulus_pa")
    poisson_ratio = material.get("poisson_ratio")
    if elastic_modulus is not None and poisson_ratio is not None:
        mat.Elastic(table=((float(elastic_modulus), float(poisson_ratio)),))
    density = material.get("density_kg_per_m3")
    if density is not None:
        mat.Density(table=((float(density),),))
    return mat_name


def _profile_points(component):
    params = component.get("section_params_m") or {}
    kind = component.get("section_kind")
    if kind == "C_CHANNEL":
        h = float(params["h_m"])
        b = float(params["b_m"])
        lip = float(params["lip_m"])
        # Cold-formed lipped C channel centerline:
        # bottom lip -> bottom flange -> web -> top flange -> top lip.
        return [(b, lip), (b, 0.0), (0.0, 0.0), (0.0, h), (b, h), (b, h - lip)]
    if kind == "ANGLE":
        a = float(params["leg_a_m"])
        b = float(params["leg_b_m"])
        return [(a, 0.0), (0.0, 0.0), (0.0, b)]
    width = max(float(params.get("width_m", 0.05) or 0.05), 0.01)
    return [(0.0, 0.0), (width, 0.0)]


def _draw_closed_polyline(sketch, points):
    count = len(points)
    for index in range(count):
        sketch.Line(point1=points[index], point2=points[(index + 1) % count])


def _create_shell_part(api, model, component):
    length = _float_or_none(component.get("length_m")) or 0.1
    thickness = _float_or_none(component.get("thickness_m"))
    if thickness is None:
        raise ValueError("Shell Part requires thickness_m.")

    part_name = _ascii(component["part_name"])
    kind = component.get("section_kind")
    params = component.get("section_params_m") or {}
    sketch = model.ConstrainedSketch(name=_ascii("SK_" + part_name), sheetSize=max(length, 1000.0) * 2.0)

    if kind in ("PIPE", "STRUT_PIPE"):
        radius = float(params["od_m"]) / 2.0 - float(params.get("t_m", thickness)) / 2.0
        sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(radius, 0.0))
    else:
        points = _profile_points(component)
        for start, end in zip(points[:-1], points[1:]):
            sketch.Line(point1=start, point2=end)

    part = model.Part(name=part_name, dimensionality=api["THREE_D"], type=api["DEFORMABLE_BODY"])
    part.BaseShellExtrude(sketch=sketch, depth=length)

    material_name = _ensure_material(model, component.get("material", {}))
    section_name = _ascii("SEC_" + part_name)
    if section_name not in model.sections:
        model.HomogeneousShellSection(
            name=section_name,
            preIntegrate=api["OFF"],
            material=material_name,
            thicknessType=api["UNIFORM"],
            thickness=thickness,
        )
    region = api["regionToolset"].Region(faces=part.faces[:])
    part.SectionAssignment(region=region, sectionName=section_name)
    return part


def _solid_dimensions(component):
    params = component.get("section_params_m") or {}
    length = _float_or_none(component.get("length_m")) or float(params.get("width_m", 0.05) or 0.05)
    width = float(params.get("leg_a_m", params.get("inner_or_fit_diameter_m", params.get("nominal_diameter_m", 0.04))) or 0.04)
    height = float(params.get("leg_b_m", params.get("t_m", 0.01)) or 0.01)
    return max(width, 1.0), max(height, 1.0), max(length, 1.0)


def _create_solid_part(api, model, component):
    part_name = _ascii(component["part_name"])
    kind = component.get("section_kind")
    params = component.get("section_params_m") or {}
    sketch = model.ConstrainedSketch(name=_ascii("SK_" + part_name), sheetSize=1000.0)
    depth = 50.0

    if kind in ("THREADED", "ROD"):
        diameter = float(params.get("nominal_diameter_m", params.get("diameter_m", 0.01)) or 0.01)
        depth = _float_or_none(component.get("length_m")) or max(5.0 * diameter, 0.03)
        radius = diameter / 2.0
        sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(radius, 0.0))
    elif kind == "ANGLE":
        a = float(params["leg_a_m"])
        b = float(params["leg_b_m"])
        t = float(params["t_m"])
        depth = _float_or_none(component.get("length_m")) or 0.05
        _draw_closed_polyline(sketch, [(0.0, 0.0), (a, 0.0), (a, t), (t, t), (t, b), (0.0, b)])
    elif kind == "HOOP_BAND":
        inner_radius = float(params["inner_or_fit_diameter_m"]) / 2.0
        outer_radius = inner_radius + float(params["t_m"])
        depth = float(params["width_m"])
        sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(outer_radius, 0.0))
        sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(inner_radius, 0.0))
    else:
        width, height, depth = _solid_dimensions(component)
        sketch.rectangle(point1=(0.0, 0.0), point2=(width, height))

    part = model.Part(name=part_name, dimensionality=api["THREE_D"], type=api["DEFORMABLE_BODY"])
    part.BaseSolidExtrude(sketch=sketch, depth=depth)

    material_name = _ensure_material(model, component.get("material", {}))
    section_name = _ascii("SEC_" + part_name)
    if section_name not in model.sections:
        model.HomogeneousSolidSection(name=section_name, material=material_name)
    region = api["regionToolset"].Region(cells=part.cells[:])
    part.SectionAssignment(region=region, sectionName=section_name)
    return part


def _mesh_part(api, part, component):
    mesh_size = 0.08 if component.get("model_policy") == "SHELL" else 0.01
    part.seedPart(size=mesh_size, deviationFactor=0.1, minSizeFactor=0.1)
    elem_code_name = component.get("element_type") or ("S4R" if component.get("model_policy") == "SHELL" else "C3D8R")
    elem_code = api.get(elem_code_name, api["S4R"])
    elem_type = api["mesh"].ElemType(elemCode=elem_code, elemLibrary=api["STANDARD"])
    if component.get("model_policy") == "SHELL":
        part.setElementType(regions=(part.faces[:],), elemTypes=(elem_type,))
    else:
        part.setElementType(regions=(part.cells[:],), elemTypes=(elem_type,))
    part.generateMesh()


def create_parts_in_abaqus(args, components):
    api = _import_abaqus()
    model = _ensure_model(api, args.model_name)
    report = []

    for component in components:
        try:
            policy = component.get("model_policy")
            if policy == "SHELL":
                part = _create_shell_part(api, model, component)
                _mesh_part(api, part, component)
                status = "created"
            elif policy == "SOLID":
                part = _create_solid_part(api, model, component)
                _mesh_part(api, part, component)
                status = "created"
            else:
                status = "skipped_manual_template"
            report.append({"part_name": _ascii(component.get("part_name")), "status": status, "issues": []})
        except Exception as exc:
            report.append({"part_name": _ascii(component.get("part_name")), "status": "failed", "issues": [str(exc)]})

    _ensure_parent(args.cae)
    api["mdb"].saveAs(pathName=os.path.abspath(args.cae))
    return report


def main(argv=None):
    argv = argv or sys.argv
    args = parse_args(argv)
    components = load_components(args.json)

    if args.dry_run:
        report = build_report_rows(components)
        output = write_report(args.report, report)
        print("Dry-run report written: %s" % output)
        return 0

    report = create_parts_in_abaqus(args, components)
    output = write_report(args.report, report)
    print("Abaqus parts report written: %s" % output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
