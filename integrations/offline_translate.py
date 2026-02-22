"""Offline multilingual translation utilities for Fonte.

This module provides an offline-first translation interface that prefers local
ML models (Argos Translate) when present, then Apertium modes, then a minimal
word-level fallback dictionary. It is designed for air-gapped deployments and
must never raise uncaught exceptions.
"""

from __future__ import annotations

import argparse
import functools
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

# Supported canonical language codes.
_LANG_EN = "en"
_LANG_DE = "de"
_LANG_PT = "pt"
_LANG_PT_BR = "pt_BR"
_LANG_ES = "es"

# Acceptable aliases for user/system input language codes.
_LANG_ALIASES = {
    "en": _LANG_EN,
    "eng": _LANG_EN,
    "english": _LANG_EN,
    "de": _LANG_DE,
    "ger": _LANG_DE,
    "deu": _LANG_DE,
    "german": _LANG_DE,
    "pt": _LANG_PT,
    "por": _LANG_PT,
    "pt_pt": _LANG_PT,
    "pt-br": _LANG_PT_BR,
    "pt_br": _LANG_PT_BR,
    "ptbr": _LANG_PT_BR,
    "por_br": _LANG_PT_BR,
    "portuguese": _LANG_PT,
    "portuguese_br": _LANG_PT_BR,
    "es": _LANG_ES,
    "spa": _LANG_ES,
    "spanish": _LANG_ES,
    "auto": "auto",
}

# Apertium mode endpoint aliases per canonical language.
_APERTIUM_CODE_ALIASES = {
    _LANG_EN: ("en", "eng"),
    _LANG_DE: ("de", "deu", "ger"),
    _LANG_PT: ("pt", "por"),
    _LANG_PT_BR: ("pt_BR", "pt-br", "ptbr", "por_BR"),
    _LANG_ES: ("es", "spa"),
}

# Minimal embedded translation concepts for dictionary fallback.
# Each key represents a concept with language-specific surface forms.
_CONCEPTS = {
    "hello": {_LANG_EN: "hello", _LANG_DE: "hallo", _LANG_PT: "ola", _LANG_PT_BR: "olá"},
    "world": {_LANG_EN: "world", _LANG_DE: "welt", _LANG_PT: "mundo", _LANG_PT_BR: "mundo"},
    "good": {_LANG_EN: "good", _LANG_DE: "gut", _LANG_PT: "bom", _LANG_PT_BR: "bom"},
    "morning": {_LANG_EN: "morning", _LANG_DE: "morgen", _LANG_PT: "manhã", _LANG_PT_BR: "manhã"},
    "night": {_LANG_EN: "night", _LANG_DE: "nacht", _LANG_PT: "noite", _LANG_PT_BR: "noite"},
    "yes": {_LANG_EN: "yes", _LANG_DE: "ja", _LANG_PT: "sim", _LANG_PT_BR: "sim"},
    "no": {_LANG_EN: "no", _LANG_DE: "nein", _LANG_PT: "não", _LANG_PT_BR: "não"},
    "please": {_LANG_EN: "please", _LANG_DE: "bitte", _LANG_PT: "por favor", _LANG_PT_BR: "por favor"},
    "thanks": {_LANG_EN: "thanks", _LANG_DE: "danke", _LANG_PT: "obrigado", _LANG_PT_BR: "obrigado"},
    "you": {_LANG_EN: "you", _LANG_DE: "du", _LANG_PT: "você", _LANG_PT_BR: "você"},
    "i": {_LANG_EN: "i", _LANG_DE: "ich", _LANG_PT: "eu", _LANG_PT_BR: "eu"},
    "am": {_LANG_EN: "am", _LANG_DE: "bin", _LANG_PT: "sou", _LANG_PT_BR: "sou"},
    "is": {_LANG_EN: "is", _LANG_DE: "ist", _LANG_PT: "é", _LANG_PT_BR: "é"},
    "my": {_LANG_EN: "my", _LANG_DE: "mein", _LANG_PT: "meu", _LANG_PT_BR: "meu"},
    "name": {_LANG_EN: "name", _LANG_DE: "name", _LANG_PT: "nome", _LANG_PT_BR: "nome"},
    "where": {_LANG_EN: "where", _LANG_DE: "wo", _LANG_PT: "onde", _LANG_PT_BR: "onde"},
    "food": {_LANG_EN: "food", _LANG_DE: "essen", _LANG_PT: "comida", _LANG_PT_BR: "comida"},
    "water": {_LANG_EN: "water", _LANG_DE: "wasser", _LANG_PT: "água", _LANG_PT_BR: "água"},
    "help": {_LANG_EN: "help", _LANG_DE: "hilfe", _LANG_PT: "ajuda", _LANG_PT_BR: "ajuda"},
}


