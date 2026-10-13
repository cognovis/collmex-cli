# Collmex Library content

The repository publishes catalog identity `https://github.com/cognovis/collmex-cli`
in `library.yaml`, with source name `cognovis-collmex-cli`. The `collmex-cli` skill
lives at `skills/collmex-cli/SKILL.md`; executable accounting behavior stays in
the existing tool runtime.

Provenance is `cognovis/library-core` commit
`7c1f546b17a36032977c3a42c272f21c783f32f5`, path
`skills/collmex-cli/SKILL.md`, recorded on its catalog row. The old vendor/invoice
and ZUGFeRD shell examples are expressed as native commands rather than copied
as executables. Command options follow the current source; accounting and message
authorization remains governed by the active policy.

## Install and sync

Register this published source in the consumer's active catalog, then select it
from the consumer repository, replacing `<harness>` with its selected harness:

```bash
library skill use collmex-cli --harness <harness>
library sync --harness <harness>
```

An explicit catalog file can be supplied with `library --catalog <file>`.
`use` establishes the requested entry and `sync` maintains its copy and receipt.
Edit the authored source rather than an installed `.agents/skills/` copy. A source
commit does not establish publication, live catalog registration or propagation.
