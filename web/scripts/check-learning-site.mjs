import { access, readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..", "dist-learning");
const required = [
  "index.html",
  "assets/learning/lesson.css",
  "assets/learning/lesson.js",
  "lessons/0001-observe-act-step.html",
  "lessons/0002-frames-and-reach.html",
  "reference/glossary.html",
];
for (const path of required) await access(resolve(root, path));

const home = await readFile(resolve(root, "index.html"), "utf8");
if (!home.includes('href="lessons/0001-observe-act-step.html"')) {
  throw new Error("Learning-site index does not link to lesson 01");
}
const lesson = await readFile(resolve(root, "lessons/0001-observe-act-step.html"), "utf8");
if (lesson.includes("../README.md") || lesson.includes("../docs/LEARNING.md")) {
  throw new Error("Generated lessons still contain repository-only navigation");
}
console.log(`Static learning site verified: ${required.length} required files`);
