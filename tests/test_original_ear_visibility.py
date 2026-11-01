import re
import unittest
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1] / "Packages/jp.suu.milfy-eat-ear/Runtime"
ANIMATION = RUNTIME / "Animation"


def documents(path):
    text = path.read_text(encoding="utf-8")
    return {
        int(match.group(1)): match.group(2)
        for match in re.finditer(r"^--- !u!\d+ &(-?\d+)\n(.*?)(?=^--- !u!|\Z)", text, re.M | re.S)
    }


def guid(path):
    return re.search(r"^guid: ([0-9a-f]{32})$", path.with_name(path.name + ".meta").read_text(), re.M).group(1)


class OriginalEarVisibilityTests(unittest.TestCase):
    def test_merge_targets_avatar_root_and_leaves_eatear_relative(self):
        prefab = documents(RUNTIME / "Milfy_EatEar.prefab")
        controller_guid = guid(ANIMATION / "OriginalEarVisibility.controller")
        original_merge = next(text for text in prefab.values() if controller_guid in text)
        existing_merge = next(text for text in prefab.values() if "491d9a42c8e563741a1f8c2e7107968f" in text)
        self.assertRegex(original_merge, r"(?m)^  pathMode: 1$")
        self.assertRegex(existing_merge, r"(?m)^  pathMode: 0$")
        self.assertIn("referencePath: Milfy_EatEar", existing_merge)

    def test_both_sides_toggle_scale_and_position_using_existing_visibility_parameter(self):
        controller = documents(ANIMATION / "OriginalEarVisibility.controller")
        for side in ("L", "R"):
            with self.subTest(side=side):
                path = f"Armature/Hips/Spine/Chest/Neck/Head/Ear_Root/Ear.{side}"
                states = {}
                for state_name, clip_name, value in (
                    ("ShowOriginalEar", f"OriginalEar_{side}_Shown.anim", 1),
                    ("HideOriginalEar", f"OriginalEar_{side}_Hidden.anim", 0),
                ):
                    clip = (ANIMATION / clip_name).read_text(encoding="utf-8")
                    self.assertIn(f"    path: {path}\n", clip)
                    scale = clip.split("  m_ScaleCurves:\n", 1)[1].split("  m_FloatCurves:", 1)[0]
                    self.assertEqual(re.findall(r"value: \{x: ([01]), y: \1, z: \1\}", scale), [str(value), str(value)])
                    states[state_name] = next((id_, doc) for id_, doc in controller.items() if f"guid: {guid(ANIMATION / clip_name)}" in doc)
                    self.assertIn(f"  m_Name: {state_name}\n", states[state_name][1])
                hidden = (ANIMATION / f"OriginalEar_{side}_Hidden.anim").read_text(encoding="utf-8")
                shown = (ANIMATION / f"OriginalEar_{side}_Shown.anim").read_text(encoding="utf-8")
                old_shown = (ANIMATION / ("DisableLeftEatEar.anim" if side == "L" else "DisableRightEatEar.anim")).read_text(encoding="utf-8")
                def positions(clip):
                    curve = clip.split("  m_PositionCurves:\n", 1)[1].split("  m_ScaleCurves:", 1)[0]
                    self.assertIn(f"    path: {path}\n", curve)
                    return re.findall(r"value: \{x: ([^,]+), y: ([^,]+), z: ([^}]+)\}", curve)
                self.assertEqual(positions(hidden), [("0", "0.15", "0")] * 2)
                self.assertEqual(positions(shown), positions(old_shown))
                for source, destination, condition in (("ShowOriginalEar", "HideOriginalEar", 1), ("HideOriginalEar", "ShowOriginalEar", 2)):
                    transition_id = int(re.search(r"m_Transitions:\n  - \{fileID: (-?\d+)\}", states[source][1]).group(1))
                    transition = controller[transition_id]
                    self.assertIn(f"m_ConditionMode: {condition}\n    m_ConditionEvent: EatEar_{side}_Visible", transition)
                    self.assertIn(f"m_DstState: {{fileID: {states[destination][0]}}}", transition)
                    self.assertIn("m_HasExitTime: 0", transition)


if __name__ == "__main__":
    unittest.main()
