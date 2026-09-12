"""Versioned, opt-in temporal ACT losses; inference and policy inputs are unchanged."""

from __future__ import annotations


def temporal_loss_definition(profile: str, chunk_size: int, *, use_vae: bool) -> dict:
    """Describe the objective independently of optional torch/LeRobot imports."""
    if type(chunk_size) is not int or chunk_size < 1:
        raise ValueError("Temporal loss requires a positive integer chunk size")
    if profile not in ("uniform", "first_action_half_v1"):
        raise ValueError("Unknown temporal loss profile")
    if profile == "first_action_half_v1" and (use_vae or chunk_size < 2):
        raise ValueError("first_action_half_v1 requires use_vae=False and chunk_size >= 2")
    return {
        "schema_version": 1,
        "profile": profile,
        "weights": ([chunk_size - 1] + [1] * (chunk_size - 1))
        if profile == "first_action_half_v1"
        else [1] * chunk_size,
        "normalization": "sum_valid_temporal_weights_times_action_dimension",
        "representation": "official_preprocessed_normalized_absolute_joint_targets",
        "vae": use_vae,
        "forward": "official_policy_forward" if profile == "uniform" else "act_model_with_autograd",
    }


def weighted_action_l1(prediction, target, action_is_pad):
    """Give the first of T actions weight T-1; exclude padding from loss and gradient.

    The first action has half the mass only for a fully valid chunk. For padded
    chunks the denominator uses the weights of the remaining valid targets.
    """
    import torch

    if (
        prediction.ndim != 3
        or prediction.shape != target.shape
        or prediction.shape[0] < 1
        or prediction.shape[1] < 2
        or prediction.shape[2] < 1
        or action_is_pad.shape != prediction.shape[:2]
        or action_is_pad.dtype != torch.bool
        or prediction.device != target.device
        or prediction.device != action_is_pad.device
        or prediction.dtype != target.dtype
        or not prediction.is_floating_point()
    ):
        raise ValueError(
            "Weighted ACT loss requires matching floating [B,T,J] targets and bool [B,T] padding"
        )
    if not torch.isfinite(prediction).all().item() or not torch.isfinite(target).all().item():
        raise ValueError("Weighted ACT loss requires finite predictions and targets")
    valid = ~action_is_pad
    if not valid.any().item():
        raise ValueError("Weighted ACT loss contains no valid action targets")
    weights = prediction.new_ones(prediction.shape[1])
    weights[0] = prediction.shape[1] - 1
    valid_weights = valid.to(prediction.dtype) * weights
    absolute_error = (prediction - target).abs()
    weighted = (absolute_error * valid_weights.unsqueeze(-1)).sum() / (
        valid_weights.sum() * prediction.shape[-1]
    )
    uniform = (absolute_error * valid.unsqueeze(-1)).sum() / (valid.sum() * prediction.shape[-1])
    return weighted, {
        "weighted_l1_loss": weighted.detach().item(),
        "uniform_l1_loss": uniform.detach().item(),
    }


def act_training_loss(policy, batch: dict, *, profile: str = "uniform"):
    """Keep default LeRobot forward exact; opt-in calls its model with autograd.

    Match ACTPolicy.forward's shallow copy and config-defined image ordering.
    Never call predict_action_chunk: it disables gradients and changes eval mode.
    """
    if profile == "uniform":
        return policy(batch)
    temporal_loss_definition(profile, policy.config.chunk_size, use_vae=policy.config.use_vae)
    from lerobot.utils.constants import OBS_IMAGES

    if policy.config.image_features:
        batch = dict(batch)
        batch[OBS_IMAGES] = [batch[key] for key in policy.config.image_features]
    prediction, _ = policy.model(batch)
    if prediction.shape[1] != policy.config.chunk_size:
        raise ValueError("ACT prediction horizon differs from the configured loss profile")
    return weighted_action_l1(prediction, batch["action"], batch["action_is_pad"])
