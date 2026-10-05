# Model Routing

Which model runs which delivery step. Claude Code on fleet hosts reaches every provider
through CLIProxyAPI (`ANTHROPIC_BASE_URL`); `~/.claude/settings.json` maps the `sonnet`
and `haiku` aliases to other models. Confirm that mapping in the settings file when the
model matters; a host without it silently runs real Sonnet or Haiku.

## Roster

| Alias | Model | Family | Delivery steps |
|---|---|---|---|
| `opus` | Claude Opus 5.5 | Claude | main session, `implementer` subagent, one of the three reviewers (fresh context) and, after triage, that reviewer as the designated repair author |
| `fable` | Claude Fable 5.1 | Claude | planning |
| `sonnet` | `gpt-6-astra` | GPT | one of the three reviewers; its findings go through triage because Astra is picky |
| `haiku` | `gpt-6.1-sol` at reasoning effort xhigh (alias value `gpt-6.1-sol(xhigh)`) | GPT | one of the three reviewers; verification, including browser and UI verification with `playwright-cli` |

`opus`, `sonnet` and `haiku` are three distinct models for the adversarial review.
`sonnet` and `haiku` are both GPT models, which the product owner accepted on 2026-10-05
as different model classes. The repair role follows the actor, not a model: repairs go
to the designated `opus` reviewer whichever reviewer surfaced the finding.

Claude Code also uses the `haiku` alias for its background calls (for example titles
and command classification) and for built-in agents that default to haiku (for example
Explore), so those calls also run Sol at xhigh. Effort scales with task difficulty, so
short background calls stay cheap. Measured on 2026-10-05: a trivial prompt used 38
thinking tokens in 3.8 s at xhigh against 3.4 s at high; a hard prompt used 1356
thinking tokens at medium against 2990 at xhigh.

## Dispatch rule

Native subagent with the alias first. The named `ccore agent` route only when the alias
is unavailable, or when the native attempt fails:

| Alias | Fallback route (`ccore agent run --model <alias> --harness <harness>`) |
|---|---|
| `opus` | `claude-opus` on `claude` |
| `fable` | `claude-fable` on `claude` |
| `sonnet` (review) | `gpt-6-sol` on `codex`; the catalog has no Astra route |
| `haiku` (review, non-UI verification) | `gpt-6.1-sol` on `codex` with `--reasoning xhigh`; not a starter route |
| `haiku` (UI verification) | `gpt-6-luna` on `codex` |

When both `sonnet` and `haiku` use their fallback routes, the two GPT reviewers are two
Sol generations (`gpt-6-sol`, `gpt-6.1-sol`). They are still distinct models; record
each reviewer's route in the pull request.

A native subagent works in the invoking session's worktree and cannot leave it. When the
candidate lives in another worktree, for example a retro pull request in a self-managed
worktree while the session runs in a T3 thread worktree, dispatch the fallback route
directly with `--cwd <worktree>`; `ccore agent run` also requires `--events-file`.

The catalog is `ccore agent models --json`. A configured catalog entry is not proof that
the route is reachable right now. When neither the alias nor the fallback route works,
stop and report the dispatch diagnostic; never substitute another model silently and
never continue a step with fewer actors than it requires.

## Not routed

The model family the shared instructions prohibit is never routed. opencode models
hold no delivery step.
