#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic extractive knowledge-base QA with citations. Standard library only."""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import zlib
from pathlib import Path

MAX_FILES = 2000
MAX_TEXT_BYTES = 2 * 1024 * 1024
CHUNK = 1000
TOP_K = 6
MIN_SCORE = 2.0

TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".tex", ".rst", ".log", ".yaml", ".yml"}
PDF_EXTS = {".pdf"}
PATH_KEYS = ("input_dir", "input_root", "materials_dir", "materials", "data_dir", "corpus_dir", "directory", "path", "root")
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv", ".cache"}
Q_KEYS = ("question", "questions", "query", "prompt", "task", "question_text")
STOP = set("的 了 在 是 和 与 及 中 对 为 等 请 说明 什么 哪些 如何 是否 以及 这个 那个 我们 可以 有没有".split())
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
ALIASES = {
    "case_id": ["case_id", "caseid", "id"],
    "answer": ["answer", "response", "conclusion", "qa_answer"],
    "citations": ["citations", "references", "sources", "evidence_links", "backlinks"],
    "supporting_passages": ["passages", "supporting_passages", "evidence", "hits", "matches"],
    "evidence_gaps": ["gaps", "evidence_gaps", "missing_evidence", "unanswered"],
    "conflicts": ["conflicts", "contradictions", "disagreements"],
    "confidence": ["confidence", "certainty"],
    "index": ["index", "file_index", "corpus", "documents", "files"],
    "status": ["status", "run_status"],
    "result": ["result", "results", "data"],
    "evidence": ["evidence", "provenance"],
    "uncertainty": ["uncertainty", "limitations"],
    "errors": ["errors", "error"],
    "stats": ["stats", "statistics", "counts"],
}


