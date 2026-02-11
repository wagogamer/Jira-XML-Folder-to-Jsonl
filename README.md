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

