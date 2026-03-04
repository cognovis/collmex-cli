# Beads Workflow Context

> **Context Recovery**: Run `bd prime` after compaction, clear, or new session
> Hooks auto-call this in Claude Code when .beads/ detected

# Session Close Protocol v2

Das erweiterte Session Close Protokoll wird durch `/session-close` orchestriert:

```bash
/session-close
```

Dies handhabt automatisch:
- Offene Beads schließen (interaktiv)
- Conventional Commits
- CalVer Versionierung (YYYY.0M.MICRO)
- Changelog-Generierung (git-cliff)
- Doku-Gaps Detection
- Learnings-Extraktion
- Git commit + tag + push + `bd dolt commit` + `bd dolt push`

Flags: `--dry-run`, `--skip-beads`, `--skip-learnings`, `--skip-push`

Siehe auch: elysium-uwm (Skill-Implementierung)

**Fallback** (wenn Skill nicht verfügbar):
```
[ ] 1. git status              (check what changed)
[ ] 2. git add <files>         (stage code changes)
[ ] 3. bd dolt commit          (commit beads changes)
[ ] 4. git commit -m "..."     (commit code)
[ ] 5. bd dolt push            (push beads to remote)
[ ] 6. git push                (push to remote)
```

**NEVER skip this.** Work is not done until pushed.

## Means of Compliance (MoC)

Jedes Akzeptanzkriterium eines Beads muss eine definierte Nachweismethode haben.
MoC wird VOR dem Coden festgelegt — nicht nachtraeglich.

### MoC-Typen

| Kuerzel | Nachweismethode | Wann verwenden |
|---------|----------------|----------------|
| `unit` | Unit-Test (pytest/jest/go test/etc.) | Funktionslogik, Berechnungen, Datentypen |
| `e2e` | E2E-Test (Playwright/Cypress) | User-Workflows, UI-Interaktionen |
| `integ` | Integration-Test | API-Aufrufe, Service-Kommunikation, DB-Queries |
| `review` | Manueller Code-Review | Architektur-Entscheidungen, Code-Qualitaet |
| `demo` | Live-Demo / Screenshot | UI-Layout, visuelles Verhalten |
| `doc` | Dokumentation / Statement | Nicht-funktionale Anforderungen, Prozessaenderungen |

### MoC-Template fuer Bead-Erstellung

Bei `bd create` oder als Comment nach Erstellung:

```markdown
## Means of Compliance

| # | Akzeptanzkriterium | MoC | Nachweis |
|---|-------------------|-----|----------|
| 1 | API gibt 200 bei gueltigem Input | unit | test_api_valid_input() |
| 2 | Fehler-Toast bei Netzwerkfehler | e2e | test_error_toast.spec.ts |
| 3 | Daten persistiert in DB | integ | test_db_persistence() |
| 4 | Code folgt Repository-Patterns | review | PR-Review durch Maintainer |
```

### Regeln

- **Pflicht**: Jedes AK braucht mindestens einen MoC-Typ
- **Vor dem Coden**: MoC wird in Phase -1 (Bead-Erstellung) oder /plan definiert
- **Nachweis-Spalte**: Wird beim Schliessen ausgefuellt (Testname, Screenshot-Link, etc.)
- **Close-Gate**: Agent darf Bead erst schliessen wenn alle MoC-Nachweise erbracht sind
- **Kein Overkill**: `review` und `doc` sind valide MoC-Typen — nicht alles braucht automatisierte Tests

## Core Rules
- **Default**: Use beads for ALL task tracking (`bd create`, `bd ready`, `bd close`)
- **Prohibited**: Do NOT use TodoWrite, TaskCreate, or markdown files for task tracking
- **Workflow**: Create beads issue BEFORE writing code, mark in_progress when starting
- Persistence you don't need beats lost context
- Git workflow: hooks auto-sync, run `bd dolt commit && bd dolt push` at session end
- Session management: check `bd ready` for available work

## Essential Commands

### Finding Work
- `bd ready` - Show issues ready to work (no blockers)
- `bd list --status=open` - All open issues
- `bd list --status=in_progress` - Your active work
- `bd show <id>` - Detailed issue view with dependencies

