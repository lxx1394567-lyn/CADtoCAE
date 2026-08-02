import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _load_abaqus_script():
    spec = importlib.util.spec_from_file_location("abaqus_build_parts", ROOT / "scripts" / "abaqus_build_parts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AbaqusGeometryTest(unittest.TestCase):
    def test_c_channel_profile_is_open_lipped_centerline(self):
        module = _load_abaqus_script()
        component = {
            "section_kind": "C_CHANNEL",
            "section_params_m": {"h_m": 0.075, "b_m": 0.04, "lip_m": 0.015, "t_m": 0.002},
        }
        self.assertEqual(
            module._profile_points(component),
            [(0.04, 0.015), (0.04, 0.0), (0.0, 0.0), (0.0, 0.075), (0.04, 0.075), (0.04, 0.06)],
        )


if __name__ == "__main__":
    unittest.main()
