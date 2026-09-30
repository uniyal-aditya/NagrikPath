"""Helpers for NagrikPath: config, PDF text, Sarvam AI calls, JSON safety, audio."""
from __future__ import annotations

import io
import json
import logging
import os
import re
import time
from typing import Any

from dotenv import load_dotenv

import prompts
from prompts import LANGUAGES, NOT_SPECIFIED, NOT_SPECIFIED_HI

load_dotenv()  # local development: read .env if present

logger = logging.getLogger("nagrikpath")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

MAX_NOTICE_CHARS = 60_000
_PLACEHOLDER_KEYS = {"", "your_api_key_here", "your_sarvam_api_key", "changeme"}

SARVAM_URL = "https://api.sarvam.ai/v1/chat/completions"
REQUEST_TIMEOUT = 120  # seconds
MAX_OUTPUT_TOKENS = 4000  # sarvam models reason before answering, so leave headroom

# Sarvam chat models. sarvam-30b was deprecated by Sarvam on 2026-09-30; do not use it.
# Override with SARVAM_MODEL (env var or Streamlit secret).
DEFAULT_MODELS = ["sarvam-105b", "sarvam-105b-conversations"]


class NagrikPathError(Exception):
    """An error with a message that is safe and useful to show to the user."""

    def __init__(self, user_message: str, technical: str | None = None):
        super().__init__(technical or user_message)
        self.user_message = user_message
        self.technical = technical


class _HttpError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
def _get_secret(name: str) -> str | None:
    """Streamlit secrets first (deployment), then environment / .env (local)."""
    try:
        import streamlit as st

        if name in st.secrets:
            value = str(st.secrets[name]).strip()
            if value:
                return value
    except Exception:  # no secrets file, or not running under Streamlit
        pass
    value = os.getenv(name)
    return value.strip() if value else None


def get_api_key() -> str | None:
    key = _get_secret("SARVAM_API_KEY")
    if key is None or key.lower() in _PLACEHOLDER_KEYS:
        return None
    return key


def model_candidates() -> list[str]:
    override = _get_secret("SARVAM_MODEL")
    if not override:
        return list(DEFAULT_MODELS)
    return [override] + [m for m in DEFAULT_MODELS if m != override]


