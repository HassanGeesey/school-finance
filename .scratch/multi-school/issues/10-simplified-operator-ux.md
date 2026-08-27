# 10 — Simplified operator UX

**Status:** ready-for-agent
**Label:** ready-for-agent
**Type:** task

## Problem Statement

School Finance currently exposes too much of its capability at once. A Campus Admin or Finance Officer must scan a broad sidebar, dense dashboard, competing header buttons, repeated cards, and report-heavy layouts before finding the next operational task.

The most frequent desk workflow is simple: understand the current Owed Month, find a student, record a Month-tagged Payment, print the receipt, and follow up students with unpaid fees. The interface should make that workflow obvious without hiding the existing financial truth, role boundaries, audit behavior, or reporting capability.

There are also visible copy-quality problems caused by corrupted character encoding, including mojibake in search and payment-related text. This undermines trust in a finance application.

## Solution

Rework the web interface around task-based operation while preserving all existing routes, permissions, billing calculations, and data behavior.

The shared navigation will organize the product into Overview, Collect payments, Follow up unpaid fees, Manage, Review, and System. Each page will have one clear primary action. The Campus dashboard will lead with the current month and actionable work lanes, then show recent activity and secondary reporting.

Payment recording will remain the central high-frequency flow: search student, select Owed Month, enter amount, review the Expected Amount and existing payments, record the Month-tagged Payment, and print or reprint the receipt. The interface will preserve useful context and defaults for repeat work.

Copy will be normalized to UTF-8 and plain English. Responsive layouts will prioritize touch-friendly collection and follow-up work on narrow screens.

## User Stories

1. As a Finance Officer, I want to open the Overview and immediately see the current Owed Month, so that I know which period I am working in.

2. As a Finance Officer, I want the Overview to show what needs attention today, so that I do not have to inspect multiple reports before starting work.

3. As a Finance Officer, I want one obvious action for recording a payment, so that I can begin collection work immediately.

4. As a Finance Officer, I want a dedicated Follow up unpaid fees action, so that I can open the oldest unpaid balances without remembering where the report lives.

5. As a Finance Officer, I want the Overview to show recent payments after the actionable work, so that I can confirm recent activity without giving it more priority than unfinished work.

6. As a Finance Officer, I want reports and charts to remain available without dominating the first viewport, so that review work does not compete with daily collection work.

7. As a Campus Admin, I want navigation grouped by work rather than by implementation module, so that the interface matches how I think about my job.

8. As a Campus Admin, I want Manage to contain Students, Classes, and Fee setup, so that structural tasks are grouped together.

9. As a Finance Officer, I want Review to contain Expenses and Reports, so that analysis is separated from payment collection.

10. As a Campus Admin, I want System actions such as Audit log and Settings separated from daily work, so that infrequent administrative actions do not add noise.

11. As a Superadmin, I want the School Dashboard and Campus drill-down to keep their existing read-only rules, so that simplifying navigation does not expose mutation controls.

12. As an Owner/Shareholder, I want the read-only state to remain obvious, so that I do not mistake monitoring screens for editable screens.

13. As a Finance Officer, I want each page to have one primary action, so that I can identify the intended next step without comparing several equally prominent buttons.

14. As a Finance Officer, I want secondary actions such as Reports, Back, and Reprint to be visually subordinate, so that they do not compete with recording money.

15. As a Finance Officer, I want form commit and cancel actions grouped consistently, so that I know where to finish or leave every form.

16. As a Finance Officer, I want table row actions to use the same placement and wording everywhere, so that I can operate ledgers quickly.

17. As a Finance Officer, I want the payment form to begin with student search, so that the rest of the form is contextual to the selected student.

18. As a Finance Officer, I want the selected student''s name, class, Monthly Amount, Expected Amount, paid amount, and remaining amount visible while recording a payment, so that I do not need to switch screens.

19. As a Finance Officer, I want the payment form to show the relevant Owed Month clearly, so that I do not mis-tag a payment.

