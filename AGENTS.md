# AGENTS.md

## Error Handling

- Include Beszel Hub and system context in logs.
- Preserve cached system data during partial API failures.
- Raise authentication failures so Home Assistant can start reauthentication.
- Return unavailable data as `None`; do not convert missing measurements to zero.

## Structure

- Keep the integration in `custom_components/beszel/`.
- Keep tests in `tests/`.
- Keep user-visible strings in `translations/en.json`.

## Style

- Add focused Home Assistant tests for behavioural changes.
- Follow Home Assistant conventions and prefer direct, readable code.
- Keep comments minimal and limited to complex business logic.
- Keep configuration and entity names stable unless a migration is included.
- Sort imports with Ruff and keep constants and helpers consistently ordered.
- Update `README.md` with feature changes.
