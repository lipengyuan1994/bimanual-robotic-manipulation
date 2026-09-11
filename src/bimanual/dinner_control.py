"""Incremental, supervised policy control of one continuous dinner simulation."""

from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Literal

import mujoco
import numpy as np
from PIL import Image

from bimanual.contracts import Artifact, CameraFrame, Contract, Digest, JointLimits, Observation
from bimanual.dinner_teacher import ASSETS, DinnerEnvironment
from bimanual.dual_arm import CAMERAS, JOINT_ORDER, verify_assets
from bimanual.evidence import canonical, digest_file
from bimanual.policy_rollout import policy_inputs
from bimanual.supervised_control import SupervisedPolicyControl
from bimanual.supervisor import Capability
from bimanual.teacher import check_carried_path, check_joint_path

PLANNER_PROFILES = {
    "policy480_v1": ((480, 270),) * 3,
    "overhead1920_wrist480_v1": ((1920, 1080), (480, 270), (480, 270)),
}


class LivePlannerCapture(Contract):
    mode: Literal["live_paused_v1"] = "live_paused_v1"
    profile: Literal["policy480_v1", "overhead1920_wrist480_v1"]
    camera_source: Literal["live_mujoco", "injected_unverified"]
    policy_observation: Observation
    planner_observation: Observation
    calibration: Artifact
    source_model_sha256: Digest
    render_model_sha256: Digest


class _PolicyDinnerEnvironment(DinnerEnvironment):
    def after_physics_step(self):
        super().after_physics_step()
        positions = self.data.qpos[self.qadr]
        if np.any(positions < self.lower) or np.any(positions > self.upper):
            self.stop()
            raise ValueError("Measured dinner joints exceeded model limits")


