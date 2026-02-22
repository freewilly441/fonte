# Fonte

Fonte is an offline-first, multilingual knowledge base and Q&A desktop application built with Python and Tkinter. It provides local search, grounded answers from user-supplied documents, and optional on-device LLM support, designed to run reliably even in constrained or disconnected environments.

## Project Intent
- Intended to run on Linux-kernel Android mobile devices with limited resources.
- Designed for limited or no internet/cell service.
- Provides an offline knowledge base with local retrieval-augmented generation (RAG) and an optional local LLM.
- Note: the current implementation is a Tkinter desktop MVP; Android packaging is a future target.

## Features
- Local-first storage of documents, embeddings, and configuration
- GUI workflow for language selection and startup diagnostics
- Optional LLM backend support via `llama-cpp-python`
- Simple, minimal dependency set for core use

## Quickstart
### Windows (Native Python)
```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### WSL/WSLg (Ubuntu/Debian)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Optional dependencies:
- `pip install -r requirements-llm.txt` for local LLM support
- `pip install -r requirements-packaging.txt` for packaging/build tooling

## Minimal vs Semantic Setup
Default install is lightweight and CPU-friendly:

```bash
pip install -r requirements.txt
```

This includes local LLM support via `llama-cpp-python` and lexical retrieval (SQLite FTS).

Optional semantic/vector retrieval can be added separately:

```bash
pip install -r requirements-semantic.txt
```

Why separate? Semantic stacks (`sentence-transformers` + `hnswlib`) typically pull large ML runtimes, especially PyTorch, which significantly increases disk and install size.

### Ollama Backend (Optional)
Fonte can use Ollama as the Q&A LLM backend instead of loading a local GGUF directly.

1. Install Ollama and start the server:
```bash
ollama serve
```
2. Pull a model (example):
```bash
ollama pull llama3.2:3b
```
3. In Fonte Manage tab:
- Set `LLM Backend` to `ollama`
- Set `Ollama URL` (default `http://127.0.0.1:11434`)
- Set `Ollama Model` (example `llama3.2:3b`)
- Click `Save LLM Settings`

## Mobile Linux/Android (Headless Parallel CLI)
For mobile devices (Termux or other Linux-based Android environments), use the headless CLI:

```bash
python3 fonte_mobile_parallel.py init
python3 fonte_mobile_parallel.py ingest ./data/user_docs --workers 4
python3 fonte_mobile_parallel.py ask "What does this knowledge base contain?"
```

Import from Wikipedia (online):
```bash
python3 fonte_mobile_parallel.py ingest-wikipedia "solar system" --limit 5 --lang en
```

To run multiple questions in parallel:
```bash
python3 fonte_mobile_parallel.py batch-ask queries.txt --workers 4
```

Build a flashable/deployable zip package:
```bash
./scripts/build_android_flashable.sh
```

The package is generated at `dist/fonte-mobile-flashable.zip` and includes:
- mobile installer: `mobile/install_termux.sh`
- mobile runner: `mobile/run_mobile.sh`

### Lightweight Android Emulator (Build or Import)
If you want a small local emulator for Android testing in Linux/WSL, use:

```bash
./scripts/android_emulator_light.sh build
./scripts/android_emulator_light.sh start
```

To import an existing emulator image:
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
- Requires Android command-line tools (`sdkmanager`, `avdmanager`, `emulator`) under `ANDROID_SDK_ROOT`.
- Defaults are optimized for low resource usage (API 24, 1 CPU core, 1024 MB RAM, no boot animation/snapshots).

## WSL/WSLg GUI Notes
- WSLg is the simplest option on Windows 11. If WSLg is working, `WAYLAND_DISPLAY` should be set and `/mnt/wslg` should exist.
- If you are not using WSLg, you need an X server on Windows (e.g., VcXsrv or X410) and `DISPLAY` exported (commonly `export DISPLAY=:0`).
- If the GUI fails to start, verify WSLg/X server setup before running again.

## Runtime Data Location
All runtime data (config, documents, embeddings) is stored under `./data` and is ignored by git.

## Environment Variables
- `FONTE_DEBUG=1` enables lightweight startup logging and display diagnostics.

Debug run examples:
```bash
FONTE_DEBUG=1 python3 app.py
```
```powershell
$env:FONTE_DEBUG=1; python app.py
```

## Make Run (Optional)
If you prefer a shortcut, you can add a `make run` target locally, but this repo does not require any heavy tooling.

## License
Add license information here if a `LICENSE` file is added.
