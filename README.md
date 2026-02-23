````markdown
# Fonte

Fonte is an offline-first, multilingual knowledge base and Q&A application built with Python and Tkinter. It provides local search, grounded answers from user-supplied documents, and optional local LLM support, designed to run reliably even in constrained or disconnected environments.

## Project intent

- Targets Linux-kernel Android mobile devices with limited resources (future target)
- Designed for limited or no internet/cell service
- Offline knowledge base with retrieval-augmented generation (RAG)
- Optional local LLM backends
- Current implementation is a Tkinter desktop MVP

## Features

- Local-first storage of documents, embeddings, and configuration
- Retrieval-augmented Q&A from local files
- GUI workflow for language selection and basic diagnostics
- Optional local LLM support (multiple backends)
- Lightweight core dependency set for baseline use
- Offline by default

## Quickstart

### Windows (native Python)

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
````

### WSL / Linux (Ubuntu/Debian)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

## Optional dependencies

### Local LLM support (GGUF / llama.cpp)

```bash
pip install -r requirements-llm.txt
```

### Packaging / build tooling

```bash
pip install -r requirements-packaging.txt
```

## Minimal vs semantic setup

Default install is lightweight and CPU-friendly:

```bash
pip install -r requirements.txt
```

This includes lexical retrieval via SQLite FTS and the core application.

Semantic/vector retrieval can be added separately:

```bash
pip install -r requirements-semantic.txt
```

Why separate? Semantic stacks (e.g., sentence-transformers + hnswlib) often pull large ML runtimes (especially PyTorch), increasing disk usage and install time.

## LM Studio backend (recommended)

Fonte can use LM Studio as a local OpenAI-compatible LLM server.

Start the LM Studio server:

```bash
lms server start --port 1234
```

Load models (examples):

```bash
lms load google/gemma-3-1b
lms load qwen/qwen3-1.7b
```

Default configuration:

* Base URL: `http://localhost:1234/v1`
* Small model: `google/gemma-3-1b`
* Large model: `qwen/qwen3-1.7b`

## Ollama backend (optional)

Start Ollama:

```bash
ollama serve
```

Pull a model:

```bash
ollama pull llama3.2:3b
```

Configure in Fonte:

* Backend: `ollama`
* URL: `http://127.0.0.1:11434`
* Model: `llama3.2:3b`

## Mobile Linux / Android (headless CLI)

For Termux or Linux-based Android environments:

Initialize:

```bash
python3 fonte_mobile_parallel.py init
```

Ingest documents:

```bash
python3 fonte_mobile_parallel.py ingest ./data/user_docs --workers 4
```

Ask:

```bash
python3 fonte_mobile_parallel.py ask "What does this knowledge base contain?"
```

Import from Wikipedia (online):

```bash
python3 fonte_mobile_parallel.py ingest-wikipedia "solar system" --limit 5 --lang en
```

Batch ask:

```bash
python3 fonte_mobile_parallel.py batch-ask queries.txt --workers 4
```

## Android flashable package

Build:

```bash
./scripts/build_android_flashable.sh
```

Output:

* `dist/fonte-mobile-flashable.zip`

Includes Termux installer and mobile runner scripts under `mobile/`.

## Lightweight Android emulator

Build and start:

```bash
./scripts/android_emulator_light.sh build
./scripts/android_emulator_light.sh start
```

Import an existing image:

```bash
./scripts/android_emulator_light.sh import /path/to/fonte-lite.avd
# or:
./scripts/android_emulator_light.sh import /path/to/fonte-lite-avd.tar.gz
```

List installed AVDs:

```bash
./scripts/android_emulator_light.sh list
```

Notes:

* Requires Android command-line tools (`sdkmanager`, `avdmanager`, `emulator`) under `ANDROID_SDK_ROOT`
* Defaults are optimized for low resource usage

## WSL / WSLg GUI notes

WSLg is simplest on Windows 11. If WSLg is working, `WAYLAND_DISPLAY` should be set and `/mnt/wslg` should exist.

Without WSLg, you need an X server on Windows (VcXsrv, X410, etc.) and `DISPLAY` exported:

```bash
export DISPLAY=:0
```

## Runtime data location

All runtime data (config, documents, embeddings) is stored under `./data` and is ignored by git.

## Environment variables

Enable debug mode:

```bash
FONTE_DEBUG=1 python3 app.py
```

PowerShell example:

```powershell
$env:FONTE_DEBUG=1; python app.py
```

## License

Add license information here if a `LICENSE` file is added.

````

