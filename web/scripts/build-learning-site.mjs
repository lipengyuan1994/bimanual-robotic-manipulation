import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const webRoot = resolve(import.meta.dirname, "..");
const projectRoot = resolve(webRoot, "..");
const outputRoot = resolve(webRoot, "dist-learning");
const repositoryUrl =
  "https://github.com/lipengyuan1994/bimanual-robotic-manipulation";
const sourceRef = process.env.LEARNING_SITE_SOURCE_REF || "main";
const repositoryFile = (path) => `${repositoryUrl}/blob/${sourceRef}/${path}`;

const replacements = new Map([
  ['href="../docs/STATUS.md"', `href="${repositoryFile("docs/STATUS.md")}"`],
  [
    'href="../docs/SKILL_TRAINING.md"',
    `href="${repositoryFile("docs/SKILL_TRAINING.md")}"`,
  ],
  [
    'href="../docs/HANDOFF_FAILURE_ANALYSIS.md"',
    `href="${repositoryFile("docs/HANDOFF_FAILURE_ANALYSIS.md")}"`,
  ],
  ['href="../README.md"', 'href="../index.html"'],
  ['href="../docs/LEARNING.md"', 'href="../index.html#learning-path"'],
  ['href="../docs/SETUP.md"', `href="${repositoryFile("docs/SETUP.md")}"`],
  ['href="../RESOURCES.md"', `href="${repositoryFile("RESOURCES.md")}"`],
  [
    'href="../docs/ARCHITECTURE.md"',
    `href="${repositoryFile("docs/ARCHITECTURE.md")}"`,
  ],
  ['href="../docs/EVIDENCE.md"', `href="${repositoryFile("docs/EVIDENCE.md")}"`],
  [
    'href="../docs/REQUIREMENTS.md"',
    `href="${repositoryFile("docs/REQUIREMENTS.md")}"`,
  ],
  [
    'href="../docs/DEPLOYMENT.md"',
    `href="${repositoryFile("docs/DEPLOYMENT.md")}"`,
  ],
]);

const lessonPages = [
  "lessons/0001-observe-act-step.html",
  "lessons/0002-frames-and-reach.html",
  "lessons/0003-contacts-grasps-handoffs.html",
  "lessons/0004-demonstrations-and-act.html",
  "lessons/0005-supervision-and-recovery.html",
  "lessons/0006-evaluation-and-uncertainty.html",
  "lessons/0007-openvino-and-benchmarks.html",
];

async function copyPage(relativePath) {
  const source = resolve(projectRoot, relativePath);
  let page = await readFile(source, "utf8");
  for (const [from, to] of replacements) page = page.replaceAll(from, to);
  await writeFile(resolve(outputRoot, relativePath), page);
}

