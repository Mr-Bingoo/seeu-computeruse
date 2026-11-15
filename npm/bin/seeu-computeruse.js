#!/usr/bin/env node
// SeeU launcher: some AI apps (e.g. Qwen / 千问) only accept MCP servers started with `npx`.
// This tiny package finds the SeeU you installed (it leaves a note at ~/.seeu/seeu_server.json
// when you run `python3 -m seeu install ...` or whenever its MCP server starts) and runs it,
// passing stdin/stdout straight through. No dependencies, nothing is downloaded.
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

// Some apps (Qwen / 千问 5.2) start tools with HOME pointed at a folder of their own. Python then can't
// find the libraries installed with `pip install --user`, and ~/.seeu isn't where we look. So use the
// account's real home folder (from the system's user record, not $HOME) and hand that to SeeU.
function realHome() {
  try {
    const h = os.userInfo().homedir;
    if (h) return h;
  } catch (e) { /* fall back below */ }
  return os.homedir();
}

function homes() {
  const out = [];
  if (process.env.SEEU_HOME) out.push(process.env.SEEU_HOME);
  out.push(path.join(realHome(), ".seeu"));
  return out;
}

// Only start what the note says if it really is a Python running SeeU's own MCP server
// (so a tampered note can't make this launcher run some other program).
function looksRight(d) {
  if (!d || typeof d.python !== "string" || typeof d.server !== "string") return false;
  if (!/^python(w)?(\d+(\.\d+)*)?(t|-intel64|-arm64|-x86_64|-universal2)?(\.exe)?$/i.test(path.basename(d.python))) return false;  // python3, python3.13t, python3.12-intel64…
  const s = d.server.replace(/\\/g, "/");
  if (!/\/seeu\/(win\/)?mcp_server\.py$/i.test(s)) return false;
  return fs.existsSync(d.python) && fs.existsSync(d.server);
}

function findSeeU() {
  for (const h of homes()) {
    const f = path.join(h, "seeu_server.json");
    try {
      const d = JSON.parse(fs.readFileSync(f, "utf8"));
      if (looksRight(d)) return d;
    } catch (e) { /* not there / unreadable: try the next one */ }
  }
  return null;
}

const d = findSeeU();
if (!d) {
  process.stderr.write(
    "SeeU is not installed on this computer yet (or has never been set up).\n" +
    "Install it first: https://github.com/Mr-Bingoo/seeu-computeruse/blob/main/README.en.md#install\n" +
    "then run once:  python3 -m seeu install qianwen   (on Windows: python -m seeu install qianwen)\n" +
    "还没装 SeeU(或还没接入过)。先按上面的链接安装，再运行一次 python3 -m seeu install qianwen。\n");
  process.exit(1);
}

const env = Object.assign({}, process.env);
const home = realHome();
if (home && env.HOME !== home) {
  env.SEEU_HOST_HOME = env.HOME || "";   // keep what the app set, in case anyone needs it
  env.HOME = home;
}
const child = spawn(d.python, [d.server], { stdio: "inherit", env });
child.on("error", (e) => {
  process.stderr.write(`Could not start SeeU (${d.python} ${d.server}): ${e.message}\n`);
  process.exit(1);
});
child.on("exit", (code) => process.exit(code === null ? 1 : code));
for (const s of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  try { process.on(s, () => child.kill(s)); } catch (e) { /* SIGHUP is not on Windows */ }
}