### Creating & Updating
- `bd create --title="..." --type=task|bug|feature --priority=2` - New issue
  - Priority: 0-4 or P0-P4 (0=critical, 2=medium, 4=backlog). NOT "high"/"medium"/"low"
- `bd update <id> --status=in_progress` - Claim work
- `bd update <id> --assignee=username` - Assign to someone
- `bd update <id> --title/--description/--notes/--design` - Update fields inline
- `bd close <id>` - Mark complete
- `bd close <id1> <id2> ...` - Close multiple issues at once (more efficient)
- `bd close <id> --reason="explanation"` - Close with reason
- **Tip**: When creating multiple issues/tasks/epics, use parallel subagents for efficiency
- **WARNING**: Do NOT use `bd edit` - it opens $EDITOR (vim/nano) which blocks agents

### Dependencies & Blocking
- `bd dep add <issue> <depends-on>` - Add dependency (issue depends on depends-on)
- `bd blocked` - Show all blocked issues
- `bd show <id>` - See what's blocking/blocked by this issue

### Sync & Collaboration
- `bd dolt commit` - Commit pending Dolt changes (snapshots current state)
- `bd dolt push` - Push to configured Dolt remote (requires remote server)
- `bd dolt pull` - Pull from configured Dolt remote

### Project Health
- `bd stats` - Project statistics (open/closed/blocked counts)
- `bd doctor` - Check for issues (sync problems, missing hooks)

## Common Workflows

**Starting work:**
```bash
bd ready           # Find available work
bd show <id>       # Review issue details
bd update <id> --status=in_progress  # Claim it
```

**Completing work:**
```bash
bd close <id1> <id2> ...    # Close all completed issues at once
bd dolt commit && bd dolt push  # Commit + push to remote
```

**Creating dependent work:**
```bash
# Run bd create commands in parallel (use subagents for many items)
bd create --title="Implement feature X" --type=feature
bd create --title="Write tests for X" --type=task
bd dep add beads-yyy beads-xxx  # Tests depend on Feature (Feature blocks tests)
```

### Labels

- `bd label list` - Show available labels
- `bd update <id> --add-label=<label>` - Add label to issue (repeatable)
- `bd list --label=<label>` - Filter issues by label

**Special Labels:**
- `decision` - Architektur-Entscheidung (ADR). Use when a bead documents a significant
  design decision, technology choice, or process change. Example:
  ```bash
  bd update <id> --add-label=decision
  bd list --label=decision  # Find all past decisions
  ```

---

## 📝 Documentation Requirements

### Progress Checkpoints (for longer tasks)

Document progress at meaningful checkpoints - not after every step, but at:
- **After research phase**: "Found 3 relevant files: x, y, z"
- **After design decisions**: "Using DataProvider pattern because..."
- **After major milestones**: "Tests passing, starting integration"
- **When blocked**: "Blocked: missing API credentials"

```bash
bd update <id> --append-notes="<checkpoint: current state, next steps>"
```

### Closing Beads

**Default (all acceptance criteria met):**
```bash
bd close <id> --reason="<1-line summary with key metrics>"
```

Good examples:
- `"12 Methoden implementiert, 30/32 Tests passing (2 Windows-only geskippt)"`
- `"Fixed SL-001 for M4/Tahoe, SIP-001 for Apple Silicon"`
- `"Migrated 4 dataclasses to Pydantic, all tests green"`

Bad examples:
- `"Closed"` ❌
- `"Done"` ❌
- `"Fixed"` ❌

**When there are exceptions or deviations:**
```bash
bd update <id> --append-notes="<what didn't go as expected>"
bd close <id> --reason="<summary>, see Notes for details"
```

Example:
```bash
bd update <id> --append-notes="get_kerberos_data() needs Domain-Joined environment - not testable standalone"
bd close <id> --reason="11/12 methods done, Kerberos stub only (see Notes)"
```

### What NOT to include

- Don't repeat acceptance criteria that were met (they're in the Description)
- Don't list all changed files (visible in git diff)
- Don't copy tables/specs already in the bead
- Only document **exceptions** and **deviations** from the plan
