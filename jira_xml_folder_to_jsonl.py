#!/usr/bin/env python3
# file: jira_xml_folder_to_jsonl.py

"""
JIRA XML ➜ JSONL (Agent-ready)

Converts a folder of Jira RSS XML exports (<rss><channel><item>...) into JSONL (1 issue per line),
cleaned for search (RAG/embeddings). Includes an interactive, colored CLI and bilingual UI (en, pt-BR).

Outputs:
- JSONL (always): one JSON object per line (best for ingestion)
- Pretty JSON (optional): <output>.pretty.json (indented array) for reading/debug

Notes:
- JSONL is intentionally not "pretty" because each record must be exactly one line.
- If you type an output name without an extension (e.g., "agent_ready"), the script will create it *without* extension.
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
from typing import Any, Callable


KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


I18N: dict[str, dict[str, str]] = {
    "en": {
        "header.title": "JIRA XML ➜ JSONL (Agent-ready)",
        "header.subtitle": "Converts Jira RSS XML exports into JSONL (1 issue per line), cleaned for search (RAG/embeddings).",
        "header.tip": "Tip: you can paste paths with quotes, or drag & drop a folder into the terminal.",
        "b1": "Strips HTML from description/comments (clean text)",
        "b2": "1 issue per line (JSONL) = great for indexing",
        "b3": "Optional: include customfields and/or raw_item_xml",
        "b4": "Beautify outputs an extra .pretty.json (indented) for reading",
        "p.example": "Example",
        "p.default": "Default",
        "p.enter": "Enter a value (or press Enter to use default)",
        "p.input.title": "1) Input folder (where the XML files are)",
        "p.input.howto": "Paste the folder path. It can be relative (./exports) or absolute.",
        "p.input.example": "./exports  or  /Users/you/Downloads/exports",
        "p.output.title": "2) Output file (JSONL)",
        "p.output.howto": "Enter path + filename. If you type 'agent_ready' it creates WITHOUT extension. If you type 'agent_ready.jsonl' it creates with extension.",
        "p.output.example": "./out/agent_ready.jsonl  or  ./out/agent_ready",
        "p.rec.title": "3) Search subfolders too?",
        "p.rec.howto": "Enable if your exports are split across nested folders.",
        "p.sort.title": "4) Sort files by name before processing?",
        "p.sort.howto": "Helps produce stable, repeatable output.",
        "p.cf.title": "5) Include customfields?",
        "p.cf.howto": "Recommended for retrieval, but can increase file size a lot.",
        "p.raw.title": "6) Include raw_item_xml (the <item> XML)?",
        "p.raw.howto": "Only if you want fully lossless storage. This can get very large.",
        "p.beautify.title": "7) Beautify?",
        "p.beautify.howto": "Generates an extra .pretty.json (indented) for reading/debug. JSONL stays 1 line per issue.",
        "p.ff.title": "8) Stop on first error?",
        "p.ff.howto": "If disabled, the script skips problematic files and continues.",
        "ui.processing": "Processing...",
        "ui.files_found": "Files found",
        "ui.no_xml": "No *.xml files found in this folder (or subfolders).",
        "ui.done": "✅ Done!",
        "ui.summary": "Summary",
        "ui.xml_read": "XML files scanned",
        "ui.issues_written": "Issues written",
        "ui.output_jsonl": "JSONL",
        "ui.output_pretty": "Pretty JSON",
        "ui.errors": "Errors occurred",
        "ui.try_again": "Try again.",
        "ui.must_be_folder": "Must be a valid folder.",
        "ui.path_not_exist": "Path does not exist.",
        "ui.answer_sn": "Answer with y/n.",
        "ui.invalid_rss": "XML is not RSS",
    },
    "pt-BR": {
        "header.title": "JIRA XML ➜ JSONL (Agent-ready)",
        "header.subtitle": "Converte exports XML (RSS) do Jira em JSONL (1 issue por linha), limpo pra busca (RAG/embeddings).",
        "header.tip": "Dica: você pode colar caminhos com aspas, ou arrastar e soltar uma pasta no terminal.",
        "b1": "Remove HTML de description/comments (texto limpo)",
        "b2": "1 issue por linha (JSONL) = ótimo para indexação",
        "b3": "Opcional: incluir customfields e/ou raw_item_xml",
        "b4": "Beautify gera um .pretty.json (indentado) para leitura",
        "p.example": "Exemplo",
        "p.default": "Padrão",
        "p.enter": "Digite o valor (ou Enter para usar o padrão)",
        "p.input.title": "1) Pasta de entrada (onde estão os XMLs)",
        "p.input.howto": "Cole o caminho da pasta. Pode ser relativo (./exports) ou absoluto.",
        "p.input.example": "./exports  ou  C:\\Users\\voce\\Downloads\\exports",
        "p.output.title": "2) Arquivo de saída (JSONL)",
        "p.output.howto": "Informe caminho + nome do arquivo. Se digitar 'agent_ready' ele cria SEM extensão. Se digitar 'agent_ready.jsonl' cria com extensão.",
        "p.output.example": "./out/agent_ready.jsonl  ou  ./out/agent_ready",
        "p.rec.title": "3) Buscar também em subpastas?",
        "p.rec.howto": "Ative se seus exports estiverem em subpastas.",
        "p.sort.title": "4) Ordenar arquivos por nome antes de processar?",
        "p.sort.howto": "Ajuda a ter saída estável/repetível.",
        "p.cf.title": "5) Incluir customfields?",
        "p.cf.howto": "Recomendado para busca, mas pode aumentar bastante o tamanho.",
        "p.raw.title": "6) Incluir raw_item_xml (XML bruto do <item>)?",
        "p.raw.howto": "Só se quiser lossless total. Pode ficar gigante.",
        "p.beautify.title": "7) Beautify?",
        "p.beautify.howto": "Gera também um .pretty.json (indentado) para leitura/debug. JSONL continua 1 linha por issue.",
        "p.ff.title": "8) Parar no primeiro erro?",
        "p.ff.howto": "Se desativar, ele pula arquivos problemáticos e segue.",
        "ui.processing": "Processando...",
        "ui.files_found": "Arquivos encontrados",
        "ui.no_xml": "Não achei nenhum *.xml nessa pasta (ou subpastas).",
        "ui.done": "✅ Concluído!",
        "ui.summary": "Resumo",
        "ui.xml_read": "XMLs lidos",
        "ui.issues_written": "Issues geradas",
        "ui.output_jsonl": "JSONL",
        "ui.output_pretty": "Pretty JSON",
        "ui.errors": "Ocorreram erros",
        "ui.try_again": "Tenta de novo.",
        "ui.must_be_folder": "Precisa ser uma pasta válida.",
        "ui.path_not_exist": "Caminho não existe.",
        "ui.answer_sn": "Responda com s/n.",
        "ui.invalid_rss": "XML não é RSS",
    },
}


def make_translator(lang: str) -> Callable[[str], str]:
    lang = (lang or "").strip()
    if lang not in I18N:
        lang = "en"

    def t(key: str, **kwargs: Any) -> str:
        s = I18N.get(lang, {}).get(key) or I18N["en"].get(key) or key
        try:
            return s.format(**kwargs)
        except Exception:
            return s

    return t


class UI:
    def __init__(self, t: Callable[[str], str]) -> None:
        self.t = t
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

    def line(self, s: str = "") -> None:
        print(s)

    def info(self, s: str) -> None:
        print(f"{self.cyan}{s}{self.reset}")

    def ok(self, s: str) -> None:
        print(f"{self.green}{s}{self.reset}")

    def warn(self, s: str) -> None:
        print(f"{self.yellow}{s}{self.reset}")

    def err(self, s: str) -> None:
        print(f"{self.red}{s}{self.reset}")

    def header(self) -> None:
        bar = "═" * 74
        self.line(f"{self.magenta}{bar}{self.reset}")
        self.line(f"{self.bold}{self.magenta}  {self.t('header.title')}{self.reset}")
        self.line(f"{self.dim}  {self.t('header.subtitle')}{self.reset}")
        self.line("")
        for b in ("b1", "b2", "b3", "b4"):
            self.line(f"  {self.green}•{self.reset} {self.t(b)}")
        self.line(f"{self.magenta}{bar}{self.reset}")
        self.line(f"{self.dim}{self.t('header.tip')}{self.reset}\n")


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


def parse_rss_items(xml_path: Path, t: Callable[[str], str]) -> list[ET.Element]:
    root = ET.parse(xml_path).getroot()
    if local_name(root.tag).lower() != "rss":
        raise ValueError(f"{t('ui.invalid_rss')} (root={root.tag})")

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
        "description_text": strip_html(find_text(item, "description")),
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
    s = (s or "").strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return Path(s).expanduser()


def prompt_path(ui: UI, title_key: str, howto_key: str, example_key: str, default: str,
                must_exist: bool, must_be_dir: bool) -> Path:
    ui.info(f"{ui.bold}{ui.t(title_key)}{ui.reset}")
    ui.line(f"{ui.dim}{ui.t(howto_key)}{ui.reset}")
    ui.line(f"{ui.dim}{ui.t('p.example')}: {ui.t(example_key)}{ui.reset}")
    ui.line(f"{ui.dim}{ui.t('p.default')}: {default}{ui.reset}")
    ui.line(f"{ui.dim}{ui.t('p.enter')}{ui.reset}")
    while True:
        s = input("> ").strip()
        p = normalize_user_path(s or default)

        if must_exist and not p.exists():
            ui.warn(f"⚠️  {ui.t('ui.path_not_exist')} {ui.t('ui.try_again')}")
            continue
        if must_be_dir and (not p.exists() or not p.is_dir()):
            ui.warn(f"⚠️  {ui.t('ui.must_be_folder')} {ui.t('ui.try_again')}")
            continue
        return p


def prompt_bool(ui: UI, title_key: str, howto_key: str, default: bool) -> bool:
    ui.info(f"{ui.bold}{ui.t(title_key)}{ui.reset}")
    ui.line(f"{ui.dim}{ui.t(howto_key)}{ui.reset}")
    d = "Y/n" if default else "y/N"
    while True:
        s = input(f"({d}) > ").strip().lower()
        if not s:
            return default
        if s in {"y", "yes", "s", "sim", "true", "1"}:
            return True
        if s in {"n", "no", "nao", "não", "false", "0"}:
            return False
        ui.warn(f"⚠️  {ui.t('ui.answer_sn')}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Convert Jira RSS XML folder to agent-ready JSONL (1 issue per line).")
    ap.add_argument("input_folder", type=Path, nargs="?", help="Folder with *.xml (Jira RSS exports)")
    ap.add_argument("output_jsonl", type=Path, nargs="?", help="Output JSONL file (no extension is allowed)")
    ap.add_argument("--lang", choices=sorted(I18N.keys()), default="pt-BR", help="UI language")
    ap.add_argument("--recursive", action="store_true", help="Search subfolders too")
    ap.add_argument("--sort", action="store_true", help="Sort files by name before processing")
    ap.add_argument("--include-customfields", action="store_true", help="Include customfields in JSON")
    ap.add_argument("--include-raw-item-xml", action="store_true", help="Include raw_item_xml (can be large)")
    ap.add_argument("--beautify", action="store_true", help="Also write <output>.pretty.json (indented array)")
    ap.add_argument("--fail-fast", action="store_true", help="Stop on first parsing error")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)

    t = make_translator(args.lang)
    ui = UI(t)

    if args.input_folder is None or args.output_jsonl is None:
        ui.header()
        args.input_folder = prompt_path(ui, "p.input.title", "p.input.howto", "p.input.example", "./exports", True, True)
        args.output_jsonl = prompt_path(ui, "p.output.title", "p.output.howto", "p.output.example", "./agent_ready.jsonl", False, False)
        args.recursive = prompt_bool(ui, "p.rec.title", "p.rec.howto", True)
        args.sort = prompt_bool(ui, "p.sort.title", "p.sort.howto", True)
        args.include_customfields = prompt_bool(ui, "p.cf.title", "p.cf.howto", True)
        args.include_raw_item_xml = prompt_bool(ui, "p.raw.title", "p.raw.howto", False)
        args.beautify = prompt_bool(ui, "p.beautify.title", "p.beautify.howto", True)
        args.fail_fast = prompt_bool(ui, "p.ff.title", "p.ff.howto", False)

    input_folder = Path(args.input_folder).expanduser()
    output_jsonl = Path(args.output_jsonl).expanduser()

    if not input_folder.exists() or not input_folder.is_dir():
        ui.err(f"{t('ui.must_be_folder')}: {input_folder}")
        return 2

    files = iter_xml_files(input_folder, args.recursive)
    if args.sort:
        files.sort(key=lambda p: str(p).lower())

    if not files:
        ui.warn(t("ui.no_xml"))
        return 2

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    opts = Options(bool(args.include_customfields), bool(args.include_raw_item_xml))

    issues_by_key: dict[str, dict[str, Any]] = {}
    errors: list[tuple[Path, str]] = []

    ui.line(f"{ui.bold}{t('ui.processing')}{ui.reset}")
    ui.line(f"{ui.dim}{t('ui.files_found')}: {len(files)}{ui.reset}\n")

    for f in files:
        try:
            for item in parse_rss_items(f, t):
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
    ui.line(f"  • {t('ui.xml_read')}: {len(files)}")
    ui.line(f"  • {t('ui.issues_written')}: {len(ordered)}")
    ui.line(f"  • {t('ui.output_jsonl')}: {output_jsonl.resolve()}")

    if args.beautify:
        pretty_path = output_jsonl.with_suffix(".pretty.json")
        with pretty_path.open("w", encoding="utf-8") as f:
            json.dump(ordered, f, ensure_ascii=False, indent=2)
        ui.line(f"  • {t('ui.output_pretty')}: {pretty_path.resolve()}")

    if errors:
        ui.warn(f"\n⚠️  {t('ui.errors')}: {len(errors)}")
        for p, msg in errors[:15]:
            ui.warn(f"  - {p.name}: {msg}")
        if len(errors) > 15:
            ui.warn(f"  ... +{len(errors) - 15}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
