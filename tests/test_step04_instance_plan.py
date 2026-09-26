from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from cadtocae.assembly_script import build_assembly_summary, export_assembly_summary, infer_project_prefix_from_coordinate_workbook
from cadtocae.main_frame_assembly import build_abaqus_script, build_payload, detect_structure_type, project_id_from_path


PROJECT_ID = "SP_DC_ANG17_11042110101187S-T0201"


def _component(code: str, length: float | None = 1.0, kind: str = "PIPE") -> dict:
    params = {"od_m": 0.1, "t_m": 0.002}
    if kind == "C_CHANNEL":
        params = {"h_m": 0.08, "b_m": 0.04, "lip_m": 0.015, "t_m": 0.002}
    elif kind == "ANGLE":
        params = {"leg_a_m": 0.09, "leg_b_m": 0.056, "t_m": 0.005}
    elif kind == "HOOP_BAND":
        params = {"width_m": 0.08, "diameter_m": 0.3, "t_m": 0.006}
    return {
        "component_code": code,
        "part_name": "P_SP_DC_ANG17_%s" % code,
        "length_m": length,
        "section_kind": kind,
        "section_params_m": params,
    }


def _build_dc_inputs(folder: Path, include_purlins: bool = True, hoop_codes: tuple[str, ...] = ("HOOP_1", "HOOP_2")) -> tuple[Path, Path]:
    workbook_path = folder / (PROJECT_ID + "_coordinate.xlsx")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "关键控制点输出"
    sheet.append(["theta_deg", "斜梁倾角", 17.0])
    sheet.append([])
    sheet.append(["点名", "X_m", "Y_m", "Z_m", "状态"])
    points = {
        "O": (0.0, 0.0, 0.0),
        "L_TOP": (0.0, 0.0, 2.0),
        "F": (0.0, 0.0, 2.474),
        "G": (-2.096220025, 0.0, 1.833121223),
        "UF0": (-0.215, 0.0, 1.2),
        "UF1": (-0.215, 0.0, 2.408),
        "UR0": (0.215, 0.0, 1.2),
        "UR1": (0.215, 0.0, 2.539),
        "B": (-0.29, 0.0, 1.2),
        "C": (-1.76151336, 0.0, 1.93545132),
        "D": (0.29, 0.0, 1.2),
        "E": (1.76151336, 0.0, 3.01254868),
        "H1": (0.0, 0.0, 1.2),
        "H2": (0.0, 0.0, 1.6),
        "H3": (0.0, 0.0, 1.8),
    }
    if include_purlins:
        points.update({
            "P1": (-1.95, 0.0, 1.88),
            "P2": (-0.42, 0.0, 2.34),
            "P3": (0.42, 0.0, 2.60),
            "P4": (1.95, 0.0, 3.07),
        })
    for name, point in points.items():
        sheet.append([name, point[0], point[1], point[2], "已确认"])
    workbook.save(workbook_path)

    components = [
        _component("COLUMN_DOWN", 2.0),
        _component("COLUMN_FRONT", 1.208, "C_CHANNEL"),
        _component("COLUMN_REAR", 1.339, "C_CHANNEL"),
        _component("BRACE_FRONT", 1.649, "C_CHANNEL"),
        _component("BRACE_REAR", 2.325, "C_CHANNEL"),
        _component("INCLINED_BEAM", 4.385, "C_CHANNEL"),
        *[_component(code, None, "HOOP_BAND") for code in hoop_codes],
        _component("PURLIN_SUPPORT", 0.05, "ANGLE"),
        _component("PURLIN_LOCAL", 0.05, "C_CHANNEL"),
    ]
    components_path = folder / "components.json"
    components_path.write_text(json.dumps({"components": components}), encoding="utf-8")
    return workbook_path, components_path


