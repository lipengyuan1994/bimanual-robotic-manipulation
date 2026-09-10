import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Milestone = { id: string; title: string; state: string; detail: string };
type Project = {
  title: string;
  phase_label: string;
  phase: string;
  summary: string;
  manipulation_available: boolean;
  intel_validated: boolean;
  compute_budget_usd: number;
  milestones: Milestone[];
  blockers: { id: string; title: string; detail: string }[];
  lessons: {
    number: string;
    title: string;
    duration: string;
    href: string;
    detail: string;
  }[];
};
type Run = {
  run_id: string;
  integrity: string;
  kind?: string;
  outcome?: string;
  created_at?: string;
  files?: Record<string, string>;
  metrics?: Record<string, unknown>;
  error?: string;
};

async function readJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok)
    throw new Error(`Unable to load ${url}: HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function RunLink({ run, select }: { run: Run; select: (id: string) => void }) {
  if (run.integrity !== "verified")
    return <span title={run.error}>Check local files</span>;
  if (run.files?.["replay.gif"])
    return <button onClick={() => select(run.run_id)}>Replay ↑</button>;
  const filename = ["error.txt", "failure.txt", "metrics.json", "doctor.json", "trajectory.csv", "observations.jsonl", "act_config.json"].find(
    (name) => run.files?.[name],
  );
  return filename ? (
    <a href={`/api/runs/${run.run_id}/files/${filename}`}>
      {filename === "error.txt" || filename === "failure.txt"
        ? "Error"
        : filename === "trajectory.csv" || filename === "observations.jsonl"
          ? "Trace"
          : "Report"}{" "}
      ↗
    </a>
  ) : (
    <span>No preview</span>
  );
}

function App() {
  const [project, setProject] = useState<Project | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    setError("");
    Promise.all([
      readJson<Project>("/api/project", controller.signal),
      readJson<Run[]>("/api/runs", controller.signal),
    ])
      .then(([data, history]) => {
        if (active) {
          setProject(data);
          setRuns(history);
        }
      })
      .catch((reason: Error) => {
        if (active)
          setError(
            controller.signal.aborted
              ? "Loading timed out. Try refresh."
              : reason.message,
          );
      })
      .finally(() => window.clearTimeout(timeout));
    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [revision]);
  const labs = runs.filter(
    (run) =>
      ["preparation_pendulum", "dual_arm_foundation", "contact_grasp_teacher", "contact_placement_teacher", "contact_handoff_teacher", "contact_drawer_teacher", "act_policy_rollout"].includes(run.kind ?? "") &&
      run.integrity === "verified",
  );
  const selected = labs.find((run) => run.run_id === selectedId) ?? labs.find((run) => run.files?.["replay.gif"]) ?? labs[0];
  const isHandoff = selected?.kind === "contact_handoff_teacher";
  const isLearned = selected?.kind === "act_policy_rollout";
  const isDrawer = selected?.kind === "contact_drawer_teacher";
  const isPlacement = selected?.kind === "contact_placement_teacher";
  const isGrasp = selected?.kind === "contact_grasp_teacher" || isPlacement || isHandoff || isDrawer || isLearned;
  const isDual = selected?.kind === "dual_arm_foundation" || isGrasp;
  const doctor = runs.find(
    (run) => run.kind === "preparation_runtime" && run.integrity === "verified",
  );
  const mps = doctor?.metrics?.mps as { status?: string } | undefined;
  const actProbe = runs.find(run => run.kind === "act_runtime_probe" && run.integrity === "verified" && run.outcome === "completed");
  const replay = selected?.files?.["replay.gif"]
    ? `/api/runs/${selected.run_id}/files/replay.gif`
    : null;
  return (
    <div className="workspace">
      <aside className="sidebar">
        <a className="brand" href="#top">
          <svg viewBox="0 0 38 34" aria-hidden="true">
            <path d="M5 29V18L15 8M33 29V18L23 8" />
            <circle cx="17" cy="6" r="3" />
            <circle cx="21" cy="6" r="3" />
          </svg>
          <span>
            Bimanual<span className="brand-sub">MANIPULATION LAB</span>
          </span>
        </a>
        <div className="workspace-label">PROJECT WORKSPACE</div>
        <nav>
          <a className="active" href="#top">
            <span>◉</span> Overview
          </a>
          <a href="#learn">
            <span>▤</span> Learn the basics
          </a>
          <a href="#evidence">
            <span>◷</span> Run evidence
          </a>
          <a href="#roadmap">
            <span>↗</span> Roadmap
          </a>
          <a href="/read/docs/README.md">
            <span>▧</span> Documentation
          </a>
        </nav>
        <div className="sidebar-note">
          <span className="tiny-dot" /> Simulation first
          <p>
            One step at a time.
            <br />
            Every result inspectable.
          </p>
        </div>
        <a className="sidebar-footer" href="/read/docs/ORGANIZER_QUESTIONS.md">
          Organizer questions <span>↗</span>
        </a>
      </aside>
      <main id="top">
        <header>
          <div className="breadcrumb">
            WORKSPACE <span>/</span> OVERVIEW
          </div>
          <a href="/read/docs/STATUS.md" className="status-pill">
            <span className="tiny-dot" />
            {project?.phase_label ?? "Loading workspace"}
          </a>
        </header>
        {error && (
          <div className="error" role="alert">
            {error}{" "}
            <button onClick={() => setRevision((n) => n + 1)}>Retry</button>
          </div>
        )}
        <section className="intro">
          <div>
            <p className="eyebrow">AI INFRA SUMMIT · ONLINE TRACK</p>
            <h1>
              From observation
              <br />
              to motion.
            </h1>
            <p className="lede">
              A workspace for building—and understanding—
              <br className="desktop-break" /> dependable two-arm manipulation.
            </p>
          </div>
          <a
            className="button primary"
            href="/read/lessons/0001-observe-act-step.html"
          >
            Start the first lesson <span>↗</span>
          </a>
        </section>
        <div className="facts">
          <div>
            <span className="fact-label">CURRENT SCOPE</span>
            <strong>{project?.phase_label ?? "Loading"}</strong>
            <small>Dinner-table control is pending</small>
          </div>
          <div>
            <span className="fact-label">LOCAL ML PROBE</span>
            <strong>
              {actProbe ? `ACT on ${String(actProbe.metrics?.actual_device ?? "local device")}` : mps?.status === "passed"
                ? "MPS + CPU checked"
                : "Awaiting recorded probe"}
            </strong>
            <small>{actProbe ? "Runtime checked · task learning unproven" : "Arithmetic only · model tests come later"}</small>
          </div>
          <div>
            <span className="fact-label">FINAL INTEL TARGET</span>
            <strong>
              {project?.intel_validated ? "Validated" : "Access pending"}
            </strong>
            <small>Core Ultra Series 2 / 3</small>
          </div>
        </div>
        <section className="lab-grid" aria-label="Foundation simulation">
          <div className="simulation-card">
            <div className="card-heading">
              <div>
                <span className="small-label">MUJOCO LEARNING LAB</span>
                <h2>{isLearned ? "What did the policy learn?" : isDrawer ? "Grasp the handle. Open the drawer." : isHandoff ? "Grasp. Share. Hand over." : isPlacement ? "Pick up. Carry. Place." : isGrasp ? "Reach. Grasp. Release." : isDual ? "Two arms. Three camera views." : "One joint. A complete loop."}</h2>
              </div>
              <span className="tag">Recorded simulation · {selected?.outcome ?? "no run"}</span>
            </div>
            <div className="replay">
              {replay ? (
                <img
                  src={replay}
                  alt={isDual ? "MuJoCo SO-101 replay: overhead, left wrist, right wrist" : "Actual MuJoCo replay of the driven pendulum"}
                />
              ) : (
                <div className="empty">
                  <span>⌁</span>
                  <h3>
                    {selected
                      ? "This run has no rendered replay"
                      : "Your first run belongs here"}
                  </h3>
                  <p>Run the command below to record a MuJoCo replay.</p>
                </div>
              )}
            </div>
            <div className="sim-footer">
              <span>
                <b>200 Hz</b> physics
              </span>
              <span>
                <b>20 Hz</b> control
              </span>
              <span>{isLearned ? "ACT · training-scene diagnostic" : isDual ? "Dual SO-101 · scripted control" : "Generic pendulum · no learned policy"}</span>
            </div>
            {isGrasp && selected && (
              <p className="scope-note">
                {isDrawer ? "Drawer" : isHandoff ? "Hand-off" : isPlacement ? "Placement" : "Grasp"} test: <strong>{selected.metrics?.[isDrawer ? "drawer_success" : isHandoff ? "handoff_success" : "grasp_success"] === true ? "passed" : "failed"}</strong>.
                {" "}{isLearned ? "Learned left-arm actions from images and joints; right arm held by supervisor. This is a training-scene test." : "Scripted teacher with simulator truth; full dinner task remains untested."}
                {" "}<a href={`/api/runs/${selected.run_id}/files/scoring-truth.jsonl`}>Inspect contact evidence →</a>
              </p>
            )}
          </div>
          <div className="next-card">
            <span className="small-label">MAKE IT CONCRETE</span>
            <h2>
              Run. Observe.
              <br />
              Change one thing.
            </h2>
            <p>
              Watch an arm lift a block, carry it to a separate place, and release it using physical contacts.
            </p>
            <code>.venv/bin/bimanual grasp --destination -.15 .08</code>
            <a className="text-link" href="/read/docs/CONTACT_GRASP.md">
              Open contact-grasp walkthrough <span>→</span>
            </a>
            <div className="scope-note">
              <strong>What this establishes</strong>
              <p>
                These are bounded contact skills. Utensil retrieval, plate and cup placement, learned
                control, task reasoning, and Intel deployment remain to be built and tested.
              </p>
            </div>
          </div>
        </section>
        <section id="learn">
          <div className="section-heading">
            <div>
              <p className="eyebrow">BUILD YOUR UNDERSTANDING</p>
              <h2>Learn alongside the code.</h2>
            </div>
            <a href="/read/docs/LEARNING.md">Full learning path →</a>
          </div>
          <div className="lesson-grid">
            {project?.lessons.map((lesson) => (
              <a className="lesson-card" href={lesson.href} key={lesson.number}>
                <div className="lesson-top">
                  <span>{lesson.number}</span>
                  <small>{lesson.duration} · BEGINNER</small>
                </div>
                <h3>{lesson.title}</h3>
                <p>{lesson.detail}</p>
                <div className="lesson-link">
                  Open lesson <span>↗</span>
                </div>
              </a>
            ))}
          </div>
        </section>
        <section id="evidence">
          <div className="section-heading">
            <div>
              <p className="eyebrow">RECORDED, THEN VERIFIED</p>
              <h2>Run evidence.</h2>
            </div>
            <button
              className="refresh"
              onClick={() => setRevision((n) => n + 1)}
            >
              ↻ Refresh
            </button>
          </div>
          <div className="evidence-table">
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Type</th>
                  <th>Outcome</th>
                  <th>Integrity</th>
                  <th>Inspect</th>
                </tr>
              </thead>
              <tbody>
                {runs.length === 0 ? (
                  <tr>
                    <td colSpan={5}>
                      No sealed runs yet. Record a lab or doctor run to begin.
                    </td>
                  </tr>
                ) : (
                  runs.map((run) => (
                    <tr key={run.run_id}>
                      <td>
                        <code>{run.run_id}</code>
                      </td>
                      <td>
                        {run.kind === "preparation_pendulum"
                          ? "Pendulum lab"
                          : run.kind === "dual_arm_foundation"
                            ? "Dual-arm foundation"
                          : run.kind === "contact_grasp_teacher"
                            ? "Contact grasp teacher"
                          : run.kind === "contact_placement_teacher"
                            ? "Contact placement teacher"
                          : run.kind === "contact_handoff_teacher"
                            ? "Contact hand-off teacher"
                          : run.kind === "contact_drawer_teacher"
                            ? "Contact drawer teacher"
                          : run.kind === "act_runtime_probe"
                            ? "ACT runtime probe"
                          : run.kind === "act_training"
                            ? "ACT training"
                          : run.kind === "act_policy_rollout"
                            ? "ACT learned rollout"
                          : run.kind === "preparation_runtime"
                            ? "Runtime probe"
                            : "Unreadable run"}
                      </td>
                      <td>
                        <span
                          className={`result ${run.outcome === "failed" ? "failed" : ""}`}
                        >
                          {run.outcome ?? "Unavailable"}
                        </span>
                      </td>
                      <td>{run.integrity}</td>
                      <td>
                        <RunLink
                          run={run}
                          select={(id) => {
                            setSelectedId(id);
                            document
                              .querySelector(".simulation-card")
                              ?.scrollIntoView({ behavior: "smooth" });
                          }}
                        />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <p className="table-note">
            These development runs cover runtime checks and bounded contact skills.
            They are not full dinner-task evaluations or judging scores.{" "}
            <a href="/read/docs/EVIDENCE.md">Evidence protocol ↗</a>
          </p>
        </section>
        <section id="roadmap">
          <div className="section-heading">
            <div>
              <p className="eyebrow">THE PATH TO A RELIABLE SYSTEM</p>
              <h2>What comes next.</h2>
            </div>
            <a href="/read/docs/ROADMAP.md">Acceptance checks →</a>
          </div>
          <div className="milestones">
            {project?.milestones.map((m) => (
              <div className="milestone" key={m.id}>
                <span className={`milestone-id ${m.state}`}>{m.id}</span>
                <div>
                  <h3>
                    {m.title}
                    <small>{m.state.replace("_", " ")}</small>
                  </h3>
                  <p>{m.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
        <footer>
          <span>Local workspace · $0 committed compute spend</span>
          <a href="/read/docs/PLAN.md">Read the accepted plan ↗</a>
        </footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
