# AI-Market Agent Instructions

## Canonical Sources

- Use `README.md` for installation and service startup.
- Use `PROJECT_OVERVIEW.md` as the canonical source for architecture, pipeline behavior,
  configuration, tests, evaluation commands, and example queries.
- Read only the sections relevant to the current task; do not duplicate those documents here.

## Project Contracts

- Keep code identifiers, file names, and inline comments in English.
- Keep catalog/database content in Turkish.
- Keep all user-facing application text in Turkish.
- PostgreSQL is the only product catalog source. Do not add a CSV fallback.
- Preserve the embedding/order contract: products load with `ORDER BY id`, the finalized
  DataFrame keeps a stable `0..N-1` index, and embeddings must remain aligned to that order.
- Ollama is only a normalizer and response writer. It must not create, remove, or reorder
  products; every Ollama failure must retain a deterministic fallback.
- Preserve unrelated user changes and avoid destructive database reseeding unless explicitly
  requested.

## Verification

- Run backend commands from `backend/` with the project virtual environment.
- Use the verification command appropriate to the change; the complete command matrix is in
  `PROJECT_OVERVIEW.md` under “Test ve Doğrulama Altyapısı”.
- Frontend changes should at least pass the relevant `npm run lint` or `npm run build` check.

## Token-Efficient Shell Output

When `rtk` is installed, prefix shell commands with `rtk` to reduce tool-output size. Prefix
each segment of a command chain. If `rtk` is unavailable, run the underlying command normally.
For debugging unfiltered output, use `rtk proxy <command>` or the raw command.
