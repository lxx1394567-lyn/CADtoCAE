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
import math
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
        from abaqusConstants import C3D8R, CLOCKWISE, COPLANAR_EDGES, COUNTERCLOCKWISE, DEFORMABLE_BODY, OFF, RIGHT, S4R, SIDE1, STANDARD, SUPERIMPOSE, THREE_D, UNIFORM
        import mesh
        import regionToolset
    except Exception as exc:
        raise RuntimeError("Abaqus Python modules are unavailable. Use --dry-run outside Abaqus: %s" % exc)
    return {
        "mdb": mdb,
        "C3D8R": C3D8R,
        "CLOCKWISE": CLOCKWISE,
        "COPLANAR_EDGES": COPLANAR_EDGES,
        "COUNTERCLOCKWISE": COUNTERCLOCKWISE,
        "DEFORMABLE_BODY": DEFORMABLE_BODY,
        "OFF": OFF,
        "RIGHT": RIGHT,
        "SIDE1": SIDE1,
        "S4R": S4R,
        "STANDARD": STANDARD,
        "SUPERIMPOSE": SUPERIMPOSE,
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


def _draw_angle_profile(sketch, params):
    a = float(params["leg_a_m"])
    b = float(params["leg_b_m"])
    t = float(params["t_m"])
    radius = float(params.get("inner_root_radius_m", 0.0) or 0.0)
    points = [(0.0, 0.0), (a, 0.0), (a, t), (t, t), (t, b), (0.0, b)]
    lines = [sketch.Line(point1=points[i], point2=points[(i + 1) % len(points)]) for i in range(len(points))]
    if radius > 0.0:
        sketch.FilletByRadius(radius=radius, curve1=lines[2], nearPoint1=(t + radius, t),
                              curve2=lines[3], nearPoint2=(t, t + radius))


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
    return [(0.0, 0.034), (0.015, 0.034), (0.015, 0.011), (0.038, 0.011),
            (0.038, 0.003), (0.046, 0.003), (0.046, 0.0), (0.035, 0.0),
            (0.035, 0.007), (0.012, 0.007), (0.012, 0.030), (0.0, 0.030)]


def _clamp_profile_points(kind):
    if kind == "MID_CLAMP_PROFILE":
        return _mid_clamp_profile_points()
    return _edge_clamp_profile_points()


def _clamp_requires_slots(kind):
    return kind == "EDGE_CLAMP_PROFILE"


def _slot_centers(component):
    params = component.get("section_params_m") or {}
    return (float(params["hole_1_center_m"]), float(params["hole_2_center_m"]))


def _draw_slot(sketch, center_x, center_y, slot_width, slot_length, clockwise):
    radius = slot_width / 2.0
    half_straight = (slot_length - slot_width) / 2.0
    if radius <= 0.0 or half_straight < 0.0:
        raise ValueError("Clamp slot requires slot_length >= slot_width > 0.")
    lower = center_y - half_straight
    upper = center_y + half_straight
    sketch.Line(point1=(center_x - radius, lower), point2=(center_x - radius, upper))
    sketch.ArcByCenterEnds(center=(center_x, upper), point1=(center_x - radius, upper),
                           point2=(center_x + radius, upper), direction=clockwise)
    sketch.Line(point1=(center_x + radius, upper), point2=(center_x + radius, lower))
    sketch.ArcByCenterEnds(center=(center_x, lower), point1=(center_x + radius, lower),
                           point2=(center_x - radius, lower), direction=clockwise)


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


def _cut_clamp_slots(api, model, part, component, top_y):
    params = component.get("section_params_m") or {}
    length = float(params["length_m"])
    kind = component.get("section_kind")
    slot_x = -0.007 if kind == "MID_CLAMP_PROFILE" else 0.008
    print("%s: locating hole sketch plane" % component.get("component_code", kind))
    face, up_edge = _find_clamp_sketch_plane(part, top_y)
    try:
        transform = part.MakeSketchTransform(sketchPlane=face, sketchUpEdge=up_edge,
                                             sketchPlaneSide=api["SIDE1"], origin=(0.0, top_y, 0.0))
    except Exception as exc:
        raise RuntimeError("%s SKETCH_PLANE: %s" % (component.get("component_code", kind), exc))
    sketch_name = _ascii("SK_SLOT_" + component["part_name"])
    cut_sketch = model.ConstrainedSketch(name=sketch_name, sheetSize=0.2, transform=transform)
    print("%s: hole sketch created" % component.get("component_code", kind))
    cut_sketch.setPrimaryObject(option=api["SUPERIMPOSE"])
    part.projectReferencesOntoSketch(sketch=cut_sketch, filter=api["COPLANAR_EDGES"])
    for center in _slot_centers(component):
        _draw_slot(cut_sketch, slot_x, center, float(params["slot_width_m"]),
                   float(params["slot_length_m"]), api["CLOCKWISE"])
    try:
        part.CutExtrude(sketchPlane=face, sketchUpEdge=up_edge, sketchPlaneSide=api["SIDE1"],
                        sketch=cut_sketch, flipExtrudeDirection=api["OFF"])
    except Exception as exc:
        raise RuntimeError("%s CUT: %s" % (component.get("component_code", kind), exc))
    print("%s: hole cut success" % component.get("component_code", kind))
    cut_sketch.unsetPrimaryObject()
    del model.sketches[sketch_name]


def _hoop_band_dimensions(component):
    """RF is the small bend radius, not the functional inner-face radius."""
    params = component.get("section_params_m") or {}
    names = ("diameter_m", "width_m", "t_m", "left_extension_m",
             "right_extension_m", "transition_fillet_m")
    values = [float(params.get(name, 0.0) or 0.0) for name in names]
    if any(math.isnan(value) or math.isinf(value) for value in values):
        raise ValueError("HOOP_BAND dimensions must be finite.")
    diameter, width, thickness, left, right, fillet = values
    if min(diameter, width, thickness, left, right) <= 0.0 or fillet < 0.0:
        raise ValueError("HOOP_BAND requires positive D/W/T/L/R and nonnegative RF.")
    rin = diameter / 2.0
    rout = rin + thickness
    # Reverse bend: the functional inner chain has the LARGER bend radius.
    bend_radius = fillet + thickness
    tangent_x = math.sqrt(rin * (rin + 2.0 * bend_radius))
    left_end = -rout - left
    right_end = rout + right
    tolerance = max(rout, left, right, bend_radius) * 1.0e-10
    if min(-left_end, right_end) - tangent_x <= tolerance:
        raise ValueError("HOOP_BAND RF leaves no straight plate: increase L/R or reduce RF.")
    return {
        "inner_radius_m": rin, "outer_radius_m": rout,
        "width_m": width, "thickness_m": thickness,
        "left_extension_m": left, "right_extension_m": right,
        "transition_fillet_m": fillet,
        "inner_chain_bend_radius_m": bend_radius,
        "outer_chain_bend_radius_m": fillet,
        "bend_center_y_m": bend_radius, "straight_tangent_x_m": tangent_x,
        # Preserve legacy L/R reference: unfilleted outer-circle endpoints.
        "left_end_x_m": left_end, "right_end_x_m": right_end,
        "left_straight_length_m": -left_end - tangent_x,
        "right_straight_length_m": right_end - tangent_x,
    }


def _hoop_band_profile_geometry(component):
    """Explicit tangent chains, both directed left to right; no sketch offset.

    XY profile is convex toward +Y, with mating lines at Y=0 and material
    at +Y. Extrusion is +Z. RF=0 retains the T-radius functional inner bend
    and omits the zero-radius outer bend. RF=T needs no special fallback.
    """
    dims = _hoop_band_dimensions(component)
    r = dims["inner_radius_m"]
    t = dims["thickness_m"]
    f = dims["inner_chain_bend_radius_m"]
    a = dims["straight_tangent_x_m"]
    centers = ((-a, f), (a, f))

    def line(start, end):
        return {"kind": "LINE", "start": start, "end": end}

    def arc(center, start, end, direction):
        return {"kind": "ARC", "center": center, "start": start,
                "end": end, "direction": direction}

    def chain(radius, y, bend_radius):
        scale = radius / (r + f)
        left_tangent = (-a * scale, f * scale)
        right_tangent = (a * scale, f * scale)
        segments = [line((dims["left_end_x_m"], y), (-a, y))]
        if bend_radius > 0.0:
            segments.append(arc(centers[0], (-a, y), left_tangent, "COUNTERCLOCKWISE"))
        segments.append(arc((0.0, 0.0), left_tangent, right_tangent, "CLOCKWISE"))
        if bend_radius > 0.0:
            segments.append(arc(centers[1], right_tangent, (a, y), "COUNTERCLOCKWISE"))
        segments.append(line((a, y), (dims["right_end_x_m"], y)))
        return segments

    inner = chain(r, 0.0, f)
    outer = chain(r + t, t, dims["outer_chain_bend_radius_m"])
    return {"dimensions": dims, "inner": inner, "outer": outer}


def _draw_hoop_band_profile(api, sketch, component):
    profile = _hoop_band_profile_geometry(component)
    for chain in (profile["inner"], profile["outer"]):
        for segment in chain:
            if segment["kind"] == "LINE":
                sketch.Line(point1=segment["start"], point2=segment["end"])
            else:
                sketch.ArcByCenterEnds(center=segment["center"],
                                      point1=segment["start"], point2=segment["end"],
                                      direction=api[segment["direction"]])
    for endpoint, index in (("start", 0), ("end", -1)):
        sketch.Line(point1=profile["inner"][index][endpoint],
                    point2=profile["outer"][index][endpoint])


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
        _draw_hoop_band_profile(api, sketch, component)
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

    part = model.Part(name=part_name, dimensionality=api["THREE_D"], type=api["DEFORMABLE_BODY"])
    try:
        part.BaseSolidExtrude(sketch=sketch, depth=depth)
    except Exception as exc:
        if kind in ("MID_CLAMP_PROFILE", "EDGE_CLAMP_PROFILE"):
            raise RuntimeError("%s EXTRUDE: %s" % (component.get("component_code", kind), exc))
        raise
    if kind in ("MID_CLAMP_PROFILE", "EDGE_CLAMP_PROFILE"):
        print("%s: solid extrude success" % component.get("component_code", kind))
    if _clamp_requires_slots(kind):
        _cut_clamp_slots(api, model, part, component, 0.023 if kind == "MID_CLAMP_PROFILE" else 0.034)

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
                status = "created"
            elif policy == "SOLID":
                part = _create_solid_part(api, model, component)
                status = "created"
            else:
                status = "skipped_manual_template"
            report.append({"part_name": _ascii(component.get("part_name")), "status": status, "issues": []})
        except Exception as exc:
            report.append({"part_name": _ascii(component.get("part_name")), "status": "failed", "issues": [str(exc)]})
            continue
        try:
            _mesh_part(api, part, component)
        except Exception as exc:
            report[-1]["issues"].append("mesh warning: %s" % exc)

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
