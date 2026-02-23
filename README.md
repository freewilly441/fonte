---

# 📄

````markdown
# Fonte

Fonte is an offline-first, multilingual knowledge base and Q&A desktop application built with Python and Tkinter. It provides local search, grounded answers from user-supplied documents, and optional on-device LLM support, designed to run reliably even in constrained or disconnected environments.

---

## Project Intent

- Intended to run on Linux-kernel Android mobile devices with limited resources  
- Designed for limited or no internet/cell service  
- Provides an offline knowledge base with local retrieval-augmented generation (RAG)  
- Supports optional local LLM backends  
- Current implementation is a Tkinter desktop MVP  
- Android packaging and mobile deployment are future targets  

---

## Features

- Local-first storage of documents, embeddings, and configuration  
- Retrieval-augmented Q&A from local files  
- GUI workflow for language selection and diagnostics  
- Optional local LLM support  
- Lightweight core with minimal dependencies  
- Works offline by design  

---

## Quickstart

### Windows (Native Python)

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
````

---

### WSL / Linux (Ubuntu / Debian)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

---

## Optional Dependencies

### Local LLM Support (GGUF / llama.cpp)

```bash
pip install -r requirements-llm.txt
```

---

### Packaging / Build Tooling

```bash
pip install -r requirements-packaging.txt
```

---

## Minimal vs Semantic Setup

Default install is lightweight and CPU-friendly:

```bash
pip install -r requirements.txt
```

Includes:

* Lexical retrieval via SQLite FTS
* Local document indexing
* Optional lightweight LLM integration

---

### Semantic / Vector Retrieval (Optional)

```bash
pip install -r requirements-semantic.txt
```

Why separate?

Semantic stacks typically pull large ML runtimes (e.g., PyTorch), greatly increasing disk usage and install time.

---

## LM Studio Backend (Recommended)

Fonte can use LM Studio as a local OpenAI-compatible LLM server.

Start LM Studio server:

```bash
lms server start --port 1234
```

Ensure models are loaded:

```bash
lms load google/gemma-3-1b
lms load qwen/qwen3-1.7b
```

Default configuration:

* Base URL: `http://localhost:1234/v1`
* Small model: `google/gemma-3-1b`
* Large model: `qwen/qwen3-1.7b`

---

## Ollama Backend (Optional)

Fonte can use Ollama instead of a local GGUF model.

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
* Model: e.g. `llama3.2:3b`

---

## Mobile Linux / Android (Headless CLI)

For Termux or Linux-based Android environments:

Initialize:

```bash
python3 fonte_mobile_parallel.py init
```

Ingest documents:

```bash
python3 fonte_mobile_parallel.py ingest ./data/user_docs --workers 4
```

Ask questions:

```bash
python3 fonte_mobile_parallel.py ask "What does this knowledge base contain?"
```

---

### Import from Wikipedia (Online)

```bash
python3 fonte_mobile_parallel.py ingest-wikipedia "solar system" --limit 5 --lang en
```

---

### Batch Processing

```bash
python3 fonte_mobile_parallel.py batch-ask queries.txt --workers 4
```

---

## Android Flashable Package

Build deployable package:

```bash
./scripts/build_android_flashable.sh
```

Output:

```
dist/fonte-mobile-flashable.zip
```

Includes:

* Termux installer
* Runtime scripts
* Headless CLI tools

---

## Lightweight Android Emulator

Build emulator:

```bash
./scripts/android_emulator_light.sh build
./scripts/android_emulator_light.sh start
```

Import existing image:

```bash
./scripts/android_emulator_light.sh import /path/to/fonte-lite.avd
```

List installed AVDs:

```bash
./scripts/android_emulator_light.sh list
```

Requirements:

* Android command-line tools
* ANDROID_SDK_ROOT configured

---

## WSL / WSLg GUI Notes

WSLg is recommended on Windows 11.

Requirements:

* `WAYLAND_DISPLAY` set
* `/mnt/wslg` present

Without WSLg:

* Install X server (VcXsrv, X410, etc.)
* Export display:

```bash
export DISPLAY=:0
```

---

## Runtime Data Location

All runtime data is stored in:

```
./data
```

Includes:

* Config
* Documents
* Embeddings

Ignored by git.

---

## Environment Variables

Enable debug mode:

```bash
FONTE_DEBUG=1 python3 app.py
```

PowerShell:

```powershell
$env:FONTE_DEBUG=1; python app.py
```

---

Make Run (Optional)

You may add a local make run shortcut, but no heavy tooling is required.

License

Add license information here if a LICENSE file is added.
