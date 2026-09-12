from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from bimanual.dinner_teacher import ASSETS
from bimanual.dual_arm import DualArm
from bimanual.scene_variants import FAMILIES, dinner_scene_variant


def _attributes(xml: str):
    root = ET.fromstring(xml)
    result = {}

    def visit(node, path):
        result[path] = dict(node.attrib)
        for index, child in enumerate(node):
            visit(child, (*path, f"{child.tag}[{index}]"))

    visit(root, (root.tag,))
    return result


def _differences(before: str, after: str):
    first, second = _attributes(before), _attributes(after)
    assert first.keys() == second.keys()
    return [
        (path, attribute, left.get(attribute), right.get(attribute))
        for path in first
        for attribute in left_right_keys(first[path], second[path])
        if (left := first[path]).get(attribute) != (right := second[path]).get(attribute)
    ]


def left_right_keys(left, right):
    return sorted(set(left) | set(right))


@pytest.mark.parametrize("family", FAMILIES)
def test_each_family_is_deterministic_bounded_and_loadable(family):
    xml = (ASSETS.with_name("dinner_teacher_v2") / "scene.xml").read_text()
    variant, report = dinner_scene_variant(xml, seed=101, family=family)
    assert dinner_scene_variant(xml, seed=101, family=family) == (variant, report)
    assert dinner_scene_variant(xml, seed=102, family=family)[0] != variant
    assert report["families"] == [family]
    assert report["evaluation_success"] is None
    assert len(report["changes"]) == len(_differences(xml, variant))
    assert DualArm(xml=variant, physics_hz=1000).model.nq > 0


def test_family_changes_only_its_declared_attributes():
    xml = (ASSETS.with_name("dinner_teacher_v2") / "scene.xml").read_text()
    allowed = {
        "placement": {("body", "pos")},
        "mass": {("geom", "mass")},
        "friction": {("geom", "friction")},
        "shape": {("geom", "size"), ("geom", "pos"), ("geom", "fromto")},
        "lighting": {("light", "diffuse"), ("light", "ambient")},
        "background": {("geom", "rgba")},
    }
    for family in FAMILIES:
        _, report = dinner_scene_variant(xml, seed=103, family=family)
        observed = {(change["element"], change["attribute"]) for change in report["changes"]}
        assert observed <= allowed[family]
        if family == "background":
            assert {change["name"] for change in report["changes"]} == {
                "floor",
                "workbench",
            }
        elif family in {"placement", "mass", "friction", "shape"}:
            names = {change["name"] for change in report["changes"]}
            assert not names & {"floor", "workbench"}


def test_combined_variant_declares_all_six_families_and_both_scopes():
    xml = (ASSETS.with_name("dinner_teacher_v2") / "scene.xml").read_text()
    variant, report = dinner_scene_variant(xml, seed=104, family="combined")
    assert report["families"] == list(FAMILIES)
    assert report["physical_layout_varied"] is True
    assert report["visual_conditions_varied"] is True
    assert report["variant_xml_sha256"] != report["base_xml_sha256"]
    assert DualArm(xml=variant, physics_hz=1000).model.nq > 0


@pytest.mark.parametrize("seed", [True, -1, 2**32, 1.5])
def test_invalid_seed_rejected(seed):
    with pytest.raises(ValueError):
        dinner_scene_variant("<mujoco/>", seed=seed, family="placement")


def test_incompatible_scene_and_family_rejected():
    with pytest.raises(ValueError):
        dinner_scene_variant("<mujoco><worldbody/></mujoco>", seed=0, family="placement")
    with pytest.raises(ValueError):
        dinner_scene_variant("<mujoco/>", seed=0, family="unknown")
