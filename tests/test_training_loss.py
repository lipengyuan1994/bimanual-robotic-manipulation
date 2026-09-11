import json
import os
import platform
from pathlib import Path
from types import SimpleNamespace

import pytest

from bimanual.evidence import EvidenceStore
from bimanual.training import ACTTrainingConfig, run_train
from bimanual.training_loss import (
    act_training_loss,
    temporal_loss_definition,
    weighted_action_l1,
)


def test_profile_definition_and_config_roundtrip():
    config = ACTTrainingConfig(
        dataset_path="unused", use_vae=False, temporal_loss_profile="first_action_half_v1"
    )
    assert ACTTrainingConfig.model_validate_json(config.model_dump_json()) == config
    definition = temporal_loss_definition(config.temporal_loss_profile, 10, use_vae=False)
    assert definition["schema_version"] == 1
    assert definition["weights"] == [9] + [1] * 9
    assert definition["normalization"] == "sum_valid_temporal_weights_times_action_dimension"
    assert json.loads(json.dumps(definition)) == definition
    assert ACTTrainingConfig(dataset_path="unused").temporal_loss_profile == "uniform"


@pytest.mark.parametrize(
    "overrides", [{"use_vae": True}, {"chunk_size": 1}, {"temporal_loss_profile": "unknown"}]
)
def test_incompatible_profile_rejected(overrides):
    values = dict(
        dataset_path="unused", use_vae=False, temporal_loss_profile="first_action_half_v1"
    )
    values.update(overrides)
    with pytest.raises(ValueError):
        ACTTrainingConfig(**values)


def test_uniform_calls_official_forward_without_touching_batch_or_config():
    batch, expected = object(), (object(), {"official": True})

    class Policy:
        def __call__(self, received):
            assert received is batch
            return expected

    assert act_training_loss(Policy(), batch) is expected


@pytest.fixture
def torch():
    return pytest.importorskip("torch")


def test_first_action_half_mass_and_joint_mean(torch):
    prediction = torch.ones(1, 10, 12, requires_grad=True)
    loss, parts = weighted_action_l1(
        prediction, torch.zeros_like(prediction), torch.zeros(1, 10, dtype=torch.bool)
    )
    assert loss.item() == 1
    assert parts == {"weighted_l1_loss": 1, "uniform_l1_loss": 1}
    loss.backward()
    assert prediction.grad[0, 0].sum().item() == pytest.approx(0.5)
    assert prediction.grad[0, 1:].sum().item() == pytest.approx(0.5)


def test_padding_excluded_from_numerator_denominator_and_gradient(torch):
    prediction = torch.tensor(
        [[[2.0, 2.0], [4.0, 4.0], [1000.0, 1000.0]], [[500.0, 500.0], [6.0, 6.0], [8.0, 8.0]]],
        requires_grad=True,
    )
    pad = torch.tensor([[False, False, True], [True, False, False]])
    loss, parts = weighted_action_l1(prediction, torch.zeros_like(prediction), pad)
    # Valid temporal mass = 2+1+1+1; two joints each, identical within a frame.
    assert loss.item() == pytest.approx((2 * 2 + 4 + 6 + 8) / 5)
    assert parts["uniform_l1_loss"] == pytest.approx(5)
    loss.backward()
    assert torch.equal(prediction.grad[pad], torch.zeros(2, 2))
    assert prediction.grad[0, 0, 0].item() == pytest.approx(2 / 10)
    assert prediction.grad[1, 2, 0].item() == pytest.approx(1 / 10)


@pytest.mark.parametrize(
    "case", ["all_pad", "mask_type", "mask_shape", "target_shape", "chunk_one", "nan"]
)
def test_invalid_weighted_batches_rejected(torch, case):
    prediction, target = torch.ones(1, 3, 2), torch.zeros(1, 3, 2)
    pad = torch.zeros(1, 3, dtype=torch.bool)
    if case == "all_pad":
        pad[:] = True
    elif case == "mask_type":
        pad = pad.float()
    elif case == "mask_shape":
        pad = pad.unsqueeze(-1)
    elif case == "target_shape":
        target = target[:, :1]
    elif case == "chunk_one":
        prediction, target, pad = prediction[:, :1], target[:, :1], pad[:, :1]
    else:
        target[0, 0, 0] = float("nan")
    with pytest.raises(ValueError):
        weighted_action_l1(prediction, target, pad)


def test_adapter_preserves_camera_order_batch_and_autograd(torch):
    constants = pytest.importorskip("lerobot.utils.constants")
    keys = ["observation.images.right", "observation.images.overhead", "observation.images.left"]
    batch = {key: torch.tensor(index) for index, key in enumerate(keys)}
    batch.update(action=torch.zeros(1, 3, 2), action_is_pad=torch.zeros(1, 3, dtype=torch.bool))
    parameter = torch.nn.Parameter(torch.ones(1, 3, 2))

    def model(received):
        assert received is not batch and constants.OBS_IMAGES not in batch
        assert all(
            value is batch[key]
            for value, key in zip(received[constants.OBS_IMAGES], keys, strict=True)
        )
        assert torch.is_grad_enabled()
        return parameter * 2, (None, None)

    policy = SimpleNamespace(
        config=SimpleNamespace(chunk_size=3, use_vae=False, image_features=dict.fromkeys(keys)),
        model=model,
    )
    loss, _ = act_training_loss(policy, batch, profile="first_action_half_v1")
    loss.backward()
    assert parameter.grad.abs().sum().item() > 0
    assert constants.OBS_IMAGES not in batch


