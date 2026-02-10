# Fonte

Fonte is a local, GUI-first knowledge base assistant that stores your documents and embeddings on disk and provides a lightweight desktop workflow for searching and interacting with them.

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