def _build_word_mapping() -> dict[str, dict[str, str]]:
    """Build source-language lookup tables from concept-level translations."""
    mapping: dict[str, dict[str, str]] = {
        _LANG_EN: {},
        _LANG_DE: {},
        _LANG_PT: {},
        _LANG_PT_BR: {},
    }
    for forms in _CONCEPTS.values():
        for source_lang, source_word in forms.items():
            if source_lang not in mapping:
                continue
            source_key = source_word.lower()
            for target_lang, target_word in forms.items():
                if target_lang == source_lang:
                    continue
                mapping[source_lang][f"{source_key}|{target_lang}"] = target_word
    return mapping


_WORD_MAPPING = _build_word_mapping()
_WORD_TOKEN_RE = re.compile(r"\w+|\s+|[^\w\s]", re.UNICODE)


@functools.lru_cache(maxsize=1)
def _dictionary_sets() -> dict[str, set[str]]:
    """Load local dictionary files once and return lowercase word sets.

    Files are optional. Missing/unreadable files are ignored.
    """
    base = Path(__file__).resolve().parent.parent
    candidates = {
        _LANG_EN: base / "english_dictionary.txt",
        _LANG_DE: base / "german_dictionary.txt",
        _LANG_PT: base / "portuguese_dictionary.txt",
        _LANG_PT_BR: base / "portuguese_br_dictionary.txt",
    }
    out: dict[str, set[str]] = {_LANG_EN: set(), _LANG_DE: set(), _LANG_PT: set(), _LANG_PT_BR: set()}

    for lang, path in candidates.items():
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith("=") or line.lower().startswith("format:"):
                        continue
                    if line.startswith("- ") and "|" in line:
                        piece = line[2:].split("|", 1)[0].strip()
                        if piece:
                            out[lang].add(piece.lower())
                        continue
                    if line.endswith(":"):
                        continue
                    if "|" in line:
                        piece = line.split("|", 1)[0].strip(" -")
                        if piece:
                            out[lang].add(piece.lower())
                        continue
                    if line[0].isalpha() or line[0] in "áàâãäçéêëíîïóôõöúüñß":
                        out[lang].add(line.lower())
        except OSError:
            continue

    if not out[_LANG_PT_BR]:
        out[_LANG_PT_BR] = set(out[_LANG_PT])
    return out


def _normalize_lang(lang: str | None) -> str | None:
    """Normalize user language input to canonical internal codes."""
    if lang is None:
        return None
    key = lang.strip().replace("-", "_").lower()
    return _LANG_ALIASES.get(key)


def _looks_like_word(token: str) -> bool:
    return any(ch.isalpha() for ch in token)


def _preserve_case(source: str, target: str) -> str:
    """Apply simple source-token casing to translated target token."""
    if source.isupper():
        return target.upper()
    if source.istitle():
        return target[:1].upper() + target[1:]
    return target


def _auto_detect_lang(text: str) -> str | None:
    """Heuristic auto language detection using dictionary membership.

    Returns one of en/de/pt/pt_BR when there is a strong signal, otherwise None.
    """
    dicts = _dictionary_sets()
    tokens = [t.lower() for t in _WORD_TOKEN_RE.findall(text) if _looks_like_word(t)]
    if not tokens:
        return None

    score = {_LANG_EN: 0, _LANG_DE: 0, _LANG_PT: 0}
    for tok in tokens:
        if tok in dicts[_LANG_EN]:
            score[_LANG_EN] += 1
        if tok in dicts[_LANG_DE]:
            score[_LANG_DE] += 1
        if tok in dicts[_LANG_PT] or tok in dicts[_LANG_PT_BR]:
            score[_LANG_PT] += 1

    best_lang = max(score, key=score.get)
    if score[best_lang] <= 0:
        return None
    top = score[best_lang]
    second = sorted(score.values(), reverse=True)[1]
    if top < 2 and top == second:
        return None
    return best_lang