20. As a Finance Officer, I want the payment form to remember the last-used month and method when safe, so that repeated entries require less typing.

21. As a Finance Officer, I want the form to explain partial payments and Credit in plain language, so that I understand how the payment will affect the student''s account.

22. As a Finance Officer, I want a successful payment to confirm the amount, student, and Owed Month, so that I can trust the record was saved.

23. As a Finance Officer, I want a Record another payment action after success, so that I can continue a collection session without rebuilding the workflow.

24. As a Finance Officer, I want the receipt action to be immediately available after payment, so that I can serve the parent without searching for the payment again.

25. As a Finance Officer, I want validation messages next to the field that needs correction, so that I can recover without guessing.

26. As a Finance Officer, I want invalid form submissions to preserve all valid fields I already entered, so that an error does not force duplicate work.

27. As a Finance Officer, I want destructive actions such as archive or disable to state their consequence before confirmation, so that I can prevent accidental mutations.

28. As a Finance Officer, I want empty lists to explain what is empty and offer the next useful action, so that a blank page never leaves me stuck.

29. As a first-time Campus Admin, I want terms such as Owed Month, Expected Amount, Waiver, and Credit explained near their first use, so that I can operate correctly without separate training.

30. As a Finance Officer, I want “unpaid fees” used alongside or instead of “arrears” where possible, so that the wording is immediately understandable.

31. As a Finance Officer, I want “Recent payments” used instead of “Recent Month-tagged Fee Collections” in summary headings, so that the interface remains precise without sounding technical.

32. As any user, I want all interface text to render as intended UTF-8, so that corrupted symbols do not make records appear unreliable.

33. As a keyboard user, I want a visible focus state on every interactive control, so that I can navigate the app without a mouse.

34. As a keyboard user, I want Escape to close dialogs and menus and return focus appropriately, so that I can leave temporary states safely.

35. As a keyboard user, I want shortcuts for payment recording, student search, and unpaid-fee follow-up, so that repeated desk work is faster without removing visible controls.

36. As a screen-reader user, I want action links and icon buttons to have meaningful accessible names, so that no task depends on visual interpretation.

37. As a screen-reader user, I want success, error, loading, and read-only states announced, so that I know what changed.

38. As a low-vision user, I want status to be communicated by text as well as color, so that green, amber, and red are not the only signals.

39. As a mobile Finance Officer, I want the primary collection action within easy thumb reach, so that I can record a payment one-handed.

40. As a mobile Finance Officer, I want recent activity represented as compact list rows rather than requiring wide table scrolling, so that important information remains readable.

41. As a mobile Finance Officer, I want touch targets to be comfortably tappable and spaced apart, so that I do not trigger the wrong action.

42. As a mobile Finance Officer, I want the selected student and Owed Month context to remain visible while scrolling a long payment form, so that I do not lose track of what I am recording.

43. As a Campus Admin, I want the simplified interface to preserve direct URLs and existing route behavior, so that bookmarks and established workflows continue to work.

44. As a Campus Admin, I want campus scope and read-only status to remain visible in the shell, so that tenant boundaries are never ambiguous.

45. As an Admin, I want the School Profile, Logo, Contact Details, and printed receipt behavior unchanged, so that this UX change does not alter parent-facing documents.

46. As a Finance Officer, I want all financial arithmetic to remain derived by the existing services, so that a visual redesign cannot introduce a discrepancy in Expected Amount, Waiver, payment, or Credit behavior.

## Implementation Decisions

