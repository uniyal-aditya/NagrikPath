"""NagrikPath - From Government Notice to Citizen Action."""
from __future__ import annotations

import base64
import hashlib
import html
import logging
import mimetypes
import os
import re
from pathlib import Path

import streamlit as st

import utils
from prompts import LANGUAGES
from utils import NagrikPathError

logger = logging.getLogger("nagrikpath")

# --------------------------------------------------------------------------
# Assets (assets/hero.png, assets/favicon.*)
# --------------------------------------------------------------------------
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _find_asset(stems: tuple[str, ...], exts: tuple[str, ...]) -> Path | None:
    for stem in stems:
        for ext in exts:
            p = ASSETS_DIR / f"{stem}{ext}"
            if p.is_file():
                return p
    return None


FAVICON_PATH = _find_asset(("favicon", "icon"), (".png", ".ico", ".jpg", ".jpeg", ".webp", ".svg"))
HERO_PATH = _find_asset(("hero",), (".png", ".jpg", ".jpeg", ".webp", ".svg"))


@st.cache_data(show_spinner=False)
def _data_uri(path_str: str) -> str:
    path = Path(path_str)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


st.set_page_config(
    page_title="NagrikPath",
    page_icon=str(FAVICON_PATH) if FAVICON_PATH else "🇮🇳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --------------------------------------------------------------------------
# Localised UI text for the results area (keys MUST match prompts.LANGUAGES)
# --------------------------------------------------------------------------
LABELS = {
    "English": {
        "summary": "Summary",
        "eligibility": "Eligibility",
        "deadline": "Deadline",
        "documents": "Documents",
        "warnings": "Warnings",
        "plan": "action plan",
        "plan_n": "-step action plan",
        "verify": "Verify with the official source before acting.",
        "listen": "Listen to action plan",
        "gen_audio": "Generate audio",
        "chat": "Ask about this notice",
        "chat_hint": "Answers come only from this notice.",
        "chat_placeholder": "Ask a question about this notice…",
        "examples": ["Am I eligible?", "Which documents do I need?", "What is the deadline?", "Where should I apply?"],
    },
    "हिंदी": {
        "summary": "सारांश",
        "eligibility": "पात्रता",
        "deadline": "अंतिम तिथि",
        "documents": "दस्तावेज़",
        "warnings": "चेतावनियाँ",
        "plan": "कार्य योजना",
        "plan_n": " चरणों की कार्य योजना",
        "verify": "कार्रवाई से पहले आधिकारिक स्रोत से पुष्टि करें।",
        "listen": "कार्य योजना सुनें",
        "gen_audio": "ऑडियो बनाएँ",
        "chat": "इस सूचना के बारे में पूछें",
        "chat_hint": "उत्तर केवल इसी सूचना से दिए जाते हैं।",
        "chat_placeholder": "इस सूचना के बारे में प्रश्न पूछें…",
        "examples": ["क्या मैं पात्र हूँ?", "मुझे कौन से दस्तावेज़ चाहिए?", "अंतिम तिथि क्या है?", "मुझे आवेदन कहाँ करना है?"],
    },
}

# --------------------------------------------------------------------------
# Styling
# --------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;500;600&display=swap');
:root{--bg:#0E1222;--surface:#151A2E;--surface-2:#1B2140;--line:#2A3153;--text:#ECEEF8;--muted:#A0A7C4;--accent:#8B9BFF;--accent-2:#6C7BFF;--warn:#F2B35E;--warn-bg:#241E14;--ok:#7FD6A4;}
html,body,[class*="css"],.stApp{font-family:'Inter','Noto Sans Devanagari',system-ui,sans-serif;}
.stApp{background:var(--bg);color:var(--text);}
.block-container{max-width:1040px;padding-top:2rem;padding-bottom:4rem;}
#MainMenu,footer,[data-testid="stToolbar"]{visibility:hidden;}
.np-hero{padding:8px 0 28px 0;display:flex;align-items:center;justify-content:space-between;gap:28px;}
.np-hero-text{flex:1 1 auto;min-width:0;}
.np-hero-img{flex:0 0 auto;width:min(300px,36%);}
.np-hero-img img{width:100%;height:auto;display:block;border-radius:18px;border:1px solid var(--line);box-shadow:0 10px 30px rgba(0,0,0,.35);}
@media (max-width:760px){.np-hero{flex-direction:column;align-items:flex-start;}.np-hero-img{width:100%;max-width:340px;}}
.np-brand{display:flex;align-items:center;gap:12px;font-size:2.1rem;font-weight:700;letter-spacing:-0.02em;}
.np-brand img.logo{width:38px;height:38px;border-radius:8px;object-fit:cover;}
.np-flag{display:flex;flex-direction:column;width:34px;height:22px;border-radius:4px;overflow:hidden;border:1px solid var(--line);}
.np-flag i{flex:1;display:block;}
.np-flag i:nth-child(1){background:#FF9933;}.np-flag i:nth-child(2){background:#F4F4F8;}.np-flag i:nth-child(3){background:#138808;}
.np-tag{margin-top:6px;font-size:1.15rem;font-weight:500;color:var(--accent);}
.np-sub{margin-top:6px;color:var(--muted);font-size:1rem;max-width:60ch;}
.np-section{margin:34px 0 14px 0;font-size:1.25rem;font-weight:600;letter-spacing:-0.01em;}
.np-hint{color:var(--muted);font-size:.9rem;margin:-8px 0 14px 0;}
.np-summary{background:linear-gradient(180deg,var(--surface-2),var(--surface));border:1px solid var(--line);border-radius:18px;padding:24px 26px;}
.np-summary h3,.np-card h4{margin:0 0 10px 0;font-size:.95rem;font-weight:600;color:var(--accent);}
.np-summary p{margin:0;font-size:1.12rem;line-height:1.65;}
.np-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:16px;}
@media (max-width:760px){.np-grid{grid-template-columns:1fr;}.np-brand{font-size:1.7rem;}}
.np-card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:20px 22px;display:flex;flex-direction:column;gap:6px;}
.np-card.warn{background:var(--warn-bg);border-color:#5a4520;}
.np-card.warn h4{color:var(--warn);}
.np-card p,.np-card li{margin:0;line-height:1.6;font-size:1rem;}
.np-card ul{margin:0;padding-left:1.15rem;}
.np-card li{margin:4px 0;}
.np-card .big{font-size:1.35rem;font-weight:600;}
.np-card .none{color:var(--muted);font-style:italic;}
.np-verify{margin-top:auto;padding-top:10px;font-size:.8rem;color:var(--muted);}
.np-steps{position:relative;display:flex;flex-direction:column;gap:14px;}
.np-step{position:relative;display:flex;gap:16px;align-items:flex-start;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:16px 20px;}
.np-step .n{flex:0 0 36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;background:var(--accent-2);color:#fff;}
.np-step .t{padding-top:5px;line-height:1.55;font-size:1.02rem;}
.np-step:not(:last-child)::after{content:"";position:absolute;left:37px;top:100%;height:14px;width:2px;background:var(--line);}
.np-empty{background:var(--surface);border:1px dashed var(--line);border-radius:18px;padding:26px;margin-top:24px;}
.np-empty h3{margin:0 0 14px 0;font-size:1.05rem;font-weight:600;}
.np-empty ol{margin:0;padding-left:1.2rem;color:var(--muted);line-height:1.9;}
.np-empty .find{margin-top:16px;color:var(--muted);font-size:.92rem;}
.np-footer{margin-top:44px;padding:16px 18px;border:1px solid #5a4520;background:var(--warn-bg);border-radius:14px;color:#E8D7B6;font-size:.92rem;line-height:1.6;}
div[data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--line)!important;border-radius:18px!important;background:var(--surface);}
.stButton>button{border-radius:12px;border:1px solid var(--line);font-weight:600;padding:.55rem 1.1rem;}
.stButton>button[kind="primary"]{background:var(--accent-2);border-color:var(--accent-2);color:#fff;}
.stButton>button[kind="primary"]:hover:not(:disabled){background:#7d8bff;border-color:#7d8bff;}
.stButton>button:focus-visible,textarea:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
textarea{border-radius:12px!important;}
[data-testid="stChatMessage"]{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px 16px;}
.stApp{background:radial-gradient(900px 500px at 8% -5%,rgba(108,123,255,.22),transparent 60%),radial-gradient(700px 420px at 100% 0%,rgba(19,136,8,.10),transparent 60%),radial-gradient(700px 420px at 60% -10%,rgba(255,153,51,.10),transparent 60%),var(--bg);}
.np-brand span.nm{background:linear-gradient(90deg,#FFB067 0%,#ECEEF8 45%,#7FE08A 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;}
.np-pills{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px;}
.np-pill{font-size:.8rem;padding:5px 12px;border-radius:999px;border:1px solid var(--line);background:rgba(139,155,255,.08);color:#C9D0F5;}
.np-summary{border-left:4px solid var(--accent-2);box-shadow:0 10px 30px rgba(0,0,0,.25);}
.np-card{position:relative;overflow:hidden;transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;box-shadow:0 6px 18px rgba(0,0,0,.18);}
.np-card::before{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg,var(--accent-2),transparent);}
.np-card.warn::before{background:linear-gradient(90deg,var(--warn),transparent);}
.np-card:hover{transform:translateY(-2px);border-color:var(--accent);box-shadow:0 12px 26px rgba(0,0,0,.3);}
.np-card h4{display:flex;align-items:center;gap:8px;text-transform:uppercase;letter-spacing:.06em;font-size:.8rem;}
.np-card h4 .ic{font-size:1.1rem;}
.np-step .n{background:linear-gradient(135deg,var(--accent-2),#B47CFF);box-shadow:0 4px 12px rgba(108,123,255,.4);}
.np-step{transition:border-color .18s ease;}.np-step:hover{border-color:var(--accent);}
.np-section{display:flex;align-items:center;gap:10px;}
.np-section::before{content:"";width:4px;height:1.1em;border-radius:2px;background:linear-gradient(180deg,#FF9933,#138808);}
.stButton>button[kind="primary"]{background:linear-gradient(90deg,#6C7BFF,#9A6CFF);border:0;box-shadow:0 8px 20px rgba(108,123,255,.35);padding:.7rem 1.1rem;font-size:1.02rem;}
.stButton>button[kind="primary"]:hover:not(:disabled){filter:brightness(1.1);transform:translateY(-1px);}
.stButton>button:disabled{opacity:.45;}
@media (prefers-reduced-motion:reduce){.np-card,.np-step{transition:none!important}.np-card:hover{transform:none}}
</style>
"""


def compact(markup: str) -> str:
    """Strip indentation/blank lines so Markdown never turns HTML into a code block."""
    return "\n".join(line.strip() for line in markup.splitlines() if line.strip())


def esc(text: object) -> str:
    """Escape untrusted text (AI output, notice text) for safe use inside HTML."""
    out = html.escape(str(text), quote=True).replace("$", "&#36;")  # $ would trigger math rendering
    return re.sub(r"\s*\n\s*", "<br>", out)


def md_safe(text: str) -> str:
    return text.replace("$", "\\$")  # keep rupee/dollar amounts from being parsed as LaTeX


# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------
DEFAULTS = {
    "notice_text": "",        # the notice currently analysed
    "analysis": None,         # structured JSON (dict)
    "analysis_lang": None,    # language the analysis was written in
    "language": "English",    # selected language
    "chat_history": [],       # [{"role": "user"|"assistant", "content": str}]
    "audio": None,            # {"sig": str, "bytes": bytes}
    "notice_input": "",
    "input_mode": "Paste text",
}
for _k, _v in DEFAULTS.items():
    st.session_state.setdefault(_k, _v)
# Widget-bound keys are dropped when their widget is not on screen (e.g. the text area while the
# PDF option is selected). Re-assigning them keeps pasted text and choices across reruns.
for _k in ("notice_input", "language", "input_mode"):
    st.session_state[_k] = st.session_state[_k]


def load_demo() -> None:
    st.session_state["notice_input"] = utils.DEMO_NOTICE
    st.session_state["input_mode"] = "Paste text"


def queue_question(question: str) -> None:
    st.session_state["queued_question"] = question


@st.cache_data(show_spinner=False, max_entries=20, ttl=3600)
def cached_audio(script: str, code: str) -> bytes:
    """Same text + language => same audio, generated once. Held in memory only."""
    return utils.generate_audio(script, code)


# --------------------------------------------------------------------------
# Rendering helpers
# --------------------------------------------------------------------------
def render_header() -> None:
    if FAVICON_PATH and FAVICON_PATH.suffix.lower() != ".ico":
        mark = f'<img class="logo" src="{_data_uri(str(FAVICON_PATH))}" alt="NagrikPath logo">'
    else:
        mark = '<span class="np-flag"><i></i><i></i><i></i></span>'
    hero = (
        f'<div class="np-hero-img"><img src="{_data_uri(str(HERO_PATH))}" alt="NagrikPath illustration"></div>'
        if HERO_PATH
        else ""
    )
    st.markdown(
        compact(
            f"""
            <div class="np-hero">
              <div class="np-hero-text">
                <div class="np-brand">{mark}<span class="nm">NagrikPath</span></div>
                <div class="np-tag">From Government Notice to Citizen Action</div>
                <div class="np-sub">Understand government information. Know what to do next.</div>
                <div class="np-pills"><span class="np-pill">🤖 Powered by Gemini</span><span class="np-pill">🌐 English · हिंदी</span><span class="np-pill">🔊 Audio plan</span><span class="np-pill">🔒 Answers only from your notice</span></div>
              </div>
              {hero}
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def render_empty_state() -> None:
    st.markdown(
        compact(
            """
            <div class="np-empty">
              <h3>How it works</h3>
              <ol>
                <li>Upload a government PDF, paste its text, or load the demo notice.</li>
                <li>Choose English or हिंदी.</li>
                <li>Get a plain-language action plan you can read, hear and ask questions about.</li>
              </ol>
              <div class="find">You will see: what the notice is · who it is for · documents needed · the deadline · what to do next.</div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def _value_html(text: str, big: bool = False) -> str:
    if utils.is_missing(text):
        return f'<p class="none">{esc(text)}</p>'
    return f'<p class="{"big" if big else ""}">{esc(text)}</p>'


def _list_html(items: list[str], missing_text: str) -> str:
    if not items:
        return f'<p class="none">{esc(missing_text)}</p>'
    return "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"


def card(title: str, body: str, verify: str | None = None, warn: bool = False, icon: str = "") -> str:
    foot = f'<div class="np-verify">{esc(verify)}</div>' if verify else ""
    return f'<div class="np-card{" warn" if warn else ""}"><h4><span class="ic">{icon}</span>{esc(title)}</h4>{body}{foot}</div>'


def render_results(analysis: dict, lang: str) -> None:
    L = LABELS[lang]
    missing = LANGUAGES[lang]["missing"]

    st.markdown(
        compact(
            f'<div class="np-summary"><h3>{esc(L["summary"])}</h3><p>{esc(analysis["summary"])}</p></div>'
        ),
        unsafe_allow_html=True,
    )

    cards = (
        card(L["eligibility"], _value_html(analysis["eligibility"]), L["verify"], icon="✅")
        + card(L["deadline"], _value_html(analysis["deadline"], big=True), L["verify"], icon="⏰")
        + card(L["documents"], _list_html(analysis["documents"], missing), L["verify"], icon="📄")
        + card(L["warnings"], _list_html(analysis["warnings"], missing), warn=True, icon="⚠️")
    )
    st.markdown(compact(f'<div class="np-grid">{cards}</div>'), unsafe_allow_html=True)

    steps = analysis["action_plan"]
    title = f"{len(steps)}{L['plan_n']}" if steps else L["plan"].capitalize()
    st.markdown(f'<div class="np-section">{esc(title)}</div>', unsafe_allow_html=True)
    if steps:
        body = "".join(f'<div class="np-step"><div class="n">{i}</div><div class="t">{esc(s)}</div></div>' for i, s in enumerate(steps, 1))
        st.markdown(compact(f'<div class="np-steps">{body}</div>'), unsafe_allow_html=True)
    else:
        st.markdown(compact(f'<div class="np-card">{_list_html([], missing)}</div>'), unsafe_allow_html=True)


def render_audio(analysis: dict, lang: str) -> None:
    L = LABELS[lang]
    code = LANGUAGES[lang]["code"]
    script = utils.build_audio_script(analysis, lang)
    sig = hashlib.sha1(f"{code}|{script}".encode("utf-8")).hexdigest()

    st.markdown(f'<div class="np-section">{esc(L["listen"])}</div>', unsafe_allow_html=True)
    if st.button(L["gen_audio"], key="gen_audio"):
        try:
            with st.spinner("…"):
                st.session_state["audio"] = {"sig": sig, "bytes": cached_audio(script, code)}
        except NagrikPathError as err:
            st.warning(err.user_message)
        except Exception:
            logger.exception("Unexpected audio error")
            st.warning("Audio could not be generated right now. The written plan is unaffected.")
    audio = st.session_state.get("audio")
    if audio and audio["sig"] == sig:
        st.audio(audio["bytes"], format="audio/mp3")


def render_chat(lang: str) -> None:
    L = LABELS[lang]
    st.markdown(f'<div class="np-section">{esc(L["chat"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="np-hint">{esc(L["chat_hint"])}</div>', unsafe_allow_html=True)

    cols = st.columns(len(L["examples"]))
    for i, (col, q) in enumerate(zip(cols, L["examples"])):
        col.button(q, key=f"ex_{i}", on_click=queue_question, args=(q,), width="stretch")

    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(md_safe(msg["content"]))

    typed = st.chat_input(L["chat_placeholder"])
    question = st.session_state.pop("queued_question", None) or typed
    if not question:
        return

    history_before = list(st.session_state["chat_history"])
    with st.chat_message("user"):
        st.markdown(md_safe(question))
    with st.chat_message("assistant"):
        try:
            with st.spinner("…"):
                answer = utils.chat_answer(
                    st.session_state["notice_text"], st.session_state["analysis"], history_before, question, lang
                )
        except NagrikPathError as err:
            answer = None
            st.error(err.user_message)
        except Exception:
            logger.exception("Unexpected chat error")
            answer = None
            st.error("Something went wrong while answering. Please try again.")
        if answer:
            st.markdown(md_safe(answer))
    if answer:
        st.session_state["chat_history"] += [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]


def render_footer() -> None:
    st.markdown(
        compact(
            """
            <div class="np-footer">⚠️ NagrikPath summarizes the provided document.<br>
            Always verify critical information with the original official government source.</div>
            """
        ),
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Analysis flow
# --------------------------------------------------------------------------
def run_analysis(mode: str, uploaded, lang: str) -> None:
    try:
        raw = utils.extract_pdf_text(uploaded) if mode == "Upload PDF" else st.session_state["notice_input"]
        notice, truncated = utils.prepare_notice(raw)
        if not notice:
            st.error("Please add a notice first: upload a PDF or paste some text.")
            return
        with st.spinner("Reading the notice and preparing your action plan…"):
            analysis = utils.analyze_notice(notice, lang)
    except NagrikPathError as err:
        if err.technical:
            logger.info("Analysis failed: %s", err.technical)
        st.error(err.user_message)
        return
    except Exception:
        logger.exception("Unexpected analysis error")
        st.error("Something unexpected went wrong. Please try again.")
        return

    st.session_state.update(
        notice_text=notice, analysis=analysis, analysis_lang=lang, chat_history=[], audio=None
    )
    st.success("Action plan ready. Review the details below and verify them with the official source.")
    if truncated:
        st.warning(f"This notice is very long, so only the first {utils.MAX_NOTICE_CHARS:,} characters were analysed.")


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
st.markdown(compact(CSS), unsafe_allow_html=True)
render_header()

api_key_ok = utils.get_api_key() is not None
if not api_key_ok:
    st.warning(
        "Gemini API key not found. Add GEMINI_API_KEY to a .env file (local) or to Streamlit secrets (deployed), "
        "then reload."
    )

with st.container(border=True):
    left, right = st.columns([3, 2])
    with left:
        st.radio("Language", list(LANGUAGES.keys()), key="language", horizontal=True)
    with right:
        st.button("Load demo notice", on_click=load_demo, width="stretch")

    st.radio("Input", ["Upload PDF", "Paste text"], key="input_mode", horizontal=True, label_visibility="collapsed")
    mode = st.session_state["input_mode"]
    uploaded = None
    if mode == "Upload PDF":
        uploaded = st.file_uploader("Upload a government notice (PDF)", type=["pdf"], key="pdf_file")
        has_input = uploaded is not None
    else:
        st.text_area(
            "Paste the notice text",
            key="notice_input",
            height=220,
            placeholder="Paste a government notice, circular or scheme text here…",
        )
        has_input = bool(st.session_state["notice_input"].strip())

    generate = st.button("Generate action plan", type="primary", disabled=not (has_input and api_key_ok), width="stretch")

lang = st.session_state["language"]
if generate:
    run_analysis(mode, uploaded, lang)

analysis = st.session_state["analysis"]
if analysis is None:
    render_empty_state()
else:
    result_lang = st.session_state["analysis_lang"]
    if result_lang != lang:
        st.info(
            f"The plan below is in {LANGUAGES[result_lang]['name'].split(' ')[0]}. "
            f"Press “Generate action plan” to see it in {LANGUAGES[lang]['name'].split(' ')[0]}. "
            "Chat answers already follow your selected language."
        )
    render_results(analysis, result_lang)
    render_audio(analysis, result_lang)
    render_chat(lang)
    if os.getenv("NAGRIKPATH_DEBUG") == "1":
        with st.expander("Extracted notice text (debug)"):
            st.text(st.session_state["notice_text"])

render_footer()