@functools.lru_cache(maxsize=1)
def _apertium_modes() -> tuple[str, ...]:
    """Read and cache available Apertium translation modes.

    Returns an empty tuple when Apertium is not installed or listing fails.
    """
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
            timeout=6,
        )
    except (OSError, subprocess.SubprocessError):
        return ()

    if proc.returncode != 0:
        return ()

    modes: list[str] = []
    for token in proc.stdout.split():
        cleaned = token.strip()
        if "-" in cleaned:
            modes.append(cleaned)
    return tuple(modes)


def _find_apertium_mode(source_lang: str, target_lang: str) -> str | None:
    """Find the best matching Apertium mode for source->target."""
    modes = _apertium_modes()
    if not modes:
        return None
    source_aliases = _APERTIUM_CODE_ALIASES.get(source_lang, ())
    target_aliases = _APERTIUM_CODE_ALIASES.get(target_lang, ())
    if not source_aliases or not target_aliases:
        return None

    for src in source_aliases:
        for tgt in target_aliases:
            candidate = f"{src}-{tgt}"
            if candidate in modes:
                return candidate
    return None


def _run_apertium(text: str, mode: str) -> str | None:
    """Run Apertium in a specific mode and return translated text on success."""
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

    out = proc.stdout
    if out is None:
        return None
    out = out.rstrip("\n")
    if not out.strip():
        return None
    return out


def _translate_apertium_direct(text: str, source_lang: str, target_lang: str) -> str | None:
    """Translate with a direct Apertium mode when available."""
    mode = _find_apertium_mode(source_lang, target_lang)
    if mode is None:
        return None
    return _run_apertium(text, mode)


def _translate_apertium_pivot(text: str, source_lang: str, target_lang: str) -> str | None:
    """Translate with Apertium via Spanish pivot (source->es->target)."""
    if source_lang == _LANG_ES or target_lang == _LANG_ES:
        return None

    first_mode = _find_apertium_mode(source_lang, _LANG_ES)
    second_mode = _find_apertium_mode(_LANG_ES, target_lang)
    if first_mode is None or second_mode is None:
        return None

    first = _run_apertium(text, first_mode)
    if first is None:
        return None
    second = _run_apertium(first, second_mode)
    return second


def _load_argos_translate_module():
    """Import argostranslate.translate lazily, returning None when unavailable."""
    try:
        import argostranslate.translate as argos_translate  # type: ignore

        return argos_translate
    except Exception:
        return None


@functools.lru_cache(maxsize=32)
def _get_argos_translation(source_lang: str, target_lang: str):
    """Return an Argos Translation object for source->target, or None."""
    argos_translate = _load_argos_translate_module()
    if argos_translate is None:
        return None

    try:
        languages = argos_translate.get_installed_languages()
    except Exception:
        return None

    source = None
    target = None
    for lang in languages:
        code = _normalize_lang(getattr(lang, "code", "")) or _normalize_lang(
            getattr(lang, "code", "").replace("_", "-")
        )
        if code == source_lang and source is None:
            source = lang
        if code == target_lang and target is None:
            target = lang

    if source is None and source_lang == _LANG_PT_BR:
        for lang in languages:
            code = _normalize_lang(getattr(lang, "code", ""))
            if code == _LANG_PT:
                source = lang
                break
    if target is None and target_lang == _LANG_PT_BR:
        for lang in languages:
            code = _normalize_lang(getattr(lang, "code", ""))
            if code == _LANG_PT:
                target = lang
                break

    if source is None or target is None:
        return None

    try:
        return source.get_translation(target)
    except Exception:
        return None


def _translate_argos(text: str, source_lang: str, target_lang: str) -> str | None:
    """Translate text with Argos Translate if installed model exists."""
    translation = _get_argos_translation(source_lang, target_lang)
    if translation is None:
        return None
    try:
        output = translation.translate(text)
    except Exception:
        return None
    if output is None:
        return None
    output = str(output)
    if not output.strip():
        return None
    return output