@pytest.mark.parametrize("device", ["cpu", "mps"])
def test_real_act_weighted_forward_backward_and_checkpoint(torch, tmp_path, device):
    if platform.system() == "Darwin":
        assert platform.machine() == "arm64"
    if device == "mps" and not torch.backends.mps.is_available():
        pytest.skip("Actual MPS unavailable; no fallback")
    if device == "mps":
        assert os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") == "0"
    ACTConfig = pytest.importorskip("lerobot.policies.act.configuration_act").ACTConfig
    ACTPolicy = pytest.importorskip("lerobot.policies.act.modeling_act").ACTPolicy
    types = pytest.importorskip("lerobot.configs.types")
    from lerobot.utils.constants import OBS_IMAGES

    old_threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        torch.manual_seed(11)
        keys = [
            "observation.images.overhead",
            "observation.images.left_wrist",
            "observation.images.right_wrist",
        ]
        config = ACTConfig(
            input_features={
                "observation.state": types.PolicyFeature(type=types.FeatureType.STATE, shape=(12,)),
                **{
                    key: types.PolicyFeature(type=types.FeatureType.VISUAL, shape=(3, 32, 32))
                    for key in keys
                },
            },
            output_features={
                "action": types.PolicyFeature(type=types.FeatureType.ACTION, shape=(12,))
            },
            chunk_size=3,
            n_action_steps=3,
            device=device,
            pretrained_backbone_weights=None,
            push_to_hub=False,
            use_vae=False,
            dropout=0,
            dim_model=32,
            n_heads=4,
            dim_feedforward=64,
            n_encoder_layers=1,
            n_decoder_layers=1,
        )
        policy = ACTPolicy(config).to(device).train()
        batch = {key: torch.rand(1, 3, 32, 32, device=device) for key in keys}
        batch.update(
            {
                "observation.state": torch.zeros(1, 12, device=device),
                "action": torch.randn(1, 3, 12, device=device),
                "action_is_pad": torch.tensor([[False, False, True]], device=device),
            }
        )
        official, official_parts = policy(batch)
        default, default_parts = act_training_loss(policy, batch)
        torch.testing.assert_close(default, official, rtol=0, atol=0)
        assert default_parts == official_parts
        prediction = policy.model({**batch, OBS_IMAGES: [batch[key] for key in keys]})[0]
        manual = (
            (prediction[:, 0] - batch["action"][:, 0]).abs().sum() * 2
            + (prediction[:, 1] - batch["action"][:, 1]).abs().sum()
        ) / 36
        loss, _ = act_training_loss(policy, batch, profile="first_action_half_v1")
        torch.testing.assert_close(loss, manual)
        assert policy.training and loss.requires_grad
        loss.backward()
        assert policy.model.action_head.weight.grad.abs().sum().item() > 0
        assert any(
            p.grad is not None and p.grad.abs().sum().item() > 0
            for p in policy.model.backbone.parameters()
        )
        assert all(
            torch.isfinite(p.grad).all().item() for p in policy.parameters() if p.grad is not None
        )
        optimizer = torch.optim.AdamW(policy.get_optim_params(), lr=1e-5)
        optimizer.step()
        checkpoint = tmp_path / device
        policy.save_pretrained(checkpoint)
        restored = ACTPolicy.from_pretrained(checkpoint, local_files_only=True).to(device).train()
        updated, _ = act_training_loss(policy, batch, profile="first_action_half_v1")
        replayed, _ = act_training_loss(restored, batch, profile="first_action_half_v1")
        torch.testing.assert_close(updated, replayed, rtol=1e-5, atol=1e-6)
    finally:
        torch.set_num_threads(old_threads)


@pytest.mark.skipif(
    not os.environ.get("BIMANUAL_TRAIN_TEST_DATASET"),
    reason="Requires explicit verified dataset and native training environment",
)
def test_real_weighted_training_metadata_and_processor_reload(torch, tmp_path):
    config = ACTTrainingConfig(
        dataset_path=Path(os.environ["BIMANUAL_TRAIN_TEST_DATASET"]),
        steps=1,
        use_vae=False,
        dropout=0,
        temporal_loss_profile="first_action_half_v1",
    )
    store = EvidenceStore(tmp_path / "evidence")
    result = run_train(config, store=store, project_root=Path.cwd())
    verified = store.verify(result.run_id)
    directory = store.root / "runs" / result.run_id
    definition = temporal_loss_definition("first_action_half_v1", 10, use_vae=False)
    assert verified.config["temporal_loss_profile"] == "first_action_half_v1"
    assert verified.metrics["temporal_loss"] == definition
    assert json.loads((directory / "checkpoint/training_loss.json").read_text()) == definition
    state = torch.load(directory / "trainer_state.pt", weights_only=True, map_location="cpu")
    assert state["temporal_loss"] == definition
    assert "checkpoint/training_loss.json" in verified.files
    for key in (
        "training_completed",
        "checkpoint_reload_verified",
        "processor_reload_verified",
        "sampler_reload_verified",
        "temporal_loss_reload_verified",
    ):
        assert verified.metrics[key] is True
    assert verified.metrics["manipulation_success"] is None
    assert verified.metrics["initial_state_sha256"] != verified.metrics["updated_state_sha256"]
    step = verified.metrics["steps"][0]
    assert step["loss"] == step["loss_parts"]["weighted_l1_loss"]
    assert "uniform_l1_loss" in step["loss_parts"]
