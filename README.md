# Jira XML Folder ➜ Agent-Ready JSONL (EN)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#requirements)
[![License](https://img.shields.io/badge/License-MPL--2.0-green.svg)](#license)
[![CLI](https://img.shields.io/badge/CLI-Interactive%20%2B%20Flags-purple.svg)](#usage)
[![i18n](https://img.shields.io/badge/i18n-en%20%7C%20pt--BR-orange.svg)](#language--i18n)

Convert a folder of **Jira RSS XML exports** into **JSONL (1 issue per line)**, cleaned for search (RAG/embeddings). Perfect for feeding an AI agent with product/epic/story context.

- ✅ Parses Jira **RSS XML** (`<rss><channel><item>...</item></channel></rss>`)
- ✅ Strips HTML from `description` and `comments` (clean text)
- ✅ Generates a search-ready `text` field (KEY/TYPE/SUMMARY/… anchors)
- ✅ Optional: include `customfields`
- ✅ Optional: include `raw_item_xml` (lossless, larger output)
- ✅ Interactive CLI + flags
- ✅ UI language: **en** / **pt-BR** (strings in `en.json` + `pt-BR.json`)



## Requirements

- Python **3.10+**
- No external dependencies (stdlib only)



## Quickstart

```bash
git clone https://github.com/wagogamer/Jira-XML-Folder-to-Jsonl.git
cd Jira-XML-Folder-to-Jsonl
python3 jira_xml_folder_to_jsonl.py
```

##Run with flags

```python
python jira_xml_folder_to_jsonl.py ./exports agent_ready.jsonl \
  --recursive --sort --include-customfields --beautify --lang en
```

## Usage

##Interactive mode (recommended)
Run without arguments:

```python
python jira_xml_folder_to_jsonl.py
```

It will ask:

- UI language (en / pt-BR)
- Input folder (where *.xml are)
- Output file path (JSONL)
- Options: recursive, sort, customfields, raw XML, beautify

> Tip: you can paste paths with quotes or drag & drop folders into the terminal.

## CLI mode (flags)

```python
python jira_xml_folder_to_jsonl.py <INPUT_FOLDER> <OUTPUT_JSONL> [options]
```

`description`

Options:

- `--lang en|pt-BR` — interface language
- `--recursive` — scan subfolders for *.xml
- `--sort` — sort filenames (stable output)
- `--include-customfields` — include all Jira custom fields
- `--include-raw-item-xml` — store raw <item>...</item> XML (lossless, bigger)
- `--beautify` — generate <output>.pretty.json (readable/debug)
- `--fail-fast` — stop at first parsing error

## Output format

Main output is JSONL: one JSON object per line, one issue per object.

Common fields:

- `key`, `type`, `summary`, `title`
- `status`, `priority`, `assignee`, `reporter`
- `created`, `updated`
- `project` (id/key/name when available)
- `parent`, `subtasks`
- `description_text` (HTML stripped)
- `comments_text` (HTML stripped)
- `customfields` (optional)
- `raw_item_xml` (optional)
- `text` (main field for search/embeddings)

> JSONL is not “pretty” by design. Use --beautify to also get a readable .pretty.json.

## Important output filename rule

When the script asks for the output file:

- If you type agent_ready.jsonl → it creates with extension.
- If you type only agent_ready → it creates without an extension.

## Project structure

´´´
.
├── jira_xml_folder_to_jsonl.py
├── en.json
├── pt-BR.json
├── README.md
└── LICENSE
´´´

## Input XML format

´´´ xml
<rss>
  <channel>
    <item>
      <key>ABC-123</key>
      <summary>...</summary>
      <description><![CDATA[<p>...</p>]]></description>
      ...
    </item>
  </channel>
</rss>
´´´

## RAG / AI Agent tips

For embeddings/retrieval, index the text field.

-If recall is low:
-- enable `--include-customfields`
-- consider also embedding `description_text` and `comments_text`
-If you need “lossless” storage, enable `--include-raw-item-xml`.
