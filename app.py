import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import tkinter.font as tkfont
import atexit
import math
import os
import sys
import signal
import socket
import stat
from pathlib import Path
import shutil
import threading
import time
import re
import json

import kb
import utils
import config
import llm as llm_api
import llm_lmstudio
import runtime
import model_manager
import task_router
from analytics import AnalyticsTracker
from app_state import AppState, load_state, save_state
from async_utils import RequestCoordinator
from crash_reporter import install_crash_hook
from design_system import (
    AppScaffold,
    CardFrame,
    EmptyState,
    ErrorState,
    FormField,
    LoadingState,
    PlaceholderEntry,
    PrimaryButton,
    ScrollableFrame,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SecondaryButton,
    SkeletonList,
    ToastManager,
    preferred_font_family,
    set_accessibility_label,
)
from documents_repository import DocumentItem, DocumentsRepository, apply_optimistic_favorite
from error_mapper import ValidationError, map_exception, to_ui_error
from feature_flags import can_access_feature, from_config
from form_validation import should_generate_search_answer, validate_question
from integrations import mediawiki_api
from integrations.offline_translate import translate
from ui_state import Empty, Error, Loading, Success, UiStateMachine

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "kb.sqlite"
SAMPLE_DIR = DATA_DIR / "sample_docs"
USER_DIR = DATA_DIR / "user_docs"
CONFIG_PATH = DATA_DIR / "config.json"
VECTOR_INDEX_PATH = DATA_DIR / "vector_index.bin"
VECTOR_META_PATH = DATA_DIR / "vector_meta.npz"
MODELS_DIR = model_manager.resolve_model_dir()
APP_STATE_PATH = DATA_DIR / "app_state.json"
CRASH_LOG_PATH = DATA_DIR / "crash.log"
DOCS_PAGE_SIZE = 200
# Language selection must be explicit to avoid unintended defaults (e.g., auto-selected locales).
PROMPT_LANGUAGE_EACH_START = False
# Production toggle: set to False for distro builds to respect saved ui_language.


def debug(msg: str) -> None:
    # Enable lightweight startup diagnostics by setting FONTE_DEBUG=1.
    if os.getenv("FONTE_DEBUG") == "1":
        print(f"[fonte] {msg}")


def _report_ui_exception(exc: Exception) -> None:
    try:
        sys.excepthook(type(exc), exc, exc.__traceback__)
    except Exception:
        debug(f"ui exception: {exc}")


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

LLM_BACKENDS = ["lmstudio", "llama_cpp"]

LANG_CHOICES = [
    ("English", "en"),
    ("Português", "pt"),
    ("Deutsch", "de"),
]

