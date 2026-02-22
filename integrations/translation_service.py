"""Local offline translation microservice for Fonte.

Run:
    python -m integrations.translation_service

The service binds to 127.0.0.1:8765 and exposes:
- GET /health
- POST /translate
- POST /translate_batch
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any


HOST = "127.0.0.1"
PORT = 8765
MAX_BODY_BYTES = 1_000_000

LANG_EN = "en"
LANG_DE = "de"
LANG_PT = "pt"
LANG_PT_BR = "pt_BR"
LANG_ES = "es"

LANG_ALIASES = {
    "en": LANG_EN,
    "eng": LANG_EN,
    "english": LANG_EN,
    "de": LANG_DE,
    "deu": LANG_DE,
    "ger": LANG_DE,
    "german": LANG_DE,
    "pt": LANG_PT,
    "por": LANG_PT,
    "pt_pt": LANG_PT,
    "pt-br": LANG_PT_BR,
    "pt_br": LANG_PT_BR,
    "ptbr": LANG_PT_BR,
    "portuguese": LANG_PT,
    "portuguese_br": LANG_PT_BR,
    "es": LANG_ES,
    "spa": LANG_ES,
    "spanish": LANG_ES,
    "auto": "auto",
}

APERTIUM_CODE_ALIASES = {
    LANG_EN: ("eng", "en"),
    LANG_DE: ("deu", "de", "ger"),
    LANG_PT: ("pt", "por"),
    LANG_PT_BR: ("pt_BR", "pt-br", "ptbr", "por_BR"),
    LANG_ES: ("spa", "es"),
}

WORD_TOKEN_RE = re.compile(r"\w+|\s+|[^\w\s]", re.UNICODE)

CONCEPTS = {
    "hello": {LANG_EN: "hello", LANG_DE: "hallo", LANG_PT: "olá", LANG_PT_BR: "olá"},
    "world": {LANG_EN: "world", LANG_DE: "welt", LANG_PT: "mundo", LANG_PT_BR: "mundo"},
    "good": {LANG_EN: "good", LANG_DE: "gut", LANG_PT: "bom", LANG_PT_BR: "bom"},
    "morning": {LANG_EN: "morning", LANG_DE: "morgen", LANG_PT: "manhã", LANG_PT_BR: "manhã"},
    "night": {LANG_EN: "night", LANG_DE: "nacht", LANG_PT: "noite", LANG_PT_BR: "noite"},
    "yes": {LANG_EN: "yes", LANG_DE: "ja", LANG_PT: "sim", LANG_PT_BR: "sim"},
    "no": {LANG_EN: "no", LANG_DE: "nein", LANG_PT: "não", LANG_PT_BR: "não"},
    "please": {LANG_EN: "please", LANG_DE: "bitte", LANG_PT: "por favor", LANG_PT_BR: "por favor"},
    "thanks": {LANG_EN: "thanks", LANG_DE: "danke", LANG_PT: "obrigado", LANG_PT_BR: "obrigado"},
    "water": {LANG_EN: "water", LANG_DE: "wasser", LANG_PT: "água", LANG_PT_BR: "água"},
    "help": {LANG_EN: "help", LANG_DE: "hilfe", LANG_PT: "ajuda", LANG_PT_BR: "ajuda"},
}


def _normalize_lang(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip().replace("-", "_").lower()
    return LANG_ALIASES.get(key)


def _preserve_case(source: str, target: str) -> str:
    if source.isupper():
        return target.upper()
    if source.istitle():
        return target[:1].upper() + target[1:]
    return target


def _looks_like_word(token: str) -> bool:
    return any(ch.isalpha() for ch in token)


def _build_word_map() -> dict[str, dict[str, str]]:
    table: dict[str, dict[str, str]] = {LANG_EN: {}, LANG_DE: {}, LANG_PT: {}, LANG_PT_BR: {}}
    for forms in CONCEPTS.values():
        for source_lang, source_word in forms.items():
            if source_lang not in table:
                continue
            source_key = source_word.lower()
            for target_lang, target_word in forms.items():
                if source_lang == target_lang:
                    continue
                table[source_lang][f"{source_key}|{target_lang}"] = target_word
    return table


class TranslationEngine:
    """Offline translation pipeline with cached resources and robust fallbacks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._word_map = _build_word_map()
        self._dictionaries = self._load_dictionaries()
        self._apertium_modes = self._load_apertium_modes()
        self._argos = self._load_argos()
        self._argos_cache: dict[tuple[str, str], Any] = {}

    def _load_dictionaries(self) -> dict[str, set[str]]:
        base = Path(__file__).resolve().parent.parent
        files = {
            LANG_EN: base / "english_dictionary.txt",
            LANG_DE: base / "german_dictionary.txt",
            LANG_PT: base / "portuguese_dictionary.txt",
            LANG_PT_BR: base / "portuguese_br_dictionary.txt",
        }
        out = {LANG_EN: set(), LANG_DE: set(), LANG_PT: set(), LANG_PT_BR: set()}

        for lang, path in files.items():
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for raw in handle:
                        line = raw.strip()
                        if not line:
                            continue
                        if line.startswith("=") or line.lower().startswith("format:"):
                            continue
                        if line.startswith("- ") and "|" in line:
                            word = line[2:].split("|", 1)[0].strip()
                            if word:
                                out[lang].add(word.lower())
                            continue
                        if "|" in line:
                            word = line.split("|", 1)[0].strip(" -")
                            if word:
                                out[lang].add(word.lower())
                            continue
                        if line[0].isalpha() or line[0] in "áàâãäçéêëíîïóôõöúüñß":
                            out[lang].add(line.lower())
            except OSError:
                continue

        if not out[LANG_PT_BR]:
            out[LANG_PT_BR] = set(out[LANG_PT])
        return out

    def _load_apertium_modes(self) -> tuple[str, ...]:
        if shutil.which("apertium") is None:
            return ()
        try:
            proc = subprocess.run(
                ["apertium", "-l"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return ()

        if proc.returncode != 0:
            return ()

        modes: list[str] = []
        for token in proc.stdout.split():
            token = token.strip()
            if "-" in token:
                modes.append(token)
        return tuple(modes)

    def _load_argos(self):
        try:
            import argostranslate.translate as argos_translate  # type: ignore

            return argos_translate
        except Exception:
            return None

    def _find_apertium_mode(self, source: str, target: str) -> str | None:
        source_aliases = APERTIUM_CODE_ALIASES.get(source, ())
        target_aliases = APERTIUM_CODE_ALIASES.get(target, ())
        for src in source_aliases:
            for tgt in target_aliases:
                mode = f"{src}-{tgt}"
                if mode in self._apertium_modes:
                    return mode
        return None

    def _run_apertium(self, text: str, mode: str) -> str | None:
        try:
            proc = subprocess.run(
                ["apertium", mode],
                input=text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode != 0:
            return None
        output = (proc.stdout or "").rstrip("\n")
        if not output.strip():
            return None
        return output

    def _translate_argos(self, text: str, source: str, target: str) -> str | None:
        if self._argos is None:
            return None

        key = (source, target)
        with self._lock:
            cached = self._argos_cache.get(key)

        if cached is None:
            try:
                langs = self._argos.get_installed_languages()
            except Exception:
                return None

            src_lang = None
            tgt_lang = None
            for lang in langs:
                code = _normalize_lang(getattr(lang, "code", ""))
                if code == source and src_lang is None:
                    src_lang = lang
                if code == target and tgt_lang is None:
                    tgt_lang = lang

            if src_lang is None and source == LANG_PT_BR:
                for lang in langs:
                    if _normalize_lang(getattr(lang, "code", "")) == LANG_PT:
                        src_lang = lang
                        break
            if tgt_lang is None and target == LANG_PT_BR:
                for lang in langs:
                    if _normalize_lang(getattr(lang, "code", "")) == LANG_PT:
                        tgt_lang = lang
                        break

            if src_lang is None or tgt_lang is None:
                return None

            try:
                cached = src_lang.get_translation(tgt_lang)
            except Exception:
                return None

            with self._lock:
                self._argos_cache[key] = cached

        try:
            result = cached.translate(text)
        except Exception:
            return None
        if result is None:
            return None
        out = str(result)
        if not out.strip():
            return None
        return out

    def _translate_apertium_direct(self, text: str, source: str, target: str) -> str | None:
        mode = self._find_apertium_mode(source, target)
        if mode is None:
            return None
        return self._run_apertium(text, mode)

    def _translate_apertium_pivot(self, text: str, source: str, target: str) -> str | None:
        if source == LANG_ES or target == LANG_ES:
            return None
        first = self._find_apertium_mode(source, LANG_ES)
        second = self._find_apertium_mode(LANG_ES, target)
        if first is None or second is None:
            return None
        step1 = self._run_apertium(text, first)
        if step1 is None:
            return None
        return self._run_apertium(step1, second)

    def _translate_dictionary(self, text: str, source: str, target: str) -> str | None:
        source_words = self._dictionaries.get(source, set())
        translated_any = False
        out: list[str] = []

        for token in WORD_TOKEN_RE.findall(text):
            if not _looks_like_word(token):
                out.append(token)
                continue

            mapped = self._word_map.get(source, {}).get(f"{token.lower()}|{target}")
            if mapped:
                out.append(_preserve_case(token, mapped))
                translated_any = True
                continue

            if source_words and token.lower() not in source_words:
                out.append(token)
                continue

            out.append(token)

        if not translated_any:
            return None
        return "".join(out)

    def _auto_detect(self, text: str) -> str | None:
        tokens = [t.lower() for t in WORD_TOKEN_RE.findall(text) if _looks_like_word(t)]
        if not tokens:
            return None

        scores = {LANG_EN: 0, LANG_DE: 0, LANG_PT: 0}
        for token in tokens:
            if token in self._dictionaries[LANG_EN]:
                scores[LANG_EN] += 1
            if token in self._dictionaries[LANG_DE]:
                scores[LANG_DE] += 1
            if token in self._dictionaries[LANG_PT] or token in self._dictionaries[LANG_PT_BR]:
                scores[LANG_PT] += 1

        best = max(scores, key=scores.get)
        if scores[best] <= 0:
            return None
        return best

    def translate(self, text: Any, source: str, target: str) -> tuple[str, str]:
        if text is None:
            return "", "original"
        if not isinstance(text, str):
            try:
                text = str(text)
            except Exception:
                return "", "original"

        if text == "":
            return "", "original"

        src = _normalize_lang(source)
        tgt = _normalize_lang(target)
        if tgt not in {LANG_EN, LANG_DE, LANG_PT, LANG_PT_BR}:
            return text, "original"

        if src == "auto":
            src = self._auto_detect(text)

        if src not in {LANG_EN, LANG_DE, LANG_PT, LANG_PT_BR}:
            return text, "original"

        if src == tgt:
            return text, "original"

        try:
            translated = self._translate_argos(text, src, tgt)
            if translated:
                return translated, "argos"
        except Exception:
            pass

        try:
            translated = self._translate_apertium_direct(text, src, tgt)
            if translated:
                return translated, "apertium-direct"
        except Exception:
            pass

        try:
            translated = self._translate_apertium_pivot(text, src, tgt)
            if translated:
                return translated, "apertium-pivot"
        except Exception:
            pass

        try:
            translated = self._translate_dictionary(text, src, tgt)
            if translated:
                return translated, "dictionary"
        except Exception:
            pass

        return text, "original"


ENGINE = TranslationEngine()


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class TranslationRequestHandler(BaseHTTPRequestHandler):
    server_version = "FonteTranslationService/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        logging.info("%s - %s", self.client_address[0], fmt % args)

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int]:
        length_header = self.headers.get("Content-Length")
        if not length_header:
            return None, self._error("missing-content-length", "Missing Content-Length header."), 411

        try:
            length = int(length_header)
        except ValueError:
            return None, self._error("invalid-content-length", "Invalid Content-Length header."), 400

        if length < 0:
            return None, self._error("invalid-content-length", "Invalid Content-Length value."), 400

        if length > MAX_BODY_BYTES:
            return None, self._error("payload-too-large", "Request body exceeds size limit."), 413

        raw = self.rfile.read(length)
        try:
            text = raw.decode("utf-8", errors="replace")
            data = json.loads(text)
        except json.JSONDecodeError:
            return None, self._error("bad-json", "Malformed JSON payload."), 400

        if not isinstance(data, dict):
            return None, self._error("invalid-body", "JSON body must be an object."), 400

        return data, None, 200

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"success": False, "error": {"code": code, "message": message}}

    def do_OPTIONS(self) -> None:
        self._send_json(200, {"success": True})

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "success": True})
            return
        self._send_json(404, self._error("not-found", "Endpoint not found."))

    def do_POST(self) -> None:
        if self.path == "/translate":
            self._handle_translate()
            return
        if self.path == "/translate_batch":
            self._handle_translate_batch()
            return
        self._send_json(404, self._error("not-found", "Endpoint not found."))

    def _handle_translate(self) -> None:
        data, error_payload, status = self._read_json_body()
        if error_payload is not None:
            self._send_json(status, error_payload)
            return

        text = data.get("text")
        source = data.get("source")
        target = data.get("target")

        if not isinstance(text, str):
            self._send_json(400, self._error("invalid-text", "Field 'text' must be a string."))
            return
        if not isinstance(source, str) or not isinstance(target, str):
            self._send_json(400, self._error("invalid-language", "Fields 'source' and 'target' must be strings."))
            return

        normalized_target = _normalize_lang(target)
        if normalized_target not in {LANG_EN, LANG_DE, LANG_PT, LANG_PT_BR}:
            self._send_json(400, self._error("unsupported-target", "Unsupported target language code."))
            return

        normalized_source = _normalize_lang(source)
        if normalized_source not in {LANG_EN, LANG_DE, LANG_PT, LANG_PT_BR, "auto"}:
            self._send_json(400, self._error("unsupported-source", "Unsupported source language code."))
            return

        translated, engine_name = ENGINE.translate(text, source, target)
        self._send_json(
            200,
            {
                "translated": translated,
                "engine": engine_name,
                "success": True,
            },
        )

    def _handle_translate_batch(self) -> None:
        data, error_payload, status = self._read_json_body()
        if error_payload is not None:
            self._send_json(status, error_payload)
            return

        texts = data.get("texts")
        source = data.get("source")
        target = data.get("target")

        if not isinstance(texts, list):
            self._send_json(400, self._error("invalid-texts", "Field 'texts' must be a list."))
            return
        if not isinstance(source, str) or not isinstance(target, str):
            self._send_json(400, self._error("invalid-language", "Fields 'source' and 'target' must be strings."))
            return

        if len(texts) > 1000:
            self._send_json(400, self._error("batch-too-large", "Maximum 1000 items per batch request."))
            return

        normalized_target = _normalize_lang(target)
        if normalized_target not in {LANG_EN, LANG_DE, LANG_PT, LANG_PT_BR}:
            self._send_json(400, self._error("unsupported-target", "Unsupported target language code."))
            return

        normalized_source = _normalize_lang(source)
        if normalized_source not in {LANG_EN, LANG_DE, LANG_PT, LANG_PT_BR, "auto"}:
            self._send_json(400, self._error("unsupported-source", "Unsupported source language code."))
            return

        results: list[dict[str, Any]] = []
        for idx, value in enumerate(texts):
            if not isinstance(value, str):
                results.append({"index": idx, "translated": "", "engine": "original", "success": False})
                continue
            translated, engine_name = ENGINE.translate(value, source, target)
            results.append(
                {
                    "index": idx,
                    "translated": translated,
                    "engine": engine_name,
                    "success": True,
                }
            )

        self._send_json(200, {"success": True, "results": results})


def run_server(host: str = HOST, port: int = PORT) -> None:
    logging.info("Starting translation service on %s:%d", host, port)
    server = ThreadingHTTPServer((host, port), TranslationRequestHandler)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        logging.info("Shutdown requested")
    finally:
        server.shutdown()
        server.server_close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fonte local translation microservice")
    parser.add_argument("--host", default=HOST, help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=PORT, help="Bind port (default: 8765)")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    level_name = str(args.log_level).upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")

    if args.host != "127.0.0.1":
        logging.warning("Overriding bind host to 127.0.0.1 for local-only security")
        args.host = "127.0.0.1"

    if args.port <= 0 or args.port > 65535:
        logging.error("Invalid port: %s", args.port)
        return 2

    run_server(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
