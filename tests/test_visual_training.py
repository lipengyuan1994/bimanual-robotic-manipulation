import hashlib
import json
from pathlib import Path

import pytest

from bimanual.evidence import canonical
from bimanual.visual_training import (
    VisualTrainingProtocol,
    create_visual_training_protocol,
    load_visual_training_protocol,
)


def create(path, **kwargs):
    return create_visual_training_protocol(
        path, training_seeds=(7, 8), validation_seeds=(100,), test_seeds=(200,), **kwargs
    )


def reseal(payload):
    payload["manifest_sha256"] = hashlib.sha256(
        canonical({key: value for key, value in payload.items() if key != "manifest_sha256"})
    ).hexdigest()
    return payload


def test_protocol_roundtrip_and_training_membership(tmp_path):
    path = tmp_path / "protocol.json"
    protocol = create(path)
    assert load_visual_training_protocol(path) == protocol
    assert protocol.physical_layout_count == 1
    assert protocol.validated_recordings is False
    protocol.require_training_seed(7)
    for seed in (True, 7.0, 100, 200, 999):
        with pytest.raises(ValueError, match="allocation"):
            protocol.require_training_seed(seed)
    with pytest.raises(FileExistsError):
        create(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("training_seeds", []),
        ("validation_seeds", []),
        ("test_seeds", []),
        ("training_seeds", [7, 7]),
        ("training_seeds", [True]),
        ("training_seeds", [7.0]),
        ("training_seeds", [-1]),
        ("training_seeds", [2**32]),
        ("validation_seeds", [7]),
        ("test_seeds", [100]),
        ("test_seeds", [0]),
        ("test_seeds", [7]),
        ("previously_used_development_seeds", []),
        ("physical_layout_count", True),
        ("physical_layout_count", 2),
        ("base_scene_sha256", "a" * 64),
        ("plan_sha256", "b" * 64),
        ("recipe", "v1"),
        ("validated_recordings", True),
    ],
)
def test_invalid_allocation_or_claim_rejected_even_if_resealed(tmp_path, field, value):
    payload = create(tmp_path / "protocol.json").model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValueError):
        VisualTrainingProtocol.model_validate(reseal(payload))


def test_unsealed_seed_change_is_rejected(tmp_path):
    path = tmp_path / "protocol.json"
    create(path)
    payload = json.loads(path.read_text())
    payload["training_seeds"] = [9]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="seal"):
        load_visual_training_protocol(path)


def test_generator_change_is_detected(tmp_path):
    from bimanual import visual_variants

    generator = tmp_path / "generator.py"
    generator.write_bytes(Path(visual_variants.__file__).read_bytes())
    path = tmp_path / "protocol.json"
    create(path, generator_path=generator)
    generator.write_bytes(generator.read_bytes() + b"\n# changed\n")
    with pytest.raises(ValueError, match="generator_sha256"):
        load_visual_training_protocol(path, generator_path=generator)


def test_invalid_protocol_creates_no_file(tmp_path):
    path = tmp_path / "invalid.json"
    with pytest.raises(ValueError):
        create_visual_training_protocol(
            path, training_seeds=(7,), validation_seeds=(7,), test_seeds=(8,)
        )
    assert not path.exists()


def test_additional_development_exposure_is_frozen_and_excluded(tmp_path):
    path = tmp_path / "protocol.json"
    protocol = create(path, previously_used_development_seeds=(0, 7, 99))
    assert load_visual_training_protocol(path).previously_used_development_seeds == (0, 7, 99)
    payload = protocol.model_dump(mode="json")
    payload["test_seeds"] = [99]
    with pytest.raises(ValueError, match="development exposure"):
        VisualTrainingProtocol.model_validate(reseal(payload))
    payload["test_seeds"] = [200]
    payload["previously_used_development_seeds"] = [0, 7, 7]
    with pytest.raises(ValueError, match="uniquely"):
        VisualTrainingProtocol.model_validate(reseal(payload))
