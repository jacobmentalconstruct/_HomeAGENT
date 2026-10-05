"""Run the chat page's script under Node with a minimal fake DOM, to test its pure functions.

`run_page_js(body)` evaluates `body` (JavaScript) with `api` bound to the functions the page script returns,
and returns whatever `body` passes to `out(...)` as parsed JSON. Skipped by callers when node is missing.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "src" / "agent_harness" / "interfaces" / "page.html"
HAVE_NODE = shutil.which("node") is not None

_PRELUDE = r"""
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const script = /<script>([\s\S]*)<\/script>/.exec(html)[1];
const els = {};
function stub(tag) {
  const o = { tag, children: [], style: {}, className: "", _text: "", value: "", options: [], disabled: false,
    classList: { add() {}, remove() {}, toggle() {} }, scrollTop: 0, scrollHeight: 0,
    appendChild(c) { this.children.push(c); return c; }, remove() {}, focus() {}, insertBefore() {},
    addEventListener() {}, requestSubmit() {}, setAttribute(k, v) { this[k] = v; } };
  Object.defineProperty(o, "innerHTML", { set() { throw new Error("innerHTML used"); }, get() { return ""; } });
  Object.defineProperty(o, "textContent", { get() { return this._text; },
    set(v) { this._text = String(v); this.children = []; } });
  return o;
}
const document = { getElementById(id) { return els[id] || (els[id] = stub("#" + id)); },
                   createElement(tag) { return stub(tag); }, querySelectorAll() { return []; } };
const names = process.argv[3];
const api = new Function("document", "location", "navigator", "localStorage", "history", "window",
  script + "\nreturn { " + names + " };")(document,
  { protocol: "file:", hash: "", origin: "", pathname: "", search: "" }, { userAgent: "" },
  { getItem() { return null; }, setItem() {} }, { replaceState() {} }, { innerHeight: 800 });
let result;
function out(value) { result = value; }
"""


def run_page_js(body: str, names: str = "showWindow") -> object:
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / "harness.js"
        harness.write_text(_PRELUDE + body + "\nconsole.log(JSON.stringify(result));\n", encoding="utf-8")
        done = subprocess.run(["node", str(harness), str(PAGE), names], capture_output=True, text=True, timeout=30)
    if done.returncode != 0:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)
