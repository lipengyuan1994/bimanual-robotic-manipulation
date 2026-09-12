import { access, readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..", "dist-learning");
const required = [
  "index.html",
  "assets/learning/lesson.css",
  "assets/learning/lesson.js",
  "lessons/0001-observe-act-step.html",
  "lessons/0002-frames-and-reach.html",
  "lessons/0003-contacts-grasps-handoffs.html",
  "lessons/0004-demonstrations-and-act.html",
  "lessons/0005-supervision-and-recovery.html",
  "lessons/0006-evaluation-and-uncertainty.html",
  "lessons/0007-openvino-and-benchmarks.html",
  "reference/glossary.html",
  "reference/training-evidence.html",
];
for (const path of required) await access(resolve(root, path));

const home = await readFile(resolve(root, "index.html"), "utf8");
if (!home.includes('href="lessons/0001-observe-act-step.html"')) {
  throw new Error("Learning-site index does not link to lesson 01");
}
if (!home.includes('href="lessons/0007-openvino-and-benchmarks.html"')) {
  throw new Error("Learning-site index does not link to lesson 07");
}
for (const path of required.filter((path) => path.startsWith("lessons/") || path.startsWith("reference/"))) {
  const lesson = await readFile(resolve(root, path), "utf8");
  if (
    lesson.includes("../README.md") ||
    lesson.includes("../docs/") ||
    lesson.includes("../RESOURCES.md")
  ) {
    throw new Error(`Generated lesson has repository-only navigation: ${path}`);
  }
}
console.log(`Static learning site verified: ${required.length} required files`);
