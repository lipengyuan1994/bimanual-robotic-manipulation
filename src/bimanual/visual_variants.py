"""Deterministic pre-episode visual variants, without physical scene changes."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

PROFILE = "dinner_visual_variants_v1"


def visual_variant(xml: str, *, seed: int) -> tuple[str, dict]:
    """Change only world lighting and floor/workbench colors before model loading.

    Seeds identify visual conditions, not independent physical layouts. This does
    not generate teacher actions, relabel datasets, or certify a successful task.
    """
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("Visual seed must be an unsigned 32-bit integer")
    root = ET.fromstring(xml)
    world = root.find("worldbody")
    if world is None:
        raise ValueError("Missing world body")
    lights = world.findall("light")
    floors = world.findall("geom[@name='floor']")
    benches = world.findall("geom[@name='workbench']")
    if len(lights) != 1 or len(floors) != 1 or len(benches) != 1:
        raise ValueError("Expected one world light, floor and workbench")

    def sample(label, lower, upper):
        raw = hashlib.sha256(f"{PROFILE}:{seed}:{label}".encode()).digest()
        unit = int.from_bytes(raw[:8], "big") / (2**64 - 1)
        return round(lower + unit * (upper - lower), 6)

    values = {
        "light_diffuse": [sample("diffuse", 0.65, 0.9)] * 3,
        "light_ambient": [sample("ambient", 0.15, 0.35)] * 3,
        "floor_rgba": [sample(f"floor_{i}", 0.12, 0.35) for i in range(3)] + [1.0],
        "workbench_rgba": [sample(f"bench_{i}", 0.25, 0.6) for i in range(3)] + [1.0],
    }
    for node, attribute, key in (
        (lights[0], "diffuse", "light_diffuse"),
        (lights[0], "ambient", "light_ambient"),
        (floors[0], "rgba", "floor_rgba"),
        (benches[0], "rgba", "workbench_rgba"),
    ):
        node.set(attribute, " ".join(str(value) for value in values[key]))
    result = ET.tostring(root, encoding="unicode")
    return result, {
        "profile": PROFILE,
        "seed": seed,
        "base_xml_sha256": hashlib.sha256(xml.encode()).hexdigest(),
        "variant_xml_sha256": hashlib.sha256(result.encode()).hexdigest(),
        "parameters": values,
        "scope": "visual_only_before_episode",
        "physical_layout_varied": False,
    }
