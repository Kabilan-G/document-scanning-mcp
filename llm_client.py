"""
llm_client.py — Provider-agnostic LLM client
=============================================
Switch providers via env vars:

  LLM_PROVIDER=anthropic  ANTHROPIC_API_KEY=sk-ant-...
  LLM_PROVIDER=google     GOOGLE_API_KEY=AIza...

File input — accepts EITHER:
  image_path  : local file path  (local dev / Slingshot)
  file_base64 : base64 string    (Horizon / remote clients)
  file_mime   : mime type        (required with file_base64)
"""

import os
import json
import base64
from pathlib import Path

PROVIDER   = os.environ.get("LLM_PROVIDER", "anthropic").lower()
MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "1024"))

_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "google":    "gemini-2.0-flash",
}
MODEL = os.environ.get("LLM_MODEL") or _DEFAULT_MODELS.get(PROVIDER, "claude-sonnet-4-20250514")

MIME_MAP = {
    ".jpg":  "image/jpeg", ".jpeg": "image/jpeg",
    ".png":  "image/png",  ".gif":  "image/gif",
    ".webp": "image/webp", ".pdf":  "application/pdf",
}


def _resolve_file(
    image_path:   str | None,
    file_base64:  str | None,
    file_mime:    str | None,
) -> tuple[str, str] | tuple[None, None]:
    """
    Resolve file input to (base64_data, mime_type) from either source.

    Priority:
      1. file_base64 + file_mime  — used when client sends encoded content (Horizon)
      2. image_path               — used when server has local file access (local dev)
      3. None, None               — no file provided, text-only LLM call
    """
    if file_base64 and file_mime:
        # Already encoded — validate it decodes cleanly
        try:
            base64.b64decode(file_base64, validate=True)
        except Exception:
            raise ValueError("file_base64 is not valid base64 encoded data.")
        return file_base64, file_mime

    if image_path:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {image_path}")
        mime = MIME_MAP.get(path.suffix.lower(), "image/png")
        b64  = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        return b64, mime

    return None, None


# ── Anthropic backend ──────────────────────────────────────────────────────────

def _call_anthropic(
    system:      str,
    user_text:   str,
    image_path:  str | None,
    file_base64: str | None,
    file_mime:   str | None,
) -> str:
    import anthropic
    client  = anthropic.Anthropic()
    content = []

    b64, mime = _resolve_file(image_path, file_base64, file_mime)
    if b64 and mime:
        if mime == "application/pdf":
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            })
        else:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            })

    content.append({"type": "text", "text": user_text})

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text


# ── Google Gemini backend ──────────────────────────────────────────────────────

def _call_google(
    system:      str,
    user_text:   str,
    image_path:  str | None,
    file_base64: str | None,
    file_mime:   str | None,
) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError("google-generativeai not installed. Run: pip install google-generativeai")

    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    gemini = genai.GenerativeModel(model_name=MODEL, system_instruction=system)
    parts  = []

    b64, mime = _resolve_file(image_path, file_base64, file_mime)
    if b64 and mime:
        import google.generativeai.types as gtypes
        parts.append(gtypes.BlobDict(mime_type=mime, data=base64.b64decode(b64)))

    parts.append(user_text)
    response = gemini.generate_content(parts)
    return response.text


# ── Public API ─────────────────────────────────────────────────────────────────

def call_llm(
    system:      str,
    user_text:   str,
    image_path:  str | None = None,   # local file path
    file_base64: str | None = None,   # base64 encoded file content
    file_mime:   str | None = None,   # mime type for base64 input
) -> str:
    """
    Call the configured LLM. Accepts file as path OR base64.

    Local dev:  pass image_path="C:/docs/dci_cert.pdf"
    Horizon:    pass file_base64="<encoded>", file_mime="application/pdf"
    """
    if PROVIDER == "anthropic":
        return _call_anthropic(system, user_text, image_path, file_base64, file_mime)
    elif PROVIDER == "google":
        return _call_google(system, user_text, image_path, file_base64, file_mime)
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER='{PROVIDER}'. Supported: anthropic, google")


def call_llm_json(
    system:      str,
    user_text:   str,
    image_path:  str | None = None,
    file_base64: str | None = None,
    file_mime:   str | None = None,
) -> dict:
    """Same as call_llm but parses response as JSON. Strips markdown fences automatically."""
    raw   = call_llm(
        system      = system + "\n\nRespond ONLY with valid JSON. No markdown fences, no preamble.",
        user_text   = user_text,
        image_path  = image_path,
        file_base64 = file_base64,
        file_mime   = file_mime,
    )
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(clean)


def current_provider_info() -> dict:
    return {"provider": PROVIDER, "model": MODEL, "max_tokens": MAX_TOKENS}