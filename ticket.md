# Ticket Management Guide

This project follows a ticket-driven convention: every change starts as a
ticket, and the ticket is what the branch, the commits and the PR all point at.

Tracker: GitHub Issues on `Dunpark/pdf2md`, via the `gh` CLI.

## Required issue sections

Every issue body contains all five, in this order:

- `### Background` — what is wrong or missing, and why it matters now
- `### Design Decisions` — the approach chosen and what was rejected
- `### Acceptance Criteria` — observable outcomes, not implementation steps
- `### Implementation Checklist` — the work, in order
- `### Verification` — the exact commands and checks that prove it

Create the issue first, then rename it so `TICKET-NNN` matches the issue number.
An issue missing a section is not ready to start.

## Branches

| Work | Format |
|---|---|
| Feature, bug, refactor | `feat/ticket-NNN-short-description` |
| Documentation | `docs/short-description` |
| Tooling | `chore/short-description` |

Branch off `main`. Never push product changes directly to it.

## Commits

Use conventional prefixes: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`,
`style:`, `test:`.

Reference the issue in the PR, not in every commit. Use `closes #N` when the PR
should close the issue and `ref #N` otherwise.

## Pull requests

PR bodies contain:

- `### Summary`
- `### Related Issue`
- `### Key Changes`
- `### Verification` — the commands that were actually run, with their outcome
- `### Known Limitations` — including anything that could not be verified

Do not use horizontal dividers in issue or PR bodies.
