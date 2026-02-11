#!/usr/bin/env python3
# file: jira_xml_folder_to_jsonl.py

"""
Jira RSS XML folder -> Agent-ready JSONL (1 issue per line), cleaned for search.

Features
- Beautiful colored terminal UI (auto-disables if not a TTY or NO_COLOR is set).
- i18n: English (en) and Portuguese (pt-BR) via external JSON files.
- Interactive mode: run without positional args and it will prompt for everything.
- CLI mode: pass args normally.
- Output rule: if you type an output filename WITHOUT extension (e.g. "agent_ready"),
  the script will create exactly that (no forced extension).
- Optional: --beautify writes an extra "<output>.pretty.json" (indented) for human reading.

Expected input
- Jira XML RSS exports: <rss><channel><item>...</item></channel></rss>

Output
- JSONL: 1 issue per line with a "text" field optimized for search/RAG
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


# ----------------------------
# i18n (external files)
# ----------------------------

def load_i18n(base_dir: Path) -> dict[str, dict[str, str]]:
    """Load i18n JSON files.

    Supported layouts:
      A) <script_dir>/i18n/en.json, <script_dir>/i18n/pt-BR.json, ...
      B) <script_dir>/en.json, <script_dir>/pt-BR.json, ... (legacy/fallback)

    If nothing is found, returns an empty dict and the UI will fall back to keys.
    """
    data: dict[str, dict[str, str]] = {}

    def _try_load(p: Path) -> None:
        try:
            lang = p.stem  # "en", "pt-BR"
            data[lang] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return

    # Layout A: ./i18n/*.json
    i18n_dir = base_dir / "i18n"
    if i18n_dir.exists():
        for p in i18n_dir.glob("*.json"):
            _try_load(p)

    # Layout B: ./en.json and ./pt-BR.json (fallback)
    for lang in ("en", "pt-BR"):
        p = base_dir / f"{lang}.json"
        if p.exists() and lang not in data:
            _try_load(p)

    return data

    for p in i18n_dir.glob("*.json"):
        try:
            lang = p.stem
            data[lang] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            # Non-fatal: fallback will handle missing/invalid files.
            continue
    return data


def normalize_lang(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    low = s.lower()
    if low in {"pt", "ptbr", "pt-br", "pt_br", "ptbrasil"}:
        return "pt-BR"
    if low in {"en", "en-us", "en_us", "english"}:
        return "en"
    return s


def make_translator(i18n: dict[str, dict[str, str]], lang: str):
    lang = normalize_lang(lang)
    if lang not in i18n:
        lang = "en"  # default if not provided/unknown

    def t(key: str, **kwargs) -> str:
        s = i18n.get(lang, {}).get(key) or i18n.get("en", {}).get(key) or key
        return s.format(**kwargs)

    return t, lang


# ----------------------------
# Terminal UI (colors + banner)
# ----------------------------
class UI:
    def __init__(self) -> None:
        self.use_color = sys.stdout.isatty() and os.getenv("NO_COLOR") is None

    def c(self, code: str) -> str:
        return f"\x1b[{code}m" if self.use_color else ""

    @property
    def reset(self) -> str:
        return self.c("0")

    @property
    def bold(self) -> str:
        return self.c("1")

    @property
    def dim(self) -> str:
        return self.c("2")

    @property
    def green(self) -> str:
        return self.c("32")

    @property
    def yellow(self) -> str:
        return self.c("33")

    @property
    def red(self) -> str:
        return self.c("31")

    @property
    def cyan(self) -> str:
        return self.c("36")

    @property
    def magenta(self) -> str:
        return self.c("35")

    def line(self, text: str = "") -> None:
        print(text)

    def ok(self, text: str) -> None:
        print(f"{self.green}{text}{self.reset}")

    def warn(self, text: str) -> None:
        print(f"{self.yellow}{text}{self.reset}")

    def err(self, text: str) -> None:
        print(f"{self.red}{text}{self.reset}")

    def info(self, text: str) -> None:
        print(f"{self.cyan}{text}{self.reset}")

    def header(self, title: str, subtitle: str, tip: str) -> None:
        bar = "═" * 72
        print(f"{self.magenta}{bar}{self.reset}")
        print(f"{self.bold}{self.magenta}  {title}{self.reset}")
        print(f"{self.dim}  {subtitle}{self.reset}")
        print()
        for b in (
            "✅ HTML → text (description/comments)",
            "✅ JSONL (1 issue per line) for RAG/embeddings",
            "✅ Optional customfields + raw XML",
            "✅ Optional .pretty.json for reading",
        ):
            print(f"  {self.green}•{self.reset} {b}")
        print(f"{self.magenta}{bar}{self.reset}")
        print(f"{self.dim}{tip}{self.reset}\n")


ui = UI()


# ----------------------------
# HTML stripper
# ----------------------------
class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data and data.strip():
            self._parts.append(data.strip())

    def get_text(self) -> str:
        return " ".join(self._parts)


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    p = _HTMLStripper()
    p.feed(s)
    return re.sub(r"\s+", " ", p.get_text()).strip()


# ----------------------------
# XML helpers
# ----------------------------
def local_name(tag: str) -> str:
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    if ":" in tag:
        tag = tag.split(":", 1)[1]
    return tag


def iter_xml_files(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.xml" if recursive else "*.xml"
    return [p for p in folder.glob(pattern) if p.is_file()]


def is_key(s: str | None) -> bool:
    return bool(s and KEY_RE.match(s.strip()))


def text_of(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def find_child(parent: ET.Element, name: str) -> ET.Element | None:
    for ch in list(parent):
        if local_name(ch.tag) == name:
            return ch
    return None


def find_text(parent: ET.Element, name: str) -> str:
    return text_of(find_child(parent, name))


def parse_rss_items(xml_path: Path) -> list[ET.Element]:
    root = ET.parse(xml_path).getroot()
    if local_name(root.tag).lower() != "rss":
        raise ValueError(f"Not RSS (root={root.tag})")

    channel = None
    for ch in list(root):
        if local_name(ch.tag).lower() == "channel":
            channel = ch
            break
    if channel is None:
        return []

    return [el for el in list(channel) if local_name(el.tag) == "item"]


def extract_customfields(item: ET.Element) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    customfields = find_child(item, "customfields")
    if customfields is None:
        return out

    for cf in list(customfields):
        if local_name(cf.tag) != "customfield":
            continue

        name = ""
        values: list[str] = []

        for c in list(cf):
            ln = local_name(c.tag)
            if ln == "customfieldname":
                name = text_of(c)
            elif ln == "customfieldvalues":
                for v in c.iter():
                    if local_name(v.tag) == "customfieldvalue":
                        if v.text and v.text.strip():
                            values.append(v.text.strip())
                        else:
                            for d in v.iter():
                                if d.text and d.text.strip():
                                    values.append(d.text.strip())

        if name:
            seen: set[str] = set()
            clean_vals: list[str] = []
            for val in values:
                val = re.sub(r"\s+", " ", val).strip()
                if val and val not in seen:
                    seen.add(val)
                    clean_vals.append(val)
            out[name] = clean_vals

    return out


def extract_comments_text(item: ET.Element) -> str:
    comments = find_child(item, "comments")
    if comments is None:
        return ""
    parts: list[str] = []
    for c in comments.iter():
        if local_name(c.tag) == "comment":
            parts.append(strip_html(text_of(c)))
    return "\n".join([p for p in parts if p]).strip()


def extract_parent_key(item: ET.Element) -> str:
    parent = find_child(item, "parent")
    if parent is None:
        return ""
    pk = find_text(parent, "key") or text_of(parent)
    return pk.strip() if is_key(pk) else ""


def extract_subtasks(item: ET.Element) -> list[str]:
    subtasks_el = find_child(item, "subtasks")
    if subtasks_el is None:
        return []
    keys: list[str] = []
    for st in list(subtasks_el):
        if local_name(st.tag) != "subtask":
            continue
        k = find_text(st, "key")
        if is_key(k):
            keys.append(k.strip())
    return keys


def extract_project(item: ET.Element) -> dict[str, str]:
    proj = find_child(item, "project")
    if proj is None:
        return {}
    return {"id": (proj.get("id") or "").strip(), "key": (proj.get("key") or "").strip(), "name": text_of(proj)}


def node_weight(obj: Any) -> int:
    if isinstance(obj, dict):
        return sum(node_weight(v) for v in obj.values()) + len(obj) * 10
    if isinstance(obj, list):
        return sum(node_weight(v) for v in obj) + len(obj) * 5
    if isinstance(obj, str):
        return len(obj)
    return 1


def build_search_text(issue: dict[str, Any], include_customfields: bool) -> str:
    lines: list[str] = []

    def add(k: str, v: Any) -> None:
        if v is None:
            return
        if isinstance(v, str) and not v.strip():
            return
        lines.append(f"{k}: {v}")

    add("KEY", issue.get("key"))
    add("TYPE", issue.get("type"))
    add("SUMMARY", issue.get("summary"))
    add("STATUS", issue.get("status"))
    add("PRIORITY", issue.get("priority"))
    add("ASSIGNEE", issue.get("assignee"))
    add("REPORTER", issue.get("reporter"))
    add("CREATED", issue.get("created"))
    add("UPDATED", issue.get("updated"))

    proj = issue.get("project") or {}
    if isinstance(proj, dict):
        if proj.get("key"):
            add("PROJECT", proj.get("key"))
        if proj.get("name"):
            add("PROJECT_NAME", proj.get("name"))

    if issue.get("parent"):
        add("PARENT", issue.get("parent"))
    if issue.get("subtasks"):
        add("SUBTASKS", ", ".join(issue.get("subtasks")))

    if include_customfields:
        cfs = issue.get("customfields") or {}
        if isinstance(cfs, dict) and cfs:
            lines.append("")
            lines.append("CUSTOMFIELDS:")
            for name in sorted(cfs.keys(), key=str.lower):
                vals = cfs[name]
                if isinstance(vals, list) and vals:
                    lines.append(f"- {name}: {', '.join(vals)}")
                elif isinstance(vals, str) and vals.strip():
                    lines.append(f"- {name}: {vals.strip()}")

    desc = issue.get("description_text", "")
    if desc:
        lines.append("")
        lines.append("DESCRIPTION:")
        lines.append(desc)

    comm = issue.get("comments_text", "")
    if comm:
        lines.append("")
        lines.append("COMMENTS:")
        lines.append(comm)

    return "\n".join(lines).strip()


@dataclass
class Options:
    include_customfields: bool
    include_raw_item_xml: bool


def item_to_issue_dict(item: ET.Element, source_file: str, opts: Options) -> dict[str, Any] | None:
    key = find_text(item, "key").strip()
    if not is_key(key):
        return None

    summary = find_text(item, "summary").strip()
    title = find_text(item, "title").strip()

    issue_type = text_of(find_child(item, "type")).strip()
    status = text_of(find_child(item, "status")).strip()
    priority = text_of(find_child(item, "priority")).strip()

    assignee = text_of(find_child(item, "assignee")).strip()
    reporter = text_of(find_child(item, "reporter")).strip()

    created = find_text(item, "created").strip()
    updated = find_text(item, "updated").strip()

    description_text = strip_html(find_text(item, "description"))

    issue: dict[str, Any] = {
        "key": key,
        "type": issue_type,
        "summary": summary or strip_html(title),
        "title": strip_html(title),
        "status": status,
        "priority": priority,
        "assignee": assignee,
        "reporter": reporter,
        "created": created,
        "updated": updated,
        "project": extract_project(item),
        "parent": extract_parent_key(item),
        "subtasks": extract_subtasks(item),
        "description_text": description_text,
        "comments_text": extract_comments_text(item),
        "source_file": source_file,
    }

    if opts.include_customfields:
        issue["customfields"] = extract_customfields(item)

    if opts.include_raw_item_xml:
        issue["raw_item_xml"] = ET.tostring(item, encoding="unicode")

    issue["text"] = build_search_text(issue, include_customfields=opts.include_customfields)
    return issue


def normalize_user_path(s: str) -> Path:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return Path(s).expanduser()


def prompt_path(t, title: str, howto: str, example: str, default: str, must_exist: bool, must_be_dir: bool) -> Path:
    ui.info(f"{ui.bold}{title}{ui.reset}")
    ui.line(f"{ui.dim}{howto}{ui.reset}")
    ui.line(f"{ui.dim}Example/Exemplo: {example}{ui.reset}")
    ui.line(f"{ui.dim}Default/Padrão: {default}{ui.reset}")
    while True:
        s = input("> ").strip()
        p = normalize_user_path(s or default)
        if must_exist and not p.exists():
            ui.warn(t("ui.retry"))
            continue
        if must_be_dir and (not p.exists() or not p.is_dir()):
            ui.warn(t("ui.must_dir"))
            continue
        return p


def prompt_bool(t, title: str, howto: str, default: bool) -> bool:
    ui.info(f"{ui.bold}{title}{ui.reset}")
    ui.line(f"{ui.dim}{howto}{ui.reset}")
    d = "Y/n" if default else "y/N"
    while True:
        s = input(f"( {d} ) > ").strip().lower()
        if not s:
            return default
        if s in {"y", "yes", "s", "sim", "true", "1"}:
            return True
        if s in {"n", "no", "nao", "não", "false", "0"}:
            return False
        ui.warn(t("ui.answer_sn"))


def parse_args_or_prompt(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_folder", type=Path, nargs="?", help="Folder containing XML files")
    ap.add_argument("output_jsonl", type=Path, nargs="?", help="Output JSONL path")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--sort", action="store_true")
    ap.add_argument("--include-customfields", action="store_true")
    ap.add_argument("--include-raw-item-xml", action="store_true")
    ap.add_argument("--beautify", action="store_true")
    ap.add_argument("--fail-fast", action="store_true")
    ap.add_argument("--lang", default="", help="Language: en or pt-BR")
    args = ap.parse_args(argv)

    base_dir = Path(__file__).resolve().parent
    i18n = load_i18n(base_dir)

    if not i18n:
        ui.warn("⚠️  i18n files not found. Expected ./i18n/en.json (or ./en.json). Falling back to keys.")

    # Interactive: ask language first (unless provided via --lang)
    if (args.input_folder is None or args.output_jsonl is None) and not args.lang:
        print("Language / Idioma")
        print("  1) pt-BR (Português)")
        print("  2) en (English)")
        choice = input("[1/2] (default=1): ").strip() or "1"
        args.lang = "en" if choice == "2" else "pt-BR"

    t, lang = make_translator(i18n, args.lang)

    if args.input_folder is None or args.output_jsonl is None:
        ui.header(t("header.title"), t("header.subtitle"), t("header.tip"))

        args.input_folder = prompt_path(
            t,
            t("step.input.title"),
            t("step.input.howto"),
            t("step.input.example"),
            "./exports",
            must_exist=True,
            must_be_dir=True,
        )

        args.output_jsonl = prompt_path(
            t,
            t("step.output.title"),
            t("step.output.howto"),
            t("step.output.example"),
            "./agent_ready.jsonl",
            must_exist=False,
            must_be_dir=False,
        )

        args.recursive = prompt_bool(t, t("step.recursive.title"), t("step.recursive.howto"), True)
        args.sort = prompt_bool(t, t("step.sort.title"), t("step.sort.howto"), True)
        args.include_customfields = prompt_bool(t, t("step.customfields.title"), t("step.customfields.howto"), True)
        args.include_raw_item_xml = prompt_bool(t, t("step.rawxml.title"), t("step.rawxml.howto"), False)
        args.beautify = prompt_bool(t, t("step.beautify.title"), t("step.beautify.howto"), True)
        args.fail_fast = prompt_bool(t, t("step.failfast.title"), t("step.failfast.howto"), False)

    args._t = t  # type: ignore[attr-defined]
    args._lang = lang  # type: ignore[attr-defined]
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args_or_prompt(argv)
    t = args._t  # type: ignore[attr-defined]

    input_folder: Path = Path(args.input_folder).expanduser()
    output_jsonl: Path = Path(args.output_jsonl).expanduser()

    if not input_folder.exists() or not input_folder.is_dir():
        ui.err(f"ERROR: input_folder is not a valid folder: {input_folder}")
        return 2

    files = iter_xml_files(input_folder, args.recursive)
    if args.sort:
        files.sort(key=lambda p: str(p).lower())

    if not files:
        ui.warn(t("ui.no_xml"))
        return 2

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    opts = Options(include_customfields=bool(args.include_customfields), include_raw_item_xml=bool(args.include_raw_item_xml))

    issues_by_key: dict[str, dict[str, Any]] = {}
    errors: list[tuple[Path, str]] = []

    ui.line(f"{ui.bold}{t('ui.processing')}{ui.reset}")
    ui.line(f"{ui.dim}{t('ui.files_found', n=len(files))}{ui.reset}\n")

    for f in files:
        try:
            for item in parse_rss_items(f):
                issue = item_to_issue_dict(item, source_file=f.name, opts=opts)
                if issue is None:
                    continue
                k = issue["key"]
                prev = issues_by_key.get(k)
                if prev is None or node_weight(issue) > node_weight(prev):
                    issues_by_key[k] = issue
        except Exception as exc:  # noqa: BLE001
            errors.append((f, f"{type(exc).__name__}: {exc}"))
            if args.fail_fast:
                break

    ordered = [issues_by_key[k] for k in sorted(issues_by_key.keys())]

    with output_jsonl.open("w", encoding="utf-8") as out:
        for obj in ordered:
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")

    ui.ok(t("ui.done"))
    ui.line(f"{ui.bold}{t('ui.summary')}{ui.reset}")
    ui.line(f"  • {t('ui.xml_read', n=len(files))}")
    ui.line(f"  • {t('ui.issues_written', n=len(ordered))}")
    ui.line(f"  • {t('ui.jsonl', path=str(output_jsonl.resolve()))}")

    if args.beautify:
        pretty_path = output_jsonl.with_suffix(".pretty.json")
        with pretty_path.open("w", encoding="utf-8") as f:
            json.dump(ordered, f, ensure_ascii=False, indent=2)
        ui.line(f"  • {t('ui.pretty', path=str(pretty_path.resolve()))}")

    if errors:
        ui.warn(t("ui.errors", n=len(errors)))
        for p, msg in errors[:15]:
            ui.warn(f"  - {p.name}: {msg}")
        if len(errors) > 15:
            ui.warn(t("ui.errors_more", n=len(errors) - 15))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
