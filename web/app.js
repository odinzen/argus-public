// Argus web front-end. The verification core (verify.py, references.py, audit.py)
// runs in the browser via Pyodide, so there is one implementation, not two.
//
// Two modes:
//   structured  - BibTeX or CSL-JSON, exact author-list check (check()).
//   audit       - PDF/Word manuscript; text is extracted in the browser, the
//                 reference list isolated, each entry matched to Crossref (audit()).
// Input can be pasted, or one/many files, or a whole folder (selected or dragged).
// The bibliography never leaves the page; only DOIs / query strings go to Crossref.

const statusEl = document.getElementById("status");
const runBtn = document.getElementById("run");
const inputEl = document.getElementById("input");
const fileEl = document.getElementById("file");
const folderEl = document.getElementById("folder");
const mailtoEl = document.getElementById("mailto");
const resultsEl = document.getElementById("results");
const cardEl = document.getElementById("card");

const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
function setStatus(msg, busy) {
  statusEl.innerHTML = (busy ? '<span class="spinner"></span>' : "") + (msg ? esc(msg) : "");
}

const SUPPORTED = [".bib", ".json", ".txt", ".pdf", ".docx"];

// BibTeX (@) and CSL-JSON ({...} or a JSON array) get the exact check; anything else
// (a plain or numbered reference list) gets the best-effort audit. A leading "[1]" is
// a citation number, not a JSON array, so look at what follows the bracket.
function detectMode(text) {
  const t = text.trimStart(); // trimStart() also drops a leading BOM
  if (t[0] === "@" || t[0] === "{") return "structured";
  if (t[0] === "[") {
    const next = t.slice(1).trimStart()[0];
    if (next === "{" || next === '"' || next === "]") return "structured";
  }
  return "audit";
}

function modeForFile(name, text) {
  const n = name.toLowerCase();
  if (n.endsWith(".pdf") || n.endsWith(".docx")) return "audit";
  if (n.endsWith(".bib") || n.endsWith(".json")) return "structured";
  return detectMode(text); // .txt or anything else: decide by content
}

const GLUE = `
import json
import re as _re
from pathlib import Path
from urllib.parse import quote
from pyodide.http import pyfetch
from argus.references import load_references
from argus.verify import CrossrefRecord, verify, first_page_of
from argus.audit import references_section, split_entries, verdict

_DOI_RE = _re.compile(r"\b(10\.\d{4,9}/\S+)", _re.IGNORECASE)

async def _get(url):
    resp = await pyfetch(url, headers={"Accept": "application/json"})
    if resp.status != 200:
        return None
    return await resp.json()

async def _record(doi, mailto):
    url = "https://api.crossref.org/works/" + quote(doi)
    if mailto:
        url += "?mailto=" + mailto
    try:
        data = await _get(url)
    except Exception:
        data = None
    if not data:
        return None
    msg = data.get("message", {})
    authors = [
        " ".join(x for x in [a.get("given"), a.get("family") or a.get("literal")] if x)
        for a in msg.get("author", [])
    ]
    parts = ((msg.get("issued") or {}).get("date-parts") or [[None]])[0] or [None]
    return CrossrefRecord(
        title=(msg.get("title") or [""])[0],
        authors=[a for a in authors if a],
        year=parts[0],
        volume=msg.get("volume"),
        first_page=first_page_of(msg.get("page")) or None,
    )

async def check(text, mailto):
    name = "/in.bib" if text.lstrip().startswith("@") else "/in.json"
    Path(name).write_text(text, encoding="utf-8")
    try:
        refs = load_references(name)
    except Exception as e:
        return json.dumps({"error": "Could not parse input: " + str(e)})
    out = []
    for r in refs:
        if not r.doi:
            out.append({"key": r.key, "status": "no-doi", "issues": []})
            continue
        rec = await _record(r.doi, mailto)
        if rec is None:
            out.append({"key": r.key, "status": "broken",
                        "issues": ["DOI did not resolve: " + r.doi]})
            continue
        f = verify(r, rec)
        out.append({"key": r.key, "status": f.status, "issues": list(f.issues)})
    return json.dumps({"results": out})

async def audit(text, mailto):
    entries = split_entries(references_section(text))
    out = []
    for e in entries[:200]:
        # If the entry contains a DOI use the direct lookup endpoint.
        # Sending a raw DOI to query.bibliographic returns the nearest keyword
        # match, which is an unrelated paper; direct lookup is unambiguous.
        doi_m = _DOI_RE.search(e)
        if doi_m:
            doi_str = doi_m.group(1).rstrip(".,;)>")
            rec = await _record(doi_str, mailto)
            if rec is None:
                out.append({"entry": e[:160], "status": "no-match", "match": ""})
                continue
            match_str = rec.title + " (" + doi_str + ")" if rec.title else doi_str
            # When the entry is just a DOI (no prose to compare against), skip the
            # title-overlap check in verdict() and report match directly.
            bare = len(e.replace(doi_m.group(1), "").strip()) < 15
            v = "match" if bare else verdict(e, rec.title, rec.authors)
            out.append({"entry": e[:160], "status": v, "match": match_str})
            continue
        url = "https://api.crossref.org/works?rows=1&query.bibliographic=" + quote(e)
        if mailto:
            url += "&mailto=" + mailto
        try:
            data = await _get(url)
            items = (data or {}).get("message", {}).get("items", [])
        except Exception:
            items = []
        if not items:
            out.append({"entry": e[:160], "status": "no-match", "match": ""})
            continue
        it = items[0]
        title = (it.get("title") or [""])[0]
        authors = [a.get("family") or a.get("literal") or "" for a in it.get("author", [])]
        doi = it.get("DOI", "")
        match = title + (" (" + doi + ")" if doi else "") if title else doi
        out.append({"entry": e[:160], "status": verdict(e, title, [a for a in authors if a]),
                    "match": match})
    return json.dumps({"audit": out, "count": len(entries)})
`;

