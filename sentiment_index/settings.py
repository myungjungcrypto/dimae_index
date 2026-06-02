from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .config import DATA_DIR, DEFAULT_CONFIG, DEFAULT_LEXICON, Lexicon, PipelineConfig


DEFAULT_SETTINGS_PATH = DATA_DIR / "settings.json"


def load_settings(path: Path | str = DEFAULT_SETTINGS_PATH) -> dict[str, Any]:
    payload = default_settings()
    settings_path = Path(path)
    if not settings_path.exists():
        return payload

    try:
        stored = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return payload

    payload["keywords"] = normalize_terms(stored.get("keywords", payload["keywords"]))
    stored_lexicon = stored.get("lexicon", {})
    if isinstance(stored_lexicon, dict):
        for name, terms in payload["lexicon"].items():
            payload["lexicon"][name] = normalize_terms(stored_lexicon.get(name, terms))
    return payload


def save_settings(settings: dict[str, Any], path: Path | str = DEFAULT_SETTINGS_PATH) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def default_settings() -> dict[str, Any]:
    return {
        "keywords": list(DEFAULT_CONFIG.keywords),
        "lexicon": {
            "positive": list(DEFAULT_LEXICON.positive),
            "negative": list(DEFAULT_LEXICON.negative),
            "fomo": list(DEFAULT_LEXICON.fomo),
            "fear": list(DEFAULT_LEXICON.fear),
            "distrust": list(DEFAULT_LEXICON.distrust),
            "spam": list(DEFAULT_LEXICON.spam),
        },
    }


def load_runtime_config(
    config: PipelineConfig = DEFAULT_CONFIG,
    path: Path | str = DEFAULT_SETTINGS_PATH,
) -> PipelineConfig:
    settings = load_settings(path)
    return replace(config, keywords=tuple(settings["keywords"]))


def load_runtime_lexicon(path: Path | str = DEFAULT_SETTINGS_PATH) -> Lexicon:
    lexicon = load_settings(path)["lexicon"]
    return Lexicon(
        positive=tuple(lexicon["positive"]),
        negative=tuple(lexicon["negative"]),
        fomo=tuple(lexicon["fomo"]),
        fear=tuple(lexicon["fear"]),
        distrust=tuple(lexicon["distrust"]),
        spam=tuple(lexicon["spam"]),
    )


def add_term(
    list_name: str,
    value: str,
    path: Path | str = DEFAULT_SETTINGS_PATH,
) -> dict[str, Any]:
    settings = load_settings(path)
    terms = _get_terms(settings, list_name)
    normalized = normalize_term(value)
    if normalized and normalized not in terms:
        terms.append(normalized)
    save_settings(settings, path)
    return settings


def remove_term(
    list_name: str,
    value: str,
    path: Path | str = DEFAULT_SETTINGS_PATH,
) -> dict[str, Any]:
    settings = load_settings(path)
    terms = _get_terms(settings, list_name)
    normalized = normalize_term(value)
    settings_terms = [term for term in terms if term != normalized]
    if list_name == "keywords":
        settings["keywords"] = settings_terms
    else:
        settings["lexicon"][list_name] = settings_terms
    save_settings(settings, path)
    return settings


def normalize_terms(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        term = normalize_term(str(value))
        if term and term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def normalize_term(value: str) -> str:
    return " ".join(value.strip().split())


def _get_terms(settings: dict[str, Any], list_name: str) -> list[str]:
    if list_name == "keywords":
        return settings["keywords"]
    if list_name == "fomo":
        return settings["lexicon"]["fomo"]
    raise ValueError(f"unsupported settings list: {list_name}")