class DinnerControlWorker:
    """Serialized owner of a single environment; never consumes teacher action plans.

    ``render_capture`` is a test seam returning RGB arrays only. Injected pixels
    are explicitly unverified and never evidence of functioning real cameras.
    Simulator state used by collision guards/evidence is not a policy input.
    This worker does not invent task success or advance unowned transition steps.
    """

    def __init__(
        self,
        directory: Path,
        registry: Iterable[Capability],
        *,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        cancelled: Callable[[], bool] = lambda: False,
        render_capture: Callable[[DinnerEnvironment], dict[str, np.ndarray]] | None = None,
        planner_render_capture: Callable[[DinnerEnvironment], np.ndarray] | None = None,
    ):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        (self.directory / "observations").mkdir()
        self._clock, self._cancelled, self._render_capture = clock_ns, cancelled, render_capture
        self._planner_render_capture = planner_render_capture
        self._planner_model = self._planner_renderer = self._planner_model_digest = None
        self._trace = (self.directory / "physics.jsonl").open("x")
        self._env = None
        self._closed = False
        self._capture_count = self._applied = 0
        self._observation = self._raw = self._state = None
        self._terminal_observation = self._terminal_state = None
        self._recovery_boundary = None
        self._generation = uuid.uuid4().hex
        self._planning_pause = None
        self.control = SupervisedPolicyControl(registry, clock_ns=clock_ns)
        self.supervisor = self.control.supervisor
        try:
            verify_assets()
            manifest = json.loads((ASSETS / "manifest.json").read_text())
            if digest_file(ASSETS / "scene.xml") != manifest["files"]["scene.xml"]:
                raise ValueError("Authored dinner scene integrity mismatch")
            # Evaluation provenance only; layout is never passed to planner/policy inputs.
            layout_bytes = (ASSETS / "layout.json").read_bytes()
            if hashlib.sha256(layout_bytes).hexdigest() != manifest["files"]["layout.json"]:
                raise ValueError("Authored dinner layout integrity mismatch")
            layout = json.loads(layout_bytes)
            if layout.get("scene_sha256") != manifest["files"]["scene.xml"]:
                raise ValueError("Authored dinner layout/scene mismatch")
            xml = (ASSETS / "scene.xml").read_text()
            (self.directory / "scene.xml").write_text(xml)
            (self.directory / "layout.json").write_bytes(layout_bytes)
            self._env = _PolicyDinnerEnvironment(xml, self._trace, cancelled)
            self._expected_model_digest = self._model_digest()
            self._env.phase = "policy/idle"
            self.limits = JointLimits(
                lower_rad=self._env.lower.tolist(), upper_rad=self._env.upper.tolist()
            )
            (self.directory / "worker.json").write_bytes(
                canonical(
                    {
                        "scene_sha256": digest_file(self.directory / "scene.xml"),
                        "layout_sha256": digest_file(self.directory / "layout.json"),
                        "layout_usage": "independent_scoring_only",
                        "camera_source": "live_mujoco"
                        if render_capture is None
                        else "injected_unverified",
                        "physics_hz": 1000,
                        "control_hz": 20,
                        "teacher_schedule_used": False,
                        "manipulation_success": None,
                        "operating_inputs": ["three RGB cameras", "twelve joint positions"],
                        "safety_guard_uses_simulator_state": True,
                    }
                )
            )
        except BaseException:
            self.close()
            raise

    @property
    def episode_id(self) -> str:
        return self._env.episode_id

    def _record(self, name: str, row: dict):
        with (self.directory / name).open("a") as stream:
            stream.write(json.dumps(row, allow_nan=False) + "\n")

    def flush_physics_trace(self) -> None:
        """Make existing append-only evidence readable; never advance physics."""
        self._trace.flush()

    def recovery_available(self) -> bool:
        """Only a declared non-completion at a confirmed boundary can be retried."""
        snapshot = self.supervisor.snapshot()
        boundary = self._recovery_boundary
        if (
            self._closed
            or not self._env.active
            or boundary is None
            or snapshot.state != "awaiting_observation"
            or snapshot.active is not None
            or not snapshot.attempts
        ):
            return False
        last = snapshot.attempts[-1]
        return (
            last.outcome == "failed"
            and last.attempt.attempt_id == boundary[0]
            and last.observation == boundary[1]
            and self._token() == boundary[2]
            and snapshot.task == boundary[3]
        )

    def acquire_planning_pause(self) -> dict:
        """Claim a ready boundary for externally executed reasoning; no physics advances."""
        self._available()
        snapshot = self.supervisor.snapshot()
        if self._planning_pause is not None:
            raise RuntimeError("A planning pause is already owned")
        recovery = snapshot.state == "awaiting_observation" and self.recovery_available()
        if (
            (snapshot.state != "ready" and not recovery)
            or snapshot.active is not None
            or snapshot.task is None
        ):
            raise RuntimeError("Planning requires a ready task or owned recovery boundary")
        if (
            not recovery
            and snapshot.completed_steps
            and (
                self._terminal_observation is None
                or self._terminal_state != self._token()
                or snapshot.attempts[-1].outcome != "succeeded"
                or snapshot.attempts[-1].observation != self._terminal_observation
            )
        ):
            raise ValueError("Planning cannot replace recovery or an unverified terminal boundary")
        self.control.clear()
        pause = {
            "pause_id": uuid.uuid4().hex,
            "boundary_kind": "recovery" if recovery else "ready",
            "failed_attempt_id": self._recovery_boundary[0] if recovery else None,
            "worker_generation": self._generation,
            "state_sha256": self._token(),
            "model_sha256": self._expected_model_digest,
            "task_sha256": hashlib.sha256(
                canonical(snapshot.task.model_dump(mode="json"))
            ).hexdigest(),
            "completed_steps": tuple(snapshot.completed_steps),
            "camera_source": "live_mujoco"
            if self._render_capture is None
            else "injected_unverified",
        }
        self._planning_pause = pause
        return pause.copy()

    def check_planning_pause(self, pause_id: str) -> dict:
        self._available()
        if self._planner_model is not None and (
            self._digest_model(self._planner_model) != self._planner_model_digest
        ):
            raise ValueError("Planner render model changed after initialization")
        pause = self._planning_pause
        snapshot = self.supervisor.snapshot()
        if (
            pause is None
            or pause["pause_id"] != pause_id
            or pause["worker_generation"] != self._generation
        ):
            raise RuntimeError("Planning pause is no longer owned by this worker generation")
        if (
            snapshot.state
            != ("awaiting_observation" if pause["boundary_kind"] == "recovery" else "ready")
            or (
                pause["boundary_kind"] == "recovery"
                and (
                    not self.recovery_available()
                    or self._recovery_boundary[0] != pause["failed_attempt_id"]
                )
            )
            or snapshot.active is not None
            or snapshot.task is None
            or hashlib.sha256(canonical(snapshot.task.model_dump(mode="json"))).hexdigest()
            != pause["task_sha256"]
            or tuple(snapshot.completed_steps) != pause["completed_steps"]
            or self._token() != pause["state_sha256"]
        ):
            raise ValueError("Worker state or task changed during planning")
        return pause.copy()

    def capture_planning_pause(self, pause_id: str) -> Observation:
        self.check_planning_pause(pause_id)
        observation = self.capture()
        self.check_planning_pause(pause_id)
        return observation

    def _ensure_planner_renderer(self):
        if self._planner_model is None:
            # A full compiled-model copy, never a reconstructed/reset episode. The
            # sole difference is offscreen framebuffer capacity; MjData stays live.
            self._planner_model = copy.copy(self._env.model)
            self._planner_model.vis.global_.offwidth = 1920
            self._planner_model.vis.global_.offheight = 1080
            self._planner_model_digest = self._digest_model(self._planner_model)
        if self._planner_renderer is None and self._planner_render_capture is None:
            self._planner_renderer = mujoco.Renderer(self._planner_model, width=1920, height=1080)

    def capture_planner_pause(self, pause_id: str, profile: str) -> LivePlannerCapture:
        """Fresh live views with separate planner/ACT pixels and calibration evidence."""
        if profile not in PLANNER_PROFILES:
            raise ValueError("Unsupported live planner camera profile")
        self.check_planning_pause(pause_id)
        high_resolution = profile != "policy480_v1"
        if high_resolution:
            self._ensure_planner_renderer()
        self.check_planning_pause(pause_id)
        before_count = self._capture_count
        policy_observation = self.capture_planning_pause(pause_id)
        if self._capture_count != before_count + 1 or policy_observation != self._observation:
            raise ValueError("Planner recapture requires new worker-owned camera artifacts")
        model, data = self._env.model, self._env.data
        camera_transforms = (data.cam_xpos.copy(), data.cam_xmat.copy())
        calibration = {
            "mode": "live_paused_v1",
            "profile": profile,
            "source_model_sha256": self._expected_model_digest,
            "render_model_sha256": self._planner_model_digest
            if high_resolution
            else self._expected_model_digest,
            "render_model_overrides": {"offwidth": 1920, "offheight": 1080}
            if high_resolution
            else {},
            "cameras": [
                {
                    "camera": name,
                    "render_dimensions_wh": list(dimensions),
                    "fovy_degrees": float(model.cam_fovy[model.camera(name).id]),
                    "intrinsic": model.cam_intrinsic[model.camera(name).id].tolist(),
                    "sensor_size": model.cam_sensorsize[model.camera(name).id].tolist(),
                    "authored_resolution": model.cam_resolution[model.camera(name).id].tolist(),
                    "position": data.cam_xpos[model.camera(name).id].tolist(),
                    "rotation": data.cam_xmat[model.camera(name).id].tolist(),
                }
                for name, dimensions in zip(CAMERAS, PLANNER_PROFILES[profile], strict=True)
            ],
        }
        observation = policy_observation
        if high_resolution:
            if self._planner_render_capture is None:
                self._planner_renderer.update_scene(data, camera="overhead")
                pixels = self._planner_renderer.render().copy()
            else:
                pixels = self._planner_render_capture(self._env)
            if not isinstance(pixels, np.ndarray) or (
                pixels.shape != (1080, 1920, 3) or pixels.dtype != np.uint8
            ):
                raise ValueError("Live planner overhead must be native 1920 x 1080 RGB8")
            self.check_planning_pause(pause_id)
            if not all(
                np.array_equal(a, b)
                for a, b in zip(camera_transforms, (data.cam_xpos, data.cam_xmat), strict=True)
            ):
                raise ValueError("Live camera calibration changed during planner rendering")
            relative = f"observations/{self._capture_count - 1:06d}-planner-overhead.png"
            with (self.directory / relative).open("xb") as stream:
                Image.fromarray(pixels).save(stream, format="PNG")
            frame = policy_observation.frames[0].model_copy(
                update={
                    "artifact": Artifact(
                        path=relative, sha256=digest_file(self.directory / relative)
                    )
                }
            )
            observation = Observation.model_validate(
                policy_observation.model_dump()
                | {"frames": (frame, *policy_observation.frames[1:])}
            )
        relative = f"observations/{self._capture_count - 1:06d}-planner-calibration.json"
        with (self.directory / relative).open("xb") as stream:
            stream.write(canonical(calibration))
        self.check_planning_pause(pause_id)
        captured = LivePlannerCapture(
            profile=profile,
            camera_source="injected_unverified"
            if (
                self._render_capture is not None
                or (high_resolution and self._planner_render_capture is not None)
            )
            else "live_mujoco",
            policy_observation=policy_observation,
            planner_observation=observation,
            calibration=Artifact(path=relative, sha256=digest_file(self.directory / relative)),
            source_model_sha256=self._expected_model_digest,
            render_model_sha256=calibration["render_model_sha256"],
        )
        self._record(
            "planner-captures.jsonl",
            {
                "capture": captured.model_dump(mode="json"),
                "capture_finished_monotonic_ns": self._clock(),
            },
        )
        return captured

    def release_planning_pause(self, pause_id: str):
        if self._planning_pause is None or self._planning_pause["pause_id"] != pause_id:
            raise RuntimeError("Planning pause is no longer owned")
        self._planning_pause = None

    def dispatch_planning_pause(
        self,
        pause_id: str,
        observation: Observation,
        *,
        proposal,
        planning_deadline_ns: int | None = None,
    ):
        """Trusted revalidation bridge: dispatch the exact recapture under its owned pause."""
        pause = self.check_planning_pause(pause_id)
        self._validate_capture(observation)
        previous = (
            self._terminal_observation if self.supervisor.snapshot().completed_steps else None
        )
        if planning_deadline_ns is not None and self._clock() >= planning_deadline_ns:
            raise TimeoutError("Planning job expired before dispatch")
        recovery = self._recovery_boundary if pause["boundary_kind"] == "recovery" else None
        self.release_planning_pause(pause_id)
        if recovery is not None:
            try:
                return self.supervisor.dispatch_recovery(
                    observation,
                    previous_observation=recovery[1],
                    failed_attempt_id=recovery[0],
                    proposal=proposal,
                )
            finally:
                self._recovery_boundary = None
        if previous is not None:
            return self.supervisor.dispatch_stationary(
                observation, previous_observation=previous, proposal=proposal
            )
        return self.supervisor.dispatch(observation, proposal=proposal)

    def _require_unpaused(self):
        if self._planning_pause is not None:
            raise RuntimeError("Physical policy control is prohibited during owned planning pause")

    def _token(self) -> str:
        env = self._env
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(env.model, spec))
        mujoco.mj_getState(env.model, env.data, state, spec)
        return hashlib.sha256(
            state.tobytes()
            + canonical(
                {
                    "episode": env.episode_id,
                    "sequence": env.sequence,
                    "model_sha256": self._model_digest(),
                }
            )
        ).hexdigest()

    def _model_digest(self) -> str:
        return self._digest_model(self._env.model)

    @staticmethod
    def _digest_model(model) -> str:
        buffer = np.empty(mujoco.mj_sizeModel(model), dtype=np.uint8)
        mujoco.mj_saveModel(model, buffer=buffer)
        return hashlib.sha256(buffer.tobytes()).hexdigest()

    def _available(self):
        if self._closed or not self._env.active:
            raise RuntimeError("Dinner worker is stopped")
        if self._cancelled():
            self.cancel("Operator cancellation observed")
            raise InterruptedError("Dinner worker cancelled")
        if self._model_digest() != self._expected_model_digest:
            self._env.stop()
            raise ValueError("Physical model changed after worker initialization")
        self.supervisor.tick()

    def capture(self) -> Observation:
        self._available()
        env = self._env
        started_ns = self._clock()
        before = self._token()
        pixels = (
            env.observe(render=True)["rgb"]
            if self._render_capture is None
            else self._render_capture(env)
        )
        if self._token() != before:
            self._env.stop()
            raise ValueError("Simulation state changed during camera capture")
        task = self.supervisor.snapshot().task
        if task is not None and task.episode_id != self.episode_id:
            raise ValueError("Task belongs to a different physical episode")
        raw = dict(
            schema_version=1,
            episode_id=env.episode_id,
            sequence=env.sequence,
            simulation_seconds=float(env.data.time),
            observed_monotonic_ns=started_ns,
            joint_order=list(JOINT_ORDER),
            joint_position_rad=env.data.qpos[env.qadr].copy(),
            joint_velocity_rad_s=env.data.qvel[env.vadr].copy(),
            rgb={name: image.copy() for name, image in pixels.items()},
            camera_order=list(pixels),
        )
        policy_inputs(raw)  # Exact input allowlist, camera order, RGB shape/dtype, finite joints.
        capture = {
            key: raw[key] for key in ("sequence", "simulation_seconds", "observed_monotonic_ns")
        }
        frames = []
        for index, name in enumerate(CAMERAS):
            relative = f"observations/{self._capture_count:06d}-{index}.png"
            with (self.directory / relative).open("xb") as stream:
                Image.fromarray(raw["rgb"][name]).save(stream, format="PNG")
            frames.append(
                CameraFrame(
                    camera=name,
                    **capture,
                    artifact=Artifact(path=relative, sha256=digest_file(self.directory / relative)),
                )
            )
        observation = Observation(
            episode_id=env.episode_id,
            instruction_revision=task.instruction_revision if task else 0,
            **capture,
            frames=tuple(frames),
            joint_position_rad=raw["joint_position_rad"].tolist(),
            joint_velocity_rad_s=raw["joint_velocity_rad_s"].tolist(),
        )
        self._observation, self._raw, self._state = observation, raw, before
        from bimanual.workflow_progress import write_snapshot

        write_snapshot(
            self.directory / "camera-preview.json",
            {
                "camera_source": "live_mujoco"
                if self._render_capture is None
                else "injected_unverified",
                "observation": observation.model_dump(mode="json"),
            },
        )
        self._capture_count += 1
        self._record(
            "captures.jsonl",
            {
                "observation": observation.model_dump(mode="json"),
                "integration_state_sha256": before,
                "capture_finished_monotonic_ns": self._clock(),
            },
        )
        return observation

    def _validate_capture(self, observation: Observation):
        self._available()
        if not isinstance(observation, Observation) or observation != self._observation:
            raise ValueError("Only the worker's exact current capture is accepted")
        current = Observation.model_validate(observation.model_dump(mode="json"))
        task = self.supervisor.snapshot().task
        if task is None or (current.episode_id, current.instruction_revision) != (
            task.episode_id,
            task.instruction_revision,
        ):
            raise ValueError("Capture no longer matches the current task identity")
        if self._token() != self._state:
            raise ValueError("Physical integration state differs from the captured boundary")
        if not 0 <= self._clock() - current.observed_monotonic_ns <= 2_000_000_000:
            raise ValueError("Physical action requires a fresh camera capture")
        policy_inputs(self._raw)
        for frame in current.frames:
            frame.artifact.verify(self.directory)

    def policy_inputs(self, observation: Observation) -> dict[str, np.ndarray]:
        self._validate_capture(observation)
        return policy_inputs(self._raw)

    def _permissions(self, attempt_id: str):
        active = self.supervisor.snapshot().active
        if active is None or active.attempt_id != attempt_id:
            raise RuntimeError("No canonical active dinner attempt")
        request = active.request
        target = "practice_object" if request.target == "practice_block" else request.target
        if (
            request.skill == "handoff"
            and target == "practice_object"
            and active.arms == ("left", "right")
        ):
            allowed = {"left": {target}, "right": {target}}
        else:
            owner = {
                "practice_object": "right",
                "cup": "right",
                "plate": "left",
                "drawer": "left",
                "spoon": "left",
                "fork": "left",
            }.get(target)
            valid_skill = (
                request.skill == "open_drawer"
                if target == "drawer"
                else request.skill in {"pick", "place"}
            )
            if target == "practice_object":
                valid_skill = request.skill == "place"
            # Canonical auxiliary arm motion does not grant auxiliary object contact.
            if not valid_skill or owner is None or request.arm != owner or owner not in active.arms:
                raise ValueError("Capability has unsupported dinner contact ownership")
            auxiliary = set(active.arms) - {owner}
            permitted_auxiliary = {
                "practice_object": {"left"},
                "plate": {"right"},
                "drawer": {"right"},
            }.get(target, set())
            if not auxiliary <= permitted_auxiliary:
                raise ValueError("Capability has unsupported auxiliary dinner ownership")
            allowed = {owner: {target}}
        return active, allowed

    def _abort(self, attempt_id: str, observation: Observation, error: BaseException):
        self._recovery_boundary = None
        active = self.supervisor.snapshot().active
        if active is not None and active.attempt_id == attempt_id:
            try:
                self.supervisor.finish(
                    attempt_id,
                    observation,
                    executor_outcome="failed",
                    reason=f"Dinner worker rejected operation: {error}"[:2048],
                )
            except (Exception, KeyboardInterrupt):
                self.control.clear()
        self._env.stop()

    def bind(self, attempt_id: str, **policy_configuration):
        observation = self._observation
        try:
            self._require_unpaused()
            self._validate_capture(observation)
            _, allowed = self._permissions(attempt_id)
            result = self.control.bind(
                attempt_id,
                hold_targets=self._env.data.ctrl[self._env.actuator_ids].copy(),
                limits=self.limits,
                **policy_configuration,
            )
            self._env.active_contacts = allowed
            self._env.phase = "policy/" + self.supervisor.snapshot().active.request.skill
            return result
        except (Exception, KeyboardInterrupt) as error:
            self._abort(attempt_id, observation, error)
            raise

    def offer(self, attempt_id: str, targets: np.ndarray, observation: Observation) -> dict:
        try:
            self._require_unpaused()
            self._validate_capture(observation)
            self._permissions(attempt_id)
            result = self.control.offer(attempt_id, targets, observation)
            self._record("forecasts.jsonl", result)
            return result
        except (Exception, KeyboardInterrupt) as error:
            self._abort(attempt_id, observation, error)
            self._record("forecast-errors.jsonl", {"attempt_id": attempt_id, "error": str(error)})
            raise

    def bind_skill(
        self,
        policy,
        attempt_id: str,
        *,
        execute_chunk_steps: int = 1,
        temporal_ensemble_coefficient: float | None = None,
    ):
        """Delegate verified checkpoint binding through the worker's physical guards."""
        observation = self._observation
        try:
            self._require_unpaused()
            self._validate_capture(observation)
            _, allowed = self._permissions(attempt_id)
            binding = policy.bind_control(
                self.control,
                attempt_id,
                hold_targets=self._env.data.ctrl[self._env.actuator_ids].copy(),
                limits=self.limits,
                execute_chunk_steps=execute_chunk_steps,
                temporal_ensemble_coefficient=temporal_ensemble_coefficient,
            )
            self._env.active_contacts = allowed
            self._env.phase = "policy/" + self.supervisor.snapshot().active.request.skill
            return binding
        except (Exception, KeyboardInterrupt) as error:
            self._abort(attempt_id, observation, error)
            raise

    def _check_path(self, targets: np.ndarray):
        env = self._env
        start = env.data.qpos[env.qadr].copy()
        carrying = []
        for arm, objects in env.active_contacts.items():
            for name in objects - {"drawer"}:
                touching = set()
                for contact in env.data.contact:
                    names = {env.model.geom(int(g)).name for g in contact.geom}
                    if any(env.geom_objects.get(g) == name for g in names):
                        for index, fingers in enumerate(env.fingers[arm]):
                            if names & fingers:
                                touching.add(index)
                if touching == {0, 1}:
                    carrying.append((arm, name))
        if carrying:
            for arm, name in carrying:
                check_carried_path(
                    env, start, targets, env.allowed, body_name=name, site_name=arm + "/pinch"
                )
        else:
            check_joint_path(env, start, targets, env.allowed)

    def step(self, attempt_id: str, observation: Observation) -> dict:
        action = dict(
            episode_id=self._env.episode_id,
            attempt_id=attempt_id,
            observation_sequence=observation.sequence,
            applied=False,
            partial_physics=False,
        )
        before = float(self._env.data.time)
        try:
            self._require_unpaused()
            self._validate_capture(observation)
            _, allowed = self._permissions(attempt_id)
            if self._env.active_contacts != allowed:
                raise ValueError("Physical contact permissions changed after binding")
            targets = self.control.take(attempt_id, observation)
            action["targets_rad"] = targets.tolist()
            self._check_path(targets)
            # Expensive path checks must not make an earlier authorization sufficient.
            self._validate_capture(observation)
            active = self.supervisor.authorize(attempt_id, observation)
            for arm in active.arms:
                self.supervisor.authorize(
                    attempt_id, observation, arm=arm, shared_workspace=active.shared_workspace
                )
            if self._cancelled():
                self.cancel("Operator cancellation before physics")
                raise InterruptedError("Dinner worker cancelled before physical step")
            if self._token() != self._state:
                raise ValueError("Physical state changed immediately before stepping")
            now = self._clock()
            if now >= active.deadline_ns:
                self.supervisor.tick()
                raise TimeoutError("Attempt expired before physical stepping")
            if now - observation.observed_monotonic_ns > 2_000_000_000:
                raise ValueError("Camera capture expired before physical stepping")
            self._env.step(
                targets, episode_id=observation.episode_id, sequence=observation.sequence
            )
            action["applied"] = True
            self._applied += 1
            return action
        except (Exception, KeyboardInterrupt) as error:
            action["error"] = f"{type(error).__name__}: {error}"
            action["partial_physics"] = float(self._env.data.time) > before
            self._abort(attempt_id, observation, error)
            raise
        finally:
            action["simulation_seconds_before"] = before
            action["simulation_seconds_after"] = float(self._env.data.time)
            self._record("actions.jsonl", action)

    def finish(
        self,
        attempt_id: str,
        observation: Observation,
        *,
        executor_outcome: str,
        reason: str,
        recoverable_failure: bool = False,
    ):
        """Only trusted executor termination logic may call this; no automatic scoring."""
        self._validate_capture(observation)
        active = self.supervisor.snapshot().active
        if type(recoverable_failure) is not bool or (
            recoverable_failure
            and (
                executor_outcome != "failed"
                or active is None
                or active.attempt_id != attempt_id
                or observation.sequence <= active.observation.sequence
                or observation.simulation_seconds <= active.observation.simulation_seconds
            )
        ):
            raise ValueError("Recovery requires declared failure after confirmed physical progress")
        self._recovery_boundary = None
        result = self.supervisor.finish(
            attempt_id, observation, executor_outcome=executor_outcome, reason=reason
        )
        if executor_outcome == "succeeded":
            self._terminal_observation, self._terminal_state = observation, self._state
        elif recoverable_failure and result.state == "awaiting_observation":
            self._recovery_boundary = (attempt_id, observation, self._state, result.task)
        return result

    def dispatch_stationary(self, previous_observation: Observation, *, proposal=None):
        """Re-render the unchanged successful terminal boundary before the next skill."""
        self._available()
        if (
            previous_observation != self._terminal_observation
            or self._token() != self._terminal_state
        ):
            raise ValueError(
                "Stationary dispatch requires this worker's unchanged successful terminal"
            )
        current = self.capture()
        self._validate_capture(current)
        return self.supervisor.dispatch_stationary(
            current, previous_observation=previous_observation, proposal=proposal
        )

    def cancel(self, reason: str = "Operator cancelled"):
        try:
            return self.supervisor.cancel(reason)
        finally:
            self._planning_pause = None
            self._recovery_boundary = None
            self._env.stop()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._planning_pause = None
        try:
            if self.supervisor.snapshot().active is not None:
                self.supervisor.cancel("Physical worker closed before attempt termination")
            else:
                self.control.clear()
        finally:
            if self._planner_renderer is not None:
                self._planner_renderer.close()
            if self._env is not None:
                self._env.close()
            self._trace.close()
            (self.directory / "supervisor.json").write_text(
                self.supervisor.snapshot().model_dump_json(indent=2)
            )
            (self.directory / "summary.json").write_bytes(
                canonical(
                    {
                        "applied_control_steps": self._applied,
                        "captures": self._capture_count,
                        "manipulation_success": None,
                        "independent_task_evaluation": "not_run",
                    }
                )
            )
