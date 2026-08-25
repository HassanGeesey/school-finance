# School Finance Web App — Resources

## Knowledge

- [FastAPI: First Steps & Tutorial](https://fastapi.tiangolo.com/tutorial/)
  Official guide: routers, dependencies (the `Depends(...)` gates), request/response model. Use for: the backend layer of this app — it is a FastAPI app (`app/main.py`).
- [FastAPI: Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
  Explains `Depends(require_login)` patterns exactly like `app/auth/deps.py`. Use for: understanding the auth/role gates.
- [Jinja2 Template Designer Documentation](https://jinja.palletsprojects.com/en/3.1.x/templates/)
  The template language all pages in `app/templates/` are written in (`{{ }}`, `{% %}`, filters like `money`). Use for: reading/modifying page templates.
- [HTMX: htmx docs](https://htmx.org/docs/)
  The library behind partial page updates (forms posting to the same URL, swapping HTML sections) — `app/static/js/htmx.min.js`. Use for: understanding why pages update without full reloads.
- [SQLAlchemy 2.0 ORM Tutorial](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)
  ORM used to fetch/save records. Use for: the database layer behind the services.
- [MDN: How the Web Works](https://developer.mozilla.org/en-US/docs/Learn/Getting_started_with_the_web/How_the_web_works)
  Ground-level primer on request/response. Use for: first-lesson orientation if any concept feels shaky.
- Local: `graphify-out/GRAPH_REPORT.md` + `graphify-out/graph.html`
  Knowledge graph of this very codebase (2637 nodes) with communities (e.g. "Debt Age & Fee Billing Engine", "Auth Dependency Chain"). Use for: locating related code and seeing architecture clusters.
- Local: `CONTEXT.md`, `docs/adr/`, `project-decisions.md`
  The project's own domain docs and decision log. Use for: why things are the way they are.

## Wisdom (Communities)

- [FastAPI Discussion Forum](https://discuss.fastapi.tiangolo.com/)
  Official Q&A forum. Use for: real-world troubleshooting when the docs don't cover a case.
- [r/fastapi](https://reddit.com/r/fastapi)
  Active practitioner community. Use for: patterns, pitfalls, review of design choices.
- [r/htmx](https://reddit.com/r/htmx)
  Community around the HTMX approach. Use for: server-rendered UI patterns and pitfalls.

## Gaps

- No single trusted resource that connects FastAPI + Jinja2 + HTMX + SQLAlchemy as one walking path; the lessons themselves fill this with the app's real request journey.