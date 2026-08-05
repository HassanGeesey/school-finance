# AGENTS.md

## Working rules

- **Grilling session rule:** During design/grilling conversations, after every user answer, record the question and answer in `project-decisions.md`. Keep that file updated as the single source of truth for project decisions.
- **Ticket completion rule:** When you finish implementing a ticket, check off its checklist items in the ticket file (`.scratch/<feature>/issues/`), set its `Status:` to `implemented`, append a `Comments` section recording what was built, verification results, and the commit hash — then commit the work to the current branch.
- **chromedev toolmcp** whe using it try to use as fast as possible .


## Agent skills

### Issue tracker

Local markdown — issues live as files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles with default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
