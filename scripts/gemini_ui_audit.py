"""
Gemini 2.5 Flash UI audit — sends the key UI artifacts to Gemini for improvement suggestions.
Run: python scripts/gemini_ui_audit.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Collect source files
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"
CSS_SRC = ROOT / "assets-src" / "input.css"

FILES: dict[str, Path] = {
    "base.html": TEMPLATES / "base.html",
    "ui.html": TEMPLATES / "components" / "ui.html",
    "home.html": TEMPLATES / "home.html",
    "students/account.html": TEMPLATES / "students" / "account.html",
    "payments/index.html": TEMPLATES / "payments" / "index.html",
    "input.css": CSS_SRC,
}

# Only send the first 250 lines of input.css (tokens + core components)
CSS_LIMIT = 250


def read_file(path: Path, limit: int = 0) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if limit:
        lines = text.splitlines(keepends=True)
        text = "".join(lines[:limit]) + f"\n... ({len(lines)} total lines)\n"
    return text


# ---------------------------------------------------------------------------
# 2. Build the prompt
# ---------------------------------------------------------------------------
sections: list[str] = []
for label, path in FILES.items():
    limit = CSS_LIMIT if label == "input.css" else 0
    content = read_file(path, limit)
    sections.append(f"### {label}\n```html\n{content}\n```" if label.endswith(".html") else f"### {label}\n```css\n{content}\n```")

file_context = "\n\n".join(sections)

PROMPT = f"""You are a senior UI/UX designer reviewing a school finance web application.

## Technology stack
- FastAPI + Jinja2 templates + htmx (no React/Vue — all server-rendered)
- Tailwind CSS v4.3.3 + DaisyUI 5.7.22
- Chart.js for data visualizations
- Vanilla JavaScript (ui.js)
- Dark mode via CSS custom properties + data-theme attribute

## Design system
The app uses a "Calm Slate" design system with these tokens:
- Colors: slate-900 primary, slate-50 canvas, white surface
- Accents: emerald (success/income), amber (warning), rose (error/expenses), indigo (info)
- Typography: Inter font, 13px body, tabular-nums for amounts
- Spacing: 4/8/16/24/32px scale
- Layout: 240px sidebar + sticky topbar + 1280px max workspace

## Files to review
{file_context}

---

## Your task

Analyze the UI code above and suggest **specific, actionable improvements** across these 4 categories.
For each suggestion, provide:
1. **Priority** (high / medium / low)
2. **Category** (Visual Design / UX & Usability / Consistency / Accessibility)
3. **What to change** — the exact file and what to modify
4. **Why** — the specific problem it solves
5. **How** — the concrete implementation (CSS values, HTML changes, etc.)

## Rules
- Only suggest changes that are realistic for a school finance SaaS — don't suggest radical redesigns
- Focus on polish and professional quality — the baseline is already solid
- Be specific: "change X to Y" not "improve X"
- No more than 15 suggestions total (quality over quantity)
- Skip anything that's already good — only call out real weaknesses
- Prioritize changes that have the highest visual/UX impact for the least effort

Output as a numbered list grouped by category.
"""

# ---------------------------------------------------------------------------
# 3. Call Gemini 2.5 Flash
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyBETFHzMt30nAZhLoaCuhepbezG-RHUUac")
MODEL = "gemini-2.5-flash-preview-05-20"

try:
    from google import genai
    client = genai.Client(api_key=API_KEY)
    response = client.models.generate_content(
        model=MODEL,
        contents=PROMPT,
    )
    print(response.text)
except Exception as exc:
    # Fallback: try REST directly
    import urllib.request
    import json

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    payload = json.dumps({"contents": [{"parts": [{"text": PROMPT}]}]}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            print(data["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as e2:
        print(f"ERROR: Both SDK and REST failed.\nSDK: {exc}\nREST: {e2}", file=sys.stderr)
        sys.exit(1)
