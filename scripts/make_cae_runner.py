from __future__ import annotations

import argparse
import json
from pathlib import Path


CAE_TEMPLATE = r'''# -*- coding: utf-8 -*-
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
from abaqusConstants import C3D8R, CLOCKWISE, COPLANAR_EDGES, COUNTERCLOCKWISE, DEFORMABLE_BODY, OFF, RIGHT, S4R, SIDE1, STANDARD, SUPERIMPOSE, THREE_D, UNIFORM
import mesh
import regionToolset


MODEL_NAME = "__MODEL_NAME__"
OVERWRITE_EXISTING_PARTS = True

COMPONENTS_JSON = r''' + "'''" + r'''
__COMPONENTS_JSON__
''' + "'''" + r'''

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


def _draw_angle_profile(sketch, params):
    a = float(params["leg_a_m"])
    b = float(params["leg_b_m"])
    t = float(params["t_m"])
    radius = float(params.get("inner_root_radius_m", 0.0) or 0.0)
    lines = []
    points = [(0.0, 0.0), (a, 0.0), (a, t), (t, t), (t, b), (0.0, b)]
    for index in range(len(points)):
        lines.append(sketch.Line(point1=points[index], point2=points[(index + 1) % len(points)]))
    if radius > 0.0:
        sketch.FilletByRadius(
            radius=radius,
            curve1=lines[2],
            nearPoint1=(t + radius, t),
            curve2=lines[3],
            nearPoint2=(t, t + radius),
        )


def _simple_c_profile_points(params):
    h = float(params["h_m"])
    b = float(params["b_m"])
    t = float(params["t_m"])
    return [(0.0, 0.0), (b, 0.0), (b, t), (t, t), (t, h - t), (b, h - t), (b, h), (0.0, h)]


def _mid_clamp_profile_points():
    # Smooth U-shaped blank: H=23, outer bottom width=20, wall=3, bottom=4.
    # Each top flange measures 15 mm from the channel inner edge to its outer tip.
    return [(-0.022, 0.023), (-0.007, 0.023), (-0.007, 0.004), (0.007, 0.004),
            (0.007, 0.023), (0.022, 0.023), (0.022, 0.019), (0.010, 0.019),
            (0.010, 0.0), (-0.010, 0.0), (-0.010, 0.019), (-0.022, 0.019)]


def _validate_mid_clamp_profile(points):
    def orientation(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def segments_intersect(a, b, c, d):
        tolerance = 1.0e-12
        if max(a[0], b[0]) + tolerance < min(c[0], d[0]) or max(c[0], d[0]) + tolerance < min(a[0], b[0]):
            return False
        if max(a[1], b[1]) + tolerance < min(c[1], d[1]) or max(c[1], d[1]) + tolerance < min(a[1], b[1]):
            return False
        first_c = orientation(a, b, c)
        first_d = orientation(a, b, d)
        second_a = orientation(c, d, a)
        second_b = orientation(c, d, b)
        return first_c * first_d <= tolerance and second_a * second_b <= tolerance

    count = len(points)
    if count < 3 or len(set(points)) != count:
        raise ValueError("MID_CLAMP profile is not a valid closed region")
    edges = [(points[index], points[(index + 1) % count]) for index in range(count)]
    if any(a == b for a, b in edges):
        raise ValueError("MID_CLAMP profile is not a valid closed region")
    for first in range(count):
        for second in range(first + 1, count):
            if second in (first, (first + 1) % count) or first == (second + 1) % count:
                continue
            a, b = edges[first]
            c, d = edges[second]
            if segments_intersect(a, b, c, d):
                raise ValueError("MID_CLAMP profile is not a valid closed region")
    twice_area = 0.0
    for index in range(count):
        next_index = (index + 1) % count
        twice_area += points[index][0] * points[next_index][1] - points[next_index][0] * points[index][1]
    if abs(twice_area) <= 1.0e-12:
        raise ValueError("MID_CLAMP profile is not a valid closed region")


def _edge_clamp_profile_points():
    # Drawing V1: H=34, top=15x4, first web=3, middle=23x4,
    # second web=3, bottom contact extension=8. Teeth are intentionally omitted.
    return [(0.0, 0.034), (0.015, 0.034), (0.015, 0.011), (0.038, 0.011),
            (0.038, 0.003), (0.046, 0.003), (0.046, 0.0), (0.035, 0.0),
            (0.035, 0.007), (0.012, 0.007), (0.012, 0.030), (0.0, 0.030)]


def _clamp_profile_points(kind):
    if kind == "MID_CLAMP_PROFILE":
        return _mid_clamp_profile_points()
    return _edge_clamp_profile_points()


def _clamp_requires_slots(kind):
    return kind == "EDGE_CLAMP_PROFILE"


def _draw_slot(sketch, center_x, center_y, slot_width, slot_length):
    radius = slot_width / 2.0
    half_straight = (slot_length - slot_width) / 2.0
    if radius <= 0.0 or half_straight < 0.0:
        raise ValueError("Clamp slot requires slot_length >= slot_width > 0.")
    lower = center_y - half_straight
    upper = center_y + half_straight
    sketch.Line(point1=(center_x - radius, lower), point2=(center_x - radius, upper))
    sketch.ArcByCenterEnds(center=(center_x, upper), point1=(center_x - radius, upper),
                           point2=(center_x + radius, upper), direction=CLOCKWISE)
    sketch.Line(point1=(center_x + radius, upper), point2=(center_x + radius, lower))
    sketch.ArcByCenterEnds(center=(center_x, lower), point1=(center_x + radius, lower),
                           point2=(center_x - radius, lower), direction=CLOCKWISE)


def _find_clamp_sketch_plane(part, top_y):
    tolerance = 1.0e-8
    for face in part.faces:
        point = tuple(face.pointOn[0])
        if abs(point[1] - top_y) > tolerance:
            continue
        normal = tuple(face.getNormal(point=point))
        if abs(normal[1]) < 0.999:
            continue
        for edge_index in tuple(face.getEdges()):
            edge = part.edges[edge_index]
            vertex_indices = tuple(edge.getVertices())
            if len(vertex_indices) != 2:
                continue
            first = tuple(part.vertices[vertex_indices[0]].pointOn[0])
            second = tuple(part.vertices[vertex_indices[1]].pointOn[0])
            if abs(first[0] - second[0]) <= tolerance and abs(first[1] - second[1]) <= tolerance:
                if abs(first[2] - second[2]) > tolerance:
                    return face, edge
    raise ValueError("CLAMP SKETCH_PLANE: no planar top face with a Z-direction up edge")


def _cut_clamp_slots(model, part, component, top_y):
    params = component.get("section_params_m") or {}
    length = float(params["length_m"])
    slot_width = float(params["slot_width_m"])
    slot_length = float(params["slot_length_m"])
    centers = (float(params["hole_1_center_m"]), float(params["hole_2_center_m"]))
    kind = component.get("section_kind")
    slot_x = -0.007 if kind == "MID_CLAMP_PROFILE" else 0.008
    print("%s: locating hole sketch plane" % component.get("component_code", kind))
    face, up_edge = _find_clamp_sketch_plane(part, top_y)
    try:
        transform = part.MakeSketchTransform(
            sketchPlane=face,
            sketchUpEdge=up_edge,
            sketchPlaneSide=SIDE1,
            origin=(0.0, top_y, 0.0),
        )
    except Exception as exc:
        raise RuntimeError("%s SKETCH_PLANE: %s" % (component.get("component_code", kind), exc))
    sketch_name = _ascii("SK_SLOT_" + component["part_name"])
    cut_sketch = model.ConstrainedSketch(name=sketch_name, sheetSize=0.2, transform=transform)
    print("%s: hole sketch created" % component.get("component_code", kind))
    cut_sketch.setPrimaryObject(option=SUPERIMPOSE)
    part.projectReferencesOntoSketch(sketch=cut_sketch, filter=COPLANAR_EDGES)
    for center in centers:
        _draw_slot(cut_sketch, slot_x, center, slot_width, slot_length)
    try:
        part.CutExtrude(
            sketchPlane=face,
            sketchUpEdge=up_edge,
            sketchPlaneSide=SIDE1,
            sketch=cut_sketch,
            flipExtrudeDirection=OFF,
        )
    except Exception as exc:
        raise RuntimeError("%s CUT: %s" % (component.get("component_code", kind), exc))
    print("%s: hole cut success" % component.get("component_code", kind))
    cut_sketch.unsetPrimaryObject()
    del model.sketches[sketch_name]


def _hoop_band_dimensions(component):
    params = component.get("section_params_m") or {}
    diameter = float(params.get("diameter_m", 0.0) or 0.0)
    width = float(params.get("width_m", 0.0) or 0.0)
    thickness = float(params.get("t_m", 0.0) or 0.0)
    left = float(params.get("left_extension_m", 0.0) or 0.0)
    right = float(params.get("right_extension_m", 0.0) or 0.0)
    fillet = float(params.get("transition_fillet_m", 0.0) or 0.0)
    if diameter <= 0.0 or width <= 0.0 or thickness <= 0.0 or left <= 0.0 or right <= 0.0:
        raise ValueError("HOOP_BAND requires positive diameter_m, width_m, t_m, left_extension_m, and right_extension_m.")
    inner_radius = diameter / 2.0
    return {
        "inner_radius_m": inner_radius,
        "outer_radius_m": inner_radius + thickness,
        "width_m": width,
        "thickness_m": thickness,
        "left_extension_m": left,
        "right_extension_m": right,
        "transition_fillet_m": fillet,
    }


def _draw_hoop_band_profile(sketch, component):
    dims = _hoop_band_dimensions(component)
    rin = dims["inner_radius_m"]
    rout = dims["outer_radius_m"]
    left = dims["left_extension_m"]
    right = dims["right_extension_m"]
    # Local axes: X = left/right extensions, Y = arc convex direction,
    # Z = extrusion/band width. Arc center O = (0, 0).
    outer_left_end = (-rout - left, 0.0)
    outer_right_end = (rout + right, 0.0)
    left_line = sketch.Line(point1=outer_left_end, point2=(-rout, 0.0))
    outer_arc = sketch.ArcByCenterEnds(center=(0.0, 0.0), point1=(-rout, 0.0), point2=(rout, 0.0), direction=CLOCKWISE)
    right_line = sketch.Line(point1=(rout, 0.0), point2=outer_right_end)
    fillet = dims["transition_fillet_m"]
    if fillet > 0.0:
        geometry_count = len(sketch.geometry)
        sketch.FilletByRadius(radius=fillet, curve1=left_line, nearPoint1=(-rout - fillet, 0.0),
                              curve2=outer_arc, nearPoint2=(-rout + fillet, fillet))
        if len(sketch.geometry) <= geometry_count:
            raise ValueError("HOOP left transition fillet did not create new sketch geometry.")
        geometry_count = len(sketch.geometry)
        sketch.FilletByRadius(radius=fillet, curve1=outer_arc, nearPoint1=(rout - fillet, fillet),
                              curve2=right_line, nearPoint2=(rout + fillet, 0.0))
        if len(sketch.geometry) <= geometry_count:
            raise ValueError("HOOP right transition fillet did not create new sketch geometry.")
    outer = tuple(sketch.geometry[key] for key in sketch.geometry.keys())
    before = set(sketch.geometry.keys())
    try:
        sketch.offset(distance=dims["thickness_m"], objectList=outer, side=RIGHT)
        created = set(sketch.geometry.keys()) - before
        if len(created) < 3:
            raise ValueError("Abaqus Sketch offset did not create the expected inner Line+Arc+Line chain.")
        offset_points = []
        for key in created:
            for vertex in sketch.geometry[key].getVertices():
                sketch_vertex = vertex if hasattr(vertex, "coords") else sketch.vertices[vertex]
                offset_points.append(tuple(sketch_vertex.coords))
        if not offset_points:
            raise ValueError("Abaqus Sketch offset did not expose inner-chain endpoints.")
        inner_left_end = min(offset_points, key=lambda point: point[0])
        inner_right_end = max(offset_points, key=lambda point: point[0])
    except Exception:
        if fillet > 0.0:
            raise ValueError("HOOP transition fillet/offset failed; no sharp-corner fallback is allowed when RF is specified.")
        created = set(sketch.geometry.keys()) - before
        if created:
            sketch.delete(objectList=tuple(sketch.geometry[key] for key in created))
        inner_left_end = (-rout - left, -dims["thickness_m"])
        inner_right_end = (rout + right, -dims["thickness_m"])
        sketch.Line(point1=inner_left_end, point2=(-rin, -dims["thickness_m"]))
        sketch.Line(point1=(-rin, -dims["thickness_m"]), point2=(-rin, 0.0))
        sketch.ArcByCenterEnds(center=(0.0, 0.0), point1=(rin, 0.0), point2=(-rin, 0.0), direction=COUNTERCLOCKWISE)
        sketch.Line(point1=(rin, 0.0), point2=(rin, -dims["thickness_m"]))
        sketch.Line(point1=(rin, -dims["thickness_m"]), point2=inner_right_end)
    sketch.Line(point1=outer_left_end, point2=inner_left_end)
    sketch.Line(point1=outer_right_end, point2=inner_right_end)


def _float_text(value):
    if value is None or str(value).strip() == "":
        return ""
    return "%.6g" % float(value)


def _print_geometry_summary(component):
    for warning in component.get("validation_warnings") or ():
        print("  WARNING " + warning)
    summary = component.get("geometry_summary") or {}
    summary_type = summary.get("type")
    if summary_type == "PURLIN_LOCAL":
        print("PURLIN_LOCAL:")
        print("  section = %s" % (summary.get("section") or component.get("section_kind") or ""))
        print("  length_m = %s" % _float_text(summary.get("length_m", component.get("length_m"))))
        print("  length_source = %s" % (summary.get("length_source") or component.get("length_source") or ""))
    elif summary_type == "HOOP":
        print("HOOP:")
        for key in ("D_m", "Ri_m", "Ro_m", "W_m", "T_m", "L_m", "R_m", "RF_m"):
            print("  %s = %s" % (key, _float_text(summary.get(key))))
        if summary.get("transition_note"):
            print("  " + summary["transition_note"])


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
    final_part_name = _ascii(component["part_name"])
    kind = component.get("section_kind")
    protected_replace = kind in ("MID_CLAMP_PROFILE", "EDGE_CLAMP_PROFILE")
    part_name = _ascii("TMP_" + final_part_name) if protected_replace else final_part_name
    _delete_existing_part(model, part_name)
    if not protected_replace:
        _delete_existing_part(model, final_part_name)
    params = component.get("section_params_m") or {}
    sketch = model.ConstrainedSketch(name=_ascii("SK_" + part_name), sheetSize=1000.0)
    depth = 50.0

    if kind in ("THREADED", "ROD"):
        diameter = float(params.get("nominal_diameter_m", params.get("diameter_m", 0.01)) or 0.01)
        depth = _float_or_none(component.get("length_m")) or max(5.0 * diameter, 0.03)
        radius = diameter / 2.0
        sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(radius, 0.0))
    elif kind == "ANGLE":
        depth = _float_or_none(component.get("length_m")) or 0.05
        _draw_angle_profile(sketch, params)
    elif kind == "C_CHANNEL_SIMPLE":
        depth = _float_or_none(component.get("length_m"))
        if depth is None:
            raise ValueError("PURLIN_SPLICE requires length_m.")
        _draw_closed_polyline(sketch, _simple_c_profile_points(params))
    elif kind == "HOOP_BAND":
        dims = _hoop_band_dimensions(component)
        depth = dims["width_m"]
        _draw_hoop_band_profile(sketch, component)
    elif kind in ("MID_CLAMP_PROFILE", "EDGE_CLAMP_PROFILE"):
        depth = float(params["length_m"])
        profile_points = _clamp_profile_points(kind)
        if kind == "MID_CLAMP_PROFILE":
            _validate_mid_clamp_profile(profile_points)
            print("MID_CLAMP profile points:")
            for index, point in enumerate(profile_points):
                print("  P%d = (%s, %s)" % (index + 1, point[0], point[1]))
            print("  closed by P%d -> P1" % len(profile_points))
        try:
            _draw_closed_polyline(sketch, profile_points)
        except Exception as exc:
            raise RuntimeError("%s PROFILE: %s" % (component.get("component_code", kind), exc))
        print("%s: profile created" % component.get("component_code", kind))
    else:
        width, height, depth = _solid_dimensions(component)
        sketch.rectangle(point1=(0.0, 0.0), point2=(width, height))

    part = model.Part(name=part_name, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    try:
        part.BaseSolidExtrude(sketch=sketch, depth=depth)
    except Exception as exc:
        if kind in ("MID_CLAMP_PROFILE", "EDGE_CLAMP_PROFILE"):
            raise RuntimeError("%s EXTRUDE: %s" % (component.get("component_code", kind), exc))
        raise
    if kind in ("MID_CLAMP_PROFILE", "EDGE_CLAMP_PROFILE"):
        print("%s: solid extrude success" % component.get("component_code", kind))
    if _clamp_requires_slots(kind):
        top_y = 0.023 if kind == "MID_CLAMP_PROFILE" else 0.034
        _cut_clamp_slots(model, part, component, top_y)

    material_name = _ensure_material(model, component.get("material", {}))
    section_name = _ascii("SEC_" + part_name)
    if section_name not in model.sections:
        model.HomogeneousSolidSection(name=section_name, material=material_name)
    region = regionToolset.Region(cells=part.cells[:])
    part.SectionAssignment(region=region, sectionName=section_name)
    if protected_replace:
        _delete_existing_part(model, final_part_name)
        model.parts.changeKey(fromName=part_name, toName=final_part_name)
        part = model.parts[final_part_name]
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
                created.append(_ascii(component["part_name"]))
                _print_geometry_summary(component)
            elif policy == "SOLID":
                part = _create_solid_part(model, component)
                created.append(_ascii(component["part_name"]))
                _print_geometry_summary(component)
            else:
                failed.append((_ascii(component.get("part_name")), "unsupported policy: " + str(policy)))
        except Exception as exc:
            temporary_name = _ascii("TMP_" + component.get("part_name", ""))
            _delete_existing_part(model, temporary_name)
            failed.append((_ascii(component.get("part_name")), str(exc)))
            continue
        try:
            _mesh_part(part, component)
        except Exception as exc:
            print("  MESH WARNING %s  %s" % (_ascii(component.get("part_name")), str(exc)))

    print("Created %d parts in model %s." % (len(created), MODEL_NAME))
    for name in created:
        print("  OK  " + name)
    if failed:
        print("Failed %d parts:" % len(failed))
        for name, message in failed:
            print("  FAIL  %s  %s" % (name, message))

    return created, failed


create_parts()
'''


