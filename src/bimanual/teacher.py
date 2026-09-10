"""Privileged, bounded IK teacher. Never a deployed image-based action policy."""

from __future__ import annotations

import mujoco
import numpy as np

from bimanual.dual_arm import DualArm


class ReachError(ValueError):
    """The requested position/direction was not solved within the joint limits."""


def solve_downward(
    env: DualArm, target: np.ndarray, initial: np.ndarray, *, arm: str = "left"
) -> np.ndarray:
    """Position plus tool-axis DLS IK, using a separate kinematics-only MjData.

    Five arm joints cannot realize arbitrary six-dimensional poses. Constrain the
    pinch site's X axis downward and let rotation about that axis remain free.
    The live simulation's positions, velocities and object state are never edited.
    """
    if arm not in {"left", "right"}:
        raise ReachError("Unknown arm")
    channels = slice(0, 5) if arm == "left" else slice(6, 11)
    target = np.asarray(target, dtype=float)
    initial = np.asarray(initial, dtype=float)
    if target.shape != (3,) or not np.isfinite(target).all():
        raise ReachError("Expected a finite XYZ target in metres")
    if initial.shape != (12,) or not np.isfinite(initial).all():
        raise ReachError("Expected twelve finite initial joint positions")
    if np.any(initial < env.lower) or np.any(initial > env.upper):
        raise ReachError("Initial joint positions exceed limits")
    data = mujoco.MjData(env.model)
    data.qpos[:] = env.data.qpos
    data.qpos[env.qadr] = initial
    site = env.model.site(f"{arm}/pinch").id
    jp = np.zeros((3, env.model.nv))
    jr = np.zeros_like(jp)
    for _ in range(250):
        mujoco.mj_forward(env.model, data)
        axis = data.site_xmat[site].reshape(3, 3)[:, 0]
        position_error = target - data.site_xpos[site]
        axis_error = np.array([0, 0, -1]) - axis
        if np.linalg.norm(position_error) < 0.0001 and np.linalg.norm(axis_error) < 0.001:
            return data.qpos[env.qadr].copy()
        mujoco.mj_jacSite(env.model, data, jp, jr, site)
        # Derivative of a unit direction is omega cross direction.
        jacobian = np.vstack([jp, 0.1 * np.cross(jr.T, axis).T])[:, env.vadr[channels]]
        error = np.r_[position_error, 0.1 * axis_error]
        delta = jacobian.T @ np.linalg.solve(jacobian @ jacobian.T + 1e-5 * np.eye(6), error)
        data.qpos[env.qadr[channels]] = np.clip(
            data.qpos[env.qadr[channels]] + np.clip(delta, -0.1, 0.1),
            env.lower[channels],
            env.upper[channels],
        )
    raise ReachError("Downward grasp target unreachable within IK tolerances and joint limits")


def check_joint_path(env: DualArm, start: np.ndarray, end: np.ndarray, allowed) -> None:
    """Check interpolated geometry every <=0.02 rad; live dynamics are checked separately.

    This is discrete collision sampling, not continuous collision certification.
    Object pose is frozen at its current state in the scratch data during planning.
    """
    data = mujoco.MjData(env.model)
    data.qpos[:] = env.data.qpos
    count = max(1, int(np.ceil(np.max(np.abs(end - start)) / 0.02)))
    for alpha in np.linspace(0, 1, count + 1):
        data.qpos[env.qadr] = start + alpha * (end - start)
        mujoco.mj_forward(env.model, data)
        for contact in data.contact:
            pair = tuple(env.model.geom(int(g)).name for g in contact.geom)
            if not allowed(pair):
                raise ReachError(f"Planned trajectory intersects forbidden geometry: {pair}")