- The highest test seam is the existing authenticated HTTP route layer, using the current TestClient fixtures and rendered HTML as the external behavior boundary.
- The shared shell navigation will be reorganized into task groups: Work (Overview, Collect payments, Follow up unpaid fees), Manage (Students, Classes, Fee setup), Review (Expenses, Reports), and System (Audit log, Settings where permitted).
- Existing route URLs and authorization behavior remain unchanged. This is an information architecture and presentation change, not a route migration.
- The current Campus Admin, Finance Officer, Superadmin, and Owner/Shareholder role distinctions remain unchanged.
- The Overview dashboard will place current-period status and two primary work lanes before recent activity and secondary charts.
- The dashboard will retain existing KPIs, payment records, expense records, reports, and charts; their order and visual emphasis will change.
- Each page will expose one filled primary action at the page level. Secondary actions use an outlined or text treatment, and destructive actions use the existing destructive confirmation pattern.
- Payment recording remains a Month-tagged Payment against an Owed Month. No new Charge rows, generation step, or billing arithmetic is introduced.
- The payment UI will keep student, class, Monthly Amount, Expected Amount, paid amount, Credit, and remaining context available during entry where the existing service supplies it.
- Repeat-payment affordances may preserve non-sensitive display defaults such as Owed Month and payment method, but must not bypass review or confirmation.
- Copy will use the project''s domain glossary: School, Campus, Campus Admin, Finance Officer, School Dashboard, Fee Template, Monthly Amount, Owed Month, Expected Amount, Waiver, Closed Month, Month-tagged Payment, and Credit.
- Interface files will be normalized to UTF-8 without changing user data, printed document content, or financial values.
- All interactive states will retain visible keyboard focus, meaningful labels, and text alternatives for color-coded statuses.
- Responsive behavior will be implemented with CSS and existing templates/components; no separate mobile application or route set is needed.
- Existing icon macros and the current icon system will be reused. Unicode characters and emoji will not be introduced as icon substitutes.
- The design remains light and professional, using the established School Finance palette and Inter type system.

## Testing Decisions

- Tests assert external behavior and rendered content, not selector names, template implementation details, or CSS internals.
- Existing route tests are the primary prior art and should cover role-specific navigation, dashboard ordering/content, payment success, validation recovery, and preserved authorization.
- Add authenticated route tests confirming:
  - Campus Admin and Finance Officer see the task-based navigation.
  - Superadmin and Owner/Shareholder retain School Dashboard/read-only behavior.
  - Existing route URLs continue to resolve.
  - Payment recording still records the correct Month-tagged Payment and provides receipt access.
  - Invalid payment submissions preserve expected user-entered values and show actionable messages where supported.
- Add template/render tests for the Overview work lanes, one-primary-action rule on representative pages, empty-state next actions, accessible names, and read-only notices.
- Add browser-level checks at desktop and narrow mobile widths for:
  - Navigation grouping and active states.
  - Header action alignment.
  - Dashboard work-lane order.
  - Payment form context visibility.
  - Responsive table/list behavior.
  - Focus visibility, Escape dismissal, and touch target sizing.
- Add a text scan or fixture assertion preventing known mojibake sequences in user-facing templates.
- Run the existing full suite and type checks; the current multi-school baseline must remain green.
- Verify that printed receipts and statements are unchanged except for intentional copy encoding repairs.
- Run the Impeccable detector on changed markup and CSS after implementation, then perform one batched desktop/mobile visual review.

## Out of Scope

- Changing the billing model, Expected Amount calculations, Waiver behavior, Closed Months, Month-tagged Payments, or Credit allocation.
- Adding new roles, changing role permissions, or changing tenant/campus authorization.
- Changing database schema or introducing new API endpoints solely for presentation.
- Replacing the School Profile, Logo, Contact Details, or printed receipt layout.
- Replacing the existing icon library or introducing a new visual brand.
- Building a native mobile app.
- Adding cloud provisioning, deployment, notifications, SMS, email, or parent accounts.
- Rewriting all reports or removing financial reporting capability.
- Changing user data or historical audit records.
- Restoring unrelated worktree files or resolving unrelated in-flight feature work.

## Further Notes

This ticket is intended to follow the completed tenant-layer tickets and preserve the existing multi-school contract. The redesign should be delivered incrementally: shared shell and copy cleanup first, then dashboard hierarchy, then payment-flow refinements, then responsive/accessibility verification.


