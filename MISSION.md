# Mission: Understand the School Finance Web App

## Why
The user maintains and extends this FastAPI + Jinja2 + HTMX school finance app. They have some code exposure (seen HTML/Python, never built anything real) and their priority is knowing *how everything connects* — the request journey from browser to database and back — so they can fix bugs and add features with confidence instead of guessing.

## Success looks like
- Trace any feature end-to-end: URL → route → service → database → template → page, naming the actual files
- Read a new page's code and explain where its data comes from and how it updates (full reload vs HTMX swap)
- Make a small real change (fix a bug or add a simple page) and see it work
- Use the knowledge graph (`graphify-out/`) and domain docs to find related code fast

## Constraints
- Beginner-leaning: keep lessons short, concrete, tied to real files in THIS repo
- One lesson per session, completable in a few minutes
- Prefers understanding the actual app over generic web-dev theory
- Windows machine; lessons open in the browser

## Out of scope
- Deep Python language mastery (type theory, metaprogramming)
- Frontend framework lands (React/Vue) — the app is server-rendered with HTMX
- Desktop launcher internals (`app/desktop/`) unless requested
- Database administration beyond the app's own usage