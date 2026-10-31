# Project Repository Backlog

Projects left out of the 2026-10-26 normalization pass: capitalized GitHub names, curated topics,
descriptions within GitHub's 350-character limit, and new versions under the Aegean 1.1
licenses. A project qualified only with a clean working tree and no open ledger task.

| Project | Why it was skipped | Pass still needed |
|---|---|---|
| `AegeanWorks` | uncommitted `docs/styles.css` | none beyond committing that change |

`MemoryReconstruction`, `voidfarer` (now `Voidfarer`), `fluid-universe` (now `Fluid-Universe`) and
`ui-sandbox` (now `UI-Sandbox`) finished their tasks and completed the pass on 2026-10-26; no
project carries an AGPL LICENSE any more. `idea-catcher` is a restricted project with no GitHub
repository and is out of scope.

## Follow-ups found during the pass

The tooling defects the pass found (catalog links to `blob/main`, 1.0 help text, the blank README
tree line and duplicate License section after a license switch, and the publish description's
byte-order mark, URL-only paragraph and mid-word cut) were fixed in ADR-227 and the
Aegean-Licensing catalog. One item remains:

- The Aegean-Licensing policy drafts still tell a maintainer to create a `vX.Y.Z-agpl` tag
  (`policies/PORTFOLIO-MIGRATION-PLAN.md`, step 2), although AegeanWorks no longer tags or
  mentions AGPL releases; the license texts keep their non-retroactivity and AGPL-incompatibility
  clauses, which protect the licensor and stay until counsel review.
