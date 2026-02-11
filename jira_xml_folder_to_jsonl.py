#!/usr/bin/env python3
# file: jira_xml_folder_to_jsonl.py

"""
Jira RSS XML folder -> Agent-ready JSONL (1 issue per line), cleaned for search.

- Reads Jira RSS exports: <rss><channel><item>...</item></channel></rss>
- Produces JSONL where each line is one issue (good for embeddings/RAG).
- Cleans HTML from description/comments.
- Optional: includes customfields and/or raw_item_xml.
- Optional: beautify generates an extra .pretty.json (indented) for reading.

Interactive mode: run without args.
CLI mode: pass args normally.
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

    def info(self, text: str) -> None:
        print(f"{self.cyan}{text}{self.reset}")

    def ok(self, text: str) -> None:
        print(f"{self.green}{text}{self.reset}")

    def warn(self, text: str) -> None:
        print(f"{self.yellow}{text}{self.reset}")

    def err(self, text: str) -> None:
        print(f"{self.red}{text}{self.reset}")

    def header(self) -> None:
        title = "JIRA XML ➜ JSONL (Agent-ready)"
        subtitle = (
            "Converte uma pasta de exports XML (RSS) do Jira em JSONL (1 issue por linha), "
            "limpo pra busca (RAG/embeddings)."
        )
        bullets = [
            "✅ Remove HTML de description/comments (vira texto limpo)",
            "✅ 1 issue por linha (JSONL) = ótimo para indexação",
            "✅ Opção de incluir customfields e/ou raw_item_xml",
            "✅ Beautify gera um .pretty.json (bonito) para leitura",
        ]

        bar = "═" * 72
        print(f"{self.magenta}{bar}{self.reset}")
        print(f"{self.bold}{self.magenta}  {title}{self.reset}")
        print(f"{self.dim}  {subtitle}{self.reset}")
        print()
        for b in bullets:
            print(f"  {self.green}•{self.reset} {b}")
        print(f"{self.magenta}{bar}{self.reset}\n")


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


# ----------------------------
# Interactive prompts (nice UX)
# ----------------------------
def normalize_user_path(s: str) -> Path:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return Path(s).expanduser()


def prompt_path(
    title: str,
    howto: str,
    example: str,
    default: str,
    must_exist: bool = False,
    must_be_dir: bool = False,
) -> Path:
    ui.info(f"{ui.bold}{title}{ui.reset}")
    ui.line(f"{ui.dim}{howto}{ui.reset}")
    ui.line(f"{ui.dim}Exemplo: {example}{ui.reset}")
    ui.line(f"{ui.dim}Padrão: {default}{ui.reset}")
    while True:
        s = input(f"> ").strip()
        if not s:
            p = normalize_user_path(default)
        else:
            p = normalize_user_path(s)

        if must_exist and not p.exists():
            ui.warn("⚠️  Caminho não existe. Tenta de novo.")
            continue
        if must_be_dir and (not p.exists() or not p.is_dir()):
            ui.warn("⚠️  Precisa ser uma pasta válida. Tenta de novo.")
            continue
        return p


def prompt_bool(title: str, howto: str, default: bool) -> bool:
    ui.info(f"{ui.bold}{title}{ui.reset}")
    ui.line(f"{ui.dim}{howto}{ui.reset}")
    d = "S/n" if default else "s/N"
    while True:
        s = input(f"( {d} ) > ").strip().lower()
        if not s:
            return default
        if s in {"s", "sim", "y", "yes", "1", "true"}:
            return True
        if s in {"n", "nao", "não", "no", "0", "false"}:
            return False
        ui.warn("⚠️  Responde com s/n (sim/não).")


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
        ui.header()
        ui.line(f"{ui.dim}Dica: você pode colar caminhos com aspas ou arrastar e soltar no terminal.{ui.reset}\n")

        args.input_folder = prompt_path(
            title="1) Pasta de entrada (onde estão os XMLs)",
            howto="Cole o caminho da pasta. Pode ser relativo (./exports) ou absoluto.",
            example="./exports   ou   C:\\\\Users\\\\voce\\\\Downloads\\\\exports",
            default="./exports",
            must_exist=True,
            must_be_dir=True,
        )

        args.output_jsonl = prompt_path(
            title="2) Arquivo de saída (JSONL)",
            howto=(
                "Informe o caminho + nome do arquivo.\n"
                "- Se você digitar 'agent_ready.jsonl' → cria com extensão.\n"
                "- Se você digitar só 'agent_ready' → cria SEM extensão (do jeito que você pediu).\n"
                "Dica: pode colocar numa pasta também (ex.: ./out/agent_ready.jsonl)."
            ),
            example="./out/agent_ready.jsonl   ou   ./out/agent_ready",
            default="./agent_ready.jsonl",
            must_exist=False,
            must_be_dir=False,
        )

        args.recursive = prompt_bool(
            title="3) Buscar também em subpastas?",
            howto="Se sua pasta tiver subpastas com XML, ative isso.",
            default=True,
        )

        args.sort = prompt_bool(
            title="4) Ordenar arquivos por nome antes de processar?",
            howto="Ajuda a ter saída estável/repetível.",
            default=True,
        )

        args.include_customfields = prompt_bool(
            title="5) Incluir customfields no JSON?",
            howto="Recomendado para busca. Pode aumentar bastante o tamanho.",
            default=True,
        )

        args.include_raw_item_xml = prompt_bool(
            title="6) Incluir raw_item_xml (XML bruto do <item>)?",
            howto="Só se você quiser lossless total. Fica bem maior.",
            default=False,
        )

        args.beautify = prompt_bool(
            title="7) Beautify?",
            howto="Gera também um arquivo .pretty.json (indentado) só pra leitura/debug. O JSONL continua 1 linha por issue.",
            default=True,
        )

        args.fail_fast = prompt_bool(
            title="8) Parar no primeiro erro?",
            howto="Se desativar, ele pula arquivos problemáticos e segue.",
            default=False,
        )

    return args


# ----------------------------
# Main
# ----------------------------
def main(argv: list[str] | None = None) -> int:
    args = parse_args_or_prompt(argv)

    input_folder: Path = Path(args.input_folder).expanduser()
    output_jsonl: Path = Path(args.output_jsonl).expanduser()

    if not input_folder.exists() or not input_folder.is_dir():
        ui.err(f"ERRO: input_folder não é uma pasta válida: {input_folder}")
        return 2

    files = iter_xml_files(input_folder, args.recursive)
    if args.sort:
        files.sort(key=lambda p: str(p).lower())

    if not files:
        ui.warn("⚠️  Não achei nenhum *.xml nessa pasta (ou subpastas).")
        ui.warn("Verifica se os arquivos terminam com .xml e se a pasta está correta.")
        return 2

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    opts = Options(
        include_customfields=bool(args.include_customfields),
        include_raw_item_xml=bool(args.include_raw_item_xml),
    )

    issues_by_key: dict[str, dict[str, Any]] = {}
    errors: list[tuple[Path, str]] = []

    ui.line(f"{ui.bold}Processando...{ui.reset}")
    ui.line(f"{ui.dim}Arquivos encontrados: {len(files)}{ui.reset}\n")

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

    # Always write JSONL
    with output_jsonl.open("w", encoding="utf-8") as out:
        for obj in ordered:
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")

    ui.ok("✅ Concluído!")
    ui.line(f"{ui.bold}Resumo{ui.reset}")
    ui.line(f"  • XMLs lidos:      {len(files)}")
    ui.line(f"  • Issues geradas:  {len(ordered)}")
    ui.line(f"  • JSONL:           {output_jsonl.resolve()}")

    # Optional Beautify -> pretty JSON array
    if args.beautify:
        pretty_path = output_jsonl.with_suffix(".pretty.json")
        with pretty_path.open("w", encoding="utf-8") as f:
            json.dump(ordered, f, ensure_ascii=False, indent=2)
        ui.line(f"  • Pretty JSON:     {pretty_path.resolve()}")

    if errors:
        ui.warn(f"\n⚠️  Ocorreram {len(errors)} erro(s):")
        for p, msg in errors[:15]:
            ui.warn(f"  - {p.name}: {msg}")
        if len(errors) > 15:
            ui.warn(f"  ... e mais {len(errors) - 15} erro(s).")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
