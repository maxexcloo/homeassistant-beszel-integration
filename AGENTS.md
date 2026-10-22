# AGENTS.md

## Structure

- Keep user-visible strings in `translations/en.json`.
- Group Beszel field constants by their source struct and sort each group alphabetically.

## Behaviour

- Include Beszel Hub and system context in logs.
- Preserve cached system data during partial API failures.
- Return unavailable data as `None`; do not convert missing measurements to zero.

## Compatibility

- Keep configuration and entity names stable unless a migration is included.
