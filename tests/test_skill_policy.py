from types import SimpleNamespace

import numpy as np
import pytest

from bimanual.dataset_export import CAMERA_FEATURES
from bimanual.skill_policy import DinnerSkillPolicy


def inputs():
    return {"observation.state": np.zeros(12, dtype=np.float32)} | {
        feature: np.zeros((3, 270, 480), dtype=np.float32) for feature in CAMERA_FEATURES.values()
    }


@pytest.mark.parametrize("fault", ["truth", "dtype", "shape", "nan", "rgb_range"])
def test_rejects_invalid_perception_before_model_call(fault):
    # No model runtime is installed in this fixture: rejection must precede tensor conversion.
    policy = object.__new__(DinnerSkillPolicy)
    values = inputs()
    if fault == "truth":
        values["object_position"] = np.zeros(3)
    elif fault == "dtype":
        values["observation.state"] = np.zeros(12, dtype=np.float64)
    elif fault == "shape":
        values["observation.state"] = np.zeros(13, dtype=np.float32)
    elif fault == "nan":
        values["observation.state"][0] = np.nan
    else:
        values[next(iter(CAMERA_FEATURES.values()))][0, 0, 0] = 1.01
    # Conversion itself is harmless; absence of policy proves no inference is entered.
    policy._torch = SimpleNamespace(from_numpy=lambda value: value)
    with pytest.raises(ValueError):
        policy.predict(values)


def test_policy_device_is_explicit():
    with pytest.raises(ValueError, match="devices"):
        DinnerSkillPolicy(None, skill_id="bar_place_and_return", dataset_root=None, device="auto")


def test_policy_binding_requires_the_registered_skill_before_reset():
    from bimanual.skill_registry import dinner_capability

    policy = object.__new__(DinnerSkillPolicy)
    policy.binding = SimpleNamespace(capability=dinner_capability("cup_pick_place"))
    active = SimpleNamespace(attempt_id="attempt", step_id="step")
    snapshot = SimpleNamespace(
        active=active,
        task=SimpleNamespace(steps=[SimpleNamespace(step_id="step", capability_id="bar")]),
    )
    control = SimpleNamespace(
        supervisor=SimpleNamespace(
            snapshot=lambda: snapshot, registry={"bar": dinner_capability("bar_place_and_return")}
        )
    )
    with pytest.raises(ValueError, match="registered attempt"):
        policy.bind_control(control, "attempt", hold_targets=np.zeros(12), limits=None)
