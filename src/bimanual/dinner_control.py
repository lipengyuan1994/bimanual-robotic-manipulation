"""Incremental, supervised policy control of one continuous dinner simulation."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterable
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

from bimanual.contracts import Artifact, CameraFrame, JointLimits, Observation
from bimanual.dinner_teacher import ASSETS, DinnerEnvironment
from bimanual.dual_arm import CAMERAS, JOINT_ORDER, verify_assets
from bimanual.evidence import canonical, digest_file
from bimanual.policy_rollout import policy_inputs
from bimanual.supervised_control import SupervisedPolicyControl
from bimanual.supervisor import Capability
from bimanual.teacher import check_carried_path, check_joint_path


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
    ):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        (self.directory / "observations").mkdir()
        self._clock, self._cancelled, self._render_capture = clock_ns, cancelled, render_capture
        self._trace = (self.directory / "physics.jsonl").open("x")
        self._env = None
        self._closed = False
        self._capture_count = self._applied = 0
        self._observation = self._raw = self._state = None
        self._terminal_observation = self._terminal_state = None
        self.control = SupervisedPolicyControl(registry, clock_ns=clock_ns)
        self.supervisor = self.control.supervisor
        try:
            verify_assets()
            manifest = json.loads((ASSETS / "manifest.json").read_text())
            if digest_file(ASSETS / "scene.xml") != manifest["files"]["scene.xml"]:
                raise ValueError("Authored dinner scene integrity mismatch")
            xml = (ASSETS / "scene.xml").read_text()
            (self.directory / "scene.xml").write_text(xml)
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
        buffer = np.empty(mujoco.mj_sizeModel(self._env.model), dtype=np.uint8)
        mujoco.mj_saveModel(self._env.model, buffer=buffer)
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
            attempt_id=attempt_id,
            observation_sequence=observation.sequence,
            applied=False,
            partial_physics=False,
        )
        before = float(self._env.data.time)
        try:
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
        self, attempt_id: str, observation: Observation, *, executor_outcome: str, reason: str
    ):
        """Only trusted executor termination logic may call this; no automatic scoring."""
        self._validate_capture(observation)
        result = self.supervisor.finish(
            attempt_id, observation, executor_outcome=executor_outcome, reason=reason
        )
        if executor_outcome == "succeeded":
            self._terminal_observation, self._terminal_state = observation, self._state
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
            self._env.stop()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self.supervisor.snapshot().active is not None:
                self.supervisor.cancel("Physical worker closed before attempt termination")
            else:
                self.control.clear()
        finally:
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
