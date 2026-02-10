import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
import os
import sys
import signal
import socket
import stat
from pathlib import Path
import shutil

import kb
import utils
import config
import llm as llm_api

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "kb.sqlite"
SAMPLE_DIR = DATA_DIR / "sample_docs"
USER_DIR = DATA_DIR / "user_docs"
CONFIG_PATH = DATA_DIR / "config.json"
VECTOR_INDEX_PATH = DATA_DIR / "vector_index.bin"
VECTOR_META_PATH = DATA_DIR / "vector_meta.npz"
MODELS_DIR = DATA_DIR / "models"
# Language selection must be explicit to avoid unintended defaults (e.g., auto-selected locales).
PROMPT_LANGUAGE_EACH_START = True
# Production toggle: set to False for distro builds to respect saved ui_language.


def debug(msg: str) -> None:
    # Enable lightweight startup diagnostics by setting FONTE_DEBUG=1.
    if os.getenv("FONTE_DEBUG") == "1":
        print(f"[fonte] {msg}")


def _ensure_required_dirs() -> None:
    for path in (DATA_DIR, SAMPLE_DIR, USER_DIR, MODELS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _is_display_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        needle in text
        for needle in (
            "no display name and no $display",
            "couldn't connect to display",
            "cannot open display",
            "can't open display",
        )
    )


