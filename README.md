# Jira XML Folder ➜ Agent-Ready JSONL

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#requirements--requisitos)
[![License](https://img.shields.io/badge/License-MPL--2.0-green.svg)](#license--licença)
[![CLI](https://img.shields.io/badge/CLI-Interactive%20%2B%20Flags-purple.svg)](#usage--como-usar)
[![i18n](https://img.shields.io/badge/i18n-en%20%7C%20pt--BR-orange.svg)](#language--idiomas)

**EN** | [PT-BR](#pt-br)

Convert a folder of **Jira RSS XML exports** into **JSONL (1 issue per line)**, cleaned for search (RAG/embeddings). Perfect for feeding an AI agent with product/epic/story context.

- ✅ Parses Jira **RSS XML** (`<rss><channel><item>...</item></channel></rss>`)
- ✅ Strips HTML from `description` and `comments` (clean text)
- ✅ Generates a search-ready `text` field (KEY/TYPE/SUMMARY/… anchors)
- ✅ Optional: include `customfields`
- ✅ Optional: include `raw_item_xml` (lossless, larger output)
- ✅ Interactive CLI + flags
- ✅ UI language: **en** / **pt-BR** (strings in `en.json` + `pt-BR.json`)

---

## Table of contents

- [Requirements / Requisitos](#requirements--requisitos)
- [Quickstart / Começar rápido](#quickstart--começar-rápido)
- [Usage / Como usar](#usage--como-usar)
- [Output format / Formato de saída](#output-format--formato-de-saída)
- [Output filename rule / Regra do nome do arquivo](#important-output-filename-rule--regra-importante-do-nome-do-arquivo)
- [Project structure / Estrutura do projeto](#project-structure--estrutura-do-projeto)
- [Input XML format / Formato do XML](#input-xml-format--formato-do-xml)
- [RAG tips / Dicas para AI Agent](#rag--ai-agent-tips--dicas-para-ai-agent)
- [Troubleshooting](#troubleshooting--solução-de-problemas)
- [Language / i18n](#language--idiomas)
- [License / Licença](#license--licença)

---

## Requirements / Requisitos

- Python **3.10+**
- No external dependencies (stdlib only) / Sem dependências externas (apenas stdlib)

---

## Quickstart / Começar rápido

```bash
git clone https://github.com/wagogamer/Jira-XML-Folder-to-Jsonl.git
cd Jira-XML-Folder-to-Jsonl
python3 jira_xml_folder_to_jsonl.py
```

### Run with flags / Rodar com flags

```bash
python3 jira_xml_folder_to_jsonl.py ./exports agent_ready.jsonl \
  --recursive --sort --include-customfields --beautify --lang en
```

```bash
python3 jira_xml_folder_to_jsonl.py ./exports agent_ready.jsonl \
  --recursive --sort --include-customfields --beautify --lang pt-BR
```

---

## Usage / Como usar

### Interactive mode (recommended) / Modo interativo (recomendado)

Run without arguments / Rode sem argumentos:

```bash
python3 jira_xml_folder_to_jsonl.py
```

It will ask / Ele vai perguntar:

- UI language (en / pt-BR) / Idioma da interface (en / pt-BR)
- Input folder (where `*.xml` are) / Pasta de entrada (onde estão `*.xml`)
- Output file path (JSONL) / Caminho do arquivo de saída (JSONL)
- Options: recursive, sort, customfields, raw XML, beautify / Opções: recursivo, sort, customfields, raw XML, beautify

> Tip: you can paste paths with quotes or drag & drop folders into the terminal.  
> Dica: você pode colar caminhos com aspas ou arrastar e soltar pastas no terminal.

### CLI mode (flags) / Modo CLI (flags)

```bash
python3 jira_xml_folder_to_jsonl.py <INPUT_FOLDER> <OUTPUT_JSONL> [options]
```

Options / Opções:

- `--lang en|pt-BR` — interface language / idioma da interface  
- `--recursive` — scan subfolders for `*.xml` / busca em subpastas  
- `--sort` — sort filenames (stable output) / ordena arquivos (saída estável)  
- `--include-customfields` — include all Jira custom fields / inclui todos customfields  
- `--include-raw-item-xml` — store raw `<item>...</item>` XML (lossless, bigger) / guarda o XML bruto `<item>` (lossless, maior)  
- `--beautify` — generate `<output>.pretty.json` (readable/debug) / gera `<output>.pretty.json` (legível/debug)  
- `--fail-fast` — stop at first parsing error / para no primeiro erro  

---

## Output format / Formato de saída

Main output is **JSONL**: one JSON object per line, one issue per object.  
A saída principal é **JSONL**: 1 JSON por linha, 1 issue por linha.

Common fields / Campos comuns:

- `key`, `type`, `summary`, `title`
- `status`, `priority`, `assignee`, `reporter`
- `created`, `updated`
- `project` (id/key/name when available) / `project` (id/key/name quando existir)
- `parent`, `subtasks`
- `description_text` (HTML stripped) / `description_text` (HTML removido)
- `comments_text` (HTML stripped) / `comments_text` (HTML removido)
- `customfields` (optional) / `customfields` (opcional)
- `raw_item_xml` (optional) / `raw_item_xml` (opcional)
- `text` (main field for search/embeddings) / `text` (principal pra busca/embeddings)

> JSONL is not “pretty” by design. Use `--beautify` to also get a readable `.pretty.json`.  
> JSONL não é “pretty” por definição. Use `--beautify` pra gerar um `.pretty.json` legível.

---

## Important output filename rule / Regra importante do nome do arquivo

When the script asks for the output file / Quando o script pedir o output:

- If you type `agent_ready.jsonl` → it creates with extension.  
  Se você digitar `agent_ready.jsonl` → cria com extensão.
- If you type only `agent_ready` → it creates **without an extension**.  
  Se digitar só `agent_ready` → cria **sem extensão**.

---

## Project structure / Estrutura do projeto

```text
.
├── jira_xml_folder_to_jsonl.py
├── en.json
├── pt-BR.json
├── README.md
└── LICENSE
```

---

## Input XML format / Formato do XML

```xml
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
```

---

## RAG / AI Agent tips / Dicas para AI Agent

For embeddings/retrieval, index the `text` field.  
Para embeddings/retrieval, indexe o campo `text`.

1. If recall is low / Se o recall estiver baixo:
   - enable `--include-customfields` / use `--include-customfields`
   - consider embedding `description_text` and `comments_text` / considere também `description_text` e `comments_text`
2. If you need “lossless” storage / Se quiser “lossless”:
   - enable `--include-raw-item-xml` / use `--include-raw-item-xml`

---

## Troubleshooting / Solução de problemas

### “No *.xml files found” / “Não achei nenhum *.xml”

- Make sure files end with `.xml` / Confirme extensão `.xml`
- Confirm the folder path / Confirme o caminho da pasta
- Try `--recursive` if XML files are in subfolders / Use `--recursive` se estiver em subpastas

### “XML is not RSS” / “XML não é RSS”

- Your file is not the Jira RSS export format. Confirm it contains `<rss><channel><item>...`.  
  Seu XML não está no formato Jira RSS. Confirme que tem `<rss><channel><item>...`.

### “My agent can’t retrieve content” / “Meu agente não encontra direito”

Usually the ingestion pipeline embeds the wrong field.  
Normalmente o pipeline está embedando o campo errado.

- Ensure you embed `text` / Garanta que embedou `text`
- Keep 1 issue = 1 document (JSONL already does this) / 1 issue = 1 documento (JSONL já faz isso)

---

## Language / i18n / Idiomas

UI strings live in / As strings da interface ficam em:

- `en.json`
- `pt-BR.json`

You can add more languages by creating a new JSON and wiring it in the script.  
Você pode adicionar novos idiomas criando outro JSON e configurando no script.

---

## License / Licença

MPL-2.0. See `LICENSE`.  
MPL-2.0. Veja `LICENSE`.

---

# PT-BR

[EN](#jira-xml-folder--agent-ready-jsonl)

Converte uma pasta de **exports XML (RSS) do Jira** em **JSONL (1 issue por linha)**, limpo pra busca (RAG/embeddings). Ideal pra alimentar um AI Agent com contexto de épicos, features e histórias.

> Este README já está bilingue acima (EN + PT-BR). Use as seções “/” para navegar rapidamente.
