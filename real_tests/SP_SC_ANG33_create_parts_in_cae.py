# -*- coding: utf-8 -*-
"""Standalone Abaqus/CAE script.

Usage:
  1. Open Abaqus/CAE.
  2. Create a new CAE or open an existing CAE manually.
  3. File -> Run Script, select this file.
     Alternatively, paste this file content into the CAE kernel command line.
  4. Parts, materials, sections, and meshes will be created in MODEL_NAME.
  5. Save the CAE manually when you are satisfied.

This file is self-contained and does not read the Excel/JSON files at runtime.
It does not open or save CAE files.

Unit system:
  length = m
  mass   = kg
  force  = N
  stress = Pa
"""
from __future__ import print_function

import json
from abaqus import mdb
from abaqusConstants import C3D8R, DEFORMABLE_BODY, OFF, S4R, STANDARD, THREE_D, UNIFORM
import mesh
import regionToolset


MODEL_NAME = "SP_SC_ANG33"
OVERWRITE_EXISTING_PARTS = True

COMPONENTS_JSON = r'''
{
  "components": [
    {
      "component_code": "INCLINED_BEAM",
      "element_type": "C3D8R",
      "length_m": 4.0,
      "material": {
        "abaqus_name": "MAT_Q355B",
        "density_kg_per_m3": 7850.0,
        "elastic_modulus_pa": 206000000000.0,
        "material_grade": "Q355 B",
        "poisson_ratio": 0.3
      },
      "model_policy": "SHELL",
      "model_units": {
        "force": "N",
        "length": "m",
        "mass": "kg",
        "stress": "Pa"
      },
      "part_name": "P_SP_SC_ANG33_INCLINED_BEAM",
      "quantity": "4",
      "section_code": "CX80X40X10X2",
      "section_kind": "C_CHANNEL",
      "section_params_m": {
        "b_m": 0.04,
        "h_m": 0.08,
        "lip_m": 0.01,
        "t_m": 0.002
      },
      "thickness_m": 0.002
    },
    {
      "component_code": "COLUMN",
      "element_type": "C3D8R",
      "length_m": 1.8,
      "material": {
        "abaqus_name": "MAT_MANUAL_CHECK",
        "density_kg_per_m3": null,
        "elastic_modulus_pa": null,
        "material_grade": "Q450B",
        "poisson_ratio": null
      },
      "model_policy": "SHELL",
      "model_units": {
        "force": "N",
        "length": "m",
        "mass": "kg",
        "stress": "Pa"
      },
      "part_name": "P_SP_SC_ANG33_COLUMN",
      "quantity": "4",
      "section_code": "PIPEX159X3",
      "section_kind": "PIPE",
      "section_params_m": {
        "od_m": 0.159,
        "t_m": 0.003
      },
      "thickness_m": 0.003
    },
    {
      "component_code": "BRACE_FRONT",
      "element_type": "S4R",
      "length_m": 1.5,
      "material": {
        "abaqus_name": "MAT_Q235B",
        "density_kg_per_m3": 7850.0,
        "elastic_modulus_pa": 206000000000.0,
        "material_grade": "Q235 B",
        "poisson_ratio": 0.3
      },
      "model_policy": "SHELL",
      "model_units": {
        "force": "N",
        "length": "m",
        "mass": "kg",
        "stress": "Pa"
      },
      "part_name": "P_SP_SC_ANG33_BRACE_FRONT",
      "quantity": "4",
      "section_code": "CX55X40X10X2",
      "section_kind": "C_CHANNEL",
      "section_params_m": {
        "b_m": 0.04,
        "h_m": 0.055,
        "lip_m": 0.01,
        "t_m": 0.002
      },
      "thickness_m": 0.002
    },
    {
      "component_code": "BRACE_REAR",
      "element_type": "S4R",
      "length_m": 2.762,
      "material": {
        "abaqus_name": "MAT_Q235B",
        "density_kg_per_m3": 7850.0,
        "elastic_modulus_pa": 206000000000.0,
        "material_grade": "Q235 B",
        "poisson_ratio": 0.3
      },
      "model_policy": "SHELL",
      "model_units": {
        "force": "N",
        "length": "m",
        "mass": "kg",
        "stress": "Pa"
      },
      "part_name": "P_SP_SC_ANG33_BRACE_REAR",
      "quantity": "4",
      "section_code": "CX60X45X15X2",
      "section_kind": "C_CHANNEL",
      "section_params_m": {
        "b_m": 0.045,
        "h_m": 0.06,
        "lip_m": 0.015,
        "t_m": 0.002
      },
      "thickness_m": 0.002
    },
    {
      "component_code": "PURLIN",
      "element_type": "C3D8R",
      "length_m": 15.182,
      "material": {
        "abaqus_name": "MAT_Q355B",
        "density_kg_per_m3": 7850.0,
        "elastic_modulus_pa": 206000000000.0,
        "material_grade": "Q355 B",
        "poisson_ratio": 0.3
      },
      "model_policy": "SHELL",
      "model_units": {
        "force": "N",
        "length": "m",
        "mass": "kg",
        "stress": "Pa"
      },
      "part_name": "P_SP_SC_ANG33_PURLIN",
      "quantity": "4",
      "section_code": "CX100X50X15X2",
      "section_kind": "C_CHANNEL",
      "section_params_m": {
        "b_m": 0.05,
        "h_m": 0.1,
        "lip_m": 0.015,
        "t_m": 0.002
      },
      "thickness_m": 0.002
    }
  ]
}
'''

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


