# ADR-0001: Language and runtime: Python 3.9+ standard library
Status: Accepted
Area: language

## Context
A small CLI for one Mac. It must run without installing anything new,
be easy to test with fake `claude`, `security` and `lsof` programs, and
leave room for more providers (requirements FR-5). Apple's Command Line
Tools ship `/usr/bin/python3` (3.9.x on current macOS releases; the G-1
spike records the exact version on the user's Mac).

## Decision
Python 3.9 or newer, standard library only. No third-party packages.
Code must not use syntax newer than 3.9 (no `match`, no `X | Y` type
unions at runtime, no `tomllib`).

## Alternatives considered
- **zsh scripts:** fastest to write and no runtime, but weak for JSON,
  locking, path checks and unit tests; the reviewer suggested it for the
  spike, where it stays allowed.
- **Swift:** native, as Claude Switcher is, but needs Xcode to build and
  is heavier to test with fakes.
- **Go:** single binary, but needs a toolchain and a build step for one
  user's tool.

## Consequences
- Zero install beyond Apple's developer tools.
- Tests run in CI on Linux with the same code.
- Python 3.9 limits newer language features.