I18N = {
    "en": {
        "app_title": "Fonte",
        "tab_search": "Search",
        "tab_qa": "Ask",
        "tab_utils": "Tools",
        "tab_manage": "Settings",
        "search_header": "Find information in your documents",
        "search_placeholder": "Ask anything in your local docs...",
        "search_hint": "Use clear keywords. Press Enter to search.",
        "onboarding_title": "Welcome to Fonte",
        "onboarding_value": "Offline-first search and grounded answers from your local documents.",
        "onboarding_quick_demo": "Run Quick Demo",
        "onboarding_import_first": "Import First Document",
        "onboarding_skip": "Skip for now",
        "onboarding_resume_draft": "Recovered your previous draft question.",
        "onboarding_resume_action": "Resume Draft",
        "search_button": "Search",
        "search_answer_title": "Quick answer",
        "search_answer_off": "Answer mode is off.",
        "search_answer_not_installed": "AI not installed.",
        "search_answer_downloading": "Downloading AI model...",
        "search_answer_ready": "Ready",
        "search_answer_generating": "Generating answer...",
        "search_answer_error": "AI unavailable",
        "ai_local_provider": "AI: Local (Embedded)",
        "download_ai_model": "Download AI model",
        "manage_ai_model": "Download / Manage model",
        "repair_ai_model": "Repair / Re-download",
        "cancel_action": "Cancel",
        "ai_download_wizard_title": "Install AI model",
        "ai_download_wizard_body": "Install a local model to enable offline AI answers.",
        "ai_download_progress": "{done} / {total}  ({eta})",
        "ai_download_complete": "AI model installed and ready.",
        "ai_download_cancelled": "Download cancelled.",
        "ai_install_failed": "Could not install the AI model. Please try again.",
        "llm_context_window": "Context window",
        "low_resource_mode": "Low resource mode",
        "no_results": "No matching results.",
        "search_empty_title": "No matches found",
        "search_empty_body": "Try a shorter question or different keywords.",
        "question_label": "Question",
        "question_placeholder": "Type your question here...",
        "qa_header": "Ask a question using your local documents",
        "answer_button": "Answer",
        "qa_empty_title": "Ask your first question",
        "qa_empty_body": "Type a question above and select Answer.",
        "qa_loading": "Generating answer...",
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
        "documents_empty_title": "No documents yet",
        "documents_empty_body": "Import a text file to get started.",
        "documents_unavailable_title": "Documents unavailable",
        "documents_unavailable_body": "Use Import Text File to start.",
        "documents_select_first": "Select a document first.",
        "models_header": "Models",
        "device_profile_header": "Device Profile",
        "status_header": "Status",
        "import_text": "Import Text File",
        "import_wikipedia": "Import from Wikipedia",
        "delete_selected": "Delete Selected",
        "rebuild_index": "Rebuild Index",
        "rebuild_vector": "Rebuild Vector Index",
        "set_embedding_model": "Set Embedding Model",
        "set_llm_model": "Set LLM Model",
        "llm_backend": "LLM Backend",
        "ollama_url": "Ollama URL",
        "ollama_model": "Ollama Model",
        "ollama_timeout": "Timeout (s)",
        "lmstudio_base_url": "LM Studio URL",
        "model_small_id": "Small model ID (0.5B)",
        "model_large_id": "Large model ID (1.5B)",
        "lmstudio_temperature": "Temperature",
        "lmstudio_max_tokens": "Max tokens",
        "lmstudio_timeout": "Timeout (s)",
        "save_llm_settings": "Save LLM Settings",
        "demo_tour": "Demo Tour",
        "device_profile": "Device Profile",
        "apply_profile": "Apply Profile",
        "demo_mode": "Demo Mode",
        "model_download_url": "Model download URL",
        "download_model": "Download Model",
        "online_sources_header": "Online Sources",
        "online_enable": "Enable online sources",
        "online_cache_days": "Cache (days)",
        "online_timeout_sec": "Timeout (s)",
        "online_user_agent": "User-Agent",
        "online_wikipedia_language": "Wikipedia language",
        "save_online_settings": "Save Online Settings",
        "pager_previous": "Previous",
        "pager_next": "Next",
        "pager_label": "Page {current} of {total}",
        "docs_status_loading": "Status: Loading...",
        "docs_status_fresh": "Status: Up to date",
        "docs_status_cached": "Status: Updated {age}s ago",
        "docs_status_stale": "Status: Could not refresh",
        "action_wait_current": "Please wait for the current action to finish.",
        "ai_answers_label": "AI answers",
        "ai_on": "On",
        "ai_off": "Off",
        "ai_provider": "Provider",
        "advanced_toggle": "Advanced",
        "mode_search_only_cta": "Open Settings > Models to enable AI answers.",
        "ai_answers_on_cta": "AI answers are enabled.",
        "storage_status": "DB size: {size_mb:.2f} MB | Documents: {count}",
        "model_status": "Embedding: {embedding} | LLM: {llm} | Profile: {profile} | Demo: {demo}",
        "status_bar": "Ready | Documents: {count} | Language: {language} | Profile: {profile}",
        "status_bar_search_only": "Ready | Documents: {count} | Language: {language} | AI answers are off",
        "mode_search_only_detail": "Mode: Search-only (AI answers off). Open Settings > Models to enable AI answers.",
        "status_busy": "Working: {activity}",
        "status_done": "Done: {activity}",
        "status_error": "Could not complete: {activity}",
        "setup_ai_button": "Set up AI",
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
        "online_disabled_title": "Online sources disabled",
        "online_disabled_msg": "Enable online sources in Manage > Online Sources first.",
        "wikipedia_query_title": "Wikipedia Import",
        "wikipedia_query_prompt": "Search query",
        "wikipedia_limit_prompt": "How many pages to import?",
        "wikipedia_imported_title": "Wikipedia import",
        "wikipedia_imported_msg": "Imported {count} page(s): {titles}",
        "wikipedia_failed_title": "Wikipedia import failed",
        "search_failed_friendly": "That query could not be searched directly.",
        "search_settings_cta": "Try simpler keywords without punctuation.",
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
        "tab_qa": "Perguntar",
        "tab_utils": "Ferramentas",
        "tab_manage": "Configurações",
        "search_header": "Encontre informações nos seus documentos",
        "search_placeholder": "Pergunte algo nos seus documentos locais...",
        "search_hint": "Use palavras-chave claras. Pressione Enter para pesquisar.",
        "onboarding_title": "Bem-vindo ao Fonte",
        "onboarding_value": "Pesquisa offline e respostas fundamentadas com seus documentos locais.",
        "onboarding_quick_demo": "Executar demo rápida",
        "onboarding_import_first": "Importar primeiro documento",
        "onboarding_skip": "Pular por enquanto",
        "onboarding_resume_draft": "Seu rascunho anterior foi recuperado.",
        "onboarding_resume_action": "Retomar rascunho",
        "search_button": "Pesquisar",
        "search_answer_title": "Resposta rápida",
        "no_results": "Nenhum resultado encontrado.",
        "search_empty_title": "Nenhuma correspondência",
        "search_empty_body": "Tente uma pergunta mais curta ou outras palavras-chave.",
        "question_label": "Pergunta",
        "question_placeholder": "Digite sua pergunta aqui...",
        "qa_header": "Faça uma pergunta usando seus documentos locais",
        "answer_button": "Responder",
        "qa_empty_title": "Faça sua primeira pergunta",
        "qa_empty_body": "Digite uma pergunta acima e clique em Responder.",
        "qa_loading": "Gerando resposta...",
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
        "documents_empty_title": "Ainda não há documentos",
        "documents_empty_body": "Importe um arquivo de texto para começar.",
        "documents_unavailable_title": "Documentos indisponíveis",
        "documents_unavailable_body": "Use Importar arquivo de texto para começar.",
        "documents_select_first": "Selecione um documento primeiro.",
        "models_header": "Modelos",
        "device_profile_header": "Perfil do dispositivo",
        "status_header": "Status",
        "import_text": "Importar arquivo de texto",
        "import_wikipedia": "Importar da Wikipedia",
        "delete_selected": "Excluir selecionado",
        "rebuild_index": "Reconstruir índice",
        "rebuild_vector": "Reconstruir índice vetorial",
        "set_embedding_model": "Definir modelo de embedding",
        "set_llm_model": "Definir modelo LLM",
        "llm_backend": "Backend LLM",
        "ollama_url": "URL do Ollama",
        "ollama_model": "Modelo Ollama",
        "ollama_timeout": "Timeout (s)",
        "save_llm_settings": "Salvar config LLM",
        "demo_tour": "Tour de demonstração",
        "device_profile": "Perfil do dispositivo",
        "apply_profile": "Aplicar perfil",
        "demo_mode": "Modo de demonstração",
        "model_download_url": "URL de download do modelo",
        "download_model": "Baixar modelo",
        "online_sources_header": "Fontes Online",
        "online_enable": "Ativar fontes online",
        "online_cache_days": "Cache (dias)",
        "online_timeout_sec": "Timeout (s)",
        "online_user_agent": "User-Agent",
        "online_wikipedia_language": "Idioma da Wikipedia",
        "save_online_settings": "Salvar config online",
        "pager_previous": "Anterior",
        "pager_next": "Próxima",
        "pager_label": "Página {current} de {total}",
        "docs_status_loading": "Status: Carregando...",
        "docs_status_fresh": "Status: Atualizado",
        "docs_status_cached": "Status: Atualizado há {age}s",
        "docs_status_stale": "Status: Não foi possível atualizar",
        "action_wait_current": "Aguarde o término da ação atual.",
        "ai_answers_label": "Respostas de IA",
        "ai_on": "Ligado",
        "ai_off": "Desligado",
        "ai_provider": "Provedor",
        "advanced_toggle": "Avançado",
        "mode_search_only_cta": "Abra Configurações > Modelos para ativar respostas de IA.",
        "ai_answers_on_cta": "Respostas de IA ativadas.",
        "storage_status": "Tamanho do BD: {size_mb:.2f} MB | Documentos: {count}",
        "model_status": "Embedding: {embedding} | LLM: {llm} | Perfil: {profile} | Demo: {demo}",
        "status_bar": "Pronto | Documentos: {count} | Idioma: {language} | Perfil: {profile}",
        "status_bar_search_only": "Pronto | Documentos: {count} | Idioma: {language} | Respostas de IA desligadas",
        "mode_search_only_detail": "Modo: Somente pesquisa (respostas de IA desligadas). Abra Configurações > Modelos para ativar respostas de IA.",
        "status_busy": "Processando: {activity}",
        "status_done": "Concluído: {activity}",
        "status_error": "Não foi possível concluir: {activity}",
        "setup_ai_button": "Configurar IA",
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
        "online_disabled_title": "Fontes online desativadas",
        "online_disabled_msg": "Ative fontes online em Gerenciar > Fontes Online primeiro.",
        "wikipedia_query_title": "Importação Wikipedia",
        "wikipedia_query_prompt": "Consulta de busca",
        "wikipedia_limit_prompt": "Quantas páginas importar?",
        "wikipedia_imported_title": "Importação Wikipedia",
        "wikipedia_imported_msg": "Importadas {count} página(s): {titles}",
        "wikipedia_failed_title": "Falha na importação Wikipedia",
        "search_failed_friendly": "Não foi possível pesquisar essa consulta diretamente.",
        "search_settings_cta": "Tente palavras-chave mais simples sem pontuação.",
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
        "tab_qa": "Fragen",
        "tab_utils": "Werkzeuge",
        "tab_manage": "Einstellungen",
        "search_header": "Finde Informationen in deinen Dokumenten",
        "search_placeholder": "Stelle eine Frage zu deinen lokalen Dokumenten...",
        "search_hint": "Nutze klare Stichwörter. Drücke Enter zum Suchen.",
        "onboarding_title": "Willkommen bei Fonte",
        "onboarding_value": "Offline-Suche und fundierte Antworten aus lokalen Dokumenten.",
        "onboarding_quick_demo": "Schnell-Demo starten",
        "onboarding_import_first": "Erstes Dokument importieren",
        "onboarding_skip": "Jetzt überspringen",
        "onboarding_resume_draft": "Dein vorheriger Fragenentwurf wurde wiederhergestellt.",
        "onboarding_resume_action": "Entwurf fortsetzen",
        "search_button": "Suchen",
        "search_answer_title": "Kurzantwort",
        "no_results": "Keine passenden Ergebnisse.",
        "search_empty_title": "Keine Treffer",
        "search_empty_body": "Versuche eine kürzere Frage oder andere Stichwörter.",
        "question_label": "Frage",
        "question_placeholder": "Schreibe deine Frage hier...",
        "qa_header": "Stelle eine Frage mit deinen lokalen Dokumenten",
        "answer_button": "Antworten",
        "qa_empty_title": "Stelle deine erste Frage",
        "qa_empty_body": "Gib oben eine Frage ein und klicke auf Antworten.",
        "qa_loading": "Antwort wird erstellt...",
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
        "documents_empty_title": "Noch keine Dokumente",
        "documents_empty_body": "Importiere eine Textdatei, um zu starten.",
        "documents_unavailable_title": "Dokumente nicht verfügbar",
        "documents_unavailable_body": "Nutze Textdatei importieren, um zu starten.",
        "documents_select_first": "Bitte zuerst ein Dokument auswählen.",
        "models_header": "Modelle",
        "device_profile_header": "Geräteprofil",
        "status_header": "Status",
        "import_text": "Textdatei importieren",
        "import_wikipedia": "Von Wikipedia importieren",
        "delete_selected": "Auswahl löschen",
        "rebuild_index": "Index neu erstellen",
        "rebuild_vector": "Vektorindex neu erstellen",
        "set_embedding_model": "Embedding-Modell festlegen",
        "set_llm_model": "LLM-Modell festlegen",
        "llm_backend": "LLM-Backend",
        "ollama_url": "Ollama-URL",
        "ollama_model": "Ollama-Modell",
        "ollama_timeout": "Timeout (s)",
        "save_llm_settings": "LLM-Einstellungen speichern",
        "demo_tour": "Demo-Tour",
        "device_profile": "Geräteprofil",
        "apply_profile": "Profil anwenden",
        "demo_mode": "Demo-Modus",
        "model_download_url": "Modell-Download-URL",
        "download_model": "Modell herunterladen",
        "online_sources_header": "Online-Quellen",
        "online_enable": "Online-Quellen aktivieren",
        "online_cache_days": "Cache (Tage)",
        "online_timeout_sec": "Timeout (s)",
        "online_user_agent": "User-Agent",
        "online_wikipedia_language": "Wikipedia-Sprache",
        "save_online_settings": "Online-Einstellungen speichern",
        "pager_previous": "Zurück",
        "pager_next": "Weiter",
        "pager_label": "Seite {current} von {total}",
        "docs_status_loading": "Status: Wird geladen...",
        "docs_status_fresh": "Status: Aktuell",
        "docs_status_cached": "Status: Vor {age}s aktualisiert",
        "docs_status_stale": "Status: Aktualisierung fehlgeschlagen",
        "action_wait_current": "Bitte warte, bis die aktuelle Aktion beendet ist.",
        "ai_answers_label": "KI-Antworten",
        "ai_on": "An",
        "ai_off": "Aus",
        "ai_provider": "Anbieter",
        "advanced_toggle": "Erweitert",
        "mode_search_only_cta": "Öffne Einstellungen > Modelle, um KI-Antworten zu aktivieren.",
        "ai_answers_on_cta": "KI-Antworten sind aktiviert.",
        "storage_status": "DB-Größe: {size_mb:.2f} MB | Dokumente: {count}",
        "model_status": "Embedding: {embedding} | LLM: {llm} | Profil: {profile} | Demo: {demo}",
        "status_bar": "Bereit | Dokumente: {count} | Sprache: {language} | Profil: {profile}",
        "status_bar_search_only": "Bereit | Dokumente: {count} | Sprache: {language} | KI-Antworten sind aus",
        "mode_search_only_detail": "Modus: Nur Suche (KI-Antworten aus). Öffne Einstellungen > Modelle, um KI-Antworten zu aktivieren.",
        "status_busy": "Verarbeitung: {activity}",
        "status_done": "Fertig: {activity}",
        "status_error": "Konnte nicht abgeschlossen werden: {activity}",
        "setup_ai_button": "KI einrichten",
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
        "online_disabled_title": "Online-Quellen deaktiviert",
        "online_disabled_msg": "Aktiviere zuerst Online-Quellen unter Verwalten > Online-Quellen.",
        "wikipedia_query_title": "Wikipedia-Import",
        "wikipedia_query_prompt": "Suchanfrage",
        "wikipedia_limit_prompt": "Wie viele Seiten importieren?",
        "wikipedia_imported_title": "Wikipedia-Import",
        "wikipedia_imported_msg": "{count} Seite(n) importiert: {titles}",
        "wikipedia_failed_title": "Wikipedia-Import fehlgeschlagen",
        "search_failed_friendly": "Diese Anfrage konnte nicht direkt gesucht werden.",
        "search_settings_cta": "Versuche einfachere Stichwörter ohne Satzzeichen.",
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
        self.geometry("980x700")
        self.minsize(900, 640)

        self._i18n_targets = []
        self._menu_targets = []
        self._tab_targets = []
        self.notebook = None
        self.ui_language = ""
        self.llm = None
        self.reduced_motion = os.getenv("FONTE_REDUCED_MOTION") == "1"
        self.analytics = AnalyticsTracker(DATA_DIR / "analytics.log", debug_logger=debug)
        self.docs_repo = DocumentsRepository(DB_PATH, CONFIG_PATH)
        self.toast = ToastManager(self, reduced_motion=self.reduced_motion)
        self.docs_state = UiStateMachine[list[DocumentItem]]()
        self.qa_state = UiStateMachine[dict[str, list[str] | str]]()
        self.docs_loading_after_id = None
        self.qa_loading_after_id = None
        self.docs_time_to_value = None
        self.qa_time_to_value = None
        self._docs_recent_taps = []
        self._docs_requests = RequestCoordinator()
        self._qa_requests = RequestCoordinator()
        self._is_closing = False
        self._last_favorite_undo = None
        self._state_save_after_id = None
        self._status_after_id = None
        self._status_snapshot = None
        self._runtime_bootstrap_started = False
        self._runtime_bootstrap_failed = False
        self.search_inflight = False
        self.docs_page_index = 0
        self.docs_page_total = 0
        self.docs_page_cached_at = 0.0
        self.docs_mutation_inflight = False
        self.search_answer_cancel_event: threading.Event | None = None
        self.search_answer_request_id = 0
        self.model_download_cancel_event: threading.Event | None = None
        self.model_download_inflight = False
        self.app_state = load_state(APP_STATE_PATH)
        self.onboarding_dismissed = self.app_state.onboarding_dismissed

        _ensure_required_dirs()
        debug(f"data dir: {DATA_DIR}")
        debug(f"db path: {DB_PATH}")
        cfg, ok = config.load_config(CONFIG_PATH, return_ok=True)
        debug(f"config loaded ok={ok}")
        self.cfg = cfg
        self.feature_flags = from_config(self.cfg)
        if not ok:
            debug("config missing or invalid; writing defaults")
            config.save_config(CONFIG_PATH, self.cfg)
        self._apply_profile_defaults()
        if str(self.cfg.get("llm_backend", "lmstudio")).strip().lower() == "llama_cpp":
            self._auto_select_llm_model()
        self._auto_set_search_only_mode()
        # Require an explicit language choice before building the full UI.
        self.ui_language = self._init_language()
        if not self.ui_language:
            print("No language selected. Exiting.")
            self.destroy()
            raise SystemExit(0)

        install_crash_hook(CRASH_LOG_PATH)
        self._init_theme()
        self._configure_style()
        debug("style configured")

        debug("initializing db")
        kb.init_db(DB_PATH)
        debug("db initialized")
        self._ensure_seed_data()

        debug("building ui")
        self._build_ui()
        debug("ui built")
        self._start_runtime_bootstrap()
        self.docs_page_index = self.app_state.docs_page
        if self.app_state.qa_draft:
            self.qa_var.set(self.app_state.qa_draft)
            self.after(400, lambda: self.toast.show(self.tr("onboarding_resume_draft")))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._load_documents_screen(initial=True)
        self._set_qa_state(Empty(title=self.tr("qa_empty_title"), message=self.tr("qa_empty_body")))
        self.after(300, self._prefetch_background)
        self._restore_last_tab()
        self._maybe_show_splash()

    def tr(self, key: str, **kwargs) -> str:
        lang = self.ui_language if self.ui_language in I18N else "en"
        text = I18N.get(lang, I18N["en"]).get(key, I18N["en"].get(key, key))
        return text.format(**kwargs)

    def _init_theme(self) -> None:
        self._using_sv_ttk = False
        theme_pref = (self.cfg.get("ui_theme") or "").strip().lower()
        if theme_pref not in {"light", "dark", "auto"}:
            theme_pref = "auto"
        selected = "light"
        if theme_pref == "dark":
            selected = "dark"
        elif theme_pref == "auto":
            try:
                import darkdetect  # type: ignore

                selected = "dark" if darkdetect.isDark() else "light"
            except Exception:
                selected = "light"
        try:
            import sv_ttk  # type: ignore

            sv_ttk.set_theme(selected)
            self._using_sv_ttk = True
            debug(f"theme engine=sv_ttk mode={selected}")
        except ModuleNotFoundError:
            debug("sv_ttk unavailable, falling back to default ttk theme")
        except Exception as exc:
            _report_ui_exception(exc)
            debug("sv_ttk unavailable, falling back to default ttk theme")

    def _configure_style(self):
        style = ttk.Style(self)
        self._style = style
        try:
            if not getattr(self, "_using_sv_ttk", False):
                style.theme_use("clam")
        except tk.TclError:
            pass
        default_font = tkfont.nametofont("TkDefaultFont")
        base_size = default_font.cget("size") or 10
        try:
            dpi_scale = float(self.winfo_fpixels("1i")) / 72.0
            self.tk.call("tk", "scaling", max(1.0, min(2.0, dpi_scale)))
        except Exception:
            pass
        try:
            scale = float(os.getenv("FONTE_FONT_SCALE", "1.0"))
        except ValueError:
            scale = 1.0
        default_font.configure(family=preferred_font_family(), size=max(11, int(base_size * max(0.85, scale))))
        self.option_add("*Font", default_font)
        style.configure("TButton", padding=(SPACE_2, 7))
        style.configure("TLabel", padding=(0, 0))
        style.configure("TEntry", padding=(10, 6))
        style.configure("TLabelframe", padding=(SPACE_2, SPACE_1))
        style.configure("TNotebook", tabposition="n")
        style.configure("TNotebook.Tab", padding=(14, 8))
        style.map("TNotebook.Tab", background=[("selected", "#DCE6F5")], foreground=[("selected", "#10243E")])
        style.configure("Primary.TButton", padding=(16, 9))
        style.configure("Secondary.TButton", padding=(14, 8))
        style.map("Primary.TButton", relief=[("pressed", "sunken"), ("active", "raised")])
        style.map(
            "Secondary.TButton",
            relief=[("pressed", "sunken"), ("active", "raised")],
            background=[("active", "#EBF1F8")],
        )
        style.configure("Card.TFrame", padding=SPACE_2, relief="groove", borderwidth=1)
        style.configure("SectionTitle.TLabel", font=(preferred_font_family(), 12, "bold"))
        style.configure("StateTitle.TLabel", font=(preferred_font_family(), 12, "bold"))
        style.configure("Subtle.TLabel", foreground="#606A78")
        style.configure("FieldLabel.TLabel", font=(preferred_font_family(), 10, "bold"))
        style.configure("StateErrorTitle.TLabel", font=(preferred_font_family(), 11, "bold"), foreground="#8B1E1E")
        style.configure("Search.TEntry", padding=(12, 8))
        style.configure("Placeholder.TEntry", padding=(12, 8), foreground="#8A93A3")
        style.map("Search.TEntry", bordercolor=[("focus", "#2D5E9E")], lightcolor=[("focus", "#2D5E9E")])
        style.configure("Toast.TLabel", background="#202020", foreground="#FFFFFF", padding=(10, 6))
        style.configure("ToastFrame.TFrame", background="#202020")
        style.configure("ToastAction.TButton", padding=(8, 4))
        style.configure("Tooltip.TLabel", background="#1E1E1E", foreground="#FFFFFF", padding=(6, 4))
        style.configure("FieldError.TLabel", foreground="#8B1E1E")

    def _apply_text_surface_style(self, widget: tk.Text) -> None:
        style = getattr(self, "_style", None)
        if style is None:
            style = ttk.Style(self)
        raw_bg = style.lookup("TFrame", "background")
        bg = self._tcl_to_str(raw_bg) or "#FFFFFF"
        fg = style.lookup("TLabel", "foreground") or "#111111"
        bg_s = self._tcl_to_str(raw_bg).strip()
        bg_lower = str(bg_s).lower()
        widget.configure(
            background=bg,
            foreground=fg,
            insertbackground=fg,
            highlightthickness=0,
            selectbackground="#BFD7FF" if bg_s and bg_lower in {"#ffffff", "white"} else "#3B557A",
            selectforeground=fg,
        )

    def _tcl_to_str(self, value) -> str:
        if value is None:
            return ""
        try:
            return str(value)
        except Exception:
            return ""

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
        self._refresh_ai_controls()
        self._refresh_docs(self.docs_repo.get_cached_documents() or [])
        self._render_docs_state()
        self._render_qa_state()

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
        if hasattr(self, "search_entry"):
            self.search_entry.set_placeholder(self.tr("search_placeholder"))
        if hasattr(self, "search_hint_label"):
            self.search_hint_label.configure(text=self.tr("search_hint"))
        if hasattr(self, "qa_field"):
            self.qa_field.set_label(self.tr("question_label"))
            self.qa_field.set_placeholder(self.tr("question_placeholder"))
        if hasattr(self, "docs_prev_btn"):
            self.docs_prev_btn.configure(text=self.tr("pager_previous"))
        if hasattr(self, "docs_next_btn"):
            self.docs_next_btn.configure(text=self.tr("pager_next"))
        self._update_docs_pager()
        self._sync_search_button_state()
        self._sync_qa_submit_state()
        self._update_status_bar_from_snapshot()

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
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=SPACE_3, pady=SPACE_3)

        self.search_tab = AppScaffold(self.notebook)
        self.qa_tab = AppScaffold(self.notebook)
        self.utils_tab = AppScaffold(self.notebook)
        self.manage_tab = AppScaffold(self.notebook)

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
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.bind_all("<Control-f>", lambda _event: self._focus_search_input(), add=True)
        self.analytics.track("screen_view", screen="search")
        self.after(140, self._focus_search_input)

    def _build_search_tab(self):
        frame = self.search_tab
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(4, weight=1)
        header = ttk.Label(frame, style="SectionTitle.TLabel")
        self._i18n_widget(header, "search_header")
        header.grid(row=0, column=0, sticky="w", pady=(0, SPACE_2))

        self.search_onboarding = CardFrame(frame)
        self.search_onboarding.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))
        self.search_onboarding.grid_columnconfigure(0, weight=1)
        onboarding_title = ttk.Label(self.search_onboarding, style="StateTitle.TLabel")
        self._i18n_widget(onboarding_title, "onboarding_title")
        onboarding_title.grid(row=0, column=0, sticky="w")
        onboarding_value = ttk.Label(self.search_onboarding, style="Subtle.TLabel", wraplength=760)
        self._i18n_widget(onboarding_value, "onboarding_value")
        onboarding_value.grid(row=1, column=0, sticky="w", pady=(SPACE_1 // 2, SPACE_2))
        onboarding_actions = ttk.Frame(self.search_onboarding)
        onboarding_actions.grid(row=2, column=0, sticky="w")
        quick_demo = PrimaryButton(onboarding_actions, command=self._run_demo)
        self._i18n_widget(quick_demo, "onboarding_quick_demo")
        quick_demo.pack(side="left")
        first_import = SecondaryButton(onboarding_actions, command=self._import_file)
        self._i18n_widget(first_import, "onboarding_import_first")
        first_import.pack(side="left", padx=(6, 0))
        resume_btn = SecondaryButton(onboarding_actions, command=self._resume_draft)
        self._i18n_widget(resume_btn, "onboarding_resume_action")
        resume_btn.pack(side="left", padx=(6, 0))
        skip_btn = SecondaryButton(onboarding_actions, command=self._dismiss_onboarding)
        self._i18n_widget(skip_btn, "onboarding_skip")
        skip_btn.pack(side="left", padx=(6, 0))

        row = CardFrame(frame)
        row.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_2))
        row.grid_columnconfigure(0, weight=1)
        self.search_var = tk.StringVar()
        self.search_entry = PlaceholderEntry(
            row,
            textvariable=self.search_var,
            placeholder=self.tr("search_placeholder"),
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")
        self.search_entry.bind("<Return>", lambda _event: self._do_search(), add=True)
        self.search_var.trace_add("write", lambda *_: self._sync_search_button_state())
        self.search_btn = PrimaryButton(row, command=self._do_search)
        self._i18n_widget(self.search_btn, "search_button")
        self.search_btn.grid(row=0, column=1, padx=(SPACE_1, 0))
        self.search_hint_label = ttk.Label(row, style="Subtle.TLabel", wraplength=680)
        self._i18n_widget(self.search_hint_label, "search_hint")
        self.search_hint_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(SPACE_1 // 2, 0))

        answer_frame = CardFrame(frame)
        answer_frame.grid(row=3, column=0, sticky="ew", pady=(0, SPACE_2))
        answer_frame.grid_columnconfigure(0, weight=1)
        self.answer_status_var = tk.StringVar(value=self.tr("search_answer_off"))
        self.answer_text_var = tk.StringVar(value="")
        self.answer_progress_var = tk.StringVar(value="")
        self.answer_provider_label = ttk.Label(answer_frame, style="Subtle.TLabel")
        self._i18n_widget(self.answer_provider_label, "ai_local_provider")
        self.answer_provider_label.grid(row=0, column=0, sticky="w")
        self.answer_action_btn = SecondaryButton(answer_frame, command=self._open_model_manager)
        self._i18n_widget(self.answer_action_btn, "download_ai_model")
        self.answer_action_btn.grid(row=0, column=1, sticky="e")
        self.answer_cancel_btn = SecondaryButton(answer_frame, command=self._cancel_search_answer)
        self._i18n_widget(self.answer_cancel_btn, "cancel_action")
        self.answer_cancel_btn.grid(row=0, column=2, sticky="e", padx=(6, 0))
        self.answer_cancel_btn.grid_remove()
        self.answer_status_label = ttk.Label(answer_frame, textvariable=self.answer_status_var, style="StateTitle.TLabel")
        self.answer_status_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.answer_text_label = ttk.Label(answer_frame, textvariable=self.answer_text_var, wraplength=760, justify="left")
        self.answer_text_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.answer_progress_label = ttk.Label(answer_frame, textvariable=self.answer_progress_var, style="Subtle.TLabel")
        self.answer_progress_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.answer_progress = ttk.Progressbar(answer_frame, mode="determinate")
        self.answer_progress.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.answer_progress.grid_remove()

        text_frame = CardFrame(frame)
        text_frame.grid(row=4, column=0, sticky="nsew")
        text_frame.grid_columnconfigure(0, weight=1)
        text_frame.grid_rowconfigure(0, weight=1)
        self.search_results = tk.Text(
            text_frame,
            height=22,
            wrap="word",
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
        )
        self._apply_text_surface_style(self.search_results)
        self.search_results.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.search_results.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.search_results.config(yscrollcommand=scrollbar.set)
        self.search_results.tag_configure("result_title", font=(preferred_font_family(), 10, "bold"), spacing3=4)
        self.search_results.tag_configure("result_body", spacing1=2, spacing3=12)
        self.search_results.tag_configure("result_separator", foreground="#8A93A3")
        self.search_results.tag_configure("answer_title", font=(preferred_font_family(), 11, "bold"), spacing3=4)
        self.search_results.tag_configure("answer_body", spacing1=2, spacing3=10, foreground="#334A67")
        self.search_results.tag_configure("empty_title", font=(preferred_font_family(), 11, "bold"))
        self.search_results.tag_configure("empty_body", foreground="#5F6B7A", spacing1=4)
        self.search_results.configure(state="disabled")
        if self._ai_answers_user_enabled() and not self._llm_ready():
            self._set_search_answer_state("not_installed")
        elif self._ai_answers_user_enabled():
            self._set_search_answer_state("ready")
        else:
            self._set_search_answer_state("off")
        self._render_search_empty()
        self._sync_search_button_state()
        self._update_onboarding_visibility()

    def _do_search(self):
        if not hasattr(self, "search_entry"):
            return
        query = self.search_entry.get_value() if hasattr(self, "search_entry") else self.search_var.get()
        query = query.strip()
        self._sync_search_button_state()
        if not query:
            self._render_search_empty()
            self._set_activity(self.tr("search_empty_title"), status_key="status_error")
            return
        self.search_inflight = True
        self.search_btn.configure(state="disabled")
        self._set_activity(query, status_key="status_busy")
        self.search_results.configure(state="normal")
        self.search_results.delete("1.0", tk.END)
        self._cancel_search_answer()
        friendly_error = None
        try:
            results, friendly_error = kb.search_with_feedback(DB_PATH, query, limit=8)
        except Exception:
            results = []
            friendly_error = self.tr("search_failed_friendly")
        finally:
            self.search_inflight = False
            self.search_btn.configure(state="normal")
            self._sync_search_button_state()
        self._render_search_results(results, friendly_error=friendly_error)
        should_answer = should_generate_search_answer(query)
        if not should_answer:
            self._set_search_answer_state("ready", text="")
            self._set_activity(self.tr("search_button"), status_key="status_done")
            return
        request_id = self.search_answer_request_id + 1
        self.search_answer_request_id = request_id
        self.search_answer_cancel_event = threading.Event()
        self._set_search_answer_state("generating")

        def worker():
            try:
                answer_text = self._build_search_answer(query, results)
                self.after(0, lambda: self._finish_search_answer(request_id, answer_text, None))
            except Exception as exc:
                self.after(0, lambda: self._finish_search_answer(request_id, "", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_search_answer(self, request_id: int, answer_text: str, err: Exception | None) -> None:
        if request_id != self.search_answer_request_id or self._is_closing:
            return
        if err is not None:
            mapped = map_exception(err)
            self.analytics.track("api_error", screen="search", category=mapped.code, detail=mapped.debug_message)
            self._set_search_answer_state("error", text=mapped.message)
            self._set_activity(self.tr("search_button"), status_key="status_error")
            return
        self._set_search_answer_state("ready", text=answer_text)
        self._set_activity(self.tr("search_button"), status_key="status_done")

    def _render_search_results(self, results: list[kb.ChunkResult], *, friendly_error: str | None = None) -> None:
        self.search_results.configure(state="normal")
        self.search_results.delete("1.0", tk.END)
        if not results:
            if friendly_error:
                self.search_results.insert(tk.END, friendly_error + "\n", "empty_title")
                self.search_results.insert(tk.END, self.tr("search_settings_cta") + "\n\n", "empty_body")
            self.search_results.insert(tk.END, self.tr("search_empty_title") + "\n", "empty_title")
            self.search_results.insert(tk.END, self.tr("search_empty_body") + "\n", "empty_body")
            self.search_results.configure(state="disabled")
            return
        for result in results:
            self.search_results.insert(
                tk.END,
                f"[{result.rowid}] {result.title} ({result.source})\n",
                "result_title",
            )
            self.search_results.insert(
                tk.END,
                f"{result.chunk_text.strip()}\n",
                "result_body",
            )
            self.search_results.insert(tk.END, "─" * 42 + "\n", "result_separator")
        self.search_results.see("1.0")
        self.search_results.configure(state="disabled")

    def _set_search_answer_state(self, state: str, *, text: str = "", done: int = 0, total: int = 0, eta: str = "") -> None:
        if not hasattr(self, "answer_status_var"):
            return
        self.answer_cancel_btn.grid_remove()
        self.answer_progress.grid_remove()
        self.answer_progress_var.set("")
        self.answer_action_btn.configure(state="normal")
        if state == "off":
            self.answer_status_var.set(self.tr("search_answer_off"))
            self.answer_text_var.set("")
            self.answer_action_btn.grid_remove()
            return
        if state == "not_installed":
            self.answer_status_var.set(self.tr("search_answer_not_installed"))
            self.answer_text_var.set("")
            self.answer_action_btn.grid()
            self.answer_action_btn.configure(text=self.tr("download_ai_model"), command=self._open_model_manager)
            return
        if state == "downloading":
            self.answer_status_var.set(self.tr("search_answer_downloading"))
            self.answer_text_var.set("")
            self.answer_action_btn.grid_remove()
            self.answer_cancel_btn.grid()
            self.answer_progress.grid()
            percent = int((done / total) * 100) if total > 0 else 0
            self.answer_progress.configure(value=max(0, min(100, percent)))
            self.answer_progress_var.set(
                self.tr(
                    "ai_download_progress",
                    done=model_manager.format_size(done),
                    total=model_manager.format_size(total) if total > 0 else "?",
                    eta=eta or "estimating...",
                )
            )
            return
        if state == "generating":
            self.answer_status_var.set(self.tr("search_answer_generating"))
            self.answer_text_var.set("")
            self.answer_action_btn.grid_remove()
            self.answer_cancel_btn.grid()
            return
        if state == "error":
            self.answer_status_var.set(self.tr("search_answer_error"))
            self.answer_text_var.set(text or self.tr("ai_install_failed"))
            self.answer_action_btn.grid()
            self.answer_action_btn.configure(text=self.tr("repair_ai_model"), command=self._open_model_manager)
            return
        self.answer_status_var.set(self.tr("search_answer_ready"))
        self.answer_text_var.set(text.strip())
        self.answer_action_btn.grid()
        self.answer_action_btn.configure(text=self.tr("manage_ai_model"), command=self._open_model_manager)

    def _cancel_search_answer(self):
        if self.model_download_inflight and self.model_download_cancel_event is not None:
            self.model_download_cancel_event.set()
        if self.search_answer_cancel_event is not None:
            self.search_answer_cancel_event.set()
        self.search_answer_request_id += 1
        if hasattr(self, "answer_cancel_btn"):
            self.answer_cancel_btn.grid_remove()

    def _build_search_answer(self, query: str, results: list[kb.ChunkResult]) -> str:
        if self.search_answer_cancel_event is not None and self.search_answer_cancel_event.is_set():
            return ""
        context = [(r.rowid, r.title, r.source, r.chunk_text) for r in results[:4]]
        llm_answer = ""
        try:
            if self.llm is None:
                self._ensure_llm()
            max_tokens = int(self.cfg.get("llm_max_tokens") or 192)
            low_resource = (self.cfg.get("ai_low_resource_mode") or "true").strip().lower() == "true"
            max_tokens = max(80, min(192 if low_resource else 256, max_tokens))
            llm_answer = llm_api.generate_answer(
                self.llm,
                query,
                context,
                max_tokens=max_tokens,
                temperature=0.3 if low_resource else 0.45,
            )
            if self.search_answer_cancel_event is not None and self.search_answer_cancel_event.is_set():
                return ""
        except Exception as exc:
            mapped = map_exception(exc)
            self.analytics.track("api_error", screen="search", category=mapped.code, detail=mapped.debug_message)
        if llm_answer.strip():
            return self._format_search_answer(llm_answer)
        return self._build_search_extractive_answer(results, query=query)

    def _format_search_answer(self, answer_text: str) -> str:
        normalized = re.sub(r"\s+", " ", (answer_text or "").strip())
        if not normalized:
            return "Here is a quick answer: focus on the main goal, choose a practical first step, and iterate."
        lines = [line.strip() for line in (answer_text or "").splitlines() if line.strip()]
        bullet_lines = []
        for line in lines:
            if line.startswith(("-", "*", "\u2022")):
                clean = line.lstrip("-*\u2022 ").strip()
                if clean:
                    bullet_lines.append(f"- {clean}")
        if bullet_lines:
            return "\n".join(bullet_lines[:6])
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]
        if len(sentences) >= 2:
            return "\n".join(f"- {sentence}" for sentence in sentences[:6])
        if len(normalized) > 320:
            return normalized[:317].rstrip() + "..."
        return normalized

    def _build_search_extractive_answer(self, results: list[kb.ChunkResult], *, query: str = "") -> str:
        sentences: list[str] = []
        seen: set[str] = set()
        for result in results[:6]:
            compact = " ".join(result.chunk_text.split())
            if not compact:
                continue
            parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", compact) if p.strip()]
            if not parts:
                continue
            for part in parts:
                if len(part) < 35:
                    continue
                key = part.lower()
                if key in seen:
                    continue
                seen.add(key)
                sentences.append(part)
                break
            if len(sentences) >= 4:
                break
        if not sentences:
            fallback = " ".join(results[0].chunk_text.split()) if results else ""
            if not fallback:
                q = query.strip() or "your request"
                return f"Quick answer: {q} can be approached by defining key terms, selecting one practical method, and validating with examples."
            if len(fallback) > 320:
                return fallback[:317].rstrip() + "..."
            return fallback
        if len(sentences) == 1:
            return sentences[0]
        return "\n".join(f"- {sentence}" for sentence in sentences)

    def _render_search_empty(self):
        if not hasattr(self, "search_results"):
            return
        self.search_results.configure(state="normal")
        self.search_results.delete("1.0", tk.END)
        self.search_results.insert(tk.END, self.tr("search_empty_title") + "\n", "empty_title")
        self.search_results.insert(tk.END, self.tr("search_empty_body") + "\n", "empty_body")
        self.search_results.configure(state="disabled")

    def _sync_search_button_state(self):
        if not hasattr(self, "search_btn") or not hasattr(self, "search_entry"):
            return
        if self.search_inflight:
            self.search_btn.configure(state="disabled")
            return
        can_search = bool(self.search_entry.get_value().strip())
        self.search_btn.configure(state="normal" if can_search else "disabled")

    def _build_qa_tab(self):
        frame = self.qa_tab
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        header = ttk.Label(frame, style="SectionTitle.TLabel")
        self._i18n_widget(header, "qa_header")
        header.grid(row=0, column=0, sticky="w", pady=(0, SPACE_2))

        row = CardFrame(frame)
        row.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))
        row.grid_columnconfigure(0, weight=1)
        self.qa_var = tk.StringVar()
        self.qa_field = FormField(
            row,
            label=self.tr("question_label"),
            textvariable=self.qa_var,
            placeholder=self.tr("question_placeholder"),
        )
        self.qa_field.grid(row=0, column=0, sticky="ew")
        self.qa_submit_btn = PrimaryButton(row, command=self._on_qa_submit)
        self._i18n_widget(self.qa_submit_btn, "answer_button")
        self.qa_submit_btn.grid(row=0, column=1, padx=(SPACE_2, 0), sticky="n")
        self.qa_submit_btn.configure(width=12)
        set_accessibility_label(self.qa_submit_btn, "Submit question")
        self.qa_field.entry.bind("<Return>", lambda _event: self._on_qa_submit())
        self.qa_field.entry.bind("<KeyRelease>", lambda _event: self._on_qa_text_edited(), add=True)
        self.qa_var.trace_add("write", lambda *_: self._sync_qa_submit_state())

        self.qa_state_host = CardFrame(frame)
        self.qa_state_host.grid(row=2, column=0, sticky="nsew")
        self.qa_state_host.grid_columnconfigure(0, weight=1)
        self.qa_state_host.grid_rowconfigure(0, weight=1)
        self._sync_qa_submit_state()

    def _on_qa_submit(self):
        self.analytics.track("primary_action_tap", screen="qa", action="submit_answer")
        query = str(self.qa_field.get_value()).strip()
        self.qa_field.set_error("")
        validation_error = validate_question(query)
        if validation_error:
            err = ValidationError({"question": validation_error})
            mapped = map_exception(err)
            self.qa_field.set_error(validation_error)
            self._set_qa_state(Error(to_ui_error(mapped)))
            self._set_activity(self.tr("answer_button"), status_key="status_error")
            self.analytics.track("api_error", screen="qa", category=mapped.code, detail=mapped.debug_message)
            self.analytics.track("action_outcome", screen="qa", action="submit_answer", outcome="validation_failed")
            return
        snapshot = self._qa_requests.start(query, dedupe=True)
        if snapshot is None:
            self.analytics.track("action_tap", screen="qa", action="deduped_submit")
            return
        if self.qa_time_to_value is not None:
            self.qa_time_to_value.cancel()
        self.qa_submit_btn.configure(state="disabled")
        self.qa_time_to_value = self.analytics.start_timer("qa")
        self._set_activity(query, status_key="status_busy")
        self._start_delayed_qa_loading()

        def worker():
            try:
                payload = self._build_qa_response(query)
                self.after(0, lambda: self._on_qa_success(snapshot, payload))
            except Exception as exc:
                mapped = map_exception(exc)
                self.after(0, lambda: self._on_qa_error(snapshot, mapped))

        threading.Thread(target=worker, daemon=True).start()

    def _build_qa_response(self, query: str) -> dict[str, list[str] | str | bool]:
        try:
            retrieval_limit = int(str(self.cfg.get("retrieval_limit") or "4").strip())
        except ValueError:
            retrieval_limit = 4
        retrieval_limit = max(1, min(12, retrieval_limit))
        try:
            results = kb.search(DB_PATH, query, limit=retrieval_limit)
        except Exception as exc:
            mapped = map_exception(exc)
            self.analytics.track("api_error", screen="qa", category=mapped.code, detail=mapped.debug_message)
            results = []
        context = [(r.rowid, r.title, r.source, r.chunk_text) for r in results]
        answer_text = self._answer_with_llm(query, context)
        answer_text = str(answer_text or "").strip()
        if not answer_text:
            answer_text = "Best effort answer: start from the key terms in your question and proceed with a practical first step."
        citations = [f"[{r.rowid}] {r.title} ({r.source})" for r in results]
        return {"answer_text": answer_text, "answer": answer_text, "citations": citations, "had_context": bool(results)}

    def _start_delayed_qa_loading(self):
        if self.qa_loading_after_id is not None:
            self.after_cancel(self.qa_loading_after_id)
        self.qa_loading_after_id = self.after(200, lambda: self._set_qa_state(Loading(self.tr("qa_loading"))))

    def _on_qa_success(self, snapshot, payload: dict[str, list[str] | str | bool]):
        if self._is_closing:
            return
        if not self._qa_requests.complete(snapshot):
            return
        if self.qa_loading_after_id is not None:
            self.after_cancel(self.qa_loading_after_id)
            self.qa_loading_after_id = None
        self._sync_qa_submit_state()
        answer = str(payload.get("answer_text", payload.get("answer", ""))).strip()
        citations = payload.get("citations", [])
        if not answer:
            answer = "Best effort answer: start from the key terms in your question and proceed with a practical first step."
        self._set_qa_state(Success({"answer": answer, "citations": citations}))
        self._set_activity(self.tr("answer_button"), status_key="status_done")
        self.analytics.track("action_outcome", screen="qa", action="submit_answer", outcome="success")
        self._mark_milestone("first_answer")
        if self.qa_time_to_value is not None:
            self.qa_time_to_value.stop(state="success")

    def _on_qa_error(self, snapshot, mapped):
        if self._is_closing:
            return
        if not self._qa_requests.complete(snapshot):
            return
        if self.qa_loading_after_id is not None:
            self.after_cancel(self.qa_loading_after_id)
            self.qa_loading_after_id = None
        self._sync_qa_submit_state()
        self._set_activity(self.tr("answer_button"), status_key="status_error")
        self._set_qa_state(Error(to_ui_error(mapped)))
        self.analytics.track("api_error", screen="qa", category=mapped.code, detail=mapped.debug_message)
        self.analytics.track("action_outcome", screen="qa", action="submit_answer", outcome="failure")
        if self.qa_time_to_value is not None:
            self.qa_time_to_value.stop(state="error")

    def _set_qa_state(self, state):
        self.qa_state.set_state(state)
        self._render_qa_state()

    def _render_qa_state(self):
        for child in self.qa_state_host.winfo_children():
            child.destroy()
        state = self.qa_state.state
        if isinstance(state, Loading):
            LoadingState(self.qa_state_host, message=state.message).grid(row=0, column=0, sticky="nsew")
            return
        if isinstance(state, Empty):
            EmptyState(self.qa_state_host, title=state.title, message=state.message).grid(row=0, column=0, sticky="nsew")
            return
        if isinstance(state, Error):
            ErrorState(
                self.qa_state_host,
                title=state.error.title,
                message=state.error.message,
                action_text=state.error.recovery_action,
                on_action=self._retry_qa,
            ).grid(row=0, column=0, sticky="nsew")
            return
        if isinstance(state, Success):
            frame = ttk.Frame(self.qa_state_host)
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)

            transcript = tk.Text(
                frame,
                height=18,
                wrap="word",
                relief="flat",
                borderwidth=0,
                padx=12,
                pady=10,
            )
            self._apply_text_surface_style(transcript)
            transcript.grid(row=0, column=0, sticky="nsew")
            t_scroll = ttk.Scrollbar(frame, orient="vertical", command=transcript.yview)
            t_scroll.grid(row=0, column=1, sticky="ns")
            transcript.configure(yscrollcommand=t_scroll.set)
            transcript.tag_configure("msg_user_label", font=(preferred_font_family(), 9, "bold"), foreground="#51627A")
            transcript.tag_configure("msg_user", lmargin1=12, lmargin2=12, rmargin=24, spacing3=10)
            transcript.tag_configure("msg_ai_label", font=(preferred_font_family(), 9, "bold"), foreground="#2C4A78")
            transcript.tag_configure("msg_ai", lmargin1=24, lmargin2=24, rmargin=12, spacing3=12)
            transcript.tag_configure("msg_cite_label", font=(preferred_font_family(), 9, "bold"), foreground="#4E5E75")
            transcript.tag_configure("msg_cite", lmargin1=24, lmargin2=24, rmargin=12, foreground="#596B84")
            transcript.tag_configure("msg_sep", foreground="#8A93A3", spacing3=10)

            user_question = str(self.qa_var.get()).strip() or "-"
            transcript.insert(tk.END, "You\n", "msg_user_label")
            transcript.insert(tk.END, user_question + "\n\n", "msg_user")
            transcript.insert(tk.END, "─" * 36 + "\n", "msg_sep")
            transcript.insert(tk.END, "Assistant\n", "msg_ai_label")
            transcript.insert(tk.END, str(state.data.get("answer", "")) + "\n\n", "msg_ai")
            citations = state.data.get("citations", [])
            transcript.insert(tk.END, self.tr("citations_label") + "\n", "msg_cite_label")
            if citations:
                transcript.insert(tk.END, "\n".join(str(c) for c in citations), "msg_cite")
            else:
                transcript.insert(tk.END, self.tr("no_citations"), "msg_cite")
            transcript.configure(state="disabled")
            return
        EmptyState(
            self.qa_state_host,
            title=self.tr("qa_empty_title"),
            message=self.tr("qa_empty_body"),
        ).grid(row=0, column=0, sticky="nsew")

    def _on_qa_text_edited(self):
        self._schedule_state_save()
        self._sync_qa_submit_state()

    def _sync_qa_submit_state(self):
        if not hasattr(self, "qa_submit_btn") or not hasattr(self, "qa_field"):
            return
        if self._qa_requests.inflight_key is not None:
            self.qa_submit_btn.configure(state="disabled")
            return
        can_submit = bool(self.qa_field.get_value().strip())
        self.qa_submit_btn.configure(state="normal" if can_submit else "disabled")

    def _retry_qa(self):
        self.analytics.track("retry", screen="qa", action="retry_submit")
        self._on_qa_submit()

    def _answer_with_llm(self, question, context):
        safe_fallback = self._direct_fallback_answer(question, context)
        try:
            mode = task_router.detect_mode(str(question or ""))
            messages = task_router.build_messages(str(question or ""), context, mode)
            selected_language = {
                "en": "English",
                "de": "German",
                "pt": "Portuguese",
            }.get(str(self.__dict__.get("ui_language", "en") or "").strip().lower(), "English")
            language_prompts = {
                "English": "Respond in English.",
                "German": "Antworte auf Deutsch.",
                "Portuguese": "Responda em português.",
            }
            language_instruction = language_prompts.get(selected_language, "Respond in English.")
            messages = [{"role": "system", "content": language_instruction}] + messages
            model_id = task_router.select_model_id(mode, str(question or ""), self.cfg)
            if not model_id:
                return "LM Studio model is not configured. Set model_small_id or model_large_id in Settings."
            try:
                max_tokens = int(str(self.cfg.get("max_tokens", self.cfg.get("llm_max_tokens", "192"))).strip())
            except ValueError:
                max_tokens = 192
            try:
                timeout_seconds = int(str(self.cfg.get("timeout_seconds") or "20").strip())
            except ValueError:
                timeout_seconds = 20
            try:
                temperature = float(str(self.cfg.get("temperature") or "0.2").strip())
            except ValueError:
                temperature = 0.2
            base_url = str(self.cfg.get("lmstudio_base_url") or "http://localhost:1234/v1").strip()
            if mode == "json_title_summary_tags":
                payload = llm_lmstudio.chat_json(
                    messages=messages,
                    model=model_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout_seconds,
                    base_url=base_url,
                )
                text = json.dumps(payload, ensure_ascii=True)
            else:
                text = llm_lmstudio.chat(
                    messages=messages,
                    model=model_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout_seconds,
                    base_url=base_url,
                )
            final = str(text or "").strip()
            return final if final else safe_fallback
        except Exception as exc:
            mapped = map_exception(exc)
            self.analytics.track("api_error", screen="qa", category=mapped.code, detail=mapped.debug_message)
            return safe_fallback

    def _direct_fallback_answer(self, question: str, context) -> str:
        for _, _, _, text in context[:2]:
            cleaned = text.strip()
            if cleaned:
                return cleaned
        q = (question or "").strip()
        number_after_match = re.search(r"\bnumber\s+after\s+(-?\d+)\b", q, flags=re.IGNORECASE)
        if number_after_match:
            try:
                value = int(number_after_match.group(1))
                return str(value + 1)
            except ValueError:
                pass
        return (
            "Please enter a question so I can generate a best-effort answer."
            if not q
            else "Best effort answer: clarify your main goal, pick one practical approach, and validate the result step by step."
        )

    def _ensure_llm(self) -> bool:
        if not self._ai_answers_active():
            return False
        if self.llm is not None:
            return True
        model_path = self._effective_llm_model_path()
        if not model_path.exists():
            if self._auto_select_llm_model():
                model_path = self._effective_llm_model_path()
            if not model_path.exists():
                return False
        low_resource = (self.cfg.get("ai_low_resource_mode") or "true").strip().lower() == "true"
        try:
            n_ctx = int(self.cfg.get("llm_context_window") or "1536")
        except ValueError:
            n_ctx = 1536
        if low_resource:
            n_ctx = min(n_ctx, 1024)
        try:
            loaded_llm = llm_api.load_llm(
                backend="llama_cpp",
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=max(1, os.cpu_count() or 2),
                n_batch=128 if low_resource else 256,
            )
            self.llm = loaded_llm
            return True
        except Exception as exc:
            self.llm = None
            mapped = map_exception(exc)
            self.analytics.track("api_error", screen="qa", category=mapped.code, detail=mapped.debug_message)
            return False

    def _shutdown_llm(self):
        llm_obj = self.llm
        if llm_obj is None:
            return
        llm_close = getattr(llm_obj, "close", None)
        if callable(llm_close):
            try:
                llm_close()
            except Exception as exc:
                debug(f"llm close failed: {exc}")
        self.llm = None

    def _build_utils_tab(self):
        frame = self.utils_tab
        frame.grid_columnconfigure(0, weight=1)
        calc_card = CardFrame(frame)
        calc_card.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_2))
        calc_card.grid_columnconfigure(0, weight=1)
        calc_label = ttk.Label(calc_card, style="SectionTitle.TLabel")
        self._i18n_widget(calc_label, "calculator")
        calc_label.grid(row=0, column=0, sticky="w")
        calc_row = ttk.Frame(calc_card)
        calc_row.grid(row=1, column=0, sticky="ew", pady=(SPACE_1 // 2, 0))
        calc_row.grid_columnconfigure(0, weight=1)
        self.calc_var = tk.StringVar()
        ttk.Entry(calc_row, textvariable=self.calc_var).grid(row=0, column=0, sticky="ew")
        calc_btn = PrimaryButton(calc_row, command=self._do_calc)
        self._i18n_widget(calc_btn, "compute")
        calc_btn.grid(row=0, column=1, padx=(6, 0))
        self.calc_out = ttk.Label(calc_card, text="", style="Subtle.TLabel")
        self.calc_out.grid(row=2, column=0, sticky="w", pady=(SPACE_1 // 2, 0))

        unit_card = CardFrame(frame)
        unit_card.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))
        unit_card.grid_columnconfigure(0, weight=1)
        unit_label = ttk.Label(unit_card, style="SectionTitle.TLabel")
        self._i18n_widget(unit_label, "unit_conversion")
        unit_label.grid(row=0, column=0, sticky="w")
        unit_row = ttk.Frame(unit_card)
        unit_row.grid(row=1, column=0, sticky="ew", pady=(SPACE_1 // 2, 0))
        unit_row.grid_columnconfigure(0, weight=1)
        self.unit_value = tk.StringVar(value="1")
        ttk.Entry(unit_row, textvariable=self.unit_value, width=10).grid(row=0, column=0, sticky="ew")
        self.unit_from = tk.StringVar(value="m")
        self.unit_to = tk.StringVar(value="km")
        ttk.Combobox(unit_row, textvariable=self.unit_from, values=list(utils.LENGTH_UNITS.keys()), width=8).grid(
            row=0, column=1, padx=5
        )
        ttk.Combobox(unit_row, textvariable=self.unit_to, values=list(utils.LENGTH_UNITS.keys()), width=8).grid(
            row=0, column=2, padx=5
        )
        unit_btn = SecondaryButton(unit_row, command=self._do_length)
        self._i18n_widget(unit_btn, "convert_length")
        unit_btn.grid(row=0, column=3, padx=5, sticky="w")
        self.unit_out = ttk.Label(unit_card, text="", style="Subtle.TLabel")
        self.unit_out.grid(row=2, column=0, sticky="w", pady=(SPACE_1 // 2, 0))

        temp_card = CardFrame(frame)
        temp_card.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_2))
        temp_card.grid_columnconfigure(0, weight=1)
        temp_label = ttk.Label(temp_card, style="SectionTitle.TLabel")
        self._i18n_widget(temp_label, "temp_conversion")
        temp_label.grid(row=0, column=0, sticky="w")
        temp_row = ttk.Frame(temp_card)
        temp_row.grid(row=1, column=0, sticky="ew", pady=(SPACE_1 // 2, 0))
        temp_row.grid_columnconfigure(0, weight=1)
        self.temp_value = tk.StringVar(value="0")
        ttk.Entry(temp_row, textvariable=self.temp_value, width=10).grid(row=0, column=0, sticky="ew")
        self.temp_from = tk.StringVar(value="C")
        self.temp_to = tk.StringVar(value="F")
        ttk.Combobox(temp_row, textvariable=self.temp_from, values=["C", "F", "K"], width=5).grid(
            row=0, column=1, padx=5
        )
        ttk.Combobox(temp_row, textvariable=self.temp_to, values=["C", "F", "K"], width=5).grid(
            row=0, column=2, padx=5
        )
        temp_btn = SecondaryButton(temp_row, command=self._do_temp)
        self._i18n_widget(temp_btn, "convert_temp")
        temp_btn.grid(row=0, column=3, padx=5, sticky="w")
        self.temp_out = ttk.Label(temp_card, text="", style="Subtle.TLabel")
        self.temp_out.grid(row=2, column=0, sticky="w", pady=(SPACE_1 // 2, 0))

        date_card = CardFrame(frame)
        date_card.grid(row=3, column=0, sticky="ew")
        date_card.grid_columnconfigure(0, weight=1)
        date_label = ttk.Label(date_card, style="SectionTitle.TLabel")
        self._i18n_widget(date_label, "date_utils")
        date_label.grid(row=0, column=0, sticky="w")
        date_row = ttk.Frame(date_card)
        date_row.grid(row=1, column=0, sticky="ew", pady=(SPACE_1 // 2, 0))
        date_row.grid_columnconfigure(0, weight=1)
        self.date_var = tk.StringVar(value=utils.today_iso())
        self.days_var = tk.StringVar(value="7")
        ttk.Entry(date_row, textvariable=self.date_var, width=12).grid(row=0, column=0, sticky="ew")
        ttk.Entry(date_row, textvariable=self.days_var, width=6).grid(row=0, column=1, sticky="w", padx=5)
        date_btn = SecondaryButton(date_row, command=self._do_date_add)
        self._i18n_widget(date_btn, "add_days")
        date_btn.grid(row=0, column=2, padx=5, sticky="w")
        self.date_out = ttk.Label(date_card, text="", style="Subtle.TLabel")
        self.date_out.grid(row=2, column=0, sticky="w", pady=(SPACE_1 // 2, 0))

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
        manage_scroll = ScrollableFrame(frame)
        manage_scroll.grid(row=0, column=0, sticky="nsew")
        content = manage_scroll.content
        content.grid_columnconfigure(0, weight=1)

        documents_frame = ttk.Labelframe(content)
        self._i18n_widget(documents_frame, "documents_header", option="text")
        documents_frame.grid(row=0, column=0, sticky="nsew", pady=(0, SPACE_2))
        documents_frame.grid_columnconfigure(0, weight=1)
        documents_frame.grid_rowconfigure(1, weight=1)

        docs_sub = ttk.Label(documents_frame)
        self._i18n_widget(docs_sub, "documents_subheader")
        docs_sub.grid(row=0, column=0, sticky="w", pady=(0, 6))

        list_row = ttk.Frame(documents_frame)
        list_row.grid(row=1, column=0, sticky="nsew")
        list_row.grid_columnconfigure(0, weight=1)
        list_row.grid_rowconfigure(0, weight=1)
        self.docs_state_host = ttk.Frame(list_row)
        self.docs_state_host.grid(row=0, column=0, sticky="nsew")
        self.docs_state_host.grid_columnconfigure(0, weight=1)
        self.docs_state_host.grid_rowconfigure(0, weight=1)

        btn_row = ttk.Frame(documents_frame)
        btn_row.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.import_btn = PrimaryButton(btn_row, command=self._import_file)
        self._i18n_widget(self.import_btn, "import_text")
        self.import_btn.pack(side="left")
        self.wiki_btn = SecondaryButton(btn_row, command=self._import_wikipedia)
        self._i18n_widget(self.wiki_btn, "import_wikipedia")
        self.wiki_btn.pack(side="left", padx=6)
        self.delete_btn = SecondaryButton(btn_row, command=self._delete_selected)
        self._i18n_widget(self.delete_btn, "delete_selected")
        self.delete_btn.pack(side="left", padx=6)
        self.rebuild_btn = SecondaryButton(btn_row, command=self._rebuild_index)
        self._i18n_widget(self.rebuild_btn, "rebuild_index")
        self.rebuild_btn.pack(side="left", padx=6)
        self.docs_refresh_btn = ttk.Button(btn_row, text="↻", width=4, command=self._retry_load_documents)
        self.docs_refresh_btn.pack(side="left", padx=6)
        set_accessibility_label(self.docs_refresh_btn, "Refresh documents")
        self.docs_favorite_btn = ttk.Button(btn_row, text="☆", width=4, command=self._toggle_selected_favorite)
        self.docs_favorite_btn.pack(side="left", padx=6)
        set_accessibility_label(self.docs_favorite_btn, "Toggle favorite for selected document")

        pager_row = ttk.Frame(documents_frame)
        pager_row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.docs_prev_btn = SecondaryButton(pager_row, text=self.tr("pager_previous"), command=self._docs_prev_page)
        self.docs_prev_btn.pack(side="left")
        self.docs_page_var = tk.StringVar(value=self.tr("pager_label", current=1, total=1))
        ttk.Label(pager_row, textvariable=self.docs_page_var).pack(side="left", padx=10)
        self.docs_next_btn = SecondaryButton(pager_row, text=self.tr("pager_next"), command=self._docs_next_page)
        self.docs_next_btn.pack(side="left")
        self.docs_freshness_var = tk.StringVar(value="")
        ttk.Label(pager_row, textvariable=self.docs_freshness_var).pack(side="left", padx=12)

        models_frame = ttk.Labelframe(content)
        self._i18n_widget(models_frame, "models_header", option="text")
        models_frame.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))
        models_frame.grid_columnconfigure(0, weight=1)

        ai_row = ttk.Frame(models_frame)
        ai_row.grid(row=0, column=0, sticky="ew")
        ai_row.grid_columnconfigure(3, weight=1)
        ai_label = ttk.Label(ai_row)
        self._i18n_widget(ai_label, "ai_answers_label")
        ai_label.grid(row=0, column=0, sticky="w")
        self.ai_answers_var = tk.BooleanVar(value=self._ai_answers_user_enabled())
        self.ai_toggle_text_var = tk.StringVar(value="")
        ai_toggle = ttk.Checkbutton(
            ai_row,
            textvariable=self.ai_toggle_text_var,
            variable=self.ai_answers_var,
            command=self._on_ai_toggle_changed,
        )
        ai_toggle.grid(row=0, column=1, sticky="w", padx=(6, 12))

        self.ai_provider_label = ttk.Label(ai_row, text=self.tr("ai_local_provider"), style="Subtle.TLabel")
        self.ai_provider_label.grid(row=0, column=2, sticky="w")
        self.ai_provider_var = tk.StringVar(value="Local")
        self.ai_provider_box = ttk.Combobox(ai_row, textvariable=self.ai_provider_var, values=["Local"], width=10)
        self.ai_provider_box.grid(row=0, column=3, sticky="w", padx=6)
        self.ai_provider_box.configure(state="disabled")

        self.ai_settings_cta = ttk.Label(models_frame, text=self.tr("mode_search_only_cta"), wraplength=760)
        self.ai_settings_cta.grid(row=1, column=0, sticky="w", pady=(4, 2))

        self.advanced_toggle_var = tk.BooleanVar(value=False)
        self.advanced_toggle_btn = ttk.Checkbutton(
            models_frame,
            variable=self.advanced_toggle_var,
            command=self._toggle_advanced_settings,
        )
        self._i18n_widget(self.advanced_toggle_btn, "advanced_toggle")
        self.advanced_toggle_btn.grid(row=2, column=0, sticky="w", pady=(4, 2))

        self.advanced_frame = ttk.Frame(models_frame)
        self.advanced_frame.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        self.advanced_frame.grid_columnconfigure(0, weight=1)

        model_btn_row = ttk.Frame(self.advanced_frame)
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

        llm_row = ttk.Frame(self.advanced_frame)
        llm_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        llm_row.grid_columnconfigure(3, weight=1)
        backend_label = ttk.Label(llm_row)
        self._i18n_widget(backend_label, "llm_backend")
        backend_label.grid(row=0, column=0, sticky="w")
        self.llm_backend_var = tk.StringVar(value=self._resolve_ai_backend())
        self.llm_backend_box = ttk.Combobox(
            llm_row,
            textvariable=self.llm_backend_var,
            values=LLM_BACKENDS,
            width=12,
            state="readonly",
        )
        self.llm_backend_box.grid(row=0, column=1, sticky="w", padx=(6, 8))
        self.llm_backend_box.configure(state="disabled")
        context_label = ttk.Label(llm_row)
        self._i18n_widget(context_label, "llm_context_window")
        context_label.grid(row=0, column=2, sticky="w")
        self.llm_context_var = tk.StringVar(value=self.cfg.get("llm_context_window", "1536"))
        ttk.Entry(llm_row, textvariable=self.llm_context_var, width=10).grid(row=0, column=3, sticky="w", padx=6)

        llm_row2 = ttk.Frame(self.advanced_frame)
        llm_row2.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        llm_row2.grid_columnconfigure(6, weight=1)
        low_resource_check = ttk.Checkbutton(llm_row2)
        self._i18n_widget(low_resource_check, "low_resource_mode")
        self.low_resource_var = tk.BooleanVar(value=self.cfg.get("ai_low_resource_mode", "true") == "true")
        low_resource_check.configure(variable=self.low_resource_var)
        low_resource_check.grid(row=0, column=0, sticky="w")
        lmstudio_url_label = ttk.Label(llm_row2)
        self._i18n_widget(lmstudio_url_label, "lmstudio_base_url")
        lmstudio_url_label.grid(row=0, column=1, sticky="w", padx=(12, 4))
        self.lmstudio_base_url_var = tk.StringVar(value=self.cfg.get("lmstudio_base_url", "http://localhost:1234/v1"))
        ttk.Entry(llm_row2, textvariable=self.lmstudio_base_url_var, width=28).grid(row=0, column=2, sticky="w")
        small_model_label = ttk.Label(llm_row2)
        self._i18n_widget(small_model_label, "model_small_id")
        small_model_label.grid(row=0, column=3, sticky="w", padx=(12, 4))
        self.model_small_id_var = tk.StringVar(value=self.cfg.get("model_small_id", "google/gemma-3-1b"))
        ttk.Entry(llm_row2, textvariable=self.model_small_id_var, width=20).grid(row=0, column=4, sticky="w")
        save_llm_btn = ttk.Button(llm_row2, command=self._save_llm_settings)
        self._i18n_widget(save_llm_btn, "save_llm_settings")
        save_llm_btn.grid(row=0, column=7, sticky="e")

        llm_row3 = ttk.Frame(self.advanced_frame)
        llm_row3.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        llm_row3.grid_columnconfigure(7, weight=1)
        large_model_label = ttk.Label(llm_row3)
        self._i18n_widget(large_model_label, "model_large_id")
        large_model_label.grid(row=0, column=0, sticky="w")
        self.model_large_id_var = tk.StringVar(value=self.cfg.get("model_large_id", "qwen/qwen3-1.7b"))
        ttk.Entry(llm_row3, textvariable=self.model_large_id_var, width=20).grid(row=0, column=1, sticky="w", padx=(4, 12))
        temp_label = ttk.Label(llm_row3)
        self._i18n_widget(temp_label, "lmstudio_temperature")
        temp_label.grid(row=0, column=2, sticky="w")
        self.temperature_var = tk.StringVar(value=self.cfg.get("temperature", "0.2"))
        ttk.Entry(llm_row3, textvariable=self.temperature_var, width=8).grid(row=0, column=3, sticky="w", padx=(4, 12))
        max_tokens_label = ttk.Label(llm_row3)
        self._i18n_widget(max_tokens_label, "lmstudio_max_tokens")
        max_tokens_label.grid(row=0, column=4, sticky="w")
        self.max_tokens_var = tk.StringVar(value=self.cfg.get("max_tokens", self.cfg.get("llm_max_tokens", "192")))
        ttk.Entry(llm_row3, textvariable=self.max_tokens_var, width=8).grid(row=0, column=5, sticky="w", padx=(4, 12))
        timeout_label = ttk.Label(llm_row3)
        self._i18n_widget(timeout_label, "lmstudio_timeout")
        timeout_label.grid(row=0, column=6, sticky="w")
        self.timeout_seconds_var = tk.StringVar(value=self.cfg.get("timeout_seconds", "20"))
        ttk.Entry(llm_row3, textvariable=self.timeout_seconds_var, width=8).grid(row=0, column=7, sticky="w", padx=(4, 0))

        download_row = ttk.Frame(self.advanced_frame)
        download_row.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        download_row.grid_columnconfigure(1, weight=1)
        download_label = ttk.Label(download_row, text=self.tr("ai_local_provider"), style="Subtle.TLabel")
        download_label.grid(row=0, column=0, sticky="w")
        download_btn = ttk.Button(download_row, command=self._download_model)
        self._i18n_widget(download_btn, "manage_ai_model")
        download_btn.grid(row=0, column=2, sticky="e")

        self._refresh_ai_controls()

        online_frame = ttk.Labelframe(content)
        self._i18n_widget(online_frame, "online_sources_header", option="text")
        online_frame.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_2))
        online_frame.grid_columnconfigure(1, weight=1)

        self.online_enabled_var = tk.BooleanVar(value=self.cfg.get("online_sources_enabled", "false") == "true")
        online_enable = ttk.Checkbutton(online_frame, variable=self.online_enabled_var)
        self._i18n_widget(online_enable, "online_enable")
        online_enable.grid(row=0, column=0, sticky="w", pady=(0, 6))

        cache_label = ttk.Label(online_frame)
        self._i18n_widget(cache_label, "online_cache_days")
        cache_label.grid(row=1, column=0, sticky="w")
        self.online_cache_days_var = tk.StringVar(value=self.cfg.get("online_cache_days", "30"))
        ttk.Entry(online_frame, textvariable=self.online_cache_days_var, width=10).grid(
            row=1, column=1, sticky="w", padx=(6, 6)
        )

        timeout_label = ttk.Label(online_frame)
        self._i18n_widget(timeout_label, "online_timeout_sec")
        timeout_label.grid(row=2, column=0, sticky="w")
        self.online_timeout_var = tk.StringVar(value=self.cfg.get("online_timeout_sec", "20"))
        ttk.Entry(online_frame, textvariable=self.online_timeout_var, width=10).grid(
            row=2, column=1, sticky="w", padx=(6, 6)
        )

        ua_label = ttk.Label(online_frame)
        self._i18n_widget(ua_label, "online_user_agent")
        ua_label.grid(row=3, column=0, sticky="w")
        self.online_user_agent_var = tk.StringVar(value=self.cfg.get("online_user_agent", "Fonte/1.0 (+local-app)"))
        ttk.Entry(online_frame, textvariable=self.online_user_agent_var).grid(
            row=3, column=1, sticky="ew", padx=(6, 6)
        )

        wiki_lang_label = ttk.Label(online_frame)
        self._i18n_widget(wiki_lang_label, "online_wikipedia_language")
        wiki_lang_label.grid(row=4, column=0, sticky="w")
        self.wikipedia_language_var = tk.StringVar(value=self.cfg.get("wikipedia_language", "en"))
        ttk.Entry(online_frame, textvariable=self.wikipedia_language_var, width=10).grid(
            row=4, column=1, sticky="w", padx=(6, 6)
        )

        save_online_btn = ttk.Button(online_frame, command=self._save_online_settings)
        self._i18n_widget(save_online_btn, "save_online_settings")
        save_online_btn.grid(row=5, column=1, sticky="e", pady=(6, 0))

        profile_frame = ttk.Labelframe(content)
        self._i18n_widget(profile_frame, "device_profile_header", option="text")
        profile_frame.grid(row=3, column=0, sticky="ew", pady=(0, SPACE_2))
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

        status_frame = ttk.Labelframe(content)
        self._i18n_widget(status_frame, "status_header", option="text")
        status_frame.grid(row=4, column=0, sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)

        self.storage_label = ttk.Label(status_frame, text="")
        self.storage_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.model_status = ttk.Label(status_frame, text="")
        self.model_status.grid(row=1, column=0, sticky="w")
        self.setup_ai_btn = SecondaryButton(status_frame, command=self._open_ai_setup)
        self._i18n_widget(self.setup_ai_btn, "setup_ai_button")
        self.setup_ai_btn.grid(row=2, column=0, sticky="w", pady=(SPACE_1, 0))
        self._sync_docs_action_state()

    def _refresh_docs(self, docs: list[DocumentItem] | None = None):
        docs = docs if docs is not None else self.docs_repo.load_documents()
        size_mb = DB_PATH.stat().st_size / (1024 * 1024) if DB_PATH.exists() else 0
        shown_count = self.docs_page_total if self.docs_page_total else len(docs)
        self.storage_label.config(text=self.tr("storage_status", size_mb=size_mb, count=shown_count))
        embed_path = self.cfg.get("embedding_model_path") or self.tr("model_not_set")
        llm_path = self._llm_status_value()
        profile = self.cfg.get("device_profile", "low")
        demo = self.cfg.get("demo_mode", "false")
        if self._is_search_only_mode():
            self.model_status.config(text=self.tr("mode_search_only_detail"))
            self.setup_ai_btn.grid()
        else:
            self.model_status.config(text=f"{self.tr('ai_local_provider')} | {self.tr('search_answer_ready')}")
            self.setup_ai_btn.grid_remove()
        self._update_status_bar(size_mb, shown_count, profile, embed_path, llm_path)
        self._update_docs_pager()
        self._sync_docs_action_state()

    def _load_documents_screen(self, *, initial: bool = False, force_refresh: bool = False):
        self.analytics.track("screen_view", screen="manage_documents", initial=initial)
        if self.docs_time_to_value is not None:
            self.docs_time_to_value.cancel()
        self.docs_time_to_value = self.analytics.start_timer("manage_documents")
        cached_page = None
        if not force_refresh:
            cached_page = self.docs_repo.get_documents_page(
                page=self.docs_page_index,
                page_size=DOCS_PAGE_SIZE,
                force_refresh=False,
            )
        if cached_page and cached_page.items:
            self.docs_page_total = cached_page.total_count
            self.docs_page_cached_at = cached_page.cached_at
            self._set_docs_state(Success(cached_page.items))
            self._refresh_docs(cached_page.items)
            if self.docs_time_to_value is not None:
                self.docs_time_to_value.stop(state="success_cached")
            self._refresh_documents_async(background=True)
            return
        self._start_delayed_docs_loading()
        self.docs_freshness_var.set(self.tr("docs_status_loading"))
        self._refresh_documents_async(background=False)

    def _start_delayed_docs_loading(self):
        if self.docs_loading_after_id is not None:
            self.after_cancel(self.docs_loading_after_id)
        self.docs_loading_after_id = self.after(200, lambda: self._set_docs_state(Loading("Loading documents...")))

    def _refresh_documents_async(self, *, background: bool):
        key = "documents:refresh" if not background else "documents:swr"
        snapshot = self._docs_requests.start(key, dedupe=True)
        if snapshot is None:
            self.analytics.track("action_tap", screen="manage_documents", action="deduped_refresh")
            return

        def worker():
            try:
                page = self.docs_repo.get_documents_page(
                    page=self.docs_page_index,
                    page_size=DOCS_PAGE_SIZE,
                    force_refresh=not background,
                )
                self.after(0, lambda: self._on_documents_loaded(snapshot, page, background=background))
            except Exception as exc:
                mapped = map_exception(exc)
                self.after(0, lambda: self._on_documents_error(snapshot, mapped))

        threading.Thread(target=worker, daemon=True).start()

    def _on_documents_loaded(self, snapshot, page, *, background: bool):
        if self._is_closing:
            return
        if not self._docs_requests.complete(snapshot):
            return
        if self.docs_loading_after_id is not None:
            self.after_cancel(self.docs_loading_after_id)
            self.docs_loading_after_id = None
        self.docs_page_total = page.total_count
        self.docs_page_cached_at = page.cached_at
        if not page.items and page.total_count > 0 and self.docs_page_index > 0:
            self.docs_page_index = max(0, self.docs_page_index - 1)
            self._schedule_state_save()
            self._load_documents_screen(force_refresh=True)
            return
        if page.items:
            self._set_docs_state(Success(page.items))
            self._refresh_docs(page.items)
            self._update_onboarding_visibility()
            self._set_activity("documents", status_key="status_done")
            self.analytics.track("action_outcome", screen="manage_documents", action="load_documents", outcome="success")
            if self.docs_time_to_value is not None:
                self.docs_time_to_value.stop(state="success")
            return
        self._set_docs_state(Empty(title=self.tr("documents_empty_title"), message=self.tr("documents_empty_body")))
        self._refresh_docs([])
        self._update_onboarding_visibility()
        self.analytics.track("action_outcome", screen="manage_documents", action="load_documents", outcome="empty")
        if self.docs_time_to_value is not None:
            self.docs_time_to_value.stop(state="empty")
        if background:
            self.toast.show(self.tr("docs_status_fresh"))

    def _on_documents_error(self, snapshot, mapped):
        if self._is_closing:
            return
        if not self._docs_requests.complete(snapshot):
            return
        if self.docs_loading_after_id is not None:
            self.after_cancel(self.docs_loading_after_id)
            self.docs_loading_after_id = None
        self._set_docs_state(Error(to_ui_error(mapped)))
        self.docs_freshness_var.set(self.tr("docs_status_stale"))
        self._set_activity("documents", status_key="status_error")
        self.analytics.track("api_error", screen="manage_documents", category=mapped.code, detail=mapped.debug_message)
        self.analytics.track("action_outcome", screen="manage_documents", action="load_documents", outcome="failure")
        if self.docs_time_to_value is not None:
            self.docs_time_to_value.stop(state="error")

    def _set_docs_state(self, state):
        self.docs_state.set_state(state)
        self._render_docs_state()

    def _render_docs_state(self):
        state = self.docs_state.state
        if (
            isinstance(state, Success)
            and hasattr(self, "docs_list")
            and self.docs_list.winfo_exists()
            and self.docs_list.master.winfo_exists()
        ):
            self.docs_list.delete(0, tk.END)
            for doc in state.data:
                prefix = "★" if doc.is_favorite else " "
                self.docs_list.insert(tk.END, f"{prefix} {doc.title}  [{doc.source}]")
            self._sync_favorite_button()
            return
        for child in self.docs_state_host.winfo_children():
            child.destroy()
        if isinstance(state, Loading):
            SkeletonList(self.docs_state_host, rows=8).grid(row=0, column=0, sticky="nsew")
            return
        if isinstance(state, Empty):
            EmptyState(self.docs_state_host, title=state.title, message=state.message).grid(
                row=0, column=0, sticky="nsew"
            )
            return
        if isinstance(state, Error):
            ErrorState(
                self.docs_state_host,
                title=state.error.title,
                message=state.error.message,
                action_text=state.error.recovery_action,
                on_action=self._retry_load_documents,
            ).grid(row=0, column=0, sticky="nsew")
            return
        if isinstance(state, Success):
            row = ttk.Frame(self.docs_state_host)
            row.grid(row=0, column=0, sticky="nsew")
            row.grid_columnconfigure(0, weight=1)
            row.grid_rowconfigure(0, weight=1)
            self.docs_list = tk.Listbox(row, activestyle="none")
            self.docs_list.grid(row=0, column=0, sticky="nsew")
            scrollbar = ttk.Scrollbar(row, orient="vertical", command=self.docs_list.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            self.docs_list.config(yscrollcommand=scrollbar.set)
            for doc in state.data:
                prefix = "★" if doc.is_favorite else " "
                self.docs_list.insert(tk.END, f"{prefix} {doc.title}  [{doc.source}]")
            self.docs_list.bind("<<ListboxSelect>>", lambda _event: self._sync_favorite_button())
            self.docs_list.bind("<Delete>", lambda _event: self._delete_selected(), add=True)
            self._sync_favorite_button()
            return
        EmptyState(
            self.docs_state_host,
            title=self.tr("documents_unavailable_title"),
            message=self.tr("documents_unavailable_body"),
        ).grid(row=0, column=0, sticky="nsew")

    def _sync_favorite_button(self):
        if not hasattr(self, "docs_list") or not self.docs_list.winfo_exists():
            self.docs_favorite_btn.configure(text="☆")
            self._sync_docs_action_state()
            return
        sel = self.docs_list.curselection()
        if not sel:
            self.docs_favorite_btn.configure(text="☆")
            self._sync_docs_action_state()
            return
        docs = self.docs_state.state.data if isinstance(self.docs_state.state, Success) else []
        selected_doc = docs[sel[0]] if sel[0] < len(docs) else None
        if selected_doc is None:
            self.docs_favorite_btn.configure(text="☆")
            self._sync_docs_action_state()
            return
        self.docs_favorite_btn.configure(text="★" if selected_doc.is_favorite else "☆")
        self._sync_docs_action_state()

    def _retry_load_documents(self):
        self.analytics.track("retry", screen="manage_documents", action="retry_load")
        self.analytics.track("primary_action_tap", screen="manage_documents", action="retry_load")
        self._load_documents_screen(force_refresh=True)

    def _toggle_selected_favorite(self):
        if not isinstance(self.docs_state.state, Success):
            return
        if not hasattr(self, "docs_list") or not self.docs_list.winfo_exists():
            return
        sel = self.docs_list.curselection()
        if not sel:
            self.toast.show(self.tr("documents_select_first"))
            return
        index = sel[0]
        docs = list(self.docs_state.state.data)
        if index >= len(docs):
            return
        now = time.monotonic()
        self._docs_recent_taps = [ts for ts in self._docs_recent_taps if now - ts < 1.5]
        self._docs_recent_taps.append(now)
        if len(self._docs_recent_taps) >= 4:
            self.analytics.track("action_tap", screen="manage_documents", action="rapid_tap")
        self.analytics.track("primary_action_tap", screen="manage_documents", action="favorite_toggle")
        docs_after_toggle, previous_item = apply_optimistic_favorite(docs, index)
        toggled_item = docs_after_toggle[index]
        self.docs_repo.set_cache(docs_after_toggle, total_count=self.docs_page_total or len(docs_after_toggle))
        self._set_docs_state(Success(docs_after_toggle))
        self.docs_list.selection_set(index)
        try:
            self.docs_repo.toggle_favorite(toggled_item.doc_id, toggled_item.is_favorite)
            self.analytics.track("action_outcome", screen="manage_documents", action="favorite_toggle", outcome="success")

            def undo():
                if not isinstance(self.docs_state.state, Success):
                    return
                current_docs = list(self.docs_state.state.data)
                if index >= len(current_docs):
                    return
                current_docs[index] = previous_item
                self.docs_repo.set_cache(current_docs, total_count=self.docs_page_total or len(current_docs))
                self.docs_repo.toggle_favorite(previous_item.doc_id, previous_item.is_favorite)
                self._set_docs_state(Success(current_docs))
                self.toast.show("Favorite undone.")
                self.analytics.track("action_tap", screen="manage_documents", action="favorite_undo")

            self._last_favorite_undo = undo
            self.toast.show("Favorite updated.", action_text="Undo", action_callback=undo)
            self._set_activity("favorite", status_key="status_done")
        except Exception as exc:
            mapped = map_exception(exc)
            docs_after_toggle[index] = previous_item
            self.docs_repo.set_cache(docs_after_toggle, total_count=self.docs_page_total or len(docs_after_toggle))
            self._set_docs_state(Success(docs_after_toggle))
            self.docs_list.selection_set(index)
            self.toast.show("Could not update favorite. Reverted.")
            self.analytics.track(
                "api_error",
                screen="manage_documents",
                category=mapped.code,
                detail=mapped.debug_message,
            )
            self.analytics.track("action_outcome", screen="manage_documents", action="favorite_toggle", outcome="failure")
            self._set_activity("favorite", status_key="status_error")

    def _llm_status_value(self) -> str:
        model_path = self._effective_llm_model_path()
        if model_path.exists():
            return str(model_path)
        return self.tr("model_not_set")

    def _update_docs_pager(self):
        total_pages = max(1, math.ceil(max(0, self.docs_page_total) / DOCS_PAGE_SIZE))
        current_page = min(self.docs_page_index + 1, total_pages)
        self.docs_page_var.set(self.tr("pager_label", current=current_page, total=total_pages))
        self.docs_prev_btn.configure(state="normal" if self.docs_page_index > 0 else "disabled")
        self.docs_next_btn.configure(state="normal" if current_page < total_pages else "disabled")
        if self.docs_page_cached_at:
            age_sec = max(0, int(time.time() - self.docs_page_cached_at))
            if age_sec <= 10:
                self.docs_freshness_var.set(self.tr("docs_status_fresh"))
            else:
                self.docs_freshness_var.set(self.tr("docs_status_cached", age=age_sec))
        else:
            self.docs_freshness_var.set(self.tr("docs_status_loading"))

    def _update_onboarding_visibility(self):
        if not hasattr(self, "search_onboarding"):
            return
        should_show = (not self.onboarding_dismissed) and self.docs_page_total == 0
        if should_show:
            self.search_onboarding.grid()
        else:
            self.search_onboarding.grid_remove()

    def _dismiss_onboarding(self):
        self.onboarding_dismissed = True
        self._update_onboarding_visibility()
        self._schedule_state_save()

    def _resume_draft(self):
        if self.notebook is not None:
            self.notebook.select(self.qa_tab)
        self.qa_field.entry.focus_set()

    def _docs_prev_page(self):
        if self.docs_page_index <= 0 or self.docs_mutation_inflight:
            return
        self.docs_page_index -= 1
        self._schedule_state_save()
        self._load_documents_screen(force_refresh=True)

    def _docs_next_page(self):
        if self.docs_mutation_inflight:
            return
        total_pages = max(1, math.ceil(max(0, self.docs_page_total) / DOCS_PAGE_SIZE))
        if (self.docs_page_index + 1) >= total_pages:
            return
        self.docs_page_index += 1
        self._schedule_state_save()
        self._load_documents_screen(force_refresh=True)

    def _set_mutation_busy(self, busy: bool):
        self.docs_mutation_inflight = busy
        state = "disabled" if busy else "normal"
        for widget_name in ("import_btn", "wiki_btn", "delete_btn", "rebuild_btn", "docs_refresh_btn", "docs_prev_btn", "docs_next_btn"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.configure(state=state)
        if hasattr(self, "docs_favorite_btn"):
            self.docs_favorite_btn.configure(state=state)
        if not busy:
            self._refresh_docs(self.docs_repo.get_cached_documents() or [])
        self._sync_docs_action_state()

    def _sync_docs_action_state(self):
        if self.docs_mutation_inflight:
            return
        has_selection = False
        if hasattr(self, "docs_list") and self.docs_list.winfo_exists():
            has_selection = bool(self.docs_list.curselection())
        if hasattr(self, "delete_btn"):
            self.delete_btn.configure(state="normal" if has_selection else "disabled")
        if hasattr(self, "docs_favorite_btn"):
            self.docs_favorite_btn.configure(state="normal" if has_selection else "disabled")

    def _effective_llm_model_path(self) -> Path:
        configured = Path(self.cfg.get("llm_model_path") or "")
        if configured.exists():
            return configured
        return model_manager.default_model_path(MODELS_DIR)

    def _schedule_state_save(self):
        if self._is_closing:
            return
        if hasattr(self, "_state_save_after_id") and self._state_save_after_id is not None:
            self.after_cancel(self._state_save_after_id)
        self._state_save_after_id = self.after(250, self._save_runtime_state)

    def _save_runtime_state(self):
        self._state_save_after_id = None
        if self.notebook is not None:
            selected = self.notebook.select()
            if selected == str(self.search_tab):
                selected_tab = "search"
            elif selected == str(self.qa_tab):
                selected_tab = "qa"
            elif selected == str(self.manage_tab):
                selected_tab = "manage"
            else:
                selected_tab = "utils"
        else:
            selected_tab = "search"
        state = AppState(
            qa_draft=self.qa_var.get().strip() if hasattr(self, "qa_var") else "",
            selected_tab=selected_tab,
            docs_page=self.docs_page_index,
            onboarding_dismissed=self.onboarding_dismissed,
        )
        save_state(APP_STATE_PATH, state)

    def _restore_last_tab(self):
        if self.notebook is None:
            return
        if self.app_state.selected_tab == "qa":
            self.notebook.select(self.qa_tab)
        elif self.app_state.selected_tab == "manage":
            self.notebook.select(self.manage_tab)
        elif self.app_state.selected_tab == "utils":
            self.notebook.select(self.utils_tab)
        else:
            self.notebook.select(self.search_tab)

    def _present_user_error(self, *, screen: str, action: str, exc: Exception) -> None:
        mapped = map_exception(exc)
        ui_error = to_ui_error(mapped)
        messagebox.showerror(ui_error.title, ui_error.message)
        self._set_activity(action, status_key="status_error")
        self.analytics.track("api_error", screen=screen, category=mapped.code, detail=mapped.debug_message)
        self.analytics.track("action_outcome", screen=screen, action=action, outcome="failure")

    def _run_blocking_task(
        self,
        *,
        screen: str,
        action: str,
        work_fn,
        on_success,
        busy_message: str,
    ) -> None:
        self._set_mutation_busy(True)
        self._set_activity(busy_message, status_key="status_busy")

        def worker():
            try:
                result = work_fn()
                self.after(0, lambda: finish(result, None))
            except Exception as exc:
                self.after(0, lambda: finish(None, exc))

        def finish(result, err):
            if self._is_closing:
                return
            self._set_mutation_busy(False)
            if err is not None:
                self._present_user_error(screen=screen, action=action, exc=err)
                self._refresh_docs(self.docs_repo.get_cached_documents() or [])
                self._set_activity(action, status_key="status_error")
                return
            self.analytics.track("action_outcome", screen=screen, action=action, outcome="success")
            self._set_activity(action, status_key="status_done")
            on_success(result)

        threading.Thread(target=worker, daemon=True).start()

    def _mark_milestone(self, key: str):
        cfg_key = f"milestone_{key}"
        if self.cfg.get(cfg_key) == "true":
            return
        self.cfg[cfg_key] = "true"
        config.save_config(CONFIG_PATH, self.cfg)
        self.analytics.track("action_tap", screen="app", action="satisfaction_milestone", milestone=key)

    def _import_file(self):
        self.analytics.track("primary_action_tap", screen="manage_documents", action="import_text")
        if self.docs_mutation_inflight:
            self.toast.show(self.tr("action_wait_current"))
            return
        path = filedialog.askopenfilename(
            title=self.tr("select_text_file"), filetypes=[("Text", "*.txt")]
        )
        if not path:
            return
        path = Path(path)
        def work():
            USER_DIR.mkdir(parents=True, exist_ok=True)
            dest = USER_DIR / path.name
            shutil.copy2(path, dest)
            kb.ingest_text_file(DB_PATH, dest, "user")
            return dest.name

        def on_success(file_name: str):
            messagebox.showinfo(self.tr("imported_title"), self.tr("imported_msg", name=file_name))
            self.onboarding_dismissed = True
            self._schedule_state_save()
            self._mark_milestone("first_import")
            self._load_documents_screen(force_refresh=True)

        self._run_blocking_task(
            screen="manage_documents",
            action="import_text",
            work_fn=work,
            on_success=on_success,
            busy_message="Importing document...",
        )

    def _import_wikipedia(self):
        self.analytics.track("action_tap", screen="manage_documents", action="import_wikipedia")
        if self.docs_mutation_inflight:
            self.toast.show(self.tr("action_wait_current"))
            return
        if not can_access_feature(cfg=self.cfg, feature_key="online_import"):
            messagebox.showerror("Unavailable", "This feature is not available for your current plan.")
            return
        if self.cfg.get("online_sources_enabled", "false") != "true":
            messagebox.showerror(self.tr("online_disabled_title"), self.tr("online_disabled_msg"))
            return
        query = simpledialog.askstring(
            self.tr("wikipedia_query_title"),
            self.tr("wikipedia_query_prompt"),
            parent=self,
        )
        if not query or not query.strip():
            return
        limit = simpledialog.askinteger(
            self.tr("wikipedia_query_title"),
            self.tr("wikipedia_limit_prompt"),
            parent=self,
            initialvalue=3,
            minvalue=1,
            maxvalue=20,
        )
        if limit is None:
            return
        language = (self.cfg.get("wikipedia_language") or "en").strip() or "en"
        try:
            timeout_sec = int(self.cfg.get("online_timeout_sec") or 20)
        except ValueError:
            timeout_sec = 20
        user_agent = self.cfg.get("online_user_agent") or "Fonte/1.0 (+local-app)"
        def work():
            inserted, titles = mediawiki_api.ingest_query(
                DB_PATH,
                query.strip(),
                limit=int(limit),
                language=language,
                source="wikipedia",
                timeout_sec=max(1, timeout_sec),
                user_agent=user_agent,
            )
            return inserted, titles

        def on_success(result):
            inserted, titles = result
            title_preview = ", ".join(titles[:3]) if titles else "-"
            messagebox.showinfo(
                self.tr("wikipedia_imported_title"),
                self.tr("wikipedia_imported_msg", count=inserted, titles=title_preview),
            )
            self.onboarding_dismissed = True
            self._schedule_state_save()
            self._mark_milestone("first_import")
            self._load_documents_screen(force_refresh=True)

        self._run_blocking_task(
            screen="manage_documents",
            action="import_wikipedia",
            work_fn=work,
            on_success=on_success,
            busy_message="Importing from Wikipedia...",
        )

    def _delete_selected(self):
        if self.docs_mutation_inflight:
            self.toast.show(self.tr("action_wait_current"))
            return
        if not isinstance(self.docs_state.state, Success):
            return
        if not hasattr(self, "docs_list") or not self.docs_list.winfo_exists():
            return
        sel = self.docs_list.curselection()
        if not sel:
            self.toast.show(self.tr("documents_select_first"))
            return
        index = sel[0]
        docs = self.docs_state.state.data
        if index >= len(docs):
            return
        doc_id = docs[index].doc_id
        self.analytics.track("action_tap", screen="manage_documents", action="delete_document")
        self._set_mutation_busy(True)
        try:
            kb.delete_document(DB_PATH, doc_id)
        except Exception as exc:
            self._present_user_error(screen="manage_documents", action="delete_document", exc=exc)
            return
        finally:
            self._set_mutation_busy(False)
        self.analytics.track("action_outcome", screen="manage_documents", action="delete_document", outcome="success")
        self._set_activity("delete document", status_key="status_done")
        self._load_documents_screen(force_refresh=True)

    def _rebuild_index(self):
        if self.docs_mutation_inflight:
            self.toast.show(self.tr("action_wait_current"))
            return
        self.analytics.track("action_tap", screen="manage_documents", action="rebuild_index")
        def work():
            kb.rebuild_from_folder(DB_PATH, SAMPLE_DIR, "sample")
            for path in sorted(USER_DIR.glob("*.txt")):
                kb.ingest_text_file(DB_PATH, path, "user")

        def on_success(_result):
            self._load_documents_screen(force_refresh=True)

        self._run_blocking_task(
            screen="manage_documents",
            action="rebuild_index",
            work_fn=work,
            on_success=on_success,
            busy_message="Rebuilding index...",
        )

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
            self.analytics.track("action_outcome", screen="manage_documents", action="rebuild_vector_index", outcome="success")
        except Exception as exc:
            self._present_user_error(screen="manage_documents", action="rebuild_vector_index", exc=exc)

    def _set_embedding_model(self):
        path = filedialog.askdirectory(title=self.tr("select_embedding_dir"))
        if not path:
            return
        self.cfg["embedding_model_path"] = path
        config.save_config(CONFIG_PATH, self.cfg)
        self._refresh_docs(self.docs_repo.get_cached_documents() or [])

    def _set_llm_model(self):
        path = filedialog.askopenfilename(
            title=self.tr("select_llm_file"), filetypes=[("GGUF", "*.gguf")]
        )
        if not path:
            return
        self.cfg["llm_backend"] = "llama_cpp"
        self.cfg["ai_provider"] = "local"
        self.cfg["llm_model_path"] = path
        config.save_config(CONFIG_PATH, self.cfg)
        self.llm = None
        self._refresh_ai_controls()
        self._set_search_answer_state("ready" if self._llm_ready() else "not_installed")
        self._refresh_docs(self.docs_repo.get_cached_documents() or [])

    def _on_ai_toggle_changed(self):
        self.cfg["ai_answers_enabled"] = "true" if self.ai_answers_var.get() else "false"
        config.save_config(CONFIG_PATH, self.cfg)
        self.llm = None
        self._refresh_ai_controls()
        if self.ai_answers_var.get():
            self._set_search_answer_state("ready" if self._llm_ready() else "not_installed")
        else:
            self._set_search_answer_state("off")
        self._refresh_docs(self.docs_repo.get_cached_documents() or [])

    def _on_ai_provider_changed(self, _event=None):
        self.cfg["ai_provider"] = "local"
        self.cfg["llm_backend"] = "lmstudio"
        self.llm_backend_var.set("lmstudio")
        self.llm = None
        config.save_config(CONFIG_PATH, self.cfg)
        self._refresh_ai_controls()
        self._refresh_docs(self.docs_repo.get_cached_documents() or [])

    def _toggle_advanced_settings(self):
        self._refresh_ai_controls()

    def _refresh_ai_controls(self):
        advanced_open = self.advanced_toggle_var.get() if hasattr(self, "advanced_toggle_var") else False
        ai_enabled = self.ai_answers_var.get() if hasattr(self, "ai_answers_var") else False
        if hasattr(self, "ai_toggle_text_var"):
            self.ai_toggle_text_var.set(self.tr("ai_on") if ai_enabled else self.tr("ai_off"))
        if hasattr(self, "ai_provider_label"):
            if ai_enabled:
                self.ai_provider_label.grid()
            else:
                self.ai_provider_label.grid_remove()
        if hasattr(self, "ai_provider_box"):
            self.ai_provider_box.configure(state="readonly" if ai_enabled else "disabled")
            if ai_enabled:
                self.ai_provider_box.grid()
            else:
                self.ai_provider_box.grid_remove()
        if hasattr(self, "advanced_frame"):
            if advanced_open:
                self.advanced_frame.grid()
            else:
                self.advanced_frame.grid_remove()
        if hasattr(self, "ai_provider_var"):
            self.ai_provider_var.set("Local")
        if hasattr(self, "llm_backend_var"):
            self.llm_backend_var.set("lmstudio")
        if hasattr(self, "ai_settings_cta"):
            cta_text = self.tr("mode_search_only_cta") if self._is_search_only_mode() else self.tr("ai_answers_on_cta")
            self.ai_settings_cta.config(text=cta_text)

    def _save_llm_settings(self):
        self.cfg["llm_backend"] = "lmstudio"
        self.cfg["ai_provider"] = "local"
        try:
            ctx = int(str(self.llm_context_var.get() or "1536").strip())
        except ValueError:
            ctx = 1536
        self.cfg["llm_context_window"] = str(max(512, min(4096, ctx)))
        self.cfg["ai_low_resource_mode"] = "true" if self.low_resource_var.get() else "false"
        self.cfg["lmstudio_base_url"] = str(self.lmstudio_base_url_var.get() or "").strip() or "http://localhost:1234/v1"
        self.cfg["model_small_id"] = str(self.model_small_id_var.get() or "").strip()
        self.cfg["model_large_id"] = str(self.model_large_id_var.get() or "").strip()
        try:
            temperature = float(str(self.temperature_var.get() or "0.2").strip())
        except ValueError:
            temperature = 0.2
        self.cfg["temperature"] = str(max(0.0, min(1.5, temperature)))
        try:
            max_tokens = int(str(self.max_tokens_var.get() or "192").strip())
        except ValueError:
            max_tokens = 192
        self.cfg["max_tokens"] = str(max(16, min(4096, max_tokens)))
        self.cfg["llm_max_tokens"] = self.cfg["max_tokens"]
        try:
            timeout_seconds = int(str(self.timeout_seconds_var.get() or "20").strip())
        except ValueError:
            timeout_seconds = 20
        self.cfg["timeout_seconds"] = str(max(1, min(120, timeout_seconds)))
        config.save_config(CONFIG_PATH, self.cfg)
        self.llm = None
        self._refresh_ai_controls()
        self._set_search_answer_state("ready")
        self._refresh_docs(self.docs_repo.get_cached_documents() or [])

    def _save_online_settings(self):
        self.cfg["online_sources_enabled"] = "true" if self.online_enabled_var.get() else "false"
        try:
            cache_days = int(self.online_cache_days_var.get().strip() or "30")
        except ValueError:
            cache_days = 30
        try:
            timeout_sec = int(self.online_timeout_var.get().strip() or "20")
        except ValueError:
            timeout_sec = 20
        self.cfg["online_cache_days"] = str(max(1, cache_days))
        self.cfg["online_timeout_sec"] = str(max(1, timeout_sec))
        self.cfg["online_user_agent"] = self.online_user_agent_var.get().strip() or "Fonte/1.0 (+local-app)"
        wiki_lang = str(self.wikipedia_language_var.get() or "en").strip().lower()
        if not wiki_lang or len(wiki_lang) > 12 or any(not (c.isalnum() or c == "-") for c in wiki_lang):
            wiki_lang = "en"
        self.cfg["wikipedia_language"] = wiki_lang
        config.save_config(CONFIG_PATH, self.cfg)
        self._refresh_docs(self.docs_repo.get_cached_documents() or [])

    def _apply_profile_defaults(self):
        profile = self.cfg.get("device_profile", "low")
        profile_cfg = PROFILES.get(profile, PROFILES["low"])
        self.cfg.setdefault("retrieval_limit", str(profile_cfg["retrieval_limit"]))
        self.cfg.setdefault("llm_max_tokens", str(profile_cfg["llm_max_tokens"]))
        self.cfg.setdefault("max_tokens", self.cfg.get("llm_max_tokens", "192"))
        self.cfg.setdefault("temperature", "0.2")
        self.cfg.setdefault("timeout_seconds", "20")
        self.cfg.setdefault("lmstudio_base_url", "http://localhost:1234/v1")
        self.cfg.setdefault("model_small_id", "google/gemma-3-1b")
        self.cfg.setdefault("model_large_id", "qwen/qwen3-1.7b")
        self.cfg.setdefault("llm_context_window", "1536")
        self.cfg.setdefault("ai_low_resource_mode", "true")
        config.save_config(CONFIG_PATH, self.cfg)

    def _resolve_ai_backend(self) -> str:
        self.cfg["ai_provider"] = "local"
        self.cfg["llm_backend"] = "lmstudio"
        return "lmstudio"

    def _embedding_ready(self) -> bool:
        embed_path = Path(self.cfg.get("embedding_model_path") or "")
        return embed_path.exists()

    def _llm_ready(self) -> bool:
        backend = str(self.cfg.get("llm_backend", "lmstudio")).strip().lower()
        if backend == "lmstudio":
            return True
        model_path = self._effective_llm_model_path()
        return model_path.exists()

    def _models_ready_for_ai(self) -> bool:
        return self._llm_ready()

    def _ai_answers_user_enabled(self) -> bool:
        return (self.cfg.get("ai_answers_enabled") or "true").strip().lower() == "true"

    def _ai_answers_active(self) -> bool:
        return self._ai_answers_user_enabled() and self._models_ready_for_ai()

    def _is_search_only_mode(self) -> bool:
        return not self._ai_answers_active()

    def _auto_set_search_only_mode(self) -> None:
        if not self._models_ready_for_ai():
            self.cfg["ai_answers_enabled"] = "false"
        self.cfg.setdefault("ai_provider", "local")
        self.cfg["llm_backend"] = self._resolve_ai_backend()
        config.save_config(CONFIG_PATH, self.cfg)

    def _auto_select_llm_model(self) -> bool:
        current = self._effective_llm_model_path()
        if current.exists():
            return False
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        candidates = sorted(MODELS_DIR.rglob("*.gguf"))
        if not candidates:
            return False
        self.cfg["llm_model_path"] = str(candidates[0])
        config.save_config(CONFIG_PATH, self.cfg)
        self.llm = None
        return True

    def _apply_profile(self):
        profile = self.profile_var.get()
        profile_cfg = PROFILES.get(profile, PROFILES["low"])
        self.cfg["device_profile"] = profile
        self.cfg["retrieval_limit"] = str(profile_cfg["retrieval_limit"])
        self.cfg["llm_max_tokens"] = str(profile_cfg["llm_max_tokens"])
        config.save_config(CONFIG_PATH, self.cfg)
        self._refresh_docs(self.docs_repo.get_cached_documents() or [])

    def _toggle_demo(self):
        self.cfg["demo_mode"] = "true" if self.demo_var.get() else "false"
        config.save_config(CONFIG_PATH, self.cfg)
        self._refresh_docs(self.docs_repo.get_cached_documents() or [])

    def _download_model(self):
        self._open_model_manager()

    def _open_model_manager(self):
        if hasattr(self, "_model_wizard") and self._model_wizard is not None:
            try:
                self._model_wizard.lift()
                self._model_wizard.focus_force()
                return
            except tk.TclError:
                self._model_wizard = None
        wizard = tk.Toplevel(self)
        self._model_wizard = wizard
        wizard.title(self.tr("ai_download_wizard_title"))
        wizard.geometry("520x230")
        wizard.resizable(False, False)
        wizard.transient(self)
        wizard.grab_set()

        container = ttk.Frame(wizard, padding=14)
        container.grid(row=0, column=0, sticky="nsew")
        wizard.grid_columnconfigure(0, weight=1)
        wizard.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        ttk.Label(container, text=self.tr("ai_download_wizard_title"), style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(container, text=self.tr("ai_download_wizard_body"), wraplength=490).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        size_text = model_manager.format_size(model_manager.DEFAULT_MODEL_SIZE_BYTES)
        ttk.Label(container, text=f"Model: {model_manager.DEFAULT_MODEL_FILENAME} ({size_text})", style="Subtle.TLabel").grid(
            row=2, column=0, sticky="w", pady=(4, 0)
        )
        progress_var = tk.StringVar(value="")
        progress_label = ttk.Label(container, textvariable=progress_var, style="Subtle.TLabel")
        progress_label.grid(row=3, column=0, sticky="w", pady=(10, 0))
        progress = ttk.Progressbar(container, mode="determinate")
        progress.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        button_row = ttk.Frame(container)
        button_row.grid(row=5, column=0, sticky="e", pady=(12, 0))
        install_btn = PrimaryButton(button_row, text=self.tr("download_ai_model"), command=lambda: None)
        install_btn.pack(side="left")
        cancel_btn = SecondaryButton(button_row, text=self.tr("cancel_action"), command=lambda: None)
        cancel_btn.pack(side="left", padx=(8, 0))

        def close_wizard():
            if self.model_download_inflight and self.model_download_cancel_event is not None:
                self.model_download_cancel_event.set()
            try:
                wizard.grab_release()
            except tk.TclError:
                pass
            wizard.destroy()
            self._model_wizard = None

        wizard.protocol("WM_DELETE_WINDOW", close_wizard)

        def start_download():
            install_btn.configure(state="disabled")
            self._start_model_download(
                on_progress=lambda done, total, speed: self._on_model_download_progress(
                    done,
                    total,
                    speed,
                    progress_widget=progress,
                    progress_var=progress_var,
                ),
                on_done=lambda ok, msg: self._on_model_download_done(
                    ok,
                    msg,
                    close_wizard=close_wizard,
                    install_btn=install_btn,
                    progress_var=progress_var,
                ),
            )

        install_btn.configure(command=start_download)
        cancel_btn.configure(command=close_wizard)

    def _on_model_download_progress(self, done: int, total: int, speed: float, *, progress_widget, progress_var) -> None:
        eta = model_manager.estimate_time_remaining(done, total, speed)
        percent = int((done / total) * 100) if total > 0 else 0
        progress_widget.configure(value=max(0, min(100, percent)))
        progress_var.set(
            self.tr(
                "ai_download_progress",
                done=model_manager.format_size(done),
                total=model_manager.format_size(total) if total > 0 else "?",
                eta=eta,
            )
        )
        self._set_search_answer_state("downloading", done=done, total=total, eta=eta)

    def _on_model_download_done(self, ok: bool, message: str, *, close_wizard, install_btn, progress_var) -> None:
        install_btn.configure(state="normal")
        progress_var.set(message)
        if ok:
            self.toast.show(self.tr("ai_download_complete"))
            close_wizard()
        else:
            self.toast.show(message)

    def _start_model_download(self, *, on_progress, on_done) -> None:
        if self.model_download_inflight:
            return
        self.model_download_inflight = True
        self.model_download_cancel_event = threading.Event()
        self._set_search_answer_state("downloading", done=0, total=model_manager.DEFAULT_MODEL_SIZE_BYTES, eta="estimating...")
        self._set_activity(self.tr("download_ai_model"), status_key="status_busy")

        def worker():
            try:
                dest = model_manager.download_model(
                    url=model_manager.DEFAULT_MODEL_URL,
                    dest_path=model_manager.default_model_path(MODELS_DIR),
                    expected_sha256=model_manager.DEFAULT_MODEL_SHA256,
                    cancel_event=self.model_download_cancel_event,
                    progress_callback=lambda done, total, speed: self.after(
                        0, lambda: on_progress(done, total, speed)
                    ),
                )
                self.after(0, lambda: finish(True, self.tr("ai_download_complete"), str(dest)))
            except model_manager.ModelDownloadCancelled:
                self.after(0, lambda: finish(False, self.tr("ai_download_cancelled"), ""))
            except Exception as exc:
                _report_ui_exception(exc)
                self.after(0, lambda: finish(False, self.tr("ai_install_failed"), ""))

        def finish(ok: bool, message: str, model_path: str):
            self.model_download_inflight = False
            if ok:
                if model_path:
                    self.cfg["llm_model_path"] = model_path
                self.cfg["ai_answers_enabled"] = "true"
                self.cfg["ai_provider"] = "local"
                config.save_config(CONFIG_PATH, self.cfg)
                self.llm = None
                self._set_search_answer_state("ready")
                self._refresh_docs(self.docs_repo.get_cached_documents() or [])
                self._set_activity(self.tr("download_ai_model"), status_key="status_done")
            else:
                if message == self.tr("ai_download_cancelled"):
                    self._set_search_answer_state("not_installed")
                else:
                    self._set_search_answer_state("error", text=message)
                self._set_activity(self.tr("download_ai_model"), status_key="status_error")
            on_done(ok, message)

        threading.Thread(target=worker, daemon=True).start()

    def _run_demo(self):
        self.search_var.set("Solar System")
        self._do_search()
        self.qa_var.set("Which planets are in the Solar System?")
        self.onboarding_dismissed = True
        self._update_onboarding_visibility()
        self._schedule_state_save()
        self._on_qa_submit()

    def _maybe_show_splash(self):
        if self.cfg.get("demo_mode") != "true":
            return
        if self.reduced_motion:
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
        status_row = ttk.Frame(self, padding=(SPACE_2, 4))
        status_row.grid(row=1, column=0, sticky="ew")
        status_row.grid_columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_row, textvariable=self.status_var, anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.status_progress = ttk.Progressbar(status_row, mode="indeterminate", length=120)
        self.status_progress.grid(row=0, column=1, sticky="e", padx=(SPACE_1, 0))
        self.status_progress.grid_remove()

    def _update_status_bar(self, size_mb: float, doc_count: int, profile: str, embed_path: str, llm_path: str):
        self._status_snapshot = {
            "size_mb": size_mb,
            "doc_count": doc_count,
            "profile": profile,
            "embed_path": embed_path,
            "llm_path": llm_path,
        }
        self._update_status_bar_from_snapshot()

    def _update_status_bar_from_snapshot(self):
        if not self._status_snapshot:
            return
        doc_count = int(self._status_snapshot["doc_count"])
        profile = str(self._status_snapshot["profile"])
        language_name = self._language_display_name(self.ui_language)
        if self._is_search_only_mode():
            self.status_var.set(
                self.tr(
                    "status_bar_search_only",
                    count=doc_count,
                    language=language_name,
                )
            )
            return
        self.status_var.set(
            self.tr(
                "status_bar",
                count=doc_count,
                profile=profile,
                language=language_name,
            )
        )

    def _set_activity(self, activity: str, *, status_key: str = "status_busy", transient_ms: int = 2200):
        if hasattr(self, "_status_after_id") and self._status_after_id is not None:
            self.after_cancel(self._status_after_id)
            self._status_after_id = None
        if status_key == "status_busy":
            self.status_var.set(self.tr("status_busy", activity=activity))
            if hasattr(self, "status_progress"):
                self.status_progress.grid()
                self.status_progress.start(12)
            return
        if hasattr(self, "status_progress"):
            self.status_progress.stop()
            self.status_progress.grid_remove()
        self.status_var.set(self.tr(status_key, activity=activity))
        self._status_after_id = self.after(transient_ms, self._update_status_bar_from_snapshot)

    def _set_runtime_bootstrap_status(self, message: str, *, busy: bool = True) -> None:
        if self._is_closing or not hasattr(self, "status_var"):
            return
        if busy:
            self.status_var.set(message)
            if hasattr(self, "status_progress"):
                self.status_progress.grid()
                self.status_progress.start(12)
            return
        if hasattr(self, "status_progress"):
            self.status_progress.stop()
            self.status_progress.grid_remove()
        self.status_var.set(message)

    def _on_runtime_bootstrap_success(self) -> None:
        if self._is_closing:
            return
        if hasattr(self, "status_progress"):
            self.status_progress.stop()
            self.status_progress.grid_remove()
        self._update_status_bar_from_snapshot()

    def _on_runtime_bootstrap_failure(self) -> None:
        if self._is_closing:
            return
        self._set_runtime_bootstrap_status("AI runtime failed to initialize", busy=False)
        if hasattr(self, "answer_status_var"):
            self.answer_status_var.set("AI runtime failed to initialize")

    def _start_runtime_bootstrap(self) -> None:
        if self._runtime_bootstrap_started:
            return
        self._runtime_bootstrap_started = True
        self._set_runtime_bootstrap_status("Initializing AI runtime...", busy=True)

        def publish(message: str) -> None:
            self.after(0, lambda msg=message: self._set_runtime_bootstrap_status(msg, busy=True))

        def worker() -> None:
            try:
                runtime.bootstrap_runtime(status_callback=publish)
            except Exception as exc:
                self._runtime_bootstrap_failed = True
                debug(f"runtime bootstrap failed: {exc}")
                self.after(0, self._on_runtime_bootstrap_failure)
                return
            self.after(0, self._on_runtime_bootstrap_success)

        threading.Thread(target=worker, daemon=True).start()

    def _language_display_name(self, code: str) -> str:
        key = f"lang_{code}"
        return self.tr(key) if key in I18N.get(self.ui_language, {}) else code

    def _focus_search_input(self):
        if hasattr(self, "search_entry") and self.search_entry.winfo_exists():
            self.search_entry.focus_set()

    def _focus_primary_input(self):
        if self.notebook is None:
            return
        selected = self.notebook.select()
        if selected == str(self.search_tab):
            self._focus_search_input()
            return
        if selected == str(self.qa_tab) and hasattr(self, "qa_field") and self.qa_field.entry.winfo_exists():
            self.qa_field.entry.focus_set()

    def _on_tab_changed(self, _event):
        if self.notebook is None:
            return
        selected = self.notebook.select()
        self._schedule_state_save()
        if selected != str(self.qa_tab):
            self._qa_requests.cancel()
            if self.qa_loading_after_id is not None:
                self.after_cancel(self.qa_loading_after_id)
                self.qa_loading_after_id = None
            self._sync_qa_submit_state()
        if selected != str(self.manage_tab):
            self._docs_requests.cancel()
        if selected == str(self.manage_tab):
            self.analytics.track("screen_view", screen="manage_documents")
            if isinstance(self.docs_state.state, Empty) and not self.docs_repo.get_cached_documents():
                self._load_documents_screen(force_refresh=True)
        elif selected == str(self.qa_tab):
            self.analytics.track("screen_view", screen="qa")
        elif selected == str(self.search_tab):
            self.analytics.track("screen_view", screen="search")
        self.after(10, self._focus_primary_input)

    def _prefetch_background(self):
        if self._is_closing:
            return
        # Warm lightweight caches/config lookups without blocking initial render.
        self.docs_repo.get_cached_documents()
        self.analytics.track(
            "action_tap",
            screen="app",
            action="feature_hooks",
            push=self.feature_flags.push_notifications_hook,
            deep_link=self.feature_flags.deep_linking_hook,
            referrals=self.feature_flags.referral_hook,
            ab_testing=self.feature_flags.ab_testing_hook,
            premium=self.feature_flags.premium_gating_hook,
        )
        self.analytics.track("action_tap", screen="app", action="prefetch_complete")

    def _on_close(self):
        self._is_closing = True
        if self.model_download_cancel_event is not None:
            self.model_download_cancel_event.set()
        if self.search_answer_cancel_event is not None:
            self.search_answer_cancel_event.set()
        if self._state_save_after_id is not None:
            self.after_cancel(self._state_save_after_id)
            self._state_save_after_id = None
        self._save_runtime_state()
        self._docs_requests.cancel()
        self._qa_requests.cancel()
        if self.docs_loading_after_id is not None:
            self.after_cancel(self.docs_loading_after_id)
            self.docs_loading_after_id = None
        if self.qa_loading_after_id is not None:
            self.after_cancel(self.qa_loading_after_id)
            self.qa_loading_after_id = None
        if self._status_after_id is not None:
            self.after_cancel(self._status_after_id)
            self._status_after_id = None
        if self.docs_time_to_value is not None:
            self.docs_time_to_value.cancel()
        if self.qa_time_to_value is not None:
            self.qa_time_to_value.cancel()
        self._shutdown_llm()
        self.destroy()

    def _build_menubar(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label=self.tr("menu_import"), command=self._import_file)
        file_import_idx = file_menu.index("end")
        file_menu.add_separator()
        file_menu.add_command(label=self.tr("menu_exit"), command=self._on_close)
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

    def _open_ai_setup(self):
        self._open_manage_tab()
        if hasattr(self, "advanced_toggle_var") and hasattr(self, "advanced_frame"):
            self.advanced_toggle_var.set(True)
            self._refresh_ai_controls()

    def _show_about(self):
        messagebox.showinfo(self.tr("menu_about"), self.tr("about_text"))


if __name__ == "__main__":
    atexit.register(runtime.shutdown_runtime)
    if os.getenv("FONTE_TRANSLATE_EXAMPLE") == "1":
        translated = translate("hello world", "en", "pt")
        debug(f"offline translation example: {translated}")
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