async function loadCore(pyodide) {
  // Production: the published package. Local dev: modules served beside this page.
  try {
    await pyodide.loadPackage("micropip");
    const micropip = pyodide.pyimport("micropip");
    await micropip.install("argus-citations");
    return;
  } catch (e) { /* not on PyPI yet, or offline */ }
  pyodide.FS.mkdirTree("/argus");
  for (const f of ["__init__.py", "verify.py", "references.py", "audit.py"]) {
    const resp = await fetch("argus/" + f);
    if (!resp.ok) throw new Error("could not load core module argus/" + f);
    pyodide.FS.writeFile("/argus/" + f, await resp.text());
  }
  await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/')");
}

async function extractPdf(file) {
  const lib = window.pdfjsLib;
  lib.GlobalWorkerOptions.workerSrc =
    "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js";
  const pdf = await lib.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
  let text = "";
  for (let p = 1; p <= pdf.numPages; p++) {
    const content = await (await pdf.getPage(p)).getTextContent();
    let lastY = null;
    for (const it of content.items) {
      const y = it.transform[5];
      if (lastY !== null && Math.abs(y - lastY) > 2) text += "\n";
      text += it.str + " ";
      lastY = y;
    }
    text += "\n";
  }
  return text;
}

async function extractDocx(file) {
  const zip = await JSZip.loadAsync(await file.arrayBuffer());
  const doc = zip.file("word/document.xml");
  if (!doc) throw new Error("not a Word .docx file");
  const xml = await doc.async("string");
  return xml.split(/<\/w:p>/)
    .map((p) => [...p.matchAll(/<w:t[^>]*>([^<]*)<\/w:t>/g)].map((m) => m[1]).join(""))
    .join("\n");
}

async function readText(file) {
  const n = file.name.toLowerCase();
  if (n.endsWith(".pdf")) return extractPdf(file);
  if (n.endsWith(".docx")) return extractDocx(file);
  return file.text();
}

let pyodide;
async function runPython(mode, text) {
  pyodide.globals.set("UI_TEXT", text);
  pyodide.globals.set("UI_MAILTO", mailtoEl.value.trim());
  const fn = mode === "audit" ? "audit" : "check";
  return JSON.parse(await pyodide.runPythonAsync(`await ${fn}(UI_TEXT, UI_MAILTO)`));
}

function structuredTable(rows) {
  const body = rows.map((r) => {
    const issues = r.issues.length
      ? "<ul>" + r.issues.map((i) => "<li>" + esc(i) + "</li>").join("") + "</ul>" : "";
    return `<tr><td><span class="badge ${r.status}">${r.status}</span></td><td>${esc(r.key)}</td><td>${issues}</td></tr>`;
  }).join("");
  return `<table><thead><tr><th>Status</th><th>Reference</th><th>Issues</th></tr></thead><tbody>${body}</tbody></table>`;
}

function auditTable(rows) {
  const label = { match: "match", check: "check authors", "no-match": "no match" };
  const cls = { match: "ok", check: "suspect", "no-match": "broken" };
  const body = rows.map((r) =>
    `<tr><td><span class="badge ${cls[r.status]}">${label[r.status]}</span></td><td>${esc(r.entry)}</td><td>${esc(r.match)}</td></tr>`
  ).join("");
  return `<table><thead><tr><th>Verdict</th><th>Reference (from your file)</th><th>Crossref match</th></tr></thead><tbody>${body}</tbody></table>`;
}

