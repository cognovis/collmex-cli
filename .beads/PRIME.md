# Beads Workflow Context

> Auto-loaded at session start by the SessionStart hook (Claude + Codex).
> Re-run `bd prime` after compaction. This file is the single source of truth
> for "how to work with bd in this repo." Do NOT duplicate its content in
> AGENTS.md, CLAUDE.md, or skills.

## Default rules

- Use `bd` for ALL task tracking. No `TodoWrite`, no `TaskCreate`, no `MEMORY.md`.
- Create a bead BEFORE writing code. Mark `in_progress` when starting.
- Memory lives in **open-brain**. **Coding harness (Claude Code / Codex CLI):** use
  `ob save` / `ob search` (direct connection, no MCP round-trip). **Mobile / admin
  (claude.ai, iOS):** use `mcp__open-brain__save_memory`. Do NOT use
  `bd remember` / `bd memories` / `bd forget` — they exist in the bd CLI but are
  not part of this workflow.
- Source code is English (comments, identifiers, log messages). User-facing
  strings may be localized.
- Work is NOT done until `git push` succeeds.

## Entrypoints

| When | Do |
|---|---|
| Start work on bead `<id>` | `cld -b <id>` (Claude) or `cdx -b <id>` (Codex) |
| Quick-fix XS/S bug | `cld -bq <id>` / `cdx -bq <id>` |
| User says "implement bead X" / "arbeite an bead X" in chat | Spawn the `bead-orchestrator` agent with bead_id=X (Claude: `Agent(subagent_type="...:bead-orchestrator")`; Codex: spawn the agent defined in `~/.codex/agents/bead-orchestrator.toml`) |
| Find work | `bd ready` (or `bd list --status=open`) |
| Show details | `bd show <id>` |

The orchestrator self-routes to quick-fix in Phase 0 if the bead's `effort` and
`type` match the quick-fix profile, so spawning the full orchestrator is always
safe.

## Bead types — the 9 built-ins

`bd types` lists what's valid. Aliases: `feat`/`enhancement` → `feature`,
`adr`/`dec` → `decision`. Custom types via `types.custom` (currently unset).

| Type | When to use | bd lint requires |
|---|---|---|
| `task` (default) | Internal work, not user-facing. Refactors, infra, docs, tooling. | Acceptance Criteria |
| `bug` | Something is broken. Behavior diverges from intent. | Steps to Reproduce + Acceptance Criteria |
| `feature` | New user-facing capability. **Project rule: also requires `## Scenario` section** (orchestrator Phase 0 blocks if missing). | Acceptance Criteria |
| `chore` | Boring maintenance: dep bumps, lint, formatting, version tags. | (none) |
| `epic` | Tracking parent for many beads. Don't implement directly — slice into children. | Success Criteria |
| `decision` | Architecture Decision Record (ADR). Tag with `--add-label=decision`. | (none enforced) |
| `spike` | Timeboxed investigation to reduce uncertainty before committing to a story. Output: notes + a follow-up bead. | (none enforced) |
| `story` | User story describing a feature from the user's perspective. We rarely use this — prefer `feature`. | (none enforced) |
| `milestone` | Marks completion of a set of related issues. Contains no work. | (none enforced) |

**In practice we use `task / bug / feature / chore / epic / decision`. The other
three (`spike / story / milestone`) are valid but dormant.**

Validate before claim: `bd lint <id>` (or `bd lint` for all open). The
orchestrator's Phase 0 also runs the scenario check for features.

## Priority

| Value | Meaning |
|---|---|
| `0` / `P0` | Critical — production down, security, data loss |
| `1` / `P1` | High — important features, blocking bugs |
| `2` (default) | Medium |
| `3` | Low — polish, optimization |
| `4` | Backlog |

Pass numeric (`-p 1`) or label (`-p P1`). Do NOT pass `high`/`medium`/`low` — bd
rejects them.

## Effort

Set with `bd update <id> --metadata='{"effort":"medium"}'`. Empty effort triggers
auto-estimation in the orchestrator's Phase 0.

| Effort | Scope |
|---|---|
| `micro` (XS) | 1 file, < 30 lines |
| `small` (S) | 2-5 files, < 100 lines |
| `medium` (M) | 5-15 files, non-trivial logic |
| `large` (L) | 15+ files, architectural impact |
| `xl` | Multiple subsystems, migration required |

Routing: `effort ∈ {micro, small}` AND `type ∈ {bug, chore, task}` → quick-fix.
Everything else → full orchestrator.

## Means of Compliance (MoC) — at create time, not retrofitted

Every acceptance criterion must declare HOW it will be proven. Pick one:

| Method | Use when |
|---|---|
| `unit` | Function logic, calculations, data types |
| `e2e` | User workflows, UI interactions (Playwright/Cypress) |
| `integ` | API calls, service communication, DB queries |
| `review` | Architectural decisions, code quality |
| `demo` | UI layout, visual behavior (screenshot or live) |
| `doc` | Non-functional requirements, process changes |

Template (paste into description or notes):

```markdown
## Means of Compliance

| # | Acceptance Criterion | MoC | Evidence |
|---|----------------------|-----|----------|
| 1 | API returns 200 on valid input | unit | test_api_valid_input() |
| 2 | Error toast on network failure | e2e | test_error_toast.spec.ts |
| 3 | Code follows repo patterns | review | PR review |
```