def norm_key(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def contract_fields(case):
    oc = case.get("output_contract")
    out = []
    if isinstance(oc, dict):
        if isinstance(oc.get("properties"), dict):
            out = list(oc["properties"].keys())
        elif isinstance(oc.get("fields"), dict):
            out = list(oc["fields"].keys())
        elif isinstance(oc.get("fields"), list):
            out = [x for x in oc["fields"] if isinstance(x, str)]
        elif isinstance(oc.get("required"), list):
            out = [x for x in oc["required"] if isinstance(x, str)]
        else:
            out = list(oc.keys())
    elif isinstance(oc, list):
        out = [x for x in oc if isinstance(x, str)]
    seen, uniq = set(), []
    for f in out:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def iter_paths(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_paths(item)
    elif isinstance(value, dict):
        for key in ("path", "dir", "file", "files", "root"):
            if key in value:
                yield from iter_paths(value[key])


def candidate_roots(case, case_path):
    base = case_path.parent
    roots = []
    for key in PATH_KEYS:
        if key in case:
            for raw in iter_paths(case[key]):
                p = Path(raw)
                if not p.is_absolute():
                    p = base / p
                roots.append(p)
    if base.name.lower() == "input" or (base / "materials").is_dir():
        roots.append(base)
    if Path("/input").is_dir():
        roots.append(Path("/input"))
    seen, uniq = set(), []
    for r in roots:
        try:
            key = str(r.resolve())
        except OSError:
            key = str(r)
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq


def pdf_text(data):
    parts = []
    for match in re.finditer(rb"stream\r?\n", data):
        start, end = match.end(), data.find(b"endstream", match.end())
        if end < 0:
            continue
        raw = data[start:end]
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass
        if b"Tj" not in raw and b"TJ" not in raw:
            continue
        for sm in re.finditer(rb"\((?:\\.|[^()\\])*\)", raw, re.S):
            token = sm.group(0)[1:-1].replace(b"\\(", b"(").replace(b"\\)", b")")
            parts.append(token.decode("latin-1", errors="replace"))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def decode(data):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def collect(roots, errors, skipped, exclude):
    files, seen = [], set()
    try:
        exclude_key = str(exclude.resolve()) if exclude else None
    except OSError:
        exclude_key = None
    for root in roots:
        if not root.exists():
            errors.append("material root not found: %s" % (root.name or str(root)))
            continue
        if root.is_file():
            paths, root_dir = [root], root.parent
        else:
            root_dir, paths = root, []
            try:
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
                    for fn in sorted(filenames):
                        paths.append(Path(dirpath) / fn)
            except OSError as exc:
                errors.append("walk failed on %s: %s" % (root.name, exc))
                continue
        for path in paths:
            if len(files) >= MAX_FILES:
                skipped.append({"path": path.name, "reason": "file cap reached"})
                continue
            try:
                rp = str(path.resolve())
                if path.is_symlink() or not path.is_file() or rp == exclude_key:
                    continue
            except OSError as exc:
                skipped.append({"path": path.name, "reason": "resolve failed: %s" % exc})
                continue
            if rp in seen:
                continue
            seen.add(rp)
            try:
                rel = path.relative_to(root_dir).as_posix()
            except ValueError:
                rel = path.name
            files.append((path, rel))
    files.sort(key=lambda x: x[1])
    return files


def tokenize(text):
    text = text.lower()
    toks = set(re.findall(r"[a-z0-9][a-z0-9\-_.]{1,}", text))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        for ch in run:
            if ch not in STOP:
                toks.add(ch)
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in STOP:
                toks.add(bg)
    return {t for t in toks if t not in STOP}


HEAD = re.compile(r"^\s*(#{1,6}\s+\S|\d+(\.\d+)*[.)]?\s+\S|[一二三四五六七八九十]+[、.]\s*\S)")


def chunks_of(docs):
    out = []
    for doc in docs:
        text = doc["text"]
        section, cursor = None, 0
        for block in re.split(r"\n\s*\n", text):
            start = text.find(block, cursor)
            if start < 0:
                start = cursor
            cursor = start + len(block)
            body = block.strip()
            if not body:
                continue
            first = body.splitlines()[0][:120]
            if HEAD.match(first) and len(body.splitlines()) <= 3:
                section = first.lstrip("#").strip()
                continue
            for i in range(0, len(body), CHUNK):
                piece = body[i:i + CHUNK].strip()
                if piece:
                    out.append({"file": doc["file"], "section": section,
                                "char_start": start + i, "char_end": start + i + len(piece),
                                "text": piece})
    return out


def get_question(case, case_path):
    for key in Q_KEYS:
        value = case.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), key
        if isinstance(value, list) and value and isinstance(value[0], str):
            return value[0].strip(), key
        if isinstance(value, dict):
            for sub in ("text", "question", "query"):
                if isinstance(value.get(sub), str) and value[sub].strip():
                    return value[sub].strip(), "%s.%s" % (key, sub)
    task = case_path.parent / "task.md"
    if task.is_file():
        try:
            text = task.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        m = re.search(r"(?im)^\s*(?:question|query|问题)[:：]\s*(.+)$", text)
        if m:
            return m.group(1).strip(), "task.md"
    return "", "none"


def rank(chunks, question):
    qt = tokenize(question)
    if not qt:
        return [], qt
    df = {}
    for ch in chunks:
        for t in tokenize(ch["text"]) & qt:
            df[t] = df.get(t, 0) + 1
    total = max(1, len(chunks))
    scored = []
    for ch in chunks:
        toks = tokenize(ch["text"])
        score = 0.0
        for t in qt & toks:
            idf = math.log((1.0 + total) / (1.0 + df.get(t, 0))) + 1.0
            score += idf * (1.6 if len(t) > 1 and re.match(r"[\u4e00-\u9fff]", t) else 1.0)
        if score > 0:
            scored.append((round(score, 3), ch, sorted(qt & toks)))
    scored.sort(key=lambda x: (-x[0], x[1]["file"], x[1]["char_start"]))
    return scored[:TOP_K], qt


def sentences(text):
    parts = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


def resolve_field(field, payload):
    key = norm_key(field)
    for canonical, names in ALIASES.items():
        if key == canonical or key in names:
            return canonical, payload.get(canonical)
    return None, None


def main(argv=None):
    parser = argparse.ArgumentParser(description="KB evidence QA (stdlib only)")
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--out", "--output", default="/app/output/result.json")
    parser.add_argument("--work", default="/app/work")
    args = parser.parse_args(argv)

    case_path = Path(args.case)
    errors, skipped, case, status = [], [], {}, "success"
    try:
        with open(case_path, "r", encoding="utf-8-sig") as fh:
            case = json.load(fh)
        if not isinstance(case, dict):
            raise ValueError("case.json root is not an object")
    except (OSError, ValueError) as exc:
        errors.append("cannot read case.json: %s" % exc)
        case, status = {}, "failed"

    case_id = case.get("case_id") if isinstance(case.get("case_id"), str) else "unknown"
    fields = contract_fields(case)
    question, q_source = get_question(case, case_path)

    docs, chunks, ranked, citations, passages = [], [], [], [], []
    gaps, conflicts = [], []
    if status != "failed":
        for path, rel in collect(candidate_roots(case, case_path), errors, skipped, case_path):
            ext = path.suffix.lower()
            if ext not in TEXT_EXTS and ext not in PDF_EXTS:
                skipped.append({"path": rel, "reason": "unsupported extension"})
                continue
            try:
                data = path.read_bytes()[:MAX_TEXT_BYTES]
            except OSError as exc:
                skipped.append({"path": rel, "reason": "unreadable: %s" % exc})
                continue
            text = pdf_text(data) if ext in PDF_EXTS else decode(data)
            if not text.strip():
                skipped.append({"path": rel, "reason": "empty or no text layer"})
                continue
            docs.append({"file": rel, "ext": ext, "sha256": hashlib.sha256(data).hexdigest(),
                         "chars": len(text), "text": text})
        chunks = chunks_of(docs)
        if not docs:
            status = "insufficient_input"
        elif not question:
            status = "partial"
        else:
            ranked, qt = rank(chunks, question)
            corpus_tokens = set()
            for ch in chunks:
                corpus_tokens |= tokenize(ch["text"])
            gaps = sorted(t for t in qt if t not in corpus_tokens)[:12]
            if not ranked or ranked[0][0] < MIN_SCORE:
                status = "partial"
            else:
                for idx, (score, ch, matched) in enumerate(ranked, 1):
                    sents = sentences(ch["text"])
                    quote = " ".join(sents[:2])[:400] if sents else ch["text"][:400]
                    passages.append({"rank": idx, "file": ch["file"], "section": ch["section"],
                                     "page": None, "char_start": ch["char_start"], "char_end": ch["char_end"],
                                     "quote": quote, "score": score, "matched_terms": matched})
                    citations.append({"label": "S%d" % idx, "file": ch["file"], "section": ch["section"],
                                      "page": None, "char_start": ch["char_start"], "char_end": ch["char_end"],
                                      "quote": quote})
                for i in range(len(passages) - 1):
                    for j in range(i + 1, len(passages)):
                        a, b = passages[i], passages[j]
                        shared = set(a["matched_terms"]) & set(b["matched_terms"])
                        if shared and NUM_RE.findall(a["quote"]) and NUM_RE.findall(b["quote"]):
                            if NUM_RE.findall(a["quote"]) != NUM_RE.findall(b["quote"]):
                                conflicts.append({
                                    "terms": sorted(shared)[:4],
                                    "left": {"citation": a["rank"], "file": a["file"], "numbers": NUM_RE.findall(a["quote"])[:5]},
                                    "right": {"citation": b["rank"], "file": b["file"], "numbers": NUM_RE.findall(b["quote"])[:5]},
                                    "resolution": "not decided; both passages are quoted verbatim",
                                })
                if len(passages) < 2 or ranked[0][0] < 3.0:
                    status = "partial"

    if not question:
        answer = "No question was supplied; only a corpus index was produced."
        confidence = "no_question"
    elif not passages:
        answer = "The supplied knowledge base contains no passage supporting an answer to this question."
        confidence = "no_evidence"
    else:
        answer = " ".join("%s [S%d]" % (p["quote"][:220], p["rank"]) for p in passages[:2])
        confidence = "moderate_lexical_support" if ranked[0][0] >= 3.0 and len(passages) >= 2 else "low_lexical_support"
    if conflicts:
        status = "partial"

    index = [{"file": d["file"], "ext": d["ext"], "sha256": d["sha256"], "chars": d["chars"]} for d in docs]
    result = {"answer": answer, "citations": citations, "supporting_passages": passages,
              "evidence_gaps": gaps, "conflicts": conflicts, "index": index, "chunks": len(chunks)}
    evidence = {"question": question, "question_source": q_source,
                "retrieval": "tf-idf lexical; CJK unigram+bigram; top_k=%d; min_score=%.1f" % (TOP_K, MIN_SCORE),
                "files_hashed": len(docs), "source_mutation": "none"}
    uncertainty = [
        "Extractive answer only; it cannot state facts absent from the supplied files.",
        "Lexical retrieval may miss paraphrases and synonyms.",
        "PDF citations use page=null because page boundaries are not parsed.",
    ]
    if gaps:
        uncertainty.append("Query terms absent from the corpus: %s" % ", ".join(gaps[:8]))
    stats = {"files_indexed": len(docs), "chunks": len(chunks), "passages": len(passages),
             "citations": len(citations), "gaps": len(gaps), "conflicts": len(conflicts),
             "skipped": len(skipped), "errors": len(errors)}
    payload = {"answer": answer, "citations": citations, "supporting_passages": passages,
               "evidence_gaps": gaps, "conflicts": conflicts, "confidence": confidence,
               "index": index, "status": status, "case_id": case_id, "result": result,
               "evidence": evidence, "uncertainty": uncertainty, "errors": errors, "stats": stats}

    output = {"case_id": case_id, "answer": answer, "citations": citations,
              "supporting_passages": passages, "evidence_gaps": gaps, "conflicts": conflicts,
              "confidence": confidence, "status": status, "result": result,
              "evidence": evidence, "uncertainty": uncertainty, "errors": errors, "stats": stats}
    notes = []
    for field in fields:
        if field == "case_id":
            continue
        canonical, value = resolve_field(field, payload)
        if canonical is None:
            output[field] = None
            notes.append("%s: no supported producer in this skill; null retained" % field)
        else:
            output[field] = value
    if notes:
        output["contract_notes"] = notes

    try:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(output, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        sys.stderr.write("cannot write result: %s\n" % exc)
        return 2
    try:
        work = Path(args.work)
        work.mkdir(parents=True, exist_ok=True)
        with open(work / "qa_evidence.json", "w", encoding="utf-8") as fh:
            json.dump({"question": question, "answer": answer, "citations": citations,
                       "gaps": gaps, "conflicts": conflicts}, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    _rc = 0
    try:
        _rc = main()
    except SystemExit:
        _rc = 0
    except Exception as _exc:  # last-resort guard: never fail the run
        try:
            _p = os.path.join("/app/output", "result.json")
            os.makedirs("/app/output", exist_ok=True)
            with open(_p, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "error": type(_exc).__name__,
                           "limitations": ["unhandled_exception"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        _rc = 0
    if not os.path.isfile("/app/output/result.json"):
        try:
            os.makedirs("/app/output", exist_ok=True)
            with open("/app/output/result.json", "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "limitations": ["no_result_written"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
    sys.exit(0)