def _float_or_none(value):
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _ensure_model(model_name):
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


def _delete_existing_part(model, part_name):
    part_name = _ascii(part_name)
    if OVERWRITE_EXISTING_PARTS and part_name in model.parts:
        del model.parts[part_name]


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


def _create_shell_part(model, component):
    length = _float_or_none(component.get("length_m")) or 0.1
    thickness = _float_or_none(component.get("thickness_m"))
    if thickness is None:
        raise ValueError("Shell Part requires thickness_m.")

    part_name = _ascii(component["part_name"])
    _delete_existing_part(model, part_name)

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

    part = model.Part(name=part_name, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseShellExtrude(sketch=sketch, depth=length)

    material_name = _ensure_material(model, component.get("material", {}))
    section_name = _ascii("SEC_" + part_name)
    if section_name not in model.sections:
        model.HomogeneousShellSection(
            name=section_name,
            preIntegrate=OFF,
            material=material_name,
            thicknessType=UNIFORM,
            thickness=thickness,
        )
    region = regionToolset.Region(faces=part.faces[:])
    part.SectionAssignment(region=region, sectionName=section_name)
    return part


def _solid_dimensions(component):
    params = component.get("section_params_m") or {}
    length = _float_or_none(component.get("length_m")) or float(params.get("width_m", 0.05) or 0.05)
    width = float(params.get("leg_a_m", params.get("inner_or_fit_diameter_m", params.get("nominal_diameter_m", 0.04))) or 0.04)
    height = float(params.get("leg_b_m", params.get("t_m", 0.01)) or 0.01)
    return max(width, 1.0), max(height, 1.0), max(length, 1.0)


def _create_solid_part(model, component):
    part_name = _ascii(component["part_name"])
    _delete_existing_part(model, part_name)

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

    part = model.Part(name=part_name, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=depth)

    material_name = _ensure_material(model, component.get("material", {}))
    section_name = _ascii("SEC_" + part_name)
    if section_name not in model.sections:
        model.HomogeneousSolidSection(name=section_name, material=material_name)
    region = regionToolset.Region(cells=part.cells[:])
    part.SectionAssignment(region=region, sectionName=section_name)
    return part


def _mesh_part(part, component):
    mesh_size = 0.08 if component.get("model_policy") == "SHELL" else 0.01
    part.seedPart(size=mesh_size, deviationFactor=0.1, minSizeFactor=0.1)
    elem_code = S4R if component.get("model_policy") == "SHELL" else C3D8R
    elem_type = mesh.ElemType(elemCode=elem_code, elemLibrary=STANDARD)
    if component.get("model_policy") == "SHELL":
        part.setElementType(regions=(part.faces[:],), elemTypes=(elem_type,))
    else:
        part.setElementType(regions=(part.cells[:],), elemTypes=(elem_type,))
    part.generateMesh()


def create_parts():
    components = json.loads(COMPONENTS_JSON)["components"]
    model = _ensure_model(MODEL_NAME)
    created = []
    failed = []

    for component in components:
        try:
            policy = component.get("model_policy")
            if policy == "SHELL":
                part = _create_shell_part(model, component)
                _mesh_part(part, component)
                created.append(_ascii(component["part_name"]))
            elif policy == "SOLID":
                part = _create_solid_part(model, component)
                _mesh_part(part, component)
                created.append(_ascii(component["part_name"]))
            else:
                failed.append((_ascii(component.get("part_name")), "unsupported policy: " + str(policy)))
        except Exception as exc:
            failed.append((_ascii(component.get("part_name")), str(exc)))

    print("Created %d parts in model %s." % (len(created), MODEL_NAME))
    for name in created:
        print("  OK  " + name)
    if failed:
        print("Failed %d parts:" % len(failed))
        for name, message in failed:
            print("  FAIL  %s  %s" % (name, message))

    return created, failed


create_parts()