# --------------------------------------------------------------------------
# Notice input
# --------------------------------------------------------------------------
def extract_pdf_text(file_obj: Any) -> str:
    """Extract text from every page of a PDF (no OCR)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise NagrikPathError("PDF support is not installed. Run: pip install -r requirements.txt", str(exc))

    try:
        reader = PdfReader(file_obj)
        if reader.is_encrypted and not reader.decrypt(""):
            raise NagrikPathError("This PDF is password-protected. Remove the password or paste the text instead.")
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:  # one bad page should not kill the rest
                logger.warning("Skipping unreadable PDF page: %s", exc)
    except NagrikPathError:
        raise
    except Exception as exc:
        logger.warning("PDF read failed: %s", exc)
        raise NagrikPathError("This file could not be read as a PDF. Please upload a valid PDF or paste the text.", repr(exc))

    text = clean_text("\n\n".join(pages))
    if not text:
        raise NagrikPathError(
            "No readable text was found in this PDF. It may be a scanned image (OCR is not supported yet). "
            "Please paste the notice text instead."
        )
    return text


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def prepare_notice(text: str) -> tuple[str, bool]:
    """Clean the notice and cap its length. Returns (text, was_truncated)."""
    text = clean_text(text or "")
    if len(text) > MAX_NOTICE_CHARS:
        return text[:MAX_NOTICE_CHARS], True
    return text, False


# --------------------------------------------------------------------------
# JSON safety
# --------------------------------------------------------------------------
def extract_json(raw: str) -> dict:
    """Pull a JSON object out of model output, tolerating markdown fences and chatter."""
    if not raw or not raw.strip():
        raise ValueError("empty response")
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("JSON root is not an object")
    return obj


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return "; ".join(t for t in (_as_text(v) for v in value) if t)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [t for t in (_as_text(v) for v in value) if t]
    text = _as_text(value)
    return [text] if text else []


def is_missing(value: str) -> bool:
    return value.strip() in (NOT_SPECIFIED, NOT_SPECIFIED_HI)


def validate_analysis(obj: dict, language: str = "English") -> dict:
    """Coerce model output to the exact schema; fill absent fields with the 'missing' text."""
    missing_text = LANGUAGES.get(language, LANGUAGES["English"])["missing"]
    result = {
        "summary": _as_text(obj.get("summary")) or missing_text,
        "eligibility": _as_text(obj.get("eligibility")) or missing_text,
        "documents": _as_list(obj.get("documents")),
        "deadline": _as_text(obj.get("deadline")) or missing_text,
        "action_plan": _as_list(obj.get("action_plan"))[:3],
        "warnings": _as_list(obj.get("warnings")),
    }
    known = ("summary", "eligibility", "documents", "deadline", "action_plan", "warnings")
    if not any(k in obj for k in known):
        raise ValueError("response contains none of the expected fields")
    return result


# --------------------------------------------------------------------------
# Sarvam AI
# --------------------------------------------------------------------------
def _classify(exc: Exception) -> str:
    if isinstance(exc, _HttpError):
        status, body = exc.status, exc.body.lower()
        if status == 429:
            return "rate_limit"
        if status in (401, 403):
            return "auth"
        if status == 404 or (status in (400, 422) and "model" in body):
            return "model_not_found"
        if status >= 500:
            return "overloaded"
        return "other"
    kind_name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if isinstance(exc, (ConnectionError, TimeoutError)) or any(
        w in kind_name for w in ("connect", "timeout", "network", "socket")
    ):
        return "network"
    if any(w in msg for w in ("connection", "timed out", "name resolution", "network is unreachable")):
        return "network"
    return "other"


_USER_MESSAGES = {
    "rate_limit": "The AI service is busy or the quota is used up. Please wait a minute and try again.",
    "model_not_found": "The configured AI model is not available. Set SARVAM_MODEL to sarvam-105b or sarvam-105b-conversations.",
    "auth": "The Sarvam API key was rejected. Check that SARVAM_API_KEY is correct and active.",
    "overloaded": "The AI service is temporarily overloaded. Please try again in a moment.",
    "network": "Could not reach the AI service. Check your internet connection and try again.",
    "other": "The AI service returned an error. Please try again.",
}
_FALLBACK_KINDS = {"model_not_found", "overloaded", "rate_limit"}


def _response_text(data: Any) -> str:
    """Pull the answer out of a chat-completions response; drop any <think> reasoning block."""
    try:
        content = data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r"^.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)  # unmatched closing tag
    return content.strip()


def _post_chat(key: str, model: str, system_instruction: str, contents: str) -> Any:
    import requests

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": contents},
        ],
        "temperature": 0.2,  # factual task: keep it steady
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    headers = {"Authorization": f"Bearer {key}", "api-subscription-key": key, "Content-Type": "application/json"}
    resp = requests.post(SARVAM_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise _HttpError(resp.status_code, resp.text)
    return resp.json()


def _generate(*, system_instruction: str, contents: str, json_mode: bool) -> str:
    key = get_api_key()
    if not key:
        raise NagrikPathError(
            "Sarvam API key not found. Add SARVAM_API_KEY to your .env file (local) or Streamlit secrets (deployed)."
        )
    try:
        import requests  # noqa: F401
    except ImportError as exc:
        raise NagrikPathError("The requests package is missing. Run: pip install -r requirements.txt", str(exc))

    if json_mode:
        system_instruction += "\n\nReturn only one valid JSON object. No markdown fences, no commentary."

    last_kind, last_exc = "other", None
    for model in model_candidates():
        data = None
        for retry in range(2):
            try:
                data = _post_chat(key, model, system_instruction, contents)
                break
            except Exception as exc:
                last_kind, last_exc = _classify(exc), exc
                logger.warning("Sarvam call failed (model=%s, attempt=%d, kind=%s): %r", model, retry + 1, last_kind, exc)
                if last_kind in {"rate_limit", "overloaded"} and retry == 0:
                    time.sleep(1.5)
                    continue
                if last_kind in _FALLBACK_KINDS:
                    break
                raise NagrikPathError(_USER_MESSAGES[last_kind], repr(last_exc))
        if data is None:
            continue
        text = _response_text(data)
        if text:
            return text
        last_kind = "other"
        last_exc = RuntimeError(f"{model} returned an empty response")

    raise NagrikPathError(_USER_MESSAGES[last_kind], repr(last_exc))


def analyze_notice(notice: str, language: str) -> dict:
    """Notice text -> validated structured analysis. Retries once on malformed JSON."""
    user_prompt = prompts.build_analysis_prompt(notice, language)
    last_error: Exception | None = None
    for attempt in (1, 2):
        raw = _generate(system_instruction=prompts.ANALYSIS_SYSTEM_PROMPT, contents=user_prompt, json_mode=True)
        try:
            return validate_analysis(extract_json(raw), language)
        except ValueError as exc:  # includes json.JSONDecodeError
            last_error = exc
            logger.warning("Malformed analysis JSON (attempt %d): %s | raw[:200]=%r", attempt, exc, raw[:200])
    raise NagrikPathError(
        "The AI reply could not be understood. Please press Generate again.", repr(last_error)
    )


def chat_answer(notice: str, analysis: dict, history: list[dict], question: str, language: str) -> str:
    """Answer a follow-up question grounded only in the notice and its analysis."""
    return _generate(
        system_instruction=prompts.build_chat_system_prompt(language),
        contents=prompts.build_chat_prompt(notice, analysis, history, question),
        json_mode=False,
    )


# --------------------------------------------------------------------------
# Audio (gTTS)
# --------------------------------------------------------------------------
_AUDIO_LABELS = {
    "English": {
        "intro": "NagrikPath action plan.",
        "deadline": "Deadline:",
        "step": "Step",
        "verify": "Please verify the details with the official government source.",
    },
    "हिंदी": {
        "intro": "नागरिक पथ कार्य योजना।",
        "deadline": "अंतिम तिथि:",
        "step": "चरण",
        "verify": "कृपया आधिकारिक सरकारी स्रोत से जानकारी की पुष्टि करें।",
    },
}


def build_audio_script(analysis: dict, language: str) -> str:
    labels = _AUDIO_LABELS.get(language, _AUDIO_LABELS["English"])
    parts = [labels["intro"]]
    if analysis.get("summary") and not is_missing(analysis["summary"]):
        parts.append(analysis["summary"])
    if analysis.get("deadline") and not is_missing(analysis["deadline"]):
        parts.append(f"{labels['deadline']} {analysis['deadline']}")
    for i, step in enumerate(analysis.get("action_plan", []), start=1):
        parts.append(f"{labels['step']} {i}. {step}")
    parts.append(labels["verify"])
    return "\n".join(p if p.rstrip().endswith((".", "।", "!", "?")) else p + "." for p in parts)


def generate_audio(text: str, language_code: str) -> bytes:
    """Return MP3 bytes for `text`. In-memory only: no files are written."""
    try:
        from gtts import gTTS
    except ImportError as exc:
        raise NagrikPathError("Audio support is not installed. Run: pip install -r requirements.txt", str(exc))
    try:
        buffer = io.BytesIO()
        gTTS(text=text, lang=language_code).write_to_fp(buffer)
        data = buffer.getvalue()
    except Exception as exc:
        logger.warning("gTTS failed: %r", exc)
        raise NagrikPathError(
            "Audio could not be generated right now (it needs an internet connection). The written plan is unaffected.",
            repr(exc),
        )
    if not data:
        raise NagrikPathError("Audio could not be generated right now. The written plan is unaffected.")
    return data


# --------------------------------------------------------------------------
# Demo notice (fictional)
# --------------------------------------------------------------------------
DEMO_NOTICE = """GOVERNMENT HOUSING ASSISTANCE PROGRAM
(Demonstration notice - fictional, created for NagrikPath)

Notice to citizens

The Government Housing Assistance Program invites applications from eligible applicants. Eligible applicants meeting the stated income requirements may apply during the application period.

Required documents:
- Identity proof
- Address proof
- Income certificate

Application deadline: 31 October 2026

Applications must be submitted through the designated official portal.

Important: Applicants should verify eligibility and document requirements through the official source before applying."""