class Step04InstancePlanTest(unittest.TestCase):
    def test_sp_dc_numbered_hoops_map_to_matching_control_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbook, components = _build_dc_inputs(
                Path(tmp), hoop_codes=("HOOP_ASSEMBLY_1", "HOOP_ASSEMBLY_2", "HOOP_ASSEMBLY_3")
            )
            payload = build_payload(workbook, components, project_code=PROJECT_ID, model_name=PROJECT_ID)

        hoops = [item for item in payload["instance_plan"] if item.get("canonical_role") == "HOOP"]
        self.assertEqual(len(hoops), 6)
        for index in range(1, 4):
            pair = [item for item in hoops if item["hoop_group_id"] == "HOOP_%02d" % index]
            self.assertEqual(len(pair), 2)
            self.assertTrue(all(item["component_code"] == "HOOP_ASSEMBLY_%d" % index for item in pair))
            self.assertTrue(all(item["part_name"] == "P_SP_DC_ANG17_HOOP_ASSEMBLY_%d" % index for item in pair))
            self.assertTrue(all(item["origin"] == payload["points"]["H%d" % index]["coords"] for item in pair))

    def test_sp_dc_generic_hoop_is_reused_for_all_control_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbook, components = _build_dc_inputs(Path(tmp), hoop_codes=("HOOP",))
            payload = build_payload(workbook, components, project_code=PROJECT_ID, model_name=PROJECT_ID)

        hoops = [item for item in payload["instance_plan"] if item.get("canonical_role") == "HOOP"]
        self.assertEqual(len(hoops), 6)
        self.assertTrue(all(item["component_code"] == "HOOP" for item in hoops))
        self.assertTrue(all(item["part_name"] == "P_SP_DC_ANG17_HOOP" for item in hoops))

    def test_numbered_hoop_does_not_fall_back_to_another_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbook, components = _build_dc_inputs(Path(tmp), hoop_codes=("HOOP_ASSEMBLY_2",))
            payload = build_payload(workbook, components, project_code=PROJECT_ID, model_name=PROJECT_ID)

        hoops = [item for item in payload["instance_plan"] if item.get("canonical_role") == "HOOP"]
        self.assertEqual([item["instance_id"] for item in hoops], ["HOOP_02_A", "HOOP_02_B"])
        self.assertTrue(all(item["origin"] == payload["points"]["H2"]["coords"] for item in hoops))

    def test_full_project_id_and_structure_detection(self):
        coordinate = Path(PROJECT_ID + "_coordinate.xlsx")
        self.assertEqual(project_id_from_path(coordinate), PROJECT_ID)
        self.assertEqual(infer_project_prefix_from_coordinate_workbook(coordinate), PROJECT_ID)
        self.assertEqual(detect_structure_type(PROJECT_ID), "SP_DC")
        self.assertEqual(detect_structure_type("SP_SC_ANG18_11042210101041S-T0202"), "SP_SC")

    def test_sp_dc_adapter_builds_unified_unique_instance_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbook, components = _build_dc_inputs(Path(tmp))
            payload = build_payload(workbook, components, project_code=PROJECT_ID, model_name=PROJECT_ID)

        self.assertEqual(payload["meta"]["structure_type"], "SP_DC")
        self.assertEqual(payload["meta"]["project_id"], PROJECT_ID)
        plan = payload["instance_plan"]
        ids = [item["instance_id"] for item in plan]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all("-" not in item for item in ids))
        self.assertEqual(len([item for item in plan if item["component_code"] == "PURLIN_SUPPORT"]), 4)
        self.assertEqual(len([item for item in plan if item["component_code"] == "PURLIN_LOCAL"]), 4)
        self.assertEqual(len(payload["purlin_nodes"]), 4)
        for index, node in enumerate(payload["purlin_nodes"], start=1):
            support = next(item for item in plan if item["instance_id"] == "PURLIN_SUPPORT_%02d" % index)
            local_purlin = next(item for item in plan if item["instance_id"] == "PURLIN_LOCAL_%02d" % index)
            self.assertEqual(support["global_anchor"], node["support_anchor_xyz"])
            self.assertEqual(support["local_anchor"], [0.0, 0.0, 0.025])
            self.assertEqual(local_purlin["component_code"], "PURLIN_LOCAL")
            self.assertEqual(local_purlin["part_name"], "P_SP_DC_ANG17_PURLIN_LOCAL")
            self.assertEqual(local_purlin["local_anchor"], [0.0, 0.0, 0.025])
            self.assertAlmostEqual(node["beam_to_purlin_gap_m"], 0.010)
            self.assertAlmostEqual(node["purlin_shell_midplane_offset_m"], 0.011)
            self.assertAlmostEqual(node["beam_surface_offset_m"], 0.041)
            self.assertAlmostEqual(node["beam_section_center_offset_m"], 0.020)
            self.assertAlmostEqual(node["y_offset_support_m"], 0.020)
            self.assertAlmostEqual(node["y_offset_local_m"], 0.020)
            self.assertAlmostEqual(node["alignment_error_m"], 0.0)
            self.assertEqual(node["web_contact_side"], "outer")
        hoops = [item for item in plan if item["component_code"] == "HOOP"]
        self.assertEqual(len(hoops), 6)
        self.assertEqual(len(payload["hoop_groups"]), 3)
        for group_index in range(1, 4):
            pair = [item for item in hoops if item["hoop_group_id"] == "HOOP_%02d" % group_index]
            self.assertEqual(len(pair), 2)
            self.assertEqual(pair[1]["post_rotation"]["axis_point"], pair[1]["origin"])
            self.assertEqual(pair[1]["post_rotation"]["axis_direction"], [0.0, 0.0, 1.0])
            self.assertEqual(pair[1]["post_rotation"]["angle_deg"], 180.0)
        skeleton_ids = [item["instance_id"] for item in plan if item["component_code"] not in {"HOOP", "PURLIN_SUPPORT", "PURLIN_LOCAL"}]
        self.assertEqual(
            skeleton_ids,
            ["COLUMN_DOWN_01", "COLUMN_FRONT_01", "COLUMN_REAR_01", "BRACE_FRONT_01", "BRACE_REAR_01", "INCLINED_BEAM_01"],
        )
        front = next(item for item in plan if item["component_code"] == "COLUMN_FRONT")
        self.assertEqual(front["placement_mode"], "LINE")
        self.assertEqual(front["start_point"], [-0.215, 0.0, 1.2])
        self.assertEqual(front["end_point"], [-0.215, 0.0, 2.408])
        self.assertNotIn("scale", json.dumps(payload).lower())

    def test_optional_purlin_placement_data_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbook, components = _build_dc_inputs(Path(tmp), include_purlins=False)
            payload = build_payload(workbook, components, project_code=PROJECT_ID, model_name=PROJECT_ID)

        skipped = {(item["component_code"], item["reason"]) for item in payload["skipped_instances"]}
        self.assertIn(("PURLIN_SUPPORT", "PLACEMENT_DATA_MISSING"), skipped)
        self.assertIn(("PURLIN_LOCAL", "PLACEMENT_DATA_MISSING"), skipped)
        self.assertTrue(any(item["component_code"] == "INCLINED_BEAM" for item in payload["instance_plan"]))

    def test_generated_script_uses_generic_instance_plan_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbook, components = _build_dc_inputs(Path(tmp))
            payload = build_payload(workbook, components, project_code=PROJECT_ID, model_name=PROJECT_ID)
            script = build_abaqus_script("full_main_frame", payload, Path("report.json"), Path("unused.cae"))

        self.assertIn('"instance_plan"', script)
        self.assertIn('data.get("instance_plan") or data.get("members", [])', script)
        self.assertIn("PURLIN NODE %s", script)
        self.assertIn("gap = 0.010 m", script)
        self.assertNotIn("assembly.scale", script.lower())

    def test_sp_dc_summary_records_hoop_and_purlin_connection_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbook, components = _build_dc_inputs(Path(tmp))
            payload = build_payload(workbook, components, project_code=PROJECT_ID, model_name=PROJECT_ID)
            summary = build_assembly_summary(payload)
            output = export_assembly_summary(payload, Path(tmp) / (PROJECT_ID + "_assembly_summary.json"))
            with output.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)

        self.assertEqual(loaded["project_id"], PROJECT_ID)
        self.assertEqual(len(loaded["instances"]), len(payload["instance_plan"]))
        self.assertEqual(len(loaded["instances"]), len(summary["instances"]))
        groups = {item["instance_name"]: item["connection_group"] for item in loaded["instances"]}
        self.assertEqual(groups["PURLIN_SUPPORT_01"], "P01")
        self.assertEqual(groups["PURLIN_LOCAL_01"], "P01")
        self.assertEqual(groups["HOOP_01_A"], "HOOP_01")
        self.assertEqual(groups["HOOP_01_B"], "HOOP_01")
        hoop_b = next(item for item in loaded["instances"] if item["instance_name"] == "HOOP_01_B")
        self.assertEqual(hoop_b["placement"]["rotation_steps"][-1]["angle_deg"], 180.0)
        self.assertIn("H1", loaded["assembly_points"])


if __name__ == "__main__":
    unittest.main()
