#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sk_entry.py - deterministic, evidence-bound knowledge-base question answering.

Standard library only.  No network, no random numbers, no timestamps.

CLI:
    python sk_entry.py --input /input --work /app/work --out /app/output

`--input` may be a directory (case.json + materials) or a case.json file.
`--out`   may be a directory (result.json is written inside) or a .json file.

The program always writes a contract-complete result.json and exits 0, even
when the input is empty, unreadable or malformed.
"""

import argparse
import codecs
import hashlib
import json
import math
import os
import re
import sys
import zlib
from pathlib import Path

VERSION = "2.0.0"

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".tex",
    ".rst", ".log", ".yaml", ".yml", ".xml", ".html", ".htm",
}
PDF_EXTS = {".pdf"}
SKIP_DIRS = {
    "__pycache__", ".git", ".svn", ".hg", "node_modules", ".venv", "venv",
    ".cache", ".idea", ".vscode", ".mypy_cache", ".pytest_cache",
}
PATH_KEYS = (
    "input_dir", "input_root", "materials_dir", "materials", "data_dir",
    "corpus_dir", "directory", "path", "root", "files", "documents",
)
QUESTION_KEYS = ("questions", "question", "query", "queries", "prompt", "task", "question_text")
STOP = set(
    "的 了 在 是 和 与 及 中 对 为 等 请 说明 什么 哪些 如何 是否 以及 "
    "这个 那个 我们 可以 有没有 根据 文件 资料".split()
)
EN_STOP = set(
    "a an the and or but if then than that this these those of in on at to for "
    "from by with as is are was were be been being it its we you they he she "
    "i not no do does did done what which who whom when where why how about "
    "into over under between during before after also such can could may might "
    "should would will shall use used using".split()
)
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
UNIT_RE = re.compile(
    r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*"
    r"(°C|%|mg|kg|mL|ml|µL|uL|L|mM|µM|uM|nM|pM|min|minutes?|hours?|days?|sec|s|"
    r"mm|cm|km|kDa|Da|g)\b"
)
PH_RE = re.compile(r"(?i)\bpH\s*[:=]?\s*(\d+(?:\.\d+)?)")
YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
HEAD_RE = re.compile(
    r"^\s*(#{1,6}\s+\S|\d+(?:\.\d+)*[.)]?\s+\S|[一二三四五六七八九十]+[、.．]\s*\S)"
)
VERSION_RE = re.compile(
    r"(?i)(?:^|[\s_\-.])(v\d+(?:\.\d+)*|rev(?:ision)?[\s_-]?\d+|final|draft|copy|"
    r"backup|old|new|终稿|修订|副本|旧版|新版)(?=$|[\s_\-_.\d])"
)
ASCII_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-.]{1,}")
CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
SENT_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+|\n+")

DEFAULT_POLICY = {
    "version": "1.0.0",
    "retrieval": {
        "top_k": 6,
        "min_score": 2.0,
        "min_moderate_score": 3.0,
        "chunk_chars": 1000,
        "quote_chars": 400,
        "max_questions": 20,
        "cjk_bigram_weight": 1.6,
        "filename_boost": 0.5,
        "section_boost": 0.6,
    },
    "caps": {
        "max_files": 2000,
        "max_file_bytes": 4 * 1024 * 1024,
        "max_text_chars": 2000000,
        "max_total_chars": 20000000,
        "max_chunks": 200000,
    },
}

CANONICAL_ALIASES = {
    "answers": ("answers", "per_question", "qa", "qa_pairs", "responses",
                "answers_by_question", "results"),
    "answer": ("answer", "final_answer", "qa_answer", "conclusion", "response"),
    "citations": ("citations", "references", "sources", "evidence_links",
                  "backlinks", "quotes", "source_passages", "source_citations"),
    "supporting_passages": ("supporting_passages", "passages", "evidence",
                            "hits", "matches", "retrieval_results", "retrieved"),
    "evidence_gaps": ("evidence_gaps", "gaps", "missing_evidence", "unanswered",
                      "knowledge_gaps", "missing", "insufficient_evidence"),
    "conflicts": ("conflicts", "contradictions", "disagreements", "version_conflicts"),
    "confidence": ("confidence", "certainty", "confidence_level"),
    "index": ("index", "file_index", "corpus", "documents", "files", "inventory",
              "file_inventory"),
    "versions": ("versions", "version_relations", "version_graph", "version_history",
                 "version_groups"),
    "duplicates": ("duplicates", "duplicate_files", "copies", "aliases"),
    "skipped": ("skipped", "skipped_files", "unreadable", "excluded", "exclusions"),
    "needs_human_confirmation": ("needs_human_confirmation", "human_review",
                                 "open_questions", "manual_checks", "review_items"),
    "status": ("status", "run_status", "run_state", "outcome"),
    "result": ("result", "data", "deliverable", "output"),
    "evidence": ("evidence", "provenance", "audit", "operation_log", "run_log"),
    "uncertainty": ("uncertainty", "limitations", "caveats", "assumptions", "notes"),
    "errors": ("errors", "error", "failures"),
    "stats": ("stats", "statistics", "counts", "metrics"),
    "case_id": ("case_id", "caseid", "input_id", "id"),
}


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def norm_key(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def merge_dict(base, extra):
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def load_policy():
    path = Path(__file__).resolve().parent.parent / "assets" / "policy.json"
    data = {}
    try:
        with open(str(path), "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError):
        data = {}
    return merge_dict(DEFAULT_POLICY, data), bool(data)


def read_text_any(path):
    data = Path(path).read_bytes()
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def read_json_file(path):
    text, _enc = read_text_any(path)
    return json.loads(text)


def write_json(path, obj):
    """Write JSON, tolerating a directory target and Windows file replacement."""
    path = Path(str(path))
    if path.exists() and path.is_dir():
        path = path / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    payload = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    try:
        with open(str(tmp), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
        os.replace(str(tmp), str(path))
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)


def write_text(path, text):
    path = Path(str(path))
    if path.exists() and path.is_dir():
        path = path / "report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def resolve_out(raw):
    path = Path(str(raw))
    if path.suffix.lower() == ".json":
        return path, path.parent
    if path.exists() and path.is_file():
        return path, path.parent
    return path / "result.json", path


def resolve_input(raw):
    path = Path(str(raw))
    if path.is_file():
        if path.name.lower().endswith(".json"):
            return path, path.parent
        return path.parent / "case.json", path.parent
    return path / "case.json", path


def contract_spec(case):
    for key in ("output_contract", "outputContract", "output_schema", "outputs"):
        spec = case.get(key)
        if isinstance(spec, (dict, list)):
            return spec, key
    return None, None


def contract_fields(spec):
    out = []
    if isinstance(spec, dict):
        if isinstance(spec.get("properties"), dict):
            out = list(spec["properties"].keys())
        elif isinstance(spec.get("fields"), (dict, list)):
            out = contract_fields(spec["fields"])
        elif isinstance(spec.get("required"), list):
            out = [x for x in spec["required"] if isinstance(x, str)]
        else:
            reserved = {"$schema", "title", "description", "type", "required",
                        "definitions", "$defs", "format", "version", "notes",
                        "instructions", "schema"}
            out = [str(k) for k in spec if str(k).lower() not in reserved]
    elif isinstance(spec, list):
        for item in spec:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field") or item.get("key")
                if isinstance(name, str):
                    out.append(name)
    seen, uniq = set(), []
    for field in out:
        if field not in seen:
            seen.add(field)
            uniq.append(field)
    return uniq


# --------------------------------------------------------------------------
# input discovery
# --------------------------------------------------------------------------

def iter_paths(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_paths(item)
    elif isinstance(value, dict):
        for key in ("path", "dir", "file", "files", "root", "input_dir"):
            if key in value:
                yield from iter_paths(value[key])


def candidate_roots(case, base):
    roots = []
    for key in PATH_KEYS:
        if key in case:
            for raw in iter_paths(case[key]):
                p = Path(raw)
                if not p.is_absolute():
                    p = base / p
                roots.append(p)
    roots.append(base)
    seen, uniq = set(), []
    for root in roots:
        try:
            key = str(root.resolve())
        except OSError:
            key = str(root)
        if key not in seen:
            seen.add(key)
            uniq.append(root)
    return uniq


def looks_binary(data):
    return b"\x00" in data[:4096]


def strip_html(text):
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h[1-6]>", "\n\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def decode_bytes(data):
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def pdf_unescape(token):
    out = []
    i = 0
    while i < len(token):
        ch = token[i]
        if ch == 0x5C and i + 1 < len(token):
            nxt = token[i + 1]
            mapping = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12,
                       0x28: 40, 0x29: 41, 0x5C: 92}
            if nxt in mapping:
                out.append(mapping[nxt])
                i += 2
                continue
            if 0x30 <= nxt <= 0x37:
                octal = token[i + 1:i + 4]
                try:
                    out.append(int(octal, 8))
                except ValueError:
                    pass
                i += 1 + len(octal)
                continue
        out.append(ch)
        i += 1
    return bytes(bytearray(out))


def pdf_hex_text(raw):
    try:
        data = bytes(bytearray.fromhex(raw))
    except ValueError:
        return ""
    if len(data) >= 2 and data[:2] in (b"\xfe\xff", b"\xff\xfe"):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            return ""
    if len(data) % 2 == 0 and data.count(0) > len(data) // 4:
        try:
            return data.decode("utf-16-be")
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1", errors="replace")


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
        for sm in re.finditer(rb"\((?:\\.|[^()\\])*\)|<([0-9A-Fa-f\s]{2,})>", raw, re.S):
            if sm.group(1) is not None:
                parts.append(pdf_hex_text(re.sub(rb"\s+", b"", sm.group(1)).decode("ascii", "ignore")))
            else:
                parts.append(pdf_unescape(sm.group(0)[1:-1]).decode("latin-1", errors="replace"))
    return re.sub(r"[ \t]+", " ", " ".join(part for part in parts if part)).strip()


def collect_materials(roots, exclude, errors, skipped, caps):
    files, seen = [], set()
    exclude_keys = set()
    for item in exclude:
        try:
            exclude_keys.add(str(item.resolve()))
        except OSError:
            pass
    for root in roots:
        if not root.exists():
            errors.append({"stage": "discover", "reason": "root_not_found",
                           "detail": root.name or str(root)})
            continue
        if root.is_file():
            paths, root_dir = [root], root.parent
        else:
            root_dir, paths = root, []
            try:
                for dirpath, dirnames, filenames in os.walk(str(root)):
                    dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
                    for name in sorted(filenames):
                        paths.append(Path(dirpath) / name)
            except OSError as exc:
                errors.append({"stage": "discover", "reason": "walk_failed",
                               "detail": "%s: %s" % (root.name, exc)})
                continue
        for path in paths:
            if len(files) >= caps["max_files"]:
                skipped.append({"path": path.name, "reason": "file_cap_reached"})
                continue
            try:
                resolved = str(path.resolve())
                if path.is_symlink():
                    skipped.append({"path": path.name, "reason": "symlink_not_followed"})
                    continue
                if not path.is_file() or resolved in exclude_keys:
                    continue
            except OSError as exc:
                skipped.append({"path": path.name, "reason": "stat_failed: %s" % exc})
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                rel = path.relative_to(root_dir).as_posix()
            except ValueError:
                rel = path.name
            files.append((path, rel))
    files.sort(key=lambda item: item[1])
    return files


# --------------------------------------------------------------------------
# indexing
# --------------------------------------------------------------------------

def version_label(rel):
    labels = []
    years = YEAR_RE.findall(rel)
    if years:
        labels.append("year:" + ",".join(sorted(set(years))))
    versions = VERSION_RE.findall(rel)
    if versions:
        labels.append("label:" + ",".join(v.lower() for v in sorted(set(versions))))
    return "; ".join(labels)


VERSION_WORD_RE = re.compile(
    r"(?i)(?<![a-z])(revision|rev|final|draft|copy|backup|old|new)(?![a-z])")


def file_version_tag(rel):
    """Short readable version label, e.g. 2021 / 2022-revision / unlabeled."""
    stem = Path(rel).stem
    years = sorted(set(YEAR_RE.findall(stem))) or sorted(set(YEAR_RE.findall(rel)))
    words = []
    for match in VERSION_WORD_RE.finditer(stem):
        word = match.group(1).lower()
        word = "revision" if word == "rev" else word
        if word not in words:
            words.append(word)
    for marker, word in (("终稿", "final"), ("修订", "revision"),
                         ("副本", "copy"), ("旧版", "old"), ("新版", "new")):
        if marker in stem and word not in words:
            words.append(word)
    if years:
        return years[0] + ("-" + "-".join(words) if words else "")
    if words:
        return "-".join(words)
    return "unlabeled"


def question_years(text):
    return sorted(set(YEAR_RE.findall(text or "")))


def version_key(rel):
    stem = Path(rel).stem.lower()
    stem = YEAR_RE.sub(" ", stem)
    stem = re.sub(r"(?i)(?:^|[\s_\-])(?:v\d+(?:\.\d+)*|rev(?:ision|ised|ised)?|"
                  r"final|draft|copy|backup|old|new|终稿|修订|副本|旧版|新版)"
                  r"(?=$|[\s_\-.\d])", " ", stem)
    tokens = [t for t in re.split(r"[^0-9a-z\u4e00-\u9fff]+", stem) if t]
    folder = str(Path(rel).parent.as_posix())
    stem_key = tokens[0] if tokens else Path(rel).stem.lower()
    return (folder + "/" if folder not in ("", ".") else "") + stem_key


def build_inventory(paths, errors, skipped, caps):
    docs, duplicates = [], []
    by_hash = {}
    total_chars = 0
    for path, rel in paths:
        ext = path.suffix.lower()
        if ext not in TEXT_EXTS and ext not in PDF_EXTS:
            skipped.append({"path": rel, "reason": "unsupported_extension"})
            continue
        try:
            stat = path.stat()
            with open(str(path), "rb") as fh:
                limited = fh.read(caps["max_file_bytes"])
        except OSError as exc:
            skipped.append({"path": rel, "reason": "unreadable: %s" % type(exc).__name__})
            continue
        hash_scope = "full" if stat.st_size <= caps["max_file_bytes"] else "prefix"
        digest = sha256_bytes(limited)
        if hash_scope == "full" and digest in by_hash:
            duplicates.append({
                "file": rel, "duplicate_of": by_hash[digest],
                "sha256": digest, "bytes": stat.st_size, "scope": "full",
            })
            continue
        if hash_scope == "full":
            by_hash[digest] = rel
        if ext in PDF_EXTS:
            text, encoding = pdf_text(limited), "latin-1/pdf"
            extractor = "pdf-flate-tj-tj"
        else:
            if looks_binary(limited):
                skipped.append({"path": rel, "reason": "binary_content"})
                continue
            text, encoding = decode_bytes(limited)
            extractor = "text"
            if ext in (".html", ".htm"):
                text = strip_html(text)
                extractor = "text-html-stripped"
        if not text.strip():
            skipped.append({"path": rel, "reason": "empty_or_no_text_layer"})
            continue
        chars = len(text)
        if total_chars + chars > caps["max_total_chars"]:
            skipped.append({"path": rel, "reason": "total_text_cap_reached"})
            continue
        total_chars += chars
        docs.append({
            "file": rel,
            "ext": ext,
            "extractor": extractor,
            "encoding": encoding,
            "bytes": stat.st_size,
            "read_bytes": len(limited),
            "sha256": digest,
            "hash_scope": hash_scope,
            "chars": chars,
            "line_count": text.count("\n") + 1,
            "title": guess_title(text, rel),
            "years": sorted(set(YEAR_RE.findall(rel) + YEAR_RE.findall(text[:4000]))),
            "version_label": version_label(rel),
            "permissions": {
                "readable": bool(os.access(str(path), os.R_OK)),
                "mode": oct(stat.st_mode & 0o777),
            },
            "text": text,
        })
        if chars > caps["max_text_chars"]:
            docs[-1]["truncated"] = True
    return docs, duplicates


def guess_title(text, rel):
    for line in text.splitlines()[:20]:
        stripped = line.strip().lstrip("#").strip()
        if len(stripped) >= 4 and not stripped.startswith(("---", "```")):
            return stripped[:160]
    return Path(rel).stem


def build_versions(docs, duplicates):
    groups = {}
    for doc in docs:
        groups.setdefault(version_key(doc["file"]), []).append(doc)
    relations = []
    for key in sorted(groups):
        members = groups[key]
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda d: d["file"])
        relations.append({
            "group": key,
            "members": [{
                "file": doc["file"], "sha256": doc["sha256"], "chars": doc["chars"],
                "years": doc["years"], "version_label": doc["version_label"],
                "title": doc["title"],
            } for doc in members],
            "distinct_content": len({doc["sha256"] for doc in members}) > 1,
            "note": "Version grouping is filename/metadata based; it is not a semantic diff.",
        })
    return relations


def line_of(text, offset):
    return text.count("\n", 0, max(0, offset)) + 1


def build_chunks(docs, policy):
    caps = policy["caps"]
    chunk_chars = policy["retrieval"].get("chunk_chars", 1000)
    chunks = []
    for doc in docs:
        text = doc["text"][:caps["max_text_chars"]]
        lines = text.splitlines(keepends=True)
        offsets, cursor = [], 0
        for line in lines:
            offsets.append(cursor)
            cursor += len(line)
        block_start, block_lines = None, []
        blocks = []

        def flush(end_line):
            if block_lines:
                start = block_start
                body = "".join(block_lines)
                blocks.append((start, end_line, body))

        for index, line in enumerate(lines):
            if line.strip() == "":
                flush(index)
                block_start, block_lines = None, []
            else:
                if block_start is None:
                    block_start = index
                block_lines.append(line)
        flush(len(lines))
        section = None
        for start_line, end_line, body in blocks:
            stripped = body.strip()
            if not stripped:
                continue
            first = stripped.splitlines()[0][:160]
            nonempty = [ln for ln in stripped.splitlines() if ln.strip()]
            if HEAD_RE.match(first) and len(nonempty) <= 2:
                section = first.lstrip("#").strip()
                continue
            base = offsets[start_line]
            lead = len(body) - len(body.lstrip())
            body = body.strip()
            for part_start in range(0, len(body), chunk_chars):
                piece = body[part_start:part_start + chunk_chars].strip()
                if not piece:
                    continue
                rel_start = body.find(piece, part_start)
                if rel_start < 0:
                    rel_start = part_start
                char_start = base + lead + rel_start
                chunks.append({
                    "file": doc["file"],
                    "section": section,
                    "char_start": char_start,
                    "char_end": char_start + len(piece),
                    "line_start": line_of(text, char_start),
                    "line_end": line_of(text, char_start + len(piece)),
                    "text": piece,
                })
    return chunks


# --------------------------------------------------------------------------
# retrieval
# --------------------------------------------------------------------------

def tokenize(text):
    text = text.lower()
    tokens = set()
    for token in ASCII_TOKEN_RE.findall(text):
        if token not in EN_STOP:
            tokens.add(token)
    for run in CJK_RUN_RE.findall(text):
        for ch in run:
            if ch not in STOP:
                tokens.add(ch)
        for i in range(len(run) - 1):
            bigram = run[i:i + 2]
            if bigram not in STOP:
                tokens.add(bigram)
    return {t for t in tokens if t not in STOP}


def cjk_weight(token, policy):
    if len(token) == 1 and CJK_RUN_RE.match(token):
        return policy["retrieval"].get("cjk_unigram_weight", 0.45)
    if len(token) == 2 and CJK_RUN_RE.match(token):
        return policy["retrieval"].get("cjk_bigram_weight", 1.6)
    if re.match(r"^\d", token):
        return policy["retrieval"].get("cjk_unigram_weight", 0.8)
    return 1.0


def rank_chunks(chunks, question, policy, years=None):
    years = years or []
    query_tokens = tokenize(question)
    if not query_tokens:
        return [], query_tokens, set()
    corpus_tokens = set()
    df = {}
    chunk_tokens = []
    for chunk in chunks:
        tokens = tokenize(chunk["text"] + "\n" + (chunk.get("section") or "") + "\n" + chunk["file"])
        chunk_tokens.append(tokens)
        corpus_tokens |= tokens
        for token in tokens & query_tokens:
            df[token] = df.get(token, 0) + 1
    total = max(1, len(chunks))
    scored = []
    for index, chunk in enumerate(chunks):
        tokens = chunk_tokens[index]
        score = 0.0
        matched = sorted(query_tokens & tokens)
        for token in matched:
            idf = math.log((1.0 + total) / (1.0 + df.get(token, 0))) + 1.0
            score += idf * cjk_weight(token, policy)
        if score <= 0:
            continue
        filename = chunk["file"].lower()
        section = (chunk.get("section") or "").lower()
        if any(token in filename for token in query_tokens if len(token) > 2):
            score += policy["retrieval"].get("filename_boost", 0.5)
        if section and any(token in section for token in query_tokens if len(token) > 2):
            score += policy["retrieval"].get("section_boost", 0.6)
        if years and any(year in chunk["file"] for year in years):
            score += policy["retrieval"].get("year_boost", 2.5)
        scored.append((round(score, 3), chunk, matched))
    scored.sort(key=lambda item: (-item[0], item[1]["file"],
                                  item[1]["line_start"], item[1]["char_start"]))
    return scored[:policy["retrieval"].get("top_k", 6)], query_tokens, corpus_tokens


def sentence_spans(text):
    spans = []
    cursor = 0
    for match in SENT_SPLIT_RE.finditer(text):
        start, end = cursor, match.start()
        if end > start:
            spans.append((start, end))
        cursor = match.end()
    if cursor < len(text):
        spans.append((cursor, len(text)))
    spans = [(s + (len(text[s:e]) - len(text[s:e].lstrip())),
              e - (len(text[s:e]) - len(text[s:e].rstrip())))
             for s, e in spans if text[s:e].strip()]
    return spans or [(0, len(text))]


def pick_quote(chunk, query_tokens, policy):
    text = chunk["text"]
    spans = sentence_spans(text)
    best, best_score = spans[0], -1
    for start, end in spans:
        segment = text[start:end]
        score = len(query_tokens & tokenize(segment))
        if NUM_RE.search(segment):
            score += 0.5
        if score > best_score:
            best, best_score = (start, end), score
    start, end = best
    limit = policy["retrieval"].get("quote_chars", 400)
    quote = text[start:min(end, start + limit)].strip()
    if not quote:
        quote = text[:limit].strip()
        start = 0
    else:
        start = text.find(quote, start)
        if start < 0:
            start = 0
    return quote, start, start + len(quote)


TEMP_DEG_C_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*(?:°\s*C|C)(?![\w])")
ROOM_TEMP_RE = re.compile(
    r"(?i)\b(room\s+temperature|ambient\s+temperature|room\s+temp)\b")
QUANTITY_BY_UNIT = {
    "g": "mass", "mg": "mass", "kg": "mass", "Da": "molar_mass", "kDa": "molar_mass",
    "mL": "volume", "µL": "volume", "L": "volume",
    "min": "time", "h": "time", "day": "time", "s": "time",
    "mm": "length", "cm": "length", "km": "length",
    "mM": "concentration", "µM": "concentration", "nM": "concentration",
    "pM": "concentration",
    "°C": "temperature", "%": "percent", "pH": "pH",
}


def normalize_unit(raw_unit):
    """Preserve case where it carries meaning (mM vs mm, mL vs ml, µM vs uM)."""
    exact = {
        "mM": "mM", "µM": "µM", "uM": "µM", "nM": "nM", "pM": "pM",
        "mL": "mL", "ml": "mL", "µL": "µL", "uL": "µL", "L": "L",
        "Da": "Da", "kDa": "kDa", "°C": "°C",
    }
    if raw_unit in exact:
        return exact[raw_unit]
    key = raw_unit.lower()
    return {"minutes": "min", "minute": "min", "hours": "h", "hour": "h",
            "days": "day", "day": "day", "sec": "s",
            "seconds": "s", "second": "s"}.get(key, key)


def measurements(text):
    """Map canonical unit -> sorted values, so an extra unit is not a conflict."""
    found = {}
    for value, raw_unit in UNIT_RE.findall(text):
        found.setdefault(normalize_unit(raw_unit), set()).add(value)
    for value in PH_RE.findall(text):
        found.setdefault("pH", set()).add(value)
    for value in TEMP_DEG_C_RE.findall(text):
        found.setdefault("°C", set()).add(value)
    return {unit: sorted(values) for unit, values in found.items()}


def quantity_of(unit):
    return QUANTITY_BY_UNIT.get(unit, "quantity")


def temperature_condition_conflict(left_quote, right_quote, left, right):
    """room temperature (~20-25 °C) vs an explicit set-point is a condition conflict."""
    left_room = bool(ROOM_TEMP_RE.search(left_quote))
    right_room = bool(ROOM_TEMP_RE.search(right_quote))
    if left_room and not left.get("°C") and not right_room and right.get("°C"):
        return {
            "unit": "°C", "quantity": "temperature", "resolution": "condition_conflict",
            "left_value": "room temperature (approx. 20-25 °C)",
            "right_value": ", ".join(right["°C"]) + " °C",
        }
    if right_room and not right.get("°C") and not left_room and left.get("°C"):
        return {
            "unit": "°C", "quantity": "temperature", "resolution": "condition_conflict",
            "left_value": ", ".join(left["°C"]) + " °C",
            "right_value": "room temperature (approx. 20-25 °C)",
        }
    return None


def measurement_conflicts(left_quote, right_quote):
    """Return real value/condition conflicts between two passages; [] when none."""
    left, right = measurements(left_quote), measurements(right_quote)
    found = []
    for unit in sorted(set(left) & set(right)):
        if left[unit] != right[unit]:
            found.append({
                "unit": unit, "quantity": quantity_of(unit),
                "resolution": "numeric_value_conflict",
                "left_value": ", ".join(left[unit]),
                "right_value": ", ".join(right[unit]),
            })
    condition = temperature_condition_conflict(left_quote, right_quote, left, right)
    if condition:
        found.append(condition)
    return found


def build_question_list(case, case_file, policy):
    found = []

    def add(value, source):
        if isinstance(value, str) and value.strip():
            found.append((value.strip(), source))
        elif isinstance(value, dict):
            text = value.get("question") or value.get("text") or value.get("query") or value.get("q")
            if isinstance(text, str) and text.strip():
                found.append((text.strip(), source))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                add(item, "%s[%d]" % (source, index))

    for key in ("questions", "question", "query", "queries", "prompt", "task", "question_text"):
        if key in case:
            add(case[key], "case.json:" + key)
    if case_file is not None:
        task = case_file.parent / "task.md"
        if task.is_file():
            try:
                task_text = task.read_text(encoding="utf-8", errors="replace")
            except OSError:
                task_text = ""
            for line in task_text.splitlines():
                match = re.match(r"(?i)^\s*(?:question|query|问题)\s*[:：]\s*(.+)$", line)
                if match:
                    found.append((match.group(1).strip(), "task.md"))
    seen, questions = set(), []
    for text, source in found:
        if text in seen:
            continue
        seen.add(text)
        questions.append({
            "id": "q%d" % (len(questions) + 1),
            "text": text,
            "source": source,
        })
        if len(questions) >= policy["retrieval"].get("max_questions", 20):
            break
    return questions


# --------------------------------------------------------------------------
# result assembly
# --------------------------------------------------------------------------

def resolve_contract_field(field, payload):
    key = norm_key(field)
    for canonical, names in CANONICAL_ALIASES.items():
        if key == canonical or key in names:
            return canonical, payload.get(canonical), "exact"
    best = (None, None, None)
    best_len = 0
    for canonical, names in CANONICAL_ALIASES.items():
        for name in (canonical,) + tuple(names):
            if len(name) < 3:
                continue
            if name in key and len(name) > best_len and (
                    key.startswith(name) or key.endswith(name)):
                best = (canonical, payload.get(canonical), "substring")
                best_len = len(name)
    return best


def unknown_value(field, payload):
    return {
        "status": "cannot_determine",
        "field": field,
        "reason": "no dedicated producer in this skill for this contract field",
        "available_result_keys": sorted(payload.get("result", {}).keys()),
        "case_id": payload.get("case_id"),
        "answer_count": len(payload.get("answers") or []),
        "citation_count": len(payload.get("citations") or []),
        "status_of_run": payload.get("status"),
    }


def make_evidence(payload, policy, policy_loaded, question_source):
    return {
        "question_source": question_source,
        "retrieval": {
            "method": "tf-idf lexical; ASCII words + CJK unigram/bigram",
            "top_k": policy["retrieval"].get("top_k"),
            "min_score": policy["retrieval"].get("min_score"),
            "chunk_chars": policy["retrieval"].get("chunk_chars"),
            "case_sensitive": False,
        },
        "files_hashed": len(payload.get("index") or []),
        "file_hashes": {item["file"]: item["sha256"] for item in payload.get("index") or []},
        "source_mutation": "none",
        "input_files_modified": False,
        "policy_loaded": policy_loaded,
        "generator": "sk_entry.py v" + VERSION,
    }


def display(value):
    """Render report cells without ever printing the string None."""
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text else "-"


def build_report(case_id, status, questions, answers, gaps, conflicts, stats, uncertainty):
    lines = [
        "# QA report (draft)",
        "",
        "> Generated by `scripts/sk_entry.py`. This is an extractive, deterministic draft.",
        "> The executing Agent must verify every quote against the cited file and line before delivery.",
        "",
        "| field | value |",
        "|-|-|",
        "| case_id | `%s` |" % display(case_id),
        "| status | `%s` |" % display(status),
        "| questions | %s |" % display(stats.get("questions", 0)),
        "| answered | %s |" % display(stats.get("answered", 0)),
        "| citations | %s |" % display(stats.get("citations", 0)),
        "",
        "## Answers",
        "",
    ]
    for item in answers:
        lines.append("### %s: %s" % (display(item.get("question_id")), display(item.get("question"))))
        lines.append("")
        lines.append(item.get("answer") or "_No evidence found in the supplied knowledge base._")
        lines.append("")
        for citation in item.get("citations") or []:
            if isinstance(citation, str):
                lines.append("- `%s`" % display(citation))
                continue
            lines.append("- `%s` %s L%s (%s, version=%s)" % (
                display(citation.get("label")), display(citation.get("file")),
                display(citation.get("line_start")), display(citation.get("section")) if citation.get("section") else "unsectioned",
                display(citation.get("version_label"))))
        lines.append("")
    lines.append("## Gaps and conflicts")
    lines.append("")
    if gaps:
        for gap in gaps:
            lines.append("- gap `%s`: question=%s; missing=%s; reason=%s" % (
                display(gap.get("question_id")), display(gap.get("question")),
                display(gap.get("missing_terms")), display(gap.get("reason"))))
    if conflicts:
        for conflict in conflicts:
            left = conflict.get("left") if isinstance(conflict.get("left"), dict) else {}
            right = conflict.get("right") if isinstance(conflict.get("right"), dict) else {}
            lines.append("- conflict `%s` [%s %s / %s]: left %s = %s; right %s = %s" % (
                display(conflict.get("question_id")), display(conflict.get("quantity")),
                display(conflict.get("unit")), display(conflict.get("resolution")),
                display(left.get("file")), display(left.get("value")),
                display(right.get("file")), display(right.get("value"))))
    if not gaps and not conflicts:
        lines.append("- none recorded.")
    lines.append("")
    for note in uncertainty:
        lines.append("- %s" % display(note))
    lines.append("")
    return "\n".join(lines)


def emergency_result(out_file, reason, input_raw, policy, policy_loaded):
    case_path, _input_dir = resolve_input(input_raw or "/input")
    case, case_id, contract = {}, "unknown", []
    try:
        if case_path.is_file():
            loaded = read_json_file(case_path)
            if isinstance(loaded, dict):
                case = loaded
                if isinstance(case.get("case_id"), str):
                    case_id = case["case_id"]
                spec, _key = contract_spec(case)
                contract = contract_fields(spec)
    except Exception:
        pass
    payload = {
        "case_id": case_id,
        "status": "failed",
        "answers": [],
        "answer": "The run failed before a grounded answer was produced.",
        "citations": [],
        "supporting_passages": [],
        "evidence_gaps": [],
        "conflicts": [],
        "confidence": "failed",
        "index": [],
        "versions": [],
        "duplicates": [],
        "skipped": [],
        "needs_human_confirmation": [{
            "item": "run_failure", "locator": "run", "reason": reason,
        }],
        "result": {"answer": "The run failed before a grounded answer was produced.",
                   "answers": [], "citations": []},
        "evidence": {"source_mutation": "none", "generator": "sk_entry.py v" + VERSION,
                     "failure_reason": reason},
        "uncertainty": ["The run did not complete; no scientific claim is made."],
        "errors": [{"stage": "run", "type": "runtime_failure", "detail": reason}],
        "stats": {},
        "contract_notes": ["run failed before contract fields could be produced"],
    }
    output = {"case_id": case_id}
    mapping = []
    for field in contract:
        if norm_key(field) in ("case_id", "caseid", "id"):
            output[field] = case_id
            mapping.append({"key": field, "mapped_to": "case_id", "mode": "exact"})
            continue
        canonical, value, mode = resolve_contract_field(field, payload)
        if canonical:
            output[field] = value
            mapping.append({"key": field, "mapped_to": canonical, "mode": mode})
        else:
            output[field] = unknown_value(field, payload)
            mapping.append({"key": field, "mapped_to": None, "mode": "unknown"})
    for key, value in payload.items():
        output.setdefault(key, value)
    output["contract_extras"] = {
        "contract_source": "case.json:output_contract",
        "contract_keys": contract,
        "mapping": mapping,
        "unknown_fields": [item["key"] for item in mapping if item["mode"] == "unknown"],
        "generator_version": VERSION,
        "failure_reason": reason,
    }
    output["contract_notes"] = payload["contract_notes"]
    try:
        write_json(out_file, output)
    except OSError:
        pass


def run(args, policy, policy_loaded):
    errors, skipped = [], []
    case, status = {}, "success"
    case_file, input_dir = resolve_input(args.input)
    case_spec = None

    if not case_file.is_file():
        errors.append({"stage": "load_case", "reason": "case_json_missing",
                       "detail": "no case.json at the resolved input path"})
        status = "failed"
    else:
        try:
            case = read_json_file(case_file)
            if not isinstance(case, dict):
                raise ValueError("case.json root is not an object")
            case_spec, _contract_key = contract_spec(case)
        except (OSError, ValueError) as exc:
            errors.append({"stage": "load_case", "reason": "case_json_invalid",
                           "detail": "%s: %s" % (type(exc).__name__, exc)})
            case, status = {}, "failed"

    case_id = case.get("case_id") if isinstance(case.get("case_id"), str) else "unknown"
    if case_id == "unknown" and isinstance(case.get("id"), str):
        case_id = case["id"]
    contract = contract_fields(case_spec)
    questions = build_question_list(case, case_file, policy)

    docs, duplicates, chunks = [], [], []
    versions, answers, citations, passages, gaps, conflicts = [], [], [], [], [], []
    if status != "failed":
        roots = candidate_roots(case, case_file.parent if case_file else input_dir)
        exclude = [case_file] if case_file else []
        task_file = (case_file.parent if case_file else input_dir) / "task.md"
        if task_file.is_file():
            exclude.append(task_file)
        paths = collect_materials(roots, exclude, errors, skipped, policy["caps"])
        docs, duplicates = build_inventory(paths, errors, skipped, policy["caps"])
        versions = build_versions(docs, duplicates)
        chunks = build_chunks(docs, policy)
        if len(chunks) > policy["caps"].get("max_chunks", 200000):
            chunks = chunks[:policy["caps"]["max_chunks"]]
            errors.append({"stage": "index", "reason": "chunk_cap_reached",
                           "detail": "chunks truncated at %d" % len(chunks)})

    confidence = "no_question"
    if status != "failed" and not docs:
        status = "insufficient_input"
        confidence = "no_material"

    if status != "failed" and docs and not questions:
        status = "partial"
        confidence = "no_question"

    year_unmet = []
    if status in ("success", "partial") and docs and questions:
        for question in questions:
            wanted_years = question_years(question["text"])
            ranked, query_tokens, corpus_tokens = rank_chunks(
                chunks, question["text"], policy, wanted_years)
            missing = sorted(token for token in query_tokens if token not in corpus_tokens)[:12]
            question_citations, question_passages = [], []
            if not ranked or ranked[0][0] < policy["retrieval"].get("min_score", 2.0):
                answer_text = ("The supplied knowledge base contains no passage that supports "
                               "an answer to this question.")
                question_confidence = "no_evidence"
                gaps.append({
                    "question_id": question["id"], "question": question["text"],
                    "missing_terms": missing,
                    "reason": "no_passage_above_threshold" if ranked else "zero_lexical_match",
                })
            else:
                for rank, (score, chunk, matched) in enumerate(ranked, 1):
                    quote, quote_start, quote_end = pick_quote(chunk, query_tokens, policy)
                    doc = next(item for item in docs if item["file"] == chunk["file"])
                    version_tag = file_version_tag(chunk["file"])
                    version_year = (sorted(set(YEAR_RE.findall(Path(chunk["file"]).stem)))
                                    or sorted(set(YEAR_RE.findall(chunk["file"]))))
                    char_start = chunk["char_start"] + quote_start
                    char_end = chunk["char_start"] + quote_end
                    citation = {
                        "label": "S%d" % (len(citations) + 1),
                        "question_id": question["id"],
                        "file": chunk["file"],
                        "section": chunk["section"],
                        "page": None,
                        "line_start": line_of(doc["text"], char_start),
                        "line_end": line_of(doc["text"], char_end),
                        "char_start": char_start,
                        "char_end": char_end,
                        "quote": quote,
                        "quote_sha256": sha256_bytes(quote.encode("utf-8")),
                        "version_label": version_tag,
                        "version_year": version_year[0] if version_year else "",
                    }
                    citations.append(citation)
                    question_citations.append(citation)
                    question_passages.append({
                        "rank": rank, "question_id": question["id"],
                        "file": chunk["file"], "section": chunk["section"],
                        "page": None,
                        "line_start": citation["line_start"],
                        "line_end": citation["line_end"],
                        "char_start": char_start, "char_end": char_end,
                        "quote": quote, "score": score, "matched_terms": matched,
                        "citation": citation["label"],
                        "version_label": version_tag,
                        "version_year": citation["version_year"],
                    })
                    passages.append(question_passages[-1])
                answer_text = " ".join(
                    "%s [%s · version %s]" % (item["quote"], item["label"], item["version_label"])
                    for item in question_citations[:2])
                if len(question_citations) > 2:
                    answer_text += " Versions cited: %s." % ", ".join(
                        "%s=%s" % (item["label"], item["version_label"])
                        for item in question_citations[2:])
                top_score = ranked[0][0]
                if top_score >= policy["retrieval"].get("min_moderate_score", 3.0) and len(
                        question_passages) >= 2:
                    question_confidence = "moderate_lexical_support"
                else:
                    question_confidence = "low_lexical_support"
                seen_conflicts = set()
                for i in range(len(question_passages) - 1):
                    for j in range(i + 1, len(question_passages)):
                        left, right = question_passages[i], question_passages[j]
                        if left["file"] == right["file"]:
                            continue
                        for found in measurement_conflicts(left["quote"], right["quote"]):
                            key = (question["id"], found["quantity"], found["unit"],
                                   left["file"], right["file"], found["left_value"],
                                   found["right_value"], found["resolution"])
                            if key in seen_conflicts:
                                continue
                            seen_conflicts.add(key)
                            conflicts.append({
                                "question_id": question["id"],
                                "quantity": found["quantity"],
                                "unit": found["unit"],
                                "left": {"file": left["file"], "quote": left["quote"],
                                         "value": found["left_value"]},
                                "right": {"file": right["file"], "quote": right["quote"],
                                          "value": found["right_value"]},
                                "resolution": found["resolution"],
                            })
                if wanted_years and question_passages:
                    if not any(item.get("version_year") in wanted_years
                               for item in question_passages):
                        year_unmet.append({
                            "question_id": question["id"], "question": question["text"],
                            "wanted_years": wanted_years,
                            "cited_versions": [item["version_label"]
                                               for item in question_passages],
                        })
            answers.append({
                "question_id": question["id"], "question": question["text"],
                "answer": answer_text, "confidence": question_confidence,
                "citations": [item["label"] for item in question_citations],
                "supporting_passages": question_passages,
                "missing_terms": missing,
            })
        if answers:
            confidence = answers[0]["confidence"]
        if any(item["confidence"] == "no_evidence" for item in answers):
            status = "partial"
        elif any(item["confidence"] == "low_lexical_support" for item in answers):
            status = "partial"
        if conflicts:
            status = "partial"
        if year_unmet:
            status = "partial"
        if any(item.get("reason") in ("unreadable", "stat_failed") for item in skipped):
            status = "partial"

    if errors and status != "failed":
        status = "partial"
    if status == "success" and not questions:
        status = "partial"

    index = [{
        "file": doc["file"], "ext": doc["ext"], "bytes": doc["bytes"],
        "sha256": doc["sha256"], "hash_scope": doc["hash_scope"],
        "chars": doc["chars"], "line_count": doc["line_count"],
        "title": doc["title"], "years": doc["years"],
        "version_label": doc["version_label"], "extractor": doc["extractor"],
        "encoding": doc["encoding"], "permissions": doc["permissions"],
        "duplicate": False,
    } for doc in docs]
    for item in duplicates:
        index.append({
            "file": item["file"], "duplicate": True, "duplicate_of": item["duplicate_of"],
            "sha256": item["sha256"], "bytes": item["bytes"],
        })
    index.sort(key=lambda item: item["file"])

    needs_confirmation = []
    for gap in gaps:
        needs_confirmation.append({
            "item": "missing_evidence", "question_id": gap["question_id"],
            "locator": "question:%s" % gap["question_id"],
            "reason": "no passage above threshold for terms: %s" % (
                ", ".join(gap["missing_terms"]) or "all query terms"),
        })
    for conflict in conflicts:
        needs_confirmation.append({
            "item": "source_conflict", "question_id": conflict["question_id"],
            "locator": "%s | %s" % (conflict["left"]["file"], conflict["right"]["file"]),
            "reason": "%s for %s (%s); both passages are quoted, no arbitration"
                      % (conflict["resolution"], conflict["quantity"], conflict["unit"]),
        })
    for item in year_unmet:
        needs_confirmation.append({
            "item": "version_constraint_unmet", "question_id": item["question_id"],
            "locator": "question:%s" % item["question_id"],
            "reason": "question asks for %s but cited versions are %s"
                      % (", ".join(item["wanted_years"]),
                         ", ".join(item["cited_versions"]) or "none"),
        })
    for item in skipped:
        if item.get("reason", "").startswith(("unreadable", "stat_failed")):
            needs_confirmation.append({
                "item": "unreadable_file", "locator": item["path"],
                "reason": item["reason"],
            })

    uncertainty = [
        "Answers are extractive: they cannot state facts absent from the supplied files.",
        "Lexical retrieval may miss paraphrases, synonyms and cross-language matches.",
        "PDF citations use page=null; line numbers refer to extracted text, not printed pages.",
        "Version groups are derived from filename and metadata labels, not semantic diffs.",
    ]
    if duplicates:
        uncertainty.append("%d duplicate file(s) were identified by sha256 and not indexed twice."
                           % len(duplicates))
    if gaps:
        uncertainty.append("Some questions had no above-threshold evidence; see evidence_gaps.")
    if conflicts:
        uncertainty.append("Some passages report conflicting values or conditions; "
                           "both sides are quoted and no arbitration was performed.")
    if year_unmet:
        uncertainty.append("A year-constrained question could not be answered from that year's "
                           "documents; status is partial and cited versions are labelled.")
    if any(doc["ext"] in PDF_EXTS for doc in docs):
        uncertainty.append("PDF text extraction is heuristic; verify quotes against the PDF.")
    if not questions:
        uncertainty.append("No question was found in case.json or task.md; only an index was produced.")

    stats = {
        "files_seen": len(docs) + len(duplicates) + len(skipped),
        "files_indexed": len(docs),
        "duplicates": len(duplicates),
        "files_skipped": len(skipped),
        "chunks": len(chunks),
        "questions": len(questions),
        "answered": sum(1 for item in answers if item["confidence"] != "no_evidence"),
        "citations": len(citations),
        "passages": len(passages),
        "gaps": len(gaps),
        "conflicts": len(conflicts),
        "version_groups": len(versions),
        "errors": len(errors),
    }
    result = {
        "answer": answers[0]["answer"] if answers else
                  "No question was supplied." if docs else
                  "No readable material was supplied.",
        "answers": answers,
        "citations": citations,
        "supporting_passages": passages,
        "evidence_gaps": gaps,
        "conflicts": conflicts,
        "confidence": confidence,
        "index": index,
        "versions": versions,
        "duplicates": duplicates,
        "needs_human_confirmation": needs_confirmation,
    }
    payload = {
        "case_id": case_id,
        "status": status,
        "answers": answers,
        "answer": result["answer"],
        "citations": citations,
        "supporting_passages": passages,
        "evidence_gaps": gaps,
        "conflicts": conflicts,
        "confidence": confidence,
        "index": index,
        "versions": versions,
        "duplicates": duplicates,
        "skipped": skipped,
        "needs_human_confirmation": needs_confirmation,
        "result": result,
        "evidence": make_evidence(
            {"index": index},
            policy, policy_loaded,
            sorted({item["source"] for item in questions}) if questions else []),
        "uncertainty": uncertainty,
        "errors": errors,
        "stats": stats,
    }
    summary = "%d question(s), %d citation(s), %d file(s) indexed, status=%s" % (
        len(questions), len(citations), len(docs), status)

    output = {"case_id": case_id}
    mapping, notes = [], []
    for field in contract:
        if norm_key(field) in ("case_id", "caseid", "id"):
            output[field] = case_id
            mapping.append({"key": field, "mapped_to": "case_id", "mode": "exact"})
            continue
        canonical, value, mode = resolve_contract_field(field, payload)
        if canonical and value is not None:
            output[field] = value
            mapping.append({"key": field, "mapped_to": canonical, "mode": mode})
            if isinstance(value, (list, dict)) and not value:
                notes.append("%s mapped to %s and is empty because no such item was found."
                             % (field, canonical))
        elif canonical:
            output[field] = unknown_value(field, payload)
            mapping.append({"key": field, "mapped_to": canonical, "mode": "empty"})
            notes.append("%s has a known producer (%s) but no value was produced; "
                         "a structured cannot_determine object was written." % (field, canonical))
        else:
            output[field] = unknown_value(field, payload)
            mapping.append({"key": field, "mapped_to": None, "mode": "unknown"})
            notes.append("%s has no dedicated producer in this skill; a structured "
                         "cannot_determine object was written." % field)
    for key, value in payload.items():
        output.setdefault(key, value)
    output.setdefault("summary", summary)
    output.setdefault("run_log", [
        "entry: sk_entry.py v%s" % VERSION,
        "input: %s" % Path(args.input).name,
        "indexed files: %d" % len(docs),
        "questions: %d" % len(questions),
        "status: %s" % status,
        "write: result.json",
    ])
    output["contract_notes"] = notes
    output["contract_extras"] = {
        "contract_source": "case.json:output_contract",
        "contract_keys": contract,
        "mapping": mapping,
        "unknown_fields": [item["key"] for item in mapping if item["mode"] == "unknown"],
        "empty_or_unproduced_fields": [item["key"] for item in mapping
                                       if item["mode"] in ("unknown", "empty")],
        "accepted_extra_contract_keys": [item["key"] for item in mapping
                                          if item["mode"] == "unknown"],
        "generator_version": VERSION,
    }

    out_file, out_dir = resolve_out(args.out)
    write_json(out_file, output)
    try:
        work_dir = Path(args.work)
        work_dir.mkdir(parents=True, exist_ok=True)
        write_json(work_dir / "inventory.json", {
            "case_id": case_id,
            "files": index,
            "versions": versions,
            "duplicates": duplicates,
            "skipped": skipped,
            "stats": stats,
        })
        write_json(work_dir / "qa_evidence.json", {
            "case_id": case_id,
            "questions": questions,
            "answers": answers,
            "gaps": gaps,
            "conflicts": conflicts,
        })
        report = build_report(case_id, status, questions, answers, gaps, conflicts,
                              stats, uncertainty)
        write_text(work_dir / "qa-report.md", report)
        out_report = out_dir / "qa-report.md"
        if not out_report.exists():
            write_text(out_report, report)
    except OSError as exc:
        errors.append({"stage": "write_work", "reason": "work_write_failed",
                       "detail": str(exc)})
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Deterministic evidence-bound knowledge-base QA (stdlib only)")
    parser.add_argument("--input", "--case", dest="input", default="/input",
                        help="input directory or case.json (default /input)")
    parser.add_argument("--work", dest="work", default="/app/work",
                        help="work directory for inventory and QA evidence")
    parser.add_argument("--out", "--output", dest="out", default="/app/output",
                        help="output directory or result .json path")
    parser.add_argument("--version", action="version", version="sk_entry " + VERSION)
    return parser.parse_known_args(argv)


def raw_arg(argv, names, default):
    value = default
    for index, item in enumerate(argv):
        for name in names:
            if item == name and index + 1 < len(argv):
                value = argv[index + 1]
            elif item.startswith(name + "="):
                value = item.split("=", 1)[1]
    return value


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    policy, policy_loaded = load_policy()
    try:
        args, _unknown = parse_args(raw)
    except SystemExit:
        out_file, _out_dir = resolve_out(raw_arg(raw, ("--out", "--output"), "/app/output"))
        emergency_result(out_file, "invalid_arguments",
                         raw_arg(raw, ("--input", "--case"), "/input"),
                         policy, policy_loaded)
        return 0
    try:
        return run(args, policy, policy_loaded)
    except Exception as exc:
        out_file, _out_dir = resolve_out(args.out)
        emergency_result(out_file, "%s: %s" % (type(exc).__name__, exc),
                         args.input, policy, policy_loaded)
        return 0


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except Exception:
        pass
    sys.exit(0)
