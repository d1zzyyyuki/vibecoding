#!/usr/bin/env node
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const extensionRoot = path.resolve(here, "..", "extension");
const fixturePath = path.join(here, "fixtures", "hltv-fixture.html");
const manifest = JSON.parse(fs.readFileSync(path.join(extensionRoot, "manifest.json"), "utf8"));
const rules = JSON.parse(fs.readFileSync(path.join(extensionRoot, "rules.json"), "utf8"));

let passed = 0;
let failed = 0;

function check(name, condition, detail = "") {
  if (condition) {
    passed += 1;
    console.log(`PASS  ${name}${detail ? " :: " + detail : ""}`);
  } else {
    failed += 1;
    console.log(`FAIL  ${name}${detail ? " :: " + detail : ""}`);
  }
}

function summary() {
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed === 0 ? 0 : 1);
}

// Static contract checks
check("manifest is MV3", manifest.manifest_version === 3);
check("manifest version is 1.2.1", manifest.version === "1.2.1", manifest.version);
check("stable extension key is present", typeof manifest.key === "string" && manifest.key.length > 100);
check("content script is top-frame only", !manifest.content_scripts?.[0]?.all_frames);
check("only HLTV host permission is declared", JSON.stringify(manifest.host_permissions) === JSON.stringify(["*://*.hltv.org/*"]));
check("rules.json has declarative rules", Array.isArray(rules) && rules.length > 0, String(rules.length) + " rules");
check("rules target HLTV pages", rules.every((rule) => JSON.stringify(rule).includes("hltv.org") || JSON.stringify(rule.condition || {}).includes("hltv.org")));

const edgeCandidates = [
  process.env.EDGE_EXE,
  process.env["ProgramFiles(x86)"] && path.join(process.env["ProgramFiles(x86)"], "Microsoft", "Edge", "Application", "msedge.exe"),
  process.env.ProgramFiles && path.join(process.env.ProgramFiles, "Microsoft", "Edge", "Application", "msedge.exe")
].filter(Boolean);
const edge = edgeCandidates.find((candidate) => fs.existsSync(candidate));

if (!edge) {
  console.log("\nSKIP  Edge not found; browser fixture was not executed.");
  summary();
}

const html = fs.readFileSync(fixturePath, "utf8");
const server = http.createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(html);
});

await new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(0, "127.0.0.1", resolve);
});
const port = server.address().port;
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "hltv-adb-ci-"));
const url = `http://hltv.org:${port}/fixture.html`;
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const edgeArgs = [
  "--headless=new",
  "--no-sandbox",
  "--disable-gpu",
  "--disable-gpu-sandbox",
  "--disable-background-networking",
  "--disable-component-update",
  "--disable-sync",
  "--metrics-recording-only",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  `--load-extension=${extensionRoot}`,
  "--host-resolver-rules=MAP hltv.org 127.0.0.1",
  "about:blank"
];
const devtoolsFile = path.join(profile, "DevToolsActivePort");
const child = spawn(edge, edgeArgs, { stdio: "ignore", windowsHide: true });
let dom = "";

try {
  let port = "";
  for (let i = 0; i < 150; i += 1) {
    if (fs.existsSync(devtoolsFile)) {
      port = fs.readFileSync(devtoolsFile, "utf8").trim().split(/\r?\n/)[0];
      break;
    }
    await delay(100);
  }
  if (!port) throw new Error("DevToolsActivePort was not created");

  const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  const page = targets.find((target) => target.type === "page");
  if (!page) throw new Error("no page target");

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });

  let nextId = 1;
  const pending = new Map();
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    const waiter = pending.get(message.id);
    if (waiter) {
      pending.delete(message.id);
      waiter(message);
    }
  });
  const send = (method, params = {}) => new Promise((resolve) => {
    const id = nextId++;
    pending.set(id, resolve);
    ws.send(JSON.stringify({ id, method, params }));
  });

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Page.navigate", { url });
  await delay(2500);
  const evaluated = await send("Runtime.evaluate", {
    expression: "document.documentElement.outerHTML",
    returnByValue: true
  });
  dom = evaluated.result?.result?.value || "";
  ws.close();

  if (child.pid) {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      timeout: 10000,
      windowsHide: true
    });
  }
} catch (error) {
  console.log("FAIL  Edge fixture run", error.message);
  failed += 1;
} finally {
  try { child.kill(); } catch {}
  server.close();
  try {
    fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  } catch {
    // Edge may still hold the profile briefly; the temp directory is safe to leave behind.
  }
}

if (!dom) {
  failed += 1;
  summary();
}
check("HLTV logo container is kept", dom.includes('class="logoCon"') && !/class="logoCon"[^>]*style="[^"]*display:\s*none/.test(dom));
check("partner link is hidden", /data-hl-ad="1"[^>]*href="\/out2\/partner"|href="\/out2\/partner"[^>]*data-hl-ad="1"/.test(dom));
check("ad element is hidden", dom.includes('data-hl-ad="1"'));
check("betting/odds section is kept", dom.includes("Odds 1.85") && !/class="betting"[^>]*style="[^"]*display:\s*none/.test(dom));
check("comment is translated", dom.includes("参考翻译：尽力了"));
check("login prompt is not translated", !dom.includes("参考翻译：登录") && !dom.includes("参考翻译：Login"));
check("dispatch headline is fixed", dom.includes("PARIVISION战胜LVG，晋级Stage 2"));
check("outlast headline is fixed", dom.includes("Imperial战胜Wildcard，晋级Stage 2"));
check("olofmeister nickname is added", dom.includes("（奥拉夫）"));
check("watermark is present in top page", dom.includes('id="hltv-adblocker-watermark"') && dom.includes("by cbd"));
check("translated ad-like text is not hidden", dom.includes('id="keep-translation"') && !/id="keep-translation"[^>]*style="[^"]*display:\s*none/.test(dom));

summary();
