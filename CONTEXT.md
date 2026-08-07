# School Finance App

A single-machine finance app for one real school: fee collection, expenses, and arrears tracking. Admin and Finance officer roles.

## Language

**School Name**:
The name of the real school the app runs for (e.g. "Sunrise Primary School"). It is configurable in Settings and appears wherever parents or printed documents are addressed — receipts, the sidebar brand, tab titles, and the footer.
_Avoid_: System name, App name

**App Name**:
The product name of the software itself, fixed as "School Finance". It is the software's identity (setup wizard, Settings page context) and is never the school's name.
_Avoid_: Program name, Software name

**School Profile**:
The school's identity as shown to parents and on printed documents: the School Name, the Logo, and the Contact Details. Configured by an Admin in Settings, collected on first launch (name only), stored as a single row in the database, and rendered live at print time.
_Avoid_: Branding, Settings, System configuration

**Logo**:
An image file representing the school, uploaded by an Admin. It lives as a file next to the app data (not in the bundled static assets) and shows centred in the sidebar brand and at the top of printed receipts. Falls back to the default icon when absent.
_Avoid_: Icon, Picture, Brandmark

**Contact Details**:
The optional free-text contact block of the School Profile — Address, Phone, Email, and Website. No validation; blank fields simply do not display on printed documents.
_Avoid_: Contact info, Contact fields, Details
