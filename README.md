# 🇮🇳 NagrikPath

**From Government Notice to Citizen Action**

> Understand government information. Know what to do next.

NagrikPath turns complicated government notices, scheme documents and circulars into a short, plain-language action plan, in **English or हिंदी**, with audio and a follow-up chat that answers **only from the notice you provided**.

---

## Problem

Government notices are long, formal and full of jargon. Many citizens miss deadlines, bring the wrong documents, or never learn they were eligible, not because the information is hidden, but because it is hard to read and act on. Language and accessibility barriers make this worse.

## Solution

Upload a PDF or paste the notice text. NagrikPath extracts what matters and answers five questions right away:

1. What is this?
2. Who is it for?
3. Which documents are needed?
4. What is the deadline?
5. What should I do next?

The AI is instructed to use **only** the supplied notice. Anything the notice does not say is reported as *"Not specified in the provided notice."* rather than guessed.

## Features

- **Two input methods:** PDF upload (multi-page, via `pypdf`) or pasted text
- **English / हिंदी** selector controlling the action plan, chat answers and audio
- **Structured analysis:** summary, eligibility, documents, deadline, action plan (up to 3 steps), warnings
- **Anti-hallucination prompt:** no invented facts, deadlines, documents, portals, fees or eligibility; never says a citizen is *definitely* eligible; verification reminders on key cards
- **Safe JSON handling:** strips markdown fences, validates and coerces fields, fills missing ones, retries once on malformed output, never crashes the app
- **Text-to-speech** with gTTS (`en` / `hi`), generated in memory and cached
- **Grounded follow-up chat** using the notice, the extracted JSON and recent history (last 8 messages)
- **One-click demo notice** (fictional)
- **Friendly errors** for missing API key, invalid or empty PDF, empty text, rate limits, network problems, malformed AI output and TTS failures. Secrets and stack traces are never shown in the UI.
- Dark, responsive UI with custom CSS. No database.

## Architecture

```
Government PDF / text
        ↓
  pypdf text extraction         (utils.extract_pdf_text)
        ↓
  Gemini (google-genai)         (utils.analyze_notice + prompts.py)
        ↓
  Structured JSON → validated   (utils.extract_json / validate_analysis)
        ↓
  Citizen dashboard             (app.py)
        ↓
  English / हिंदी → gTTS audio  (utils.generate_audio)
        ↓
  Follow-up chat                (notice + JSON + history → Gemini)
```

```
nagrikpath/
├── app.py            # Streamlit UI, session state, rendering
├── prompts.py        # Analysis prompt + chat prompt
├── utils.py          # PDF, Gemini, JSON safety, TTS, demo notice
├── requirements.txt
├── .env.example
├── .gitignore
├── .streamlit/config.toml   # dark theme, upload limit (no secrets)
└── README.md
```

## Tech stack

Python 3.10+ · Streamlit · `google-genai` (Google's current Gen AI SDK) · pypdf · gTTS · python-dotenv

## Local setup

```bash
git clone <your-repo-url> nagrikpath
cd nagrikpath

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # Windows: copy .env.example .env
# edit .env and paste your Gemini API key
```

Get a key from [Google AI Studio](https://aistudio.google.com/apikey).

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Gemini API key. Read from Streamlit secrets first, then `.env` / environment. |
| `GEMINI_MODEL` | No | Force a specific model. If unset, NagrikPath tries `gemini-3.5-flash`, then `gemini-flash-latest`, then `gemini-2.5-flash`. |
| `NAGRIKPATH_DEBUG` | No | Set to `1` to show an "Extracted notice text" panel for debugging PDFs. |

> **Models:** `gemini-1.5-flash` and `gemini-2.0-flash` are retired, so they are not used. Model availability changes. If you see a "model not available" message, set `GEMINI_MODEL` to a current Flash model listed at <https://ai.google.dev/gemini-api/docs/models>.

## How to run

```bash
streamlit run app.py
```

Then open the URL shown in the terminal (usually <http://localhost:8501>).

**Quick demo (2-3 minutes):** click *Load demo notice* → pick English or हिंदी → *Generate action plan* → review Eligibility / Documents / Deadline / Steps → *Generate audio* → ask "Where should I apply?" in the chat. The demo notice says applications go through "the designated official portal" but never names it, so the assistant should say exactly that: what the notice states, and where it stops. For a bare *"Not specified in the provided notice."* answer, ask something the notice never covers, such as "What is the income limit?" or "What is the application fee?". Wording can vary between runs, so try it once before presenting.

## Deployment on Streamlit Community Cloud

1. Push this project to a **public or private GitHub repo**. Confirm `.env` is **not** committed (it is in `.gitignore`).
2. Go to <https://share.streamlit.io> → **Create app** → select the repo, branch, and set **Main file path** to `app.py`.
3. Open **Advanced settings → Secrets** and add:
   ```toml
   GEMINI_API_KEY = "your_real_key_here"
   ```
4. Click **Deploy**. Streamlit installs `requirements.txt` automatically.

Never commit a real key. `.streamlit/secrets.toml` is git-ignored for local use.

## Limitations

- **No OCR:** scanned or image-only PDFs have no extractable text and are rejected with a clear message. Paste the text instead.
- **Only as accurate as the source and the model.** Outputs can still contain mistakes. NagrikPath summarizes the document; always verify critical details with the original official source.
- Very long notices are truncated to the first 60,000 characters.
- Text-to-speech needs internet access (gTTS calls Google's service) and Hindi voice quality depends on it.
- Not legal advice, and it does not check real-world eligibility.
- Follow-up chat is grounded by prompting. It is designed to refuse outside knowledge, but LLM behaviour cannot be guaranteed.
- Free-tier Gemini quotas can cause temporary "busy" errors.
- No accounts, no database, and no saved history. State lives only in the browser session.

## Future scope (not implemented)

These are **FUTURE** ideas, not current features:

- More Indian languages
- Official-source verification (checking details against government portals)
- Voice input
- Government portal integrations
- OCR for scanned PDFs
- Personalized accessibility features

## Disclaimer

⚠️ NagrikPath summarizes the provided document. Always verify critical information with the original official government source. The bundled demo notice is fictional.
