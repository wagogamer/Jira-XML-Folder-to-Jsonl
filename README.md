# Jira XML ➜ Agent-Ready JSONL

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#requirements)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#license)
[![CLI](https://img.shields.io/badge/CLI-Interactive%20%2B%20Flags-purple.svg)](#usage)
[![i18n](https://img.shields.io/badge/i18n-en%20%7C%20pt--BR-orange.svg)](#language--i18n)

Converte uma pasta de **exports XML (RSS) do Jira** em **JSONL (1 issue por linha)**, **limpo pra busca** (RAG/embeddings), ideal para alimentar um **AI Agent**.

✅ Remove HTML de `description` e `comments` (vira texto “clean”)  
✅ Gera campo `text` com âncoras (`KEY`, `TYPE`, `SUMMARY`, etc.) pronto pra retrieval  
✅ Opções: incluir `customfields` e/ou `raw_item_xml` (lossless)  
✅ Interface bonita no terminal + **modo interativo**  
✅ **Idiomas separados** em `i18n/en.json` e `i18n/pt-BR.json` (fallback automático)

---

## Output (o que você recebe)

Você recebe um arquivo `.jsonl` onde **cada linha é um JSON** representando **uma issue**:

- `key`, `type`, `summary`, `status`, `priority`, `assignee`, `reporter`
- `created`, `updated`
- `project`
- `parent`, `subtasks` (quando existir)
- `description_text` (HTML removido)
- `comments_text` (HTML removido)
- `customfields` (opcional)
- `raw_item_xml` (opcional)
- `text` (campo principal para busca/embeddings)

> **JSONL não é “pretty” por definição**: é 1 JSON por linha para ingestão eficiente.

Opcionalmente, com `--beautify`, você ganha também um arquivo adicional:
- `<output>.pretty.json` (array JSON indentado, só para leitura/debug)

---

## Requirements

- Python **3.10+**
- Sem dependências externas (usa apenas stdlib)

---

## Instalação

Clone o repo e rode direto:

```bash
git clone <SEU_REPO_AQUI>
cd <SEU_REPO_AQUI>
python3 jira_xml_folder_to_jsonl.py