def _dictionary_translate_word(word: str, source_lang: str, target_lang: str) -> str:
    """Translate one token with embedded mapping, preserving source casing."""
    key = f"{word.lower()}|{target_lang}"
    translated = _WORD_MAPPING.get(source_lang, {}).get(key)
    if translated is None:
        return word
    return _preserve_case(word, translated)


def _translate_dictionary(text: str, source_lang: str, target_lang: str) -> str | None:
    """Word-by-word dictionary fallback translation.

    Punctuation, spacing, and unknown words are preserved.
    """
    dicts = _dictionary_sets()
    source_words = dicts.get(source_lang) or set()
    translated_any = False

    pieces = _WORD_TOKEN_RE.findall(text)
    out: list[str] = []
    for piece in pieces:
        if not _looks_like_word(piece):
            out.append(piece)
            continue

        # If we have source dictionary data and the word is clearly unknown,
        # leave it untouched unless it is in our embedded map.
        lower = piece.lower()
        mapped = _dictionary_translate_word(piece, source_lang, target_lang)
        if mapped != piece:
            out.append(mapped)
            translated_any = True
            continue

        if source_words and lower not in source_words:
            out.append(piece)
            continue

        out.append(piece)

    if not translated_any:
        return None
    return "".join(out)


def _safe_text(text: str) -> str:
    """Return a best-effort safe text value for translation."""
    if text is None:
        return ""
    if isinstance(text, str):
        return text
    try:
        return str(text)
    except Exception:
        return ""


def translate(text: str, source_lang: str, target_lang: str) -> str:
    """Translate text offline across English, German, and Portuguese.

    Priority order:
    1. Argos Translate (if installed and model exists)
    2. Apertium direct mode
    3. Apertium Spanish pivot
    4. Dictionary fallback
    5. Original text

    Args:
        text: Input text to translate.
        source_lang: Source language code (en, de, pt, pt_BR, auto).
        target_lang: Target language code (en, de, pt, pt_BR).

    Returns:
        Translated text on best effort; original input text when translation is
        not possible.
    """
    original = _safe_text(text)
    if not original:
        return original

    src = _normalize_lang(source_lang)
    tgt = _normalize_lang(target_lang)

    if tgt not in {_LANG_EN, _LANG_DE, _LANG_PT, _LANG_PT_BR}:
        return original

    if src == "auto":
        guessed = _auto_detect_lang(original)
        src = guessed or None

    if src not in {_LANG_EN, _LANG_DE, _LANG_PT, _LANG_PT_BR}:
        return original

    if src == tgt:
        return original

    for engine in (
        _translate_argos,
        _translate_apertium_direct,
        _translate_apertium_pivot,
        _translate_dictionary,
    ):
        try:
            translated = engine(original, src, tgt)
        except Exception:
            translated = None
        if translated:
            return translated

    return original


def translate_batch(texts: Iterable[str], source_lang: str, target_lang: str) -> list[str]:
    """Translate a batch of texts with the same source/target pair."""
    return [translate(item, source_lang, target_lang) for item in texts]


def translate_file(
    input_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    source_lang: str,
    target_lang: str,
) -> bool:
    """Translate a UTF-8 text file and write the translated output.

    Returns True on success, False on failure.
    """
    try:
        source_text = Path(input_path).read_text(encoding="utf-8", errors="ignore")
        translated = translate(source_text, source_lang, target_lang)
        Path(output_path).write_text(translated, encoding="utf-8", errors="ignore")
        return True
    except OSError:
        return False


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline translation helper for Fonte")
    parser.add_argument("text", nargs="?", help="Text to translate")
    parser.add_argument("source_lang", nargs="?", default="auto", help="Source language code")
    parser.add_argument("target_lang", nargs="?", default="en", help="Target language code")
    parser.add_argument("--in-file", dest="in_file", help="Input file path")
    parser.add_argument("--out-file", dest="out_file", help="Output file path")
    return parser


def _main() -> int:
    parser = _build_cli_parser()
    args = parser.parse_args()

    if args.in_file and args.out_file:
        ok = translate_file(args.in_file, args.out_file, args.source_lang, args.target_lang)
        return 0 if ok else 1

    if args.text is None:
        parser.print_usage()
        return 2

    result = translate(args.text, args.source_lang, args.target_lang)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
