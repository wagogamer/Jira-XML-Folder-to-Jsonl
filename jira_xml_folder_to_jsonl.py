#!/usr/bin/env python3
# file: jira_xml_folder_to_jsonl.py

"""
Convert Jira RSS XML exports in a folder to agent-ready JSONL (1 issue per line), cleaned for search.

Beautify option:
- Always writes JSONL (best for ingestion).
- If --beautify is enabled, also writes a pretty JSON array file:
    <output>.pretty.json

Modes:
- CLI mode: provide args normally.
- Interactive mode: run with no args and it will prompt for inputs.

Examples:
  python3 jira_xml_folder_to_jsonl.py ./exports agent_ready.jsonl --recursive --sort --include-customfields --beautify
  python3 jira_xml_folder_to_jsonl.py   # interactive prompts
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


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
        raise ValueError(f"XML não é RSS (root={root.tag})")

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
    return {
        "id": (proj.get("id") or "").strip(),
        "key": (proj.get("key") or "").strip(),
        "name": text_of(proj),
    }


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


def _prompt_path(prompt: str, default: str) -> Path:
    s = input(f"{prompt} [{default}]: ").strip()
    return Path((s or default)).expanduser()


def _prompt_bool(prompt: str, default: bool) -> bool:
    d = "Y/n" if default else "y/N"
    s = input(f"{prompt} ({d}): ").strip().lower()
    if not s:
        return default
    return s in {"y", "yes", "s", "sim", "true", "1"}


def parse_args_or_prompt(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Convert Jira RSS XML folder to agent-ready JSONL (1 issue per line).")
    ap.add_argument("input_folder", type=Path, nargs="?", help="Pasta com *.xml (Jira RSS exports)")
    ap.add_argument("output_jsonl", type=Path, nargs="?", help="Arquivo JSONL de saída")
    ap.add_argument("--recursive", action="store_true", help="Buscar em subpastas")
    ap.add_argument("--sort", action="store_true", help="Ordenar arquivos por nome")
    ap.add_argument("--include-customfields", action="store_true", help="Incluir customfields no JSON")
    ap.add_argument("--include-raw-item-xml", action="store_true", help="Incluir raw_item_xml (fica grande)")
    ap.add_argument("--beautify", action="store_true", help="Gerar também <output>.pretty.json (indentado)")
    ap.add_argument("--fail-fast", action="store_true", help="Parar no primeiro erro de parse")
    args = ap.parse_args(argv)

    if args.input_folder is None or args.output_jsonl is None:
        print("\nModo interativo:\n")
        args.input_folder = _prompt_path("Pasta de entrada (XMLs)", "./exports")
        args.output_jsonl = _prompt_path("Arquivo JSONL de saída", "./agent_ready.jsonl")
        args.recursive = _prompt_bool("Buscar subpastas?", True)
        args.sort = _prompt_bool("Ordenar arquivos por nome?", True)
        args.include_customfields = _prompt_bool("Incluir customfields?", True)
        args.include_raw_item_xml = _prompt_bool("Incluir raw_item_xml? (fica grande)", False)
        args.beautify = _prompt_bool("Beautify (gerar .pretty.json)?", True)
        args.fail_fast = _prompt_bool("Parar no primeiro erro?", False)

    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args_or_prompt(argv)

    input_folder: Path = args.input_folder
    output_jsonl: Path = args.output_jsonl

    if not input_folder.exists() or not input_folder.is_dir():
        print(f"ERRO: input_folder não é diretório: {input_folder}", file=sys.stderr)
        return 2

    files = iter_xml_files(input_folder, args.recursive)
    if args.sort:
        files.sort(key=lambda p: str(p).lower())

    opts = Options(
        include_customfields=args.include_customfields,
        include_raw_item_xml=args.include_raw_item_xml,
    )

    issues_by_key: dict[str, dict[str, Any]] = {}
    errors: list[tuple[Path, str]] = []

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

    # Always JSONL
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    ordered = [issues_by_key[k] for k in sorted(issues_by_key.keys())]

    with output_jsonl.open("w", encoding="utf-8") as out:
        for obj in ordered:
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(f"\nArquivos lidos:   {len(files)}")
    print(f"Issues escritas: {len(ordered)}")
    print(f"JSONL:           {output_jsonl.resolve()}")

    # Optional Beautify
    if args.beautify:
        pretty_path = output_jsonl.with_suffix(".pretty.json")
        with pretty_path.open("w", encoding="utf-8") as f:
            json.dump(ordered, f, ensure_ascii=False, indent=2)
        print(f"Pretty JSON:     {pretty_path.resolve()}")

    if errors:
        print(f"\nOcorreram {len(errors)} erro(s):", file=sys.stderr)
        for p, msg in errors:
            print(f"- {p.name}: {msg}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
