# ADR-0005: Observability: local append-only log
Status: Accepted
Area: observability

## Context
NFR-OPS needs a record of state-changing commands and switch start and
end times for the success metric, with no secrets.

## Decision
`~/.config/ais/ais.log`, 0600, opened with `O_APPEND`. Rotated at 1 MB, keeping one old file (`ais.log.1`).
One line per state-changing command: ISO 8601 UTC time, command name, account id, session ID,
result, and for switches the switch time computed from the transcript
(last usage-limit message before launch to first line after launch). Never passed-through
arguments, prompts or paths outside `~/.claude`. `ais status` prints the
provider self-check.

## Alternatives considered
- **macOS unified log (`os_log` via `logger`):** native, but harder to read
  back and not available on Linux CI.
- **No logging:** simplest, but the switch-time metric could not be
  measured.

## Consequences
- The metric is computable with `grep`.
- The log stays under about 2 MB.
