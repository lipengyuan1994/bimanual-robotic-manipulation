import xml.etree.ElementTree as ET

import pytest

from bimanual.dinner_teacher import ASSETS
from bimanual.visual_variants import visual_variant


def test_variant_changes_only_declared_visual_attributes():
    xml = (ASSETS.with_name("dinner_teacher_v2") / "scene.xml").read_text()
    variant, report = visual_variant(xml, seed=42)
    assert visual_variant(xml, seed=42) == (variant, report)
    assert visual_variant(xml, seed=43)[0] != variant
    original, changed = ET.fromstring(xml), ET.fromstring(variant)
    for tree in (original, changed):
        light = tree.find("worldbody/light")
        for key in ("ambient", "diffuse"):
            light.attrib.pop(key, None)
        for name in ("floor", "workbench"):
            tree.find(f"worldbody/geom[@name='{name}']").attrib.pop("rgba", None)
    assert ET.tostring(original) == ET.tostring(changed)
    assert report["physical_layout_varied"] is False
    assert report["base_xml_sha256"] != report["variant_xml_sha256"]


@pytest.mark.parametrize("seed", [True, -1, 2**32, 1.5])
def test_invalid_seed_rejected(seed):
    with pytest.raises(ValueError):
        visual_variant("<mujoco/>", seed=seed)


def test_incompatible_scene_rejected():
    with pytest.raises(ValueError):
        visual_variant("<mujoco><worldbody/></mujoco>", seed=0)


def test_teacher_variant_binds_scene_without_changing_packaged_assets(tmp_path):
    from bimanual.dinner_teacher import load_plan, prepare_teacher_assets
    from bimanual.evidence import digest_file

    base = ASSETS.with_name("dinner_teacher_v2")
    original, plan, _ = load_plan(base)
    destination = tmp_path / "assets"
    generated, variant_plan, layout = prepare_teacher_assets(base, destination, 7)
    assert variant_plan == plan
    assert generated["files"]["plan.json.gz"] == original["files"]["plan.json.gz"]
    assert generated["files"]["scene.xml"] != original["files"]["scene.xml"]
    assert layout["scene_sha256"] == digest_file(destination / "scene.xml")
    assert (destination / "visual-variant.json").is_file()
    assert load_plan(base)[0] == original


def test_nominal_asset_preparation_preserves_bytes(tmp_path):
    from bimanual.dinner_teacher import prepare_teacher_assets

    destination = tmp_path / "assets"
    prepare_teacher_assets(ASSETS, destination, None)
    for name in ("scene.xml", "layout.json", "manifest.json", "plan.json.gz"):
        assert (ASSETS / name).read_bytes() == (destination / name).read_bytes()