ASCII_COMPONENT_FIELDS = {
    "part_name",
    "component_code",
    "length_m",
    "quantity",
    "material",
    "model_units",
    "model_policy",
    "element_type",
    "section_kind",
    "section_params_m",
    "thickness_m",
    "section_code",
    "auxiliary_part",
    "source_component_code",
    "length_source",
    "geometry_summary",
    "validation_warnings",
}


def _ascii_component(component: dict) -> dict:
    return {key: component.get(key) for key in sorted(ASCII_COMPONENT_FIELDS)}


def generate_cae_runner(
    json_path: str | Path,
    output_path: str | Path,
    model_name: str | None = None,
    save_as_path: str | Path | None = None,
) -> Path:
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    components = [_ascii_component(component) for component in payload.get("components", [])]
    embedded = json.dumps({"components": components}, ensure_ascii=True, indent=2, sort_keys=True)
    script = CAE_TEMPLATE.replace("__COMPONENTS_JSON__", embedded)
    script = script.replace("__MODEL_NAME__", model_name or "PV_SUPPORT_PARTS")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(script, encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="生成可直接在 Abaqus/CAE 中运行的独立建模脚本。")
    parser.add_argument("--json", required=True, help="Abaqus 输入 JSON。")
    parser.add_argument("--out", required=True, help="输出 CAE 独立脚本路径。")
    args = parser.parse_args()

    output = generate_cae_runner(args.json, args.out)
    print(f"已生成 CAE 独立脚本: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
