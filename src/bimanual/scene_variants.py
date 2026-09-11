"""Deterministic dinner-scene perturbations applied only before model loading."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from typing import Literal

Family = Literal["placement", "mass", "friction", "shape", "lighting", "background", "combined"]
PHYSICAL_FAMILIES = ("placement", "mass", "friction", "shape")
VISUAL_FAMILIES = ("lighting", "background")
FAMILIES = (*PHYSICAL_FAMILIES, *VISUAL_FAMILIES)
OBJECTS = ("practice_object", "cup", "plate", "spoon", "fork")
PROFILE = "dinner_scene_variants_v1"


def _sample(seed: int, family: str, label: str, lower: float, upper: float) -> float:
    raw = hashlib.sha256(f"{PROFILE}:{seed}:{family}:{label}".encode()).digest()
    unit = int.from_bytes(raw[:8], "big") / (2**64 - 1)
    return lower + unit * (upper - lower)


def _numbers(value: str) -> list[float]:
    return [float(item) for item in value.split()]


def _text(values: list[float]) -> str:
    return " ".join(f"{value:.9g}" for value in values)


def _set(node, attribute: str, values: list[float], changes: list[dict]) -> None:
    before = node.get(attribute)
    after = _text(values)
    if before == after:
        raise ValueError("Perturbation did not change its target attribute")
    node.set(attribute, after)
    changes.append(
        {
            "element": node.tag,
            "name": node.get("name"),
            "attribute": attribute,
            "before": before,
            "after": after,
        }
    )


def _body(root, name: str):
    matches = root.findall(f".//body[@name='{name}']")
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one dinner object body: {name}")
    return matches[0]


def _placement(root, seed: int, changes: list[dict], parameters: dict) -> None:
    bounds = {
        "practice_object": 0.006,
        "cup": 0.006,
        "plate": 0.006,
        "spoon": 0.0015,
        "fork": 0.0015,
    }
    offsets = {}
    for name, bound in bounds.items():
        body = _body(root, name)
        pos = _numbers(body.get("pos", ""))
        if len(pos) != 3:
            raise ValueError(f"Dinner object lacks a three-dimensional position: {name}")
        dx = _sample(seed, "placement", f"{name}:x", -bound, bound)
        dy = _sample(seed, "placement", f"{name}:y", -bound, bound)
        _set(body, "pos", [pos[0] + dx, pos[1] + dy, pos[2]], changes)
        offsets[name] = [round(dx, 9), round(dy, 9), 0.0]
    parameters["placement_offset_m"] = offsets


def _mass(root, seed: int, changes: list[dict], parameters: dict) -> None:
    scales = {}
    for name in OBJECTS:
        body = _body(root, name)
        scale = _sample(seed, "mass", name, 0.85, 1.15)
        geoms = body.findall(".//geom[@mass]")
        if not geoms:
            raise ValueError(f"Dinner object has no explicit geom mass: {name}")
        for geom in geoms:
            mass = _numbers(geom.get("mass", ""))
            if len(mass) != 1 or mass[0] <= 0:
                raise ValueError(f"Invalid explicit mass for {geom.get('name')}")
            _set(geom, "mass", [mass[0] * scale], changes)
        scales[name] = round(scale, 9)
    parameters["mass_scale"] = scales


def _friction(root, seed: int, changes: list[dict], parameters: dict) -> None:
    scales = {}
    for name in OBJECTS:
        body = _body(root, name)
        scale = _sample(seed, "friction", name, 0.8, 1.2)
        geoms = body.findall(".//geom[@friction]")
        if not geoms:
            raise ValueError(f"Dinner object has no explicit contact friction: {name}")
        for geom in geoms:
            friction = _numbers(geom.get("friction", ""))
            if len(friction) != 3 or friction[0] <= 0:
                raise ValueError(f"Invalid explicit friction for {geom.get('name')}")
            _set(geom, "friction", [friction[0] * scale, *friction[1:]], changes)
        scales[name] = round(scale, 9)
    parameters["sliding_friction_scale"] = scales


def _scale_horizontal_geom(geom, scale: float, changes: list[dict]) -> None:
    kind = geom.get("type", "sphere")
    size = _numbers(geom.get("size", ""))
    if not size:
        raise ValueError(f"Shape perturbation requires explicit geom size: {geom.get('name')}")
    if kind in {"box", "ellipsoid"}:
        count = min(2, len(size))
    elif kind in {"cylinder", "capsule", "sphere"}:
        count = 1
    else:
        raise ValueError(f"Unsupported dinner shape geom type: {kind}")
    size[:count] = [value * scale for value in size[:count]]
    _set(geom, "size", size, changes)
    if geom.get("pos") is not None:
        pos = _numbers(geom.get("pos", ""))
        if len(pos) != 3:
            raise ValueError(f"Invalid local geom position: {geom.get('name')}")
        _set(geom, "pos", [pos[0] * scale, pos[1] * scale, pos[2]], changes)
    if geom.get("fromto") is not None:
        points = _numbers(geom.get("fromto", ""))
        if len(points) != 6:
            raise ValueError(f"Invalid capsule endpoints: {geom.get('name')}")
        _set(
            geom,
            "fromto",
            [
                points[0] * scale,
                points[1] * scale,
                points[2],
                points[3] * scale,
                points[4] * scale,
                points[5],
            ],
            changes,
        )


def _shape(root, seed: int, changes: list[dict], parameters: dict) -> None:
    scales = {}
    for name in OBJECTS:
        body = _body(root, name)
        scale = _sample(seed, "shape", name, 0.94, 1.06)
        geoms = body.findall(".//geom")
        if not geoms:
            raise ValueError(f"Dinner object has no geometry: {name}")
        for geom in geoms:
            _scale_horizontal_geom(geom, scale, changes)
        scales[name] = round(scale, 9)
    parameters["horizontal_shape_scale"] = scales


def _lighting(root, seed: int, changes: list[dict], parameters: dict) -> None:
    lights = root.findall("worldbody/light")
    if len(lights) != 1:
        raise ValueError("Expected exactly one world light")
    diffuse = [_sample(seed, "lighting", "diffuse", 0.65, 0.9)] * 3
    ambient = [_sample(seed, "lighting", "ambient", 0.15, 0.35)] * 3
    _set(lights[0], "diffuse", diffuse, changes)
    _set(lights[0], "ambient", ambient, changes)
    parameters["light_diffuse"] = [round(value, 9) for value in diffuse]
    parameters["light_ambient"] = [round(value, 9) for value in ambient]


def _background(root, seed: int, changes: list[dict], parameters: dict) -> None:
    values = {}
    for name, lower, upper in (("floor", 0.12, 0.35), ("workbench", 0.25, 0.6)):
        matches = root.findall(f"worldbody/geom[@name='{name}']")
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one background geom: {name}")
        rgba = [_sample(seed, "background", f"{name}:{i}", lower, upper) for i in range(3)]
        rgba.append(1.0)
        _set(matches[0], "rgba", rgba, changes)
        values[f"{name}_rgba"] = [round(value, 9) for value in rgba]
    parameters.update(values)


_APPLIERS = {
    "placement": _placement,
    "mass": _mass,
    "friction": _friction,
    "shape": _shape,
    "lighting": _lighting,
    "background": _background,
}


def dinner_scene_variant(xml: str, *, seed: int, family: Family) -> tuple[str, dict]:
    """Generate one bounded variant without actions, labels, or evaluation claims."""
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("Scene variant seed must be an unsigned 32-bit integer")
    if family not in (*FAMILIES, "combined"):
        raise ValueError("Unsupported dinner scene perturbation family")
    root = ET.fromstring(xml)
    selected = FAMILIES if family == "combined" else (family,)
    changes: list[dict] = []
    parameters = {}
    for name in selected:
        _APPLIERS[name](root, seed, changes, parameters)
    result = ET.tostring(root, encoding="unicode")
    if not changes or result == xml:
        raise ValueError("Scene perturbation produced no change")
    return result, {
        "schema_version": 1,
        "profile": PROFILE,
        "seed": seed,
        "requested_family": family,
        "families": list(selected),
        "base_xml_sha256": hashlib.sha256(xml.encode()).hexdigest(),
        "variant_xml_sha256": hashlib.sha256(result.encode()).hexdigest(),
        "parameters": parameters,
        "changes": changes,
        "scope": "pre_episode_scene_generation_only",
        "physical_layout_varied": any(name in PHYSICAL_FAMILIES for name in selected),
        "visual_conditions_varied": any(name in VISUAL_FAMILIES for name in selected),
        "evaluation_success": None,
    }
