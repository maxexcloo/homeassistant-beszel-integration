# AGENTS.md

## Error handling

- Include Beszel Hub and system context in logs.
- Preserve cached system data during partial API failures.
- Raise authentication failures so Home Assistant can start reauthentication.
- Return unavailable data as `None`; do not convert missing measurements to zero.

## Structure

- Keep the integration in `custom_components/beszel/`.
- Keep only `AGENTS.md` and `README.md` as root Markdown files; put other project
  documentation in `docs/`.
- Keep tests in `tests/`.
- Keep user-visible strings in `translations/en.json`.

## Style

- Add focused Home Assistant tests for behavioural changes.
- Follow Home Assistant conventions and prefer direct, readable code.
- Keep comments minimal and limited to complex business logic.
- Keep configuration and entity names stable unless a migration is included.
- Preserve `LICENSE` and its legal text; never relicense without explicit approval.
- Sort imports with Ruff and keep constants and helpers consistently ordered.
- Sort unordered peer entries by value shape: simple or single-line values first,
  then structured or multiline values, alphabetically within each group.
- Sort unordered peer headings, lists, and table rows alphabetically. Preserve
  narrative, procedural, dependency, interface, priority, and chronological order.
- Update `README.md` with feature changes.
- Use `.yaml`, never `.yml`, for project-owned YAML files unless external tooling
  requires a fixed filename.
- Use Australian English throughout authored prose and every project-owned name,
  including identifiers, configuration keys, environment variables, paths, CLI
  commands, and options. Update every producer and consumer together; preserve only
  externally defined names and terminology.

## Verification

- Run `mise run check` before handoff.