function sectionHtml(title, mode, data) {
  const head = title ? `<h3 class="file-head">${esc(title)}</h3>` : "";
  if (data.error) return `<div class="file-block">${head}<p class="sec-sum">${esc(data.error)}</p></div>`;
  if (mode === "audit") {
    const rows = data.audit || [];
    if (!rows.length) {
      return `<div class="file-block">${head}<p class="sec-sum">No reference list found (looked for a "References" heading).</p></div>`;
    }
    const flagged = rows.filter((r) => r.status !== "match").length;
    return `<div class="file-block">${head}<p class="sec-sum">${rows.length} references, ${flagged} to review (best-effort audit).</p>${auditTable(rows)}</div>`;
  }
  const rows = data.results || [];
  const need = rows.filter((r) => r.status !== "ok").length;
  return `<div class="file-block">${head}<p class="sec-sum">${rows.length} checked, ${need} need review.</p>${structuredTable(rows)}</div>`;
}

async function processFiles(list) {
  const files = [...list].filter((f) => SUPPORTED.some((ext) => f.name.toLowerCase().endsWith(ext)));
  if (!files.length) {
    setStatus("No supported files (.bib, .json, .txt, .pdf, .docx) in that selection.");
    return;
  }
  runBtn.disabled = true;
  resultsEl.innerHTML = "";
  let html = "";
  try {
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      setStatus(`Processing ${i + 1} of ${files.length}: ${f.name}…`, true);
      let mode = "structured";
      try {
        const text = await readText(f);
        mode = modeForFile(f.name, text);
        html += sectionHtml(f.name, mode, await runPython(mode, text));
      } catch (e) {
        html += sectionHtml(f.name, mode, { error: "Could not process: " + e.message });
      }
      resultsEl.innerHTML = html;
    }
    setStatus(`Done. Processed ${files.length} file${files.length > 1 ? "s" : ""}.`);
  } finally {
    runBtn.disabled = false;
  }
}

// Recurse a dropped folder into a flat list of File objects.
function walkEntry(entry) {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file((f) => resolve([f]), () => resolve([]));
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const all = [];
      const read = () => reader.readEntries(async (batch) => {
        if (!batch.length) {
          const nested = await Promise.all(all.map(walkEntry));
          resolve(nested.flat());
          return;
        }
        all.push(...batch);
        read();
      }, () => resolve([]));
      read();
    } else {
      resolve([]);
    }
  });
}

async function main() {
  const themeBtn = document.getElementById("theme");
  const applyTheme = (t) => {
    document.documentElement.dataset.theme = t;
    localStorage.setItem("argus-theme", t);
    themeBtn.textContent = t === "dark" ? "☀" : "☾"; // sun when dark, moon when light
    themeBtn.title = t === "dark" ? "Switch to light" : "Switch to dark";
  };
  applyTheme(document.documentElement.dataset.theme || "dark");
  themeBtn.addEventListener("click", () =>
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));

  try {
    pyodide = await loadPyodide();
    setStatus("Starting the checker. The first load downloads the engine (a few MB) — this is normal, one moment…", true);
    await loadCore(pyodide);
    await pyodide.runPythonAsync(GLUE);
  } catch (e) {
    setStatus("Failed to start: " + e.message);
    return;
  }
  runBtn.disabled = false;
  runBtn.textContent = "Check references";
  setStatus("Ready. Paste a list and Check, or choose files / a folder (or drag them onto the box).");
  const repo = document.getElementById("repo-link");
  if (repo) repo.innerHTML = '<a href="https://github.com/odinzen/argus-public">Source on GitHub</a>.';

  fileEl.addEventListener("change", () => processFiles(fileEl.files));
  folderEl.addEventListener("change", () => processFiles(folderEl.files));

  runBtn.addEventListener("click", async () => {
    const text = inputEl.value.trim();
    if (!text) { setStatus("Nothing to check: paste a reference list, or choose files / a folder."); return; }
    const mode = detectMode(text);
    runBtn.disabled = true;
    resultsEl.innerHTML = "";
    setStatus(mode === "audit"
      ? "Matching pasted references against Crossref…"
      : "Checking against Crossref…", true);
    try {
      resultsEl.innerHTML = sectionHtml(null, mode, await runPython(mode, text));
      setStatus("Done.");
    } catch (e) {
      setStatus("Error: " + e.message);
    } finally {
      runBtn.disabled = false;
    }
  });

  cardEl.addEventListener("dragover", (e) => { e.preventDefault(); cardEl.classList.add("dropping"); });
  cardEl.addEventListener("dragleave", () => cardEl.classList.remove("dropping"));
  cardEl.addEventListener("drop", async (e) => {
    e.preventDefault();
    cardEl.classList.remove("dropping");
    const dt = e.dataTransfer;
    const entries = [];
    if (dt.items && dt.items.length && dt.items[0].webkitGetAsEntry) {
      for (const it of dt.items) { const en = it.webkitGetAsEntry(); if (en) entries.push(en); }
    }
    const files = entries.length
      ? (await Promise.all(entries.map(walkEntry))).flat()
      : [...dt.files];
    processFiles(files);
  });
}

main();