def _is_wsl() -> bool:
    if os.getenv("WSL_INTEROP") or os.getenv("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def _parse_display_socket(display: str) -> Path | None:
    if not display:
        return None
    if ":" not in display:
        return None
    suffix = display.rsplit(":", 1)[-1]
    number = suffix.split(".", 1)[0]
    if not number.isdigit():
        return None
    return Path("/tmp/.X11-unix") / f"X{number}"


def _check_unix_socket(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, f"socket missing: {path}"
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        return False, f"cannot stat socket {path}: {exc}"
    if not stat.S_ISSOCK(mode):
        return False, f"not a socket: {path}"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.connect(str(path))
        return True, None
    except OSError as exc:
        return False, f"cannot connect to socket {path}: {exc}"


def _gui_preflight() -> tuple[bool, str | None]:
    # WSLg/X11/Wayland display checks give fast, actionable errors instead of a hung Tk init.
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True, None
    display = os.getenv("DISPLAY") or ""
    wayland = os.getenv("WAYLAND_DISPLAY") or ""
    mir = os.getenv("MIR_SOCKET") or ""
    if not (display or wayland or mir):
        return False, "no DISPLAY/Wayland environment detected"

    reasons = []
    if display:
        sock_path = _parse_display_socket(display)
        if sock_path is None:
            reasons.append(f"unrecognized DISPLAY value: {display!r}")
        else:
            ok, reason = _check_unix_socket(sock_path)
            if ok:
                return True, None
            reasons.append(reason or "X11 socket check failed")
    if wayland:
        runtime_dir = os.getenv("XDG_RUNTIME_DIR") or ""
        if not runtime_dir:
            reasons.append("XDG_RUNTIME_DIR is not set for Wayland")
        else:
            sock_path = Path(runtime_dir) / wayland
            ok, reason = _check_unix_socket(sock_path)
            if ok:
                return True, None
            reasons.append(reason or "Wayland socket check failed")
    if mir:
        return True, None
    return False, "; ".join(r for r in reasons if r)


def _tk_timeout_handler(signum, frame) -> None:  # pragma: no cover - signal path
    _print_no_display_help("tk.Tk() timed out while connecting to the display")
    raise SystemExit(2)


def _start_tk_init_watchdog(timeout_sec: int) -> bool:
    if os.name != "posix":
        return False
    try:
        signal.signal(signal.SIGALRM, _tk_timeout_handler)
        signal.alarm(timeout_sec)
        return True
    except (ValueError, OSError):
        return False


def _cancel_tk_init_watchdog() -> None:
    if os.name == "posix":
        signal.alarm(0)


def _print_no_display_help(reason: str | None = None) -> None:
    print("Fonte requires a GUI display, but no display is available.")
    if reason:
        print(f"Reason: {reason}")
    print("Hints:")
    print("- If you use an X server, try: export DISPLAY=:0")
    print("- Install/run an X server on Windows (VcXsrv/X410) or use WSLg if available")
    if _is_wsl():
        print("- WSL detected: confirm WSLg is installed and /mnt/wslg exists")
        print("- Try restarting WSL (`wsl --shutdown` from Windows) and relaunch")
    print("How to run: python3 app.py")

PROFILES = {
    "low": {"retrieval_limit": 3, "llm_max_tokens": 160},
    "balanced": {"retrieval_limit": 4, "llm_max_tokens": 192},
    "high": {"retrieval_limit": 6, "llm_max_tokens": 256},
}

LANG_CHOICES = [
    ("English", "en"),
    ("Português", "pt"),
    ("Deutsch", "de"),
]

I18N = {
    "en": {
        "app_title": "Fonte",
        "tab_search": "Search",
        "tab_qa": "Q&A",
        "tab_utils": "Utilities",
        "tab_manage": "Manage",
        "search_header": "Search the local knowledge base",
        "search_button": "Search",
        "no_results": "No results.",
        "qa_header": "Ask a question (answers only from local data)",
        "answer_button": "Answer",
        "citations_label": "Citations",
        "no_citations": "No citations",
        "calculator": "Calculator",
        "compute": "Compute",
        "unit_conversion": "Unit Conversion",
        "convert_length": "Convert (Length)",
        "temp_conversion": "Temperature Conversion",
        "convert_temp": "Convert (Temp)",
        "date_utils": "Date Utilities",
        "add_days": "Add Days",
        "documents_header": "Documents",
        "documents_subheader": "Documents in local knowledge base",
        "models_header": "Models",
        "device_profile_header": "Device Profile",
        "status_header": "Status",
        "import_text": "Import Text File",
        "delete_selected": "Delete Selected",
        "rebuild_index": "Rebuild Index",
        "rebuild_vector": "Rebuild Vector Index",
        "set_embedding_model": "Set Embedding Model",
        "set_llm_model": "Set LLM Model",
        "demo_tour": "Demo Tour",
        "device_profile": "Device Profile",
        "apply_profile": "Apply Profile",
        "demo_mode": "Demo Mode",
        "model_download_url": "Model download URL",
        "download_model": "Download Model",
        "storage_status": "DB size: {size_mb:.2f} MB | Documents: {count}",
        "model_status": "Embedding: {embedding} | LLM: {llm} | Profile: {profile} | Demo: {demo}",
        "status_bar": "DB: {size_mb:.2f} MB | Docs: {count} | Profile: {profile} | Language: {language} | Models: {models}",
        "model_set": "set",
        "model_not_set": "not set",
        "lang_en": "English",
        "lang_pt": "Português",
        "lang_de": "Deutsch",
        "imported_title": "Imported",
        "imported_msg": "Imported {name}",
        "import_failed_title": "Import failed",
        "select_text_file": "Select text file",
        "missing_model_title": "Missing model",
        "missing_model_msg": "Set the embedding model path first.",
        "vector_index_title": "Vector index",
        "vector_index_built": "Built vector index for {count} chunks (dim {dim}).",
        "vector_index_failed": "Vector index failed",
        "select_embedding_dir": "Select embedding model directory",
        "select_llm_file": "Select LLM model file",
        "download_failed_title": "Download failed",
        "download_failed_msg": "Provide a model URL first.",
        "download_complete_title": "Download complete",
        "download_complete_msg": "Saved to {dest}",
        "llm_error": "LLM error: {error}",
        "error_prefix": "Error: {error}",
        "unknown_answer": "I don't know. The local knowledge base doesn't contain this information.",
        "splash_text": "Fonte\n\nLocal search + grounded Q&A\nNo internet required.",
        "menu_file": "File",
        "menu_settings": "Settings",
        "menu_help": "Help",
        "menu_import": "Import Text File",
        "menu_exit": "Exit",
        "menu_language": "Language...",
        "menu_device_profile": "Device Profile",
        "menu_about": "About",
        "about_text": "Fonte - Offline knowledge base and grounded Q&A",
        "language_dialog_title": "Fonte",
        "language_dialog_prompt": "Select language / Selecione o idioma / Sprache wählen",
        "language_dialog_ok": "OK",
        "language_dialog_cancel": "Cancel",
    },
    "pt": {
        "app_title": "Fonte",
        "tab_search": "Pesquisa",
        "tab_qa": "Perguntas e Respostas",
        "tab_utils": "Utilitários",
        "tab_manage": "Gerenciar",
        "search_header": "Pesquisar na base de conhecimento local",
        "search_button": "Pesquisar",
        "no_results": "Nenhum resultado.",
        "qa_header": "Faça uma pergunta (respostas apenas de dados locais)",
        "answer_button": "Responder",
        "citations_label": "Citações",
        "no_citations": "Sem citações",
        "calculator": "Calculadora",
        "compute": "Calcular",
        "unit_conversion": "Conversão de Unidades",
        "convert_length": "Converter (Comprimento)",
        "temp_conversion": "Conversão de Temperatura",
        "convert_temp": "Converter (Temperatura)",
        "date_utils": "Utilitários de Data",
        "add_days": "Adicionar dias",
        "documents_header": "Documentos",
        "documents_subheader": "Documentos na base de conhecimento local",
        "models_header": "Modelos",
        "device_profile_header": "Perfil do dispositivo",
        "status_header": "Status",
        "import_text": "Importar arquivo de texto",
        "delete_selected": "Excluir selecionado",
        "rebuild_index": "Reconstruir índice",
        "rebuild_vector": "Reconstruir índice vetorial",
        "set_embedding_model": "Definir modelo de embedding",
        "set_llm_model": "Definir modelo LLM",
        "demo_tour": "Tour de demonstração",
        "device_profile": "Perfil do dispositivo",
        "apply_profile": "Aplicar perfil",
        "demo_mode": "Modo de demonstração",
        "model_download_url": "URL de download do modelo",
        "download_model": "Baixar modelo",
        "storage_status": "Tamanho do BD: {size_mb:.2f} MB | Documentos: {count}",
        "model_status": "Embedding: {embedding} | LLM: {llm} | Perfil: {profile} | Demo: {demo}",
        "status_bar": "BD: {size_mb:.2f} MB | Docs: {count} | Perfil: {profile} | Idioma: {language} | Modelos: {models}",
        "model_set": "definido",
        "model_not_set": "não definido",
        "lang_en": "Inglês",
        "lang_pt": "Português",
        "lang_de": "Alemão",
        "imported_title": "Importado",
        "imported_msg": "Importado {name}",
        "import_failed_title": "Falha na importação",
        "select_text_file": "Selecionar arquivo de texto",
        "missing_model_title": "Modelo ausente",
        "missing_model_msg": "Defina primeiro o caminho do modelo de embedding.",
        "vector_index_title": "Índice vetorial",
        "vector_index_built": "Índice vetorial criado para {count} trechos (dim {dim}).",
        "vector_index_failed": "Falha no índice vetorial",
        "select_embedding_dir": "Selecionar diretório do modelo de embedding",
        "select_llm_file": "Selecionar arquivo do modelo LLM",
        "download_failed_title": "Falha no download",
        "download_failed_msg": "Forneça primeiro uma URL do modelo.",
        "download_complete_title": "Download concluído",
        "download_complete_msg": "Salvo em {dest}",
        "llm_error": "Erro do LLM: {error}",
        "error_prefix": "Erro: {error}",
        "unknown_answer": "Não sei. A base de conhecimento local não contém esta informação.",
        "splash_text": "Fonte\n\nPesquisa local + Q&A fundamentado\nSem internet.",
        "menu_file": "Arquivo",
        "menu_settings": "Configurações",
        "menu_help": "Ajuda",
        "menu_import": "Importar arquivo de texto",
        "menu_exit": "Sair",
        "menu_language": "Idioma...",
        "menu_device_profile": "Perfil do dispositivo",
        "menu_about": "Sobre",
        "about_text": "Fonte - Base de conhecimento offline e Q&A fundamentado",
        "language_dialog_title": "Fonte",
        "language_dialog_prompt": "Select language / Selecione o idioma / Sprache wählen",
        "language_dialog_ok": "OK",
        "language_dialog_cancel": "Cancelar",
    },
    "de": {
        "app_title": "Fonte",
        "tab_search": "Suche",
        "tab_qa": "Fragen & Antworten",
        "tab_utils": "Werkzeuge",
        "tab_manage": "Verwalten",
        "search_header": "Lokale Wissensbasis durchsuchen",
        "search_button": "Suchen",
        "no_results": "Keine Ergebnisse.",
        "qa_header": "Stelle eine Frage (Antworten nur aus lokalen Daten)",
        "answer_button": "Antworten",
        "citations_label": "Quellen",
        "no_citations": "Keine Quellen",
        "calculator": "Rechner",
        "compute": "Berechnen",
        "unit_conversion": "Einheitenumrechnung",
        "convert_length": "Umrechnen (Länge)",
        "temp_conversion": "Temperaturumrechnung",
        "convert_temp": "Umrechnen (Temperatur)",
        "date_utils": "Datumswerkzeuge",
        "add_days": "Tage hinzufügen",
        "documents_header": "Dokumente",
        "documents_subheader": "Dokumente in der lokalen Wissensbasis",
        "models_header": "Modelle",
        "device_profile_header": "Geräteprofil",
        "status_header": "Status",
        "import_text": "Textdatei importieren",
        "delete_selected": "Auswahl löschen",
        "rebuild_index": "Index neu erstellen",
        "rebuild_vector": "Vektorindex neu erstellen",
        "set_embedding_model": "Embedding-Modell festlegen",
        "set_llm_model": "LLM-Modell festlegen",
        "demo_tour": "Demo-Tour",
        "device_profile": "Geräteprofil",
        "apply_profile": "Profil anwenden",
        "demo_mode": "Demo-Modus",
        "model_download_url": "Modell-Download-URL",
        "download_model": "Modell herunterladen",
        "storage_status": "DB-Größe: {size_mb:.2f} MB | Dokumente: {count}",
        "model_status": "Embedding: {embedding} | LLM: {llm} | Profil: {profile} | Demo: {demo}",
        "status_bar": "DB: {size_mb:.2f} MB | Docs: {count} | Profil: {profile} | Sprache: {language} | Modelle: {models}",
        "model_set": "gesetzt",
        "model_not_set": "nicht gesetzt",
        "lang_en": "Englisch",
        "lang_pt": "Portugiesisch",
        "lang_de": "Deutsch",
        "imported_title": "Importiert",
        "imported_msg": "Importiert {name}",
        "import_failed_title": "Import fehlgeschlagen",
        "select_text_file": "Textdatei auswählen",
        "missing_model_title": "Fehlendes Modell",
        "missing_model_msg": "Bitte zuerst den Pfad zum Embedding-Modell festlegen.",
        "vector_index_title": "Vektorindex",
        "vector_index_built": "Vektorindex für {count} Segmente erstellt (Dim {dim}).",
        "vector_index_failed": "Vektorindex fehlgeschlagen",
        "select_embedding_dir": "Verzeichnis des Embedding-Modells auswählen",
        "select_llm_file": "LLM-Modell-Datei auswählen",
        "download_failed_title": "Download fehlgeschlagen",
        "download_failed_msg": "Bitte zuerst eine Modell-URL angeben.",
        "download_complete_title": "Download abgeschlossen",
        "download_complete_msg": "Gespeichert unter {dest}",
        "llm_error": "LLM-Fehler: {error}",
        "error_prefix": "Fehler: {error}",
        "unknown_answer": "Ich weiß es nicht. Die lokale Wissensbasis enthält diese Information nicht.",
        "splash_text": "Fonte\n\nLokale Suche + fundierte Q&A\nKein Internet erforderlich.",
        "menu_file": "Datei",
        "menu_settings": "Einstellungen",
        "menu_help": "Hilfe",
        "menu_import": "Textdatei importieren",
        "menu_exit": "Beenden",
        "menu_language": "Sprache...",
        "menu_device_profile": "Geräteprofil",
        "menu_about": "Info",
        "about_text": "Fonte - Offline-Wissensbasis und fundierte Q&A",
        "language_dialog_title": "Fonte",
        "language_dialog_prompt": "Select language / Selecione o idioma / Sprache wählen",
        "language_dialog_ok": "OK",
        "language_dialog_cancel": "Abbrechen",
    },
}


class KnowledgeApp(tk.Tk):
    def __init__(self):
        debug("before tk.Tk()")
        _start_tk_init_watchdog(10)
        super().__init__()
        _cancel_tk_init_watchdog()
        debug("after tk.Tk()")
        self.title("Fonte")
        self.geometry("900x650")
        self.minsize(820, 600)

        self._i18n_targets = []
        self._menu_targets = []
        self._tab_targets = []
        self.notebook = None
        self.ui_language = ""
        self.llm = None

        _ensure_required_dirs()
        debug(f"data dir: {DATA_DIR}")
        debug(f"db path: {DB_PATH}")
        cfg, ok = config.load_config(CONFIG_PATH, return_ok=True)
        debug(f"config loaded ok={ok}")
        self.cfg = cfg
        if not ok:
            debug("config missing or invalid; writing defaults")
            config.save_config(CONFIG_PATH, self.cfg)
        self._apply_profile_defaults()
        # Require an explicit language choice before building the full UI.
        self.ui_language = self._init_language()
        if not self.ui_language:
            print("No language selected. Exiting.")
            self.destroy()
            raise SystemExit(0)

        self._configure_style()
        debug("style configured")

        debug("initializing db")
        kb.init_db(DB_PATH)
        debug("db initialized")
        self._ensure_seed_data()

        debug("building ui")
        self._build_ui()
        debug("ui built")
        self._refresh_docs()
        self._maybe_show_splash()

    def tr(self, key: str, **kwargs) -> str:
        lang = self.ui_language if self.ui_language in I18N else "en"
        text = I18N.get(lang, I18N["en"]).get(key, I18N["en"].get(key, key))
        return text.format(**kwargs)

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(size=11)
        self.option_add("*Font", default_font)
        style.configure("TButton", padding=(10, 5))
        style.configure("TLabel", padding=(2, 2))
        style.configure("TEntry", padding=(4, 2))
        style.configure("TLabelframe", padding=(8, 6))

    def _init_language(self) -> str | None:
        saved = (self.cfg.get("ui_language") or "").strip()
        if PROMPT_LANGUAGE_EACH_START:
            chosen = self._prompt_language(startup=True, preselect=None)
            if not chosen:
                return None
            self.cfg["ui_language"] = chosen
            config.save_config(CONFIG_PATH, self.cfg)
            return chosen
        if saved in I18N:
            return saved
        chosen = self._prompt_language(startup=True, preselect=None)
        if not chosen:
            return None
        self.cfg["ui_language"] = chosen
        config.save_config(CONFIG_PATH, self.cfg)
        return chosen

    def _prompt_language(self, startup: bool = False, preselect: str | None = None):
        debug("showing language dialog")
        dlg = tk.Toplevel(self)
        dlg.title("Fonte")
        dlg.resizable(False, False)
        dlg.transient(self)
        try:
            dlg.attributes("-topmost", True)
        except tk.TclError:
            pass
        dlg.lift()
        dlg.focus_force()

        container = ttk.Frame(dlg, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        dlg.grid_columnconfigure(0, weight=1)

        if startup:
            prompt_text = "Select language / Selecione o idioma / Sprache wählen"
            ok_text = "OK"
            cancel_text = "Cancel"
        else:
            prompt_text = self.tr("language_dialog_prompt")
            ok_text = self.tr("language_dialog_ok")
            cancel_text = self.tr("language_dialog_cancel")

        ttk.Label(container, text=prompt_text).grid(row=0, column=0, sticky="w")
        if preselect in I18N:
            lang_var = tk.StringVar(value=preselect)
        else:
            lang_var = tk.StringVar(value="")
        for idx, (label, code) in enumerate(LANG_CHOICES, start=1):
            ttk.Radiobutton(container, text=label, variable=lang_var, value=code).grid(
                row=idx, column=0, sticky="w", pady=2
            )

        btn_row = ttk.Frame(container)
        btn_row.grid(row=idx + 1, column=0, pady=(8, 0), sticky="e")

        result_var = tk.StringVar(value="__pending__")

        def finish(value: str):
            if result_var.get() == "__pending__":
                result_var.set(value)

        def confirm():
            finish(lang_var.get())

        def cancel():
            finish("")

        ok_btn = ttk.Button(btn_row, text=ok_text, command=confirm, state="disabled")
        ok_btn.pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text=cancel_text, command=cancel).pack(side="left")
        dlg.protocol("WM_DELETE_WINDOW", cancel)

        def update_ok_state(*_):
            ok_btn.configure(state="normal" if lang_var.get() else "disabled")

        lang_var.trace_add("write", update_ok_state)
        update_ok_state()

        dlg.update_idletasks()
        w = dlg.winfo_reqwidth()
        h = dlg.winfo_reqheight()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        x = max((sw - w) // 2, 0)
        y = max((sh - h) // 2, 0)
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        try:
            dlg.attributes("-topmost", False)
        except tk.TclError:
            pass
        dlg.grab_set()
        dlg.wait_visibility()
        dlg.focus_force()

        self.wait_variable(result_var)
        try:
            dlg.grab_release()
        except tk.TclError:
            pass
        try:
            dlg.destroy()
        except tk.TclError:
            pass

        result = result_var.get()
        debug(f"language dialog result={result or 'cancel'}")
        if result in ("__pending__", ""):
            return None
        return result

    def _set_language(self):
        new_lang = self._prompt_language(startup=False, preselect=None)
        if not new_lang or new_lang == self.ui_language:
            return
        self.ui_language = new_lang
        self.cfg["ui_language"] = new_lang
        config.save_config(CONFIG_PATH, self.cfg)
        self._update_i18n()
        self._refresh_docs()

    def _i18n_widget(self, widget, key: str, option: str = "text"):
        try:
            widget.configure(**{option: self.tr(key)})
        except tk.TclError:
            return
        self._i18n_targets.append((widget, option, key))

    def _i18n_tab(self, notebook, tab, key: str):
        try:
            notebook.tab(tab, text=self.tr(key))
        except tk.TclError:
            return
        self._tab_targets.append((notebook, tab, key))

    def _i18n_menu(self, menu, index: int, key: str):
        try:
            menu.entryconfigure(index, label=self.tr(key))
        except tk.TclError:
            return
        self._menu_targets.append((menu, index, key))

    def _update_i18n(self):
        self.title(self.tr("app_title"))
        for widget, option, key in self._i18n_targets:
            try:
                widget.configure(**{option: self.tr(key)})
            except tk.TclError:
                continue
        for notebook, tab, key in self._tab_targets:
            try:
                notebook.tab(tab, text=self.tr(key))
            except tk.TclError:
                continue
        for menu, index, key in self._menu_targets:
            try:
                menu.entryconfigure(index, label=self.tr(key))
            except tk.TclError:
                continue

    def _ensure_seed_data(self):
        if not DB_PATH.exists():
            kb.init_db(DB_PATH)
        docs = kb.list_documents(DB_PATH)
        if docs:
            return
        for path in sorted(SAMPLE_DIR.glob("*.txt")):
            kb.ingest_text_file(DB_PATH, path, "sample")

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.search_tab = ttk.Frame(self.notebook)
        self.qa_tab = ttk.Frame(self.notebook)
        self.utils_tab = ttk.Frame(self.notebook)
        self.manage_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.search_tab, text=self.tr("tab_search"))
        self.notebook.add(self.qa_tab, text=self.tr("tab_qa"))
        self.notebook.add(self.utils_tab, text=self.tr("tab_utils"))
        self.notebook.add(self.manage_tab, text=self.tr("tab_manage"))

        self._i18n_tab(self.notebook, self.search_tab, "tab_search")
        self._i18n_tab(self.notebook, self.qa_tab, "tab_qa")
        self._i18n_tab(self.notebook, self.utils_tab, "tab_utils")
        self._i18n_tab(self.notebook, self.manage_tab, "tab_manage")

        self._build_search_tab()
        self._build_qa_tab()
        self._build_utils_tab()
        self._build_manage_tab()

        self._build_menubar()
        self._build_status_bar()

    def _build_search_tab(self):
        frame = self.search_tab
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        header = ttk.Label(frame)
        self._i18n_widget(header, "search_header")
        header.grid(row=0, column=0, sticky="w", pady=(0, 6))

        row = ttk.Frame(frame)
        row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        row.grid_columnconfigure(0, weight=1)
        self.search_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.search_var)
        entry.grid(row=0, column=0, sticky="ew")
        btn = ttk.Button(row, command=self._do_search)
        self._i18n_widget(btn, "search_button")
        btn.grid(row=0, column=1, padx=(6, 0))

        text_frame = ttk.Frame(frame)
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.grid_columnconfigure(0, weight=1)
        text_frame.grid_rowconfigure(0, weight=1)
        self.search_results = tk.Text(text_frame, height=22, wrap="word")
        self.search_results.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.search_results.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.search_results.config(yscrollcommand=scrollbar.set)

    def _do_search(self):
        query = self.search_var.get()
        results = kb.search(DB_PATH, query, limit=8)
        self.search_results.delete("1.0", tk.END)
        if not results:
            self.search_results.insert(tk.END, self.tr("no_results") + "\n")
            return
        for result in results:
            self.search_results.insert(
                tk.END,
                f"[{result.rowid}] {result.title} ({result.source})\n{result.chunk_text.strip()}\n\n",
            )

    def _build_qa_tab(self):
        frame = self.qa_tab
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=3)
        frame.grid_rowconfigure(4, weight=1)
        header = ttk.Label(frame)
        self._i18n_widget(header, "qa_header")
        header.grid(row=0, column=0, sticky="w", pady=(0, 6))
        row = ttk.Frame(frame)
        row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        row.grid_columnconfigure(0, weight=1)
        self.qa_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.qa_var)
        entry.grid(row=0, column=0, sticky="ew")
        btn = ttk.Button(row, command=self._do_answer)
        self._i18n_widget(btn, "answer_button")
        btn.grid(row=0, column=1, padx=(6, 0))

        answer_frame = ttk.Frame(frame)
        answer_frame.grid(row=2, column=0, sticky="nsew")
        answer_frame.grid_columnconfigure(0, weight=1)
        answer_frame.grid_rowconfigure(0, weight=1)
        self.qa_answer = tk.Text(answer_frame, height=16, wrap="word")
        self.qa_answer.grid(row=0, column=0, sticky="nsew")
        answer_scroll = ttk.Scrollbar(answer_frame, orient="vertical", command=self.qa_answer.yview)
        answer_scroll.grid(row=0, column=1, sticky="ns")
        self.qa_answer.config(yscrollcommand=answer_scroll.set)

        citations_label = ttk.Label(frame)
        self._i18n_widget(citations_label, "citations_label")
        citations_label.grid(row=3, column=0, sticky="w", pady=(8, 2))
        cite_frame = ttk.Frame(frame)
        cite_frame.grid(row=4, column=0, sticky="nsew")
        cite_frame.grid_columnconfigure(0, weight=1)
        cite_frame.grid_rowconfigure(0, weight=1)
        self.qa_citations = tk.Text(cite_frame, height=6, wrap="word")
        self.qa_citations.grid(row=0, column=0, sticky="nsew")
        cite_scroll = ttk.Scrollbar(cite_frame, orient="vertical", command=self.qa_citations.yview)
        cite_scroll.grid(row=0, column=1, sticky="ns")
        self.qa_citations.config(yscrollcommand=cite_scroll.set)

    def _do_answer(self):
        query = self.qa_var.get()
        embed_path = Path(self.cfg.get("embedding_model_path") or "")
        limit = int(self.cfg.get("retrieval_limit") or 4)
        results = kb.hybrid_search(
            DB_PATH,
            query,
            embed_path if embed_path.exists() else None,
            VECTOR_INDEX_PATH,
            VECTOR_META_PATH,
            limit=limit,
        )
        if not results:
            answer_text = self.tr("unknown_answer")
            citations = []
        else:
            context = [(r.rowid, r.title, r.source, r.chunk_text) for r in results]
            answer_text = self._answer_with_llm(query, context)
            citations = [f"[{r.rowid}] {r.title} ({r.source})" for r in results]
        self.qa_answer.delete("1.0", tk.END)
        self.qa_answer.insert(tk.END, answer_text)
        self.qa_citations.delete("1.0", tk.END)
        if citations:
            self.qa_citations.insert(tk.END, "\n".join(citations))
        else:
            self.qa_citations.insert(tk.END, self.tr("no_citations"))

    def _answer_with_llm(self, question, context):
        if not self._ensure_llm():
            return "\n\n".join([c[3].strip() for c in context[:2]])
        try:
            max_tokens = int(self.cfg.get("llm_max_tokens") or 192)
            return llm_api.generate_answer(self.llm, question, context, max_tokens=max_tokens)
        except Exception as exc:
            return self.tr("llm_error", error=exc) + "\n\n" + "\n\n".join([c[3].strip() for c in context[:2]])

    def _ensure_llm(self) -> bool:
        if self.llm is not None:
            return True
        model_path = Path(self.cfg.get("llm_model_path") or "")
        if not model_path.exists():
            return False
        try:
            self.llm = llm_api.load_llm(model_path)
            return True
        except Exception:
            return False

    def _build_utils_tab(self):
        frame = self.utils_tab
        frame.grid_columnconfigure(0, weight=1)
        row = 0
        calc_label = ttk.Label(frame)
        self._i18n_widget(calc_label, "calculator")
        calc_label.grid(row=row, column=0, sticky="w")
        row += 1
        calc_row = ttk.Frame(frame)
        calc_row.grid(row=row, column=0, sticky="ew", pady=(4, 10))
        calc_row.grid_columnconfigure(0, weight=1)
        self.calc_var = tk.StringVar()
        ttk.Entry(calc_row, textvariable=self.calc_var).grid(row=0, column=0, sticky="ew")
        calc_btn = ttk.Button(calc_row, command=self._do_calc)
        self._i18n_widget(calc_btn, "compute")
        calc_btn.grid(row=0, column=1, padx=(6, 0))
        self.calc_out = ttk.Label(frame, text="")
        row += 1
        self.calc_out.grid(row=row, column=0, sticky="w", pady=(0, 12))

        row += 1
        unit_label = ttk.Label(frame)
        self._i18n_widget(unit_label, "unit_conversion")
        unit_label.grid(row=row, column=0, sticky="w")
        row += 1
        unit_row = ttk.Frame(frame)
        unit_row.grid(row=row, column=0, sticky="w", pady=(4, 8))
        unit_row.grid_columnconfigure(4, weight=1)
        self.unit_value = tk.StringVar(value="1")
        ttk.Entry(unit_row, textvariable=self.unit_value, width=10).grid(row=0, column=0, sticky="w")
        self.unit_from = tk.StringVar(value="m")
        self.unit_to = tk.StringVar(value="km")
        ttk.Combobox(unit_row, textvariable=self.unit_from, values=list(utils.LENGTH_UNITS.keys()), width=8).grid(
            row=0, column=1, padx=5
        )
        ttk.Combobox(unit_row, textvariable=self.unit_to, values=list(utils.LENGTH_UNITS.keys()), width=8).grid(
            row=0, column=2, padx=5
        )
        unit_btn = ttk.Button(unit_row, command=self._do_length)
        self._i18n_widget(unit_btn, "convert_length")
        unit_btn.grid(row=0, column=3, padx=5, sticky="w")
        self.unit_out = ttk.Label(frame, text="")
        row += 1
        self.unit_out.grid(row=row, column=0, sticky="w", pady=(0, 12))

        row += 1
        temp_label = ttk.Label(frame)
        self._i18n_widget(temp_label, "temp_conversion")
        temp_label.grid(row=row, column=0, sticky="w")
        row += 1
        temp_row = ttk.Frame(frame)
        temp_row.grid(row=row, column=0, sticky="w", pady=(4, 8))
        temp_row.grid_columnconfigure(4, weight=1)
        self.temp_value = tk.StringVar(value="0")
        ttk.Entry(temp_row, textvariable=self.temp_value, width=10).grid(row=0, column=0, sticky="w")
        self.temp_from = tk.StringVar(value="C")
        self.temp_to = tk.StringVar(value="F")
        ttk.Combobox(temp_row, textvariable=self.temp_from, values=["C", "F", "K"], width=5).grid(
            row=0, column=1, padx=5
        )
        ttk.Combobox(temp_row, textvariable=self.temp_to, values=["C", "F", "K"], width=5).grid(
            row=0, column=2, padx=5
        )
        temp_btn = ttk.Button(temp_row, command=self._do_temp)
        self._i18n_widget(temp_btn, "convert_temp")
        temp_btn.grid(row=0, column=3, padx=5, sticky="w")
        self.temp_out = ttk.Label(frame, text="")
        row += 1
        self.temp_out.grid(row=row, column=0, sticky="w", pady=(0, 12))

        row += 1
        date_label = ttk.Label(frame)
        self._i18n_widget(date_label, "date_utils")
        date_label.grid(row=row, column=0, sticky="w")
        row += 1
        date_row = ttk.Frame(frame)
        date_row.grid(row=row, column=0, sticky="w", pady=(4, 0))
        date_row.grid_columnconfigure(3, weight=1)
        self.date_var = tk.StringVar(value=utils.today_iso())
        self.days_var = tk.StringVar(value="7")
        ttk.Entry(date_row, textvariable=self.date_var, width=12).grid(row=0, column=0, sticky="w")
        ttk.Entry(date_row, textvariable=self.days_var, width=6).grid(row=0, column=1, sticky="w", padx=5)
        date_btn = ttk.Button(date_row, command=self._do_date_add)
        self._i18n_widget(date_btn, "add_days")
        date_btn.grid(row=0, column=2, padx=5, sticky="w")
        self.date_out = ttk.Label(frame, text="")
        row += 1
        self.date_out.grid(row=row, column=0, sticky="w", pady=(4, 0))

    def _do_calc(self):
        self.calc_out.config(text=utils.safe_calc(self.calc_var.get()))

    def _do_length(self):
        try:
            value = float(self.unit_value.get())
            out = utils.convert_length(value, self.unit_from.get(), self.unit_to.get())
            self.unit_out.config(text=str(out))
        except Exception as exc:
            self.unit_out.config(text=self.tr("error_prefix", error=exc))

    def _do_temp(self):
        try:
            value = float(self.temp_value.get())
            out = utils.convert_temp(value, self.temp_from.get(), self.temp_to.get())
            self.temp_out.config(text=str(out))
        except Exception as exc:
            self.temp_out.config(text=self.tr("error_prefix", error=exc))

    def _do_date_add(self):
        try:
            days = int(self.days_var.get())
            out = utils.date_add_days(self.date_var.get(), days)
            self.date_out.config(text=out)
        except Exception as exc:
            self.date_out.config(text=self.tr("error_prefix", error=exc))

    def _build_manage_tab(self):
        frame = self.manage_tab
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        documents_frame = ttk.Labelframe(frame)
        self._i18n_widget(documents_frame, "documents_header", option="text")
        documents_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        documents_frame.grid_columnconfigure(0, weight=1)
        documents_frame.grid_rowconfigure(1, weight=1)

        docs_sub = ttk.Label(documents_frame)
        self._i18n_widget(docs_sub, "documents_subheader")
        docs_sub.grid(row=0, column=0, sticky="w", pady=(0, 6))

        list_row = ttk.Frame(documents_frame)
        list_row.grid(row=1, column=0, sticky="nsew")
        list_row.grid_columnconfigure(0, weight=1)
        list_row.grid_rowconfigure(0, weight=1)
        self.docs_list = tk.Listbox(list_row)
        self.docs_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_row, orient="vertical", command=self.docs_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.docs_list.config(yscrollcommand=scrollbar.set)

        btn_row = ttk.Frame(documents_frame)
        btn_row.grid(row=2, column=0, sticky="w", pady=(6, 0))
        import_btn = ttk.Button(btn_row, command=self._import_file)
        self._i18n_widget(import_btn, "import_text")
        import_btn.pack(side="left")
        delete_btn = ttk.Button(btn_row, command=self._delete_selected)
        self._i18n_widget(delete_btn, "delete_selected")
        delete_btn.pack(side="left", padx=6)
        rebuild_btn = ttk.Button(btn_row, command=self._rebuild_index)
        self._i18n_widget(rebuild_btn, "rebuild_index")
        rebuild_btn.pack(side="left", padx=6)

        models_frame = ttk.Labelframe(frame)
        self._i18n_widget(models_frame, "models_header", option="text")
        models_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        models_frame.grid_columnconfigure(0, weight=1)

        model_btn_row = ttk.Frame(models_frame)
        model_btn_row.grid(row=0, column=0, sticky="w")
        embed_btn = ttk.Button(model_btn_row, command=self._set_embedding_model)
        self._i18n_widget(embed_btn, "set_embedding_model")
        embed_btn.pack(side="left")
        llm_btn = ttk.Button(model_btn_row, command=self._set_llm_model)
        self._i18n_widget(llm_btn, "set_llm_model")
        llm_btn.pack(side="left", padx=6)
        rebuild_vec_btn = ttk.Button(model_btn_row, command=self._rebuild_vector_index)
        self._i18n_widget(rebuild_vec_btn, "rebuild_vector")
        rebuild_vec_btn.pack(side="left", padx=6)

        download_row = ttk.Frame(models_frame)
        download_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        download_row.grid_columnconfigure(1, weight=1)
        download_label = ttk.Label(download_row)
        self._i18n_widget(download_label, "model_download_url")
        download_label.grid(row=0, column=0, sticky="w")
        self.download_var = tk.StringVar(value=self.cfg.get("model_download_url", ""))
        ttk.Entry(download_row, textvariable=self.download_var).grid(row=0, column=1, sticky="ew", padx=6)
        download_btn = ttk.Button(download_row, command=self._download_model)
        self._i18n_widget(download_btn, "download_model")
        download_btn.grid(row=0, column=2, sticky="e")

        profile_frame = ttk.Labelframe(frame)
        self._i18n_widget(profile_frame, "device_profile_header", option="text")
        profile_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        profile_frame.grid_columnconfigure(3, weight=1)

        profile_label = ttk.Label(profile_frame)
        self._i18n_widget(profile_label, "device_profile")
        profile_label.grid(row=0, column=0, sticky="w")
        self.profile_var = tk.StringVar(value=self.cfg.get("device_profile", "low"))
        ttk.Combobox(profile_frame, textvariable=self.profile_var, values=list(PROFILES.keys()), width=10).grid(
            row=0, column=1, sticky="w", padx=6
        )
        apply_btn = ttk.Button(profile_frame, command=self._apply_profile)
        self._i18n_widget(apply_btn, "apply_profile")
        apply_btn.grid(row=0, column=2, sticky="w")

        self.demo_var = tk.BooleanVar(value=self.cfg.get("demo_mode") == "true")
        demo_check = ttk.Checkbutton(profile_frame, variable=self.demo_var, command=self._toggle_demo)
        self._i18n_widget(demo_check, "demo_mode")
        demo_check.grid(row=1, column=0, sticky="w", pady=(6, 0))
        demo_btn = ttk.Button(profile_frame, command=self._run_demo)
        self._i18n_widget(demo_btn, "demo_tour")
        demo_btn.grid(row=1, column=1, sticky="w", pady=(6, 0))

        status_frame = ttk.Labelframe(frame)
        self._i18n_widget(status_frame, "status_header", option="text")
        status_frame.grid(row=3, column=0, sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)

        self.storage_label = ttk.Label(status_frame, text="")
        self.storage_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.model_status = ttk.Label(status_frame, text="")
        self.model_status.grid(row=1, column=0, sticky="w")

    def _refresh_docs(self):
        self.docs_list.delete(0, tk.END)
        docs = kb.list_documents(DB_PATH)
        for doc_id, title, source, path in docs:
            self.docs_list.insert(tk.END, f"{doc_id} | {title} | {source} | {path or ''}")
        size_mb = DB_PATH.stat().st_size / (1024 * 1024) if DB_PATH.exists() else 0
        self.storage_label.config(text=self.tr("storage_status", size_mb=size_mb, count=len(docs)))
        embed_path = self.cfg.get("embedding_model_path") or self.tr("model_not_set")
        llm_path = self.cfg.get("llm_model_path") or self.tr("model_not_set")
        profile = self.cfg.get("device_profile", "low")
        demo = self.cfg.get("demo_mode", "false")
        self.model_status.config(
            text=self.tr(
                "model_status",
                embedding=embed_path,
                llm=llm_path,
                profile=profile,
                demo=demo,
            )
        )
        self._update_status_bar(size_mb, len(docs), profile, embed_path, llm_path)

    def _import_file(self):
        path = filedialog.askopenfilename(
            title=self.tr("select_text_file"), filetypes=[("Text", "*.txt")]
        )
        if not path:
            return
        path = Path(path)
        try:
            USER_DIR.mkdir(parents=True, exist_ok=True)
            dest = USER_DIR / path.name
            shutil.copy2(path, dest)
            kb.ingest_text_file(DB_PATH, dest, "user")
            messagebox.showinfo(self.tr("imported_title"), self.tr("imported_msg", name=dest.name))
        except Exception as exc:
            messagebox.showerror(self.tr("import_failed_title"), str(exc))
        self._refresh_docs()

    def _delete_selected(self):
        sel = self.docs_list.curselection()
        if not sel:
            return
        item = self.docs_list.get(sel[0])
        doc_id = int(item.split("|")[0].strip())
        kb.delete_document(DB_PATH, doc_id)
        self._refresh_docs()

    def _rebuild_index(self):
        kb.rebuild_from_folder(DB_PATH, SAMPLE_DIR, "sample")
        for path in sorted(USER_DIR.glob("*.txt")):
            kb.ingest_text_file(DB_PATH, path, "user")
        self._refresh_docs()

    def _rebuild_vector_index(self):
        embed_path = Path(self.cfg.get("embedding_model_path") or "")
        if not embed_path.exists():
            messagebox.showerror(self.tr("missing_model_title"), self.tr("missing_model_msg"))
            return
        try:
            count, dim = kb.build_vector_index(DB_PATH, embed_path, VECTOR_INDEX_PATH, VECTOR_META_PATH)
            messagebox.showinfo(
                self.tr("vector_index_title"),
                self.tr("vector_index_built", count=count, dim=dim),
            )
        except Exception as exc:
            messagebox.showerror(self.tr("vector_index_failed"), str(exc))

    def _set_embedding_model(self):
        path = filedialog.askdirectory(title=self.tr("select_embedding_dir"))
        if not path:
            return
        self.cfg["embedding_model_path"] = path
        config.save_config(CONFIG_PATH, self.cfg)
        self._refresh_docs()

    def _set_llm_model(self):
        path = filedialog.askopenfilename(
            title=self.tr("select_llm_file"), filetypes=[("GGUF", "*.gguf")]
        )
        if not path:
            return
        self.cfg["llm_model_path"] = path
        config.save_config(CONFIG_PATH, self.cfg)
        self.llm = None
        self._refresh_docs()

    def _apply_profile_defaults(self):
        profile = self.cfg.get("device_profile", "low")
        profile_cfg = PROFILES.get(profile, PROFILES["low"])
        self.cfg.setdefault("retrieval_limit", str(profile_cfg["retrieval_limit"]))
        self.cfg.setdefault("llm_max_tokens", str(profile_cfg["llm_max_tokens"]))
        config.save_config(CONFIG_PATH, self.cfg)

    def _apply_profile(self):
        profile = self.profile_var.get()
        profile_cfg = PROFILES.get(profile, PROFILES["low"])
        self.cfg["device_profile"] = profile
        self.cfg["retrieval_limit"] = str(profile_cfg["retrieval_limit"])
        self.cfg["llm_max_tokens"] = str(profile_cfg["llm_max_tokens"])
        config.save_config(CONFIG_PATH, self.cfg)
        self._refresh_docs()

    def _toggle_demo(self):
        self.cfg["demo_mode"] = "true" if self.demo_var.get() else "false"
        config.save_config(CONFIG_PATH, self.cfg)
        self._refresh_docs()

    def _download_model(self):
        url = self.download_var.get().strip()
        if not url:
            messagebox.showerror(self.tr("download_failed_title"), self.tr("download_failed_msg"))
            return
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        filename = url.split("/")[-1] or "model.bin"
        dest = MODELS_DIR / filename
        try:
            import urllib.request

            urllib.request.urlretrieve(url, dest)
            messagebox.showinfo(
                self.tr("download_complete_title"),
                self.tr("download_complete_msg", dest=dest),
            )
        except Exception as exc:
            messagebox.showerror(self.tr("download_failed_title"), str(exc))

    def _run_demo(self):
        self.search_var.set("Solar System")
        self._do_search()
        self.qa_var.set("Which planets are in the Solar System?")
        self._do_answer()

    def _maybe_show_splash(self):
        if self.cfg.get("demo_mode") != "true":
            return
        splash = tk.Toplevel(self)
        splash.title(self.tr("app_title"))
        splash.geometry("420x180")
        splash_label = ttk.Label(
            splash,
            text=self.tr("splash_text"),
            justify="center",
        )
        splash_label.pack(expand=True)
        splash.after(1500, splash.destroy)

    def _build_status_bar(self):
        self.status_var = tk.StringVar()
        status = ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken")
        status.grid(row=1, column=0, sticky="ew")

    def _update_status_bar(self, size_mb: float, doc_count: int, profile: str, embed_path: str, llm_path: str):
        language_name = self._language_display_name(self.ui_language)
        embed_set = self.tr("model_set") if embed_path != self.tr("model_not_set") else self.tr("model_not_set")
        llm_set = self.tr("model_set") if llm_path != self.tr("model_not_set") else self.tr("model_not_set")
        models = f"emb {embed_set}, llm {llm_set}"
        self.status_var.set(
            self.tr(
                "status_bar",
                size_mb=size_mb,
                count=doc_count,
                profile=profile,
                language=language_name,
                models=models,
            )
        )

    def _language_display_name(self, code: str) -> str:
        key = f"lang_{code}"
        return self.tr(key) if key in I18N.get(self.ui_language, {}) else code

    def _build_menubar(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label=self.tr("menu_import"), command=self._import_file)
        file_import_idx = file_menu.index("end")
        file_menu.add_separator()
        file_menu.add_command(label=self.tr("menu_exit"), command=self.destroy)
        file_exit_idx = file_menu.index("end")
        menubar.add_cascade(label=self.tr("menu_file"), menu=file_menu)
        menu_file_idx = menubar.index("end")

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label=self.tr("menu_language"), command=self._set_language)
        menu_lang_idx = settings_menu.index("end")
        settings_menu.add_command(label=self.tr("menu_device_profile"), command=self._open_manage_tab)
        menu_profile_idx = settings_menu.index("end")
        menubar.add_cascade(label=self.tr("menu_settings"), menu=settings_menu)
        menu_settings_idx = menubar.index("end")

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=self.tr("menu_about"), command=self._show_about)
        menu_about_idx = help_menu.index("end")
        menubar.add_cascade(label=self.tr("menu_help"), menu=help_menu)
        menu_help_idx = menubar.index("end")

        self.config(menu=menubar)

        self._i18n_menu(menubar, menu_file_idx, "menu_file")
        self._i18n_menu(menubar, menu_settings_idx, "menu_settings")
        self._i18n_menu(menubar, menu_help_idx, "menu_help")
        self._i18n_menu(file_menu, file_import_idx, "menu_import")
        self._i18n_menu(file_menu, file_exit_idx, "menu_exit")
        self._i18n_menu(settings_menu, menu_lang_idx, "menu_language")
        self._i18n_menu(settings_menu, menu_profile_idx, "menu_device_profile")
        self._i18n_menu(help_menu, menu_about_idx, "menu_about")

    def _open_manage_tab(self):
        if self.notebook is not None:
            self.notebook.select(self.manage_tab)

    def _show_about(self):
        messagebox.showinfo(self.tr("menu_about"), self.tr("about_text"))


if __name__ == "__main__":
    if os.getenv("FONTE_DEBUG") == "1":
        import faulthandler

        faulthandler.enable()
        faulthandler.dump_traceback_later(10, repeat=True)
        debug("faulthandler watchdog enabled (10s)")
    ok, reason = _gui_preflight()
    if not ok:
        _print_no_display_help(reason)
        sys.exit(2)
    try:
        app = KnowledgeApp()
    except tk.TclError as exc:
        if _is_display_error(exc):
            _print_no_display_help(str(exc))
            sys.exit(2)
        raise
    if os.getenv("FONTE_DEBUG") == "1":
        import faulthandler

        faulthandler.cancel_dump_traceback_later()
    app.mainloop()