Close gate: orchestrator refuses to hand off to session-close until each AK has
recorded evidence. `review` and `doc` are valid — not everything needs an
automated test.

## Creating beads

```bash
bd create \
  --title="Short summary" \
  -t task|bug|feature|chore|epic|decision \
  -p 0..4 \
  --description="<long form, with required sections>" \
  --acceptance="<criterion 1>; <criterion 2>" \
  --metadata='{"effort":"medium"}'
```

For multi-line description / design / notes: write the body to a file first
(e.g. `/tmp/<bead-slug>.md`) and pass `--body-file <path>`.

NEVER use:
- `--description "$(cat <<EOF…EOF)"` — under codex's `zsh -lc` wrapper the
  nested quoting breaks and surfaces a misleading "Dolt server unreachable"
  error.
- `--body-file -` with inline heredoc on the `bd` invocation itself — the
  destructive-bash guardrail (dcg) matches patterns inside the heredoc body
  (false positive) and blocks the whole `bd create`. See CL-2l4. Also
  fragile under codex's shell wrapper.

```bash
cat > /tmp/cl-foo.md <<'EOF'
<description>

## Scenario
As a <persona>, I can <action> so that <outcome>.

## Means of Compliance
| # | AK | MoC | Evidence |
| 1 | ... | unit | ... |
EOF

bd create --title="..." -t feature -p 2 --body-file /tmp/cl-foo.md
```

The `cat > /tmp/foo <<EOF` step is fine — dcg only inspects `Bash` tool
calls for destructive command-tokens, not heredoc bodies fed to `cat`.

Discovered work? Link via dependency:

```bash
bd create --title="Found bug" -t bug -p 1 --deps discovered-from:<parent-id>
```

## Updating, claiming, closing

| Action | Command |
|---|---|
| Claim atomically | `bd update <id> --claim` |
| Append to audit trail | `bd update <id> --append-notes "<context: state, next steps>"` |
| Replace description (long) | `bd update <id> --body-file <path>` (write to file first) |
| Add label | `bd update <id> --add-label=<label>` |
| Close with reason | `bd close <id> --reason "<1-line summary with metrics>"` |
| Close many at once | `bd close <id1> <id2> ...` |

Good close reasons: `"Migrated 4 dataclasses to Pydantic, all tests green"`,
`"12 methods done, 30/32 tests passing (2 Windows-only skipped)"`.

Bad: `"Done"`, `"Fixed"`, `"Closed"`.

**Never use `bd edit`** — it opens `$EDITOR` and blocks agents.

## Memory routing

| What you want to save | Where |
|---|---|
| Decision/fact specific to *this bead's work* | `bd update <id> --append-notes "..."` |
| Session summary at end of bead run | coding harness: `ob save "<text>" --type=session_summary --project=<proj>` · mobile/admin: `mcp__open-brain__save_memory` |
| Cross-project learning, person/topic insight, architectural pattern | coding harness: `ob save "<text>" --type=observation --project=<proj>` · mobile/admin: `mcp__open-brain__save_memory` |
| Per-session scratch | conversation context only — don't persist |

Rule of thumb: if the next agent (in this repo or another) would benefit from
knowing it tomorrow → open-brain. If it's just a footnote on this specific bead
→ `--append-notes`. Anything else does not need to be persisted.

## Session close

The `core:session-close` agent owns merge + push + changelog + version tag +
session summary. Trigger phrases: "session close", "session beenden", "release",
"rc". Spawn via `Agent(subagent_type="core:session-close")` (Claude) or by
invoking the agent defined in `~/.codex/agents/session-close.toml` (Codex).

Manual fallback if the agent is unavailable:

```
[ ] git status               # confirm what changed
[ ] git add <files>          # stage specific files (no -A / no .)
[ ] bd dolt commit           # commit pending bd changes
[ ] git commit -m "..."      # conventional commit
[ ] bd dolt pull && bd dolt push --force   # Dolt bug dolthub/dolt#10807 workaround
[ ] git push                 # push to remote
```

**Work is NOT done until pushed.**

## Operational hazards

- **Dolt lifecycle is owned by `brew services`, not `bd`.** Dolt runs under
  `brew services start dolt` (launchd, `keep_alive: true`) from `~/.dolt-data/`
  on port 3306. Never `bd dolt start` / `bd dolt stop` / `pkill dolt`
  (corrupts journal). Use `brew services restart dolt` if the user has
  authorized it; otherwise escalate. For deep diagnosis load the `dolt` skill.
- **`bd dolt push` fails**: always retry as `bd dolt pull && bd dolt push --force`
  (Dolt bug dolthub/dolt#10807). Never use raw `dolt push --force`. Exception:
  on `no common ancestor`, do NOT force-push — re-clone (see `dolt` skill).
- **"Dolt server unreachable … externally managed"**: shared-server mode is
  intentional. Run `bd dolt status` once. If running → retry the bd command
  (likely shell quoting); if not running → escalate to user. Do NOT `bd dolt
  start`; the user owns the brew-services lifecycle.
- **`bd show --json` returns an array**: always use `.[0]` in jq:
  `bd show <id> --json | jq -r '.[0].description'`.
- **No `--append-description`**: doesn't exist. For description edits: dump,
  edit, write back via `--body-file`.

## Labels

- `bd label list` — show available labels
- `bd update <id> --add-label=<label>` — add (repeatable)
- `bd list --label=<label>` — filter

Special labels:
- `decision` — architectural decision record. `bd list --label=decision` finds them.
