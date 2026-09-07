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
  const filename = ["error.txt", "doctor.json", "trajectory.csv"].find(
    (name) => run.files?.[name],
  );
  return filename ? (
    <a href={`/api/runs/${run.run_id}/files/${filename}`}>
      {filename === "error.txt"
        ? "Error"
        : filename === "trajectory.csv"
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
      run.kind === "preparation_pendulum" &&
      run.integrity === "verified" &&
      run.outcome === "completed",
  );
  const selected = labs.find((run) => run.run_id === selectedId) ?? labs[0];
  const doctor = runs.find(
    (run) => run.kind === "preparation_runtime" && run.integrity === "verified",
  );
  const mps = doctor?.metrics?.mps as { status?: string } | undefined;
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
            <strong>Preparation lab</strong>
            <small>Dinner-table control is pending</small>
          </div>
          <div>
            <span className="fact-label">LOCAL ML PROBE</span>
            <strong>
              {mps?.status === "passed"
                ? "MPS + CPU checked"
                : "Awaiting recorded probe"}
            </strong>
            <small>Arithmetic only · model tests come later</small>
          </div>
          <div>
            <span className="fact-label">FINAL INTEL TARGET</span>
            <strong>
              {project?.intel_validated ? "Validated" : "Access pending"}
            </strong>
            <small>Core Ultra Series 2 / 3</small>
          </div>
        </div>
        <section className="lab-grid" aria-label="Preparation simulation">
          <div className="simulation-card">
            <div className="card-heading">
              <div>
                <span className="small-label">MUJOCO LEARNING LAB</span>
                <h2>One joint. A complete loop.</h2>
              </div>
              <span className="tag">Recorded simulation</span>
            </div>
            <div className="replay">
              {replay ? (
                <img
                  src={replay}
                  alt="Actual MuJoCo replay of the driven pendulum"
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
              <span>Generic pendulum · no learned policy</span>
            </div>
          </div>
          <div className="next-card">
            <span className="small-label">MAKE IT CONCRETE</span>
            <h2>
              Run. Observe.
              <br />
              Change one thing.
            </h2>
            <p>
              Watch a real physics trace, then increase damping and compare the
              motion.
            </p>
            <code>.venv/bin/bimanual lab --seed 7 --seconds 4</code>
            <a className="text-link" href="/read/docs/SETUP.md">
              Open setup & commands <span>→</span>
            </a>
            <div className="scope-note">
              <strong>What this establishes</strong>
              <p>
                Simulation and rendering work. Grasping, task reasoning, and
                Intel deployment each need their own evidence.
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
              <h2>Preparation evidence.</h2>
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
            These runs validate preparation tools. They are not manipulation
            trials or judging scores.{" "}
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