function indexPage() {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bimanual Manipulation Lab · Learning</title>
  <link rel="stylesheet" href="assets/learning/lesson.css">
</head>
<body>
  <main class="lesson">
    <nav><a href="index.html">Bimanual Manipulation Lab</a> / Learning</nav>
    <p class="eyebrow">Preparation curriculum · Simulation only</p>
    <h1>Learn robotic manipulation<br>from the ground up.</h1>
    <p class="intro">Short, practical lessons connected to a real MuJoCo project.
    Start with the feedback loop, then learn how frames make robot motion precise.</p>
    <div class="callout"><strong>Current scope.</strong> This public site teaches the
    project’s preparation material. It does not claim a completed dinner-table
    robot, a trained policy, or Intel validation.</div>
    <h2 id="learning-path">Learning path</h2>
    <ol>
      <li><a href="lessons/0001-observe-act-step.html"><strong>Lesson 01 — Observe, act, and step time</strong></a><br>
      Understand observations, actions, control intervals, physics steps, and what a runtime check establishes.</li>
      <li><a href="lessons/0002-frames-and-reach.html"><strong>Lesson 02 — Frames and reachable positions</strong></a><br>
      Use an interactive two-link sketch to see how coordinates, frames, and reachability relate.</li>
      <li><a href="lessons/0003-contacts-grasps-handoffs.html"><strong>Lesson 03 — Contacts, grasps, and hand-offs</strong></a><br>
      See why a grasp and hand-off require physical evidence, not a convincing animation.</li>
      <li><a href="lessons/0004-demonstrations-and-act.html"><strong>Lesson 04 — Demonstrations and ACT</strong></a><br>
      Learn the aligned observation-action records that a bounded learned policy needs.</li>
      <li><a href="lessons/0005-supervision-and-recovery.html"><strong>Lesson 05 — Supervision and recovery</strong></a><br>
      Separate visual reasoning, bounded action policies, and the component that can stop.</li>
      <li><a href="lessons/0006-evaluation-and-uncertainty.html"><strong>Lesson 06 — Evaluation and uncertainty</strong></a><br>
      Freeze test conditions and report every outcome before trusting a score.</li>
      <li><a href="lessons/0007-openvino-and-benchmarks.html"><strong>Lesson 07 — OpenVINO and benchmarks</strong></a><br>
      Measure actual device selection and complete application timing on Intel hardware.</li>
    </ol>
    <h2>Keep nearby</h2>
    <p><a href="demo/index.html">Open the product demo</a> ·
    <a href="reference/glossary.html">Robotics vocabulary reference</a> ·
    <a href="reference/training-evidence.html">Training evidence reference</a></p>
    <h2>Build with the project</h2>
    <p>The lessons correspond to a local, native-Apple-Silicon MuJoCo learning lab.
    The exact setup, evidence boundaries, and current implementation status live in
    the <a href="${repositoryUrl}">source repository</a>.</p>
    <footer>Published from the repository’s tracked learning sources. Interactive
    answers stay in your browser; this static site collects no learner data.</footer>
  </main>
</body>
</html>`;
}

function demoPage() {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>TableMate · Product demo</title><style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;color:#102a43;background:#f5f7f8;line-height:1.5}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1120px;margin:auto;padding:28px 24px 64px}nav{display:flex;justify-content:space-between;align-items:center;margin-bottom:64px;font-weight:700}nav a{color:#087f8c;text-decoration:none}.eyebrow{color:#087f8c;font-size:.78rem;letter-spacing:.12em;font-weight:800}.hero{display:grid;grid-template-columns:1.05fr .95fr;gap:56px;align-items:center}.hero h1{font-size:clamp(2.6rem,6vw,5rem);line-height:1.02;margin:12px 0 20px;letter-spacing:-.05em}.lede{font-size:1.25rem;color:#52677d;max-width:600px}.hero img{width:100%;border-radius:18px;box-shadow:0 20px 50px #102a4330}.button{display:inline-block;background:#087f8c;color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:700;margin-top:12px}.section{margin-top:88px}.section h2{font-size:2rem;margin:8px 0 24px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{background:#fff;border:1px solid #dce5ea;border-radius:14px;padding:22px}.card h3{margin:0 0 8px}.card p{color:#52677d;margin:0}.evidence{display:grid;grid-template-columns:1fr 1fr;gap:28px;align-items:start}.evidence video{width:100%;border-radius:12px;background:#102a43}.badge{display:inline-block;border-radius:999px;padding:5px 10px;background:#dff5f2;color:#087f8c;font-size:.78rem;font-weight:800}.notice{border-left:4px solid #f0a202;background:#fff8e6;padding:16px 18px;color:#5d4b22}footer{margin-top:80px;padding-top:22px;border-top:1px solid #dce5ea;color:#52677d}@media(max-width:760px){.hero,.evidence{grid-template-columns:1fr}.grid{grid-template-columns:1fr}nav{margin-bottom:36px}}
</style></head><body><main class="wrap"><nav><a href="../index.html">Bimanual Manipulation Lab</a><a href="https://github.com/lipengyuan1994/bimanual-robotic-manipulation">Source ↗</a></nav>
<section class="hero"><div><p class="eyebrow">TABLEMATE · PRODUCT DEMO</p><h1>From observation to motion.</h1><p class="lede">An inspectable MuJoCo workstation for coordinating two SO-101 arms around a dinner table.</p><a class="button" href="#evidence">Watch the evidence ↓</a></div><img src="../assets/submission/tablemate-cover.png" alt="Two simulated robot arms coordinating around dinner table objects"></section>
<section class="section"><p class="eyebrow">HOW IT WORKS</p><h2>Bounded autonomy, visible decisions.</h2><div class="grid"><article class="card"><span class="badge">01 · Observe</span><h3>Camera-grounded context</h3><p>Overhead and wrist views feed a planner while joint observations keep the action interface explicit.</p></article><article class="card"><span class="badge">02 · Plan</span><h3>Supervisor-owned steps</h3><p>Supported skills, prerequisites, arm ownership, timeouts, and cancellation are checked before execution.</p></article><article class="card"><span class="badge">03 · Act</span><h3>Contact-aware control</h3><p>MuJoCo contacts represent grasps and hand-offs. Invalid or unsafe actions stop the run.</p></article></div></section>
<section class="section evidence" id="evidence"><div><p class="eyebrow">RECORDED EVIDENCE</p><h2>A safe stop is a result.</h2><p>These frames show a sealed contact-based teacher correction run. The repository preserves synchronized observations, actions, contacts, and outcome records for inspection.</p><div class="notice"><strong>Evidence boundary.</strong> The learned ACT candidate trained for 20,000 updates but stopped at the workbench-overlap guard during physical evaluation. Full learned dinner completion and Intel/OpenVINO execution are not claimed.</div></div><div><video controls preload="metadata" poster="../assets/submission/tablemate-cover.png"><source src="../assets/submission/tablemate-teacher-evidence.mp4" type="video/mp4">Your browser does not support video playback.</video><p><small>58-second MuJoCo teacher-evidence replay · source and manifests in the repository</small></p></div></section>
<section class="section"><p class="eyebrow">REPRODUCE</p><h2>Inspect the implementation.</h2><p>Use the <a href="https://github.com/lipengyuan1994/bimanual-robotic-manipulation/blob/main/docs/SUBMISSION_HANDOFF.md">submission handoff</a> for exact evidence boundaries, local commands, and artifact lineage. Explore the <a href="../index.html#learning-path">learning path</a> to understand the system from first principles.</p></section>
<footer>Simulation only · $0 committed compute spend · Built for the AI Infra Summit online track</footer></main></body></html>`;
}

await rm(outputRoot, { recursive: true, force: true });
await mkdir(outputRoot, { recursive: true });
await cp(resolve(projectRoot, "assets"), resolve(outputRoot, "assets"), { recursive: true });
await mkdir(resolve(outputRoot, "lessons"), { recursive: true });
await mkdir(resolve(outputRoot, "reference"), { recursive: true });
await mkdir(resolve(outputRoot, "demo"), { recursive: true });
await Promise.all([
  ...lessonPages.map(copyPage),
  copyPage("reference/glossary.html"),
  copyPage("reference/training-evidence.html"),
]);
await writeFile(resolve(outputRoot, "index.html"), indexPage());
await writeFile(resolve(outputRoot, "demo/index.html"), demoPage());
