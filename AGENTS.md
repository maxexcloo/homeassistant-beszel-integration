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
- Group Beszel field constants by their source struct and sort each group alphabetically.
- Keep configuration and entity names stable unless a migration is included.
- Update `README.md` with feature changes.
