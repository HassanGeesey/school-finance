# 17 — Class filter on the student list

**What to build:** The `/students` page (school-wide student list/search) gains a Class dropdown. Picking a class narrows the list to that class's students; "All classes" (the default) keeps showing everyone. The class filter combines with the existing name search, and selection survives across reloads (plain GET form).

**Blocked by:** None — can start immediately.

**Status:** implemented

- [x] A Class dropdown (All classes + every class) on the `/students` page
- [x] Selecting a class shows only that class's students; name search still applies on top
- [x] Archived students still appear (they always did)
- [x] Service seam tested: searching with a class id filters correctly; route-level test asserts the dropdown and the filtered rows

## Comments

Built. `StudentService.search_students(query, class_id=None)` now narrows by class (raising `ClassNotFound` for an unknown id, matching `list_students`); the `/students` route accepts `class_id`, 404s on an unknown class, and passes `class_options` to the template; the search form gained a Class select (All classes default, selection persists in the GET query). Class and name filters combine, archived students still show.

Verification: 7 new tests (3 service, 4 route) — 73 pass in `tests/test_students_service.py` + `test_students_routes.py`; full suite 554 passed; `mypy app` clean (46 source files). Manually smoke-tested the dropdown and class filtering in a browser.

Commit: 36d5edd

