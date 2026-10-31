"""Generated top-level CLI help for the `--help` fast path (ADR-180).

The string is compared with `scripts.aikit_parser.build_parser().format_help()` by
`tests.test_kit.TestAikitHelpFastPath`. Regenerate it when the grammar or a help string
changes; the test fails before the fast path can drift.
"""

TOP_LEVEL_HELP = """\
usage: python aikit.py [-h] [--workspace DIR]
                       {new,attach,list,status,resume,checkpoint,complete,clean,guideline,check,fix,publish,license,topics,ui-id,media,ui,reforge,idea-catcher,delegate} ...

Create and manage the projects AIKit builds. Each project is its own folder
and git repository with its memory in .aikit/.

positional arguments:
  {new,attach,list,status,resume,checkpoint,complete,clean,guideline,check,fix,publish,license,topics,ui-id,media,ui,reforge,idea-catcher,delegate}
    new                 create projects/<name>/ as a new git repository
    attach              register an existing project folder and add the AIKit
                        Integrated badge to its README
    list                show every project, its stacks and test command
    status              a project's task, uncommitted work, latest decision
                        and gates
    resume              the cold-start report for a project (PRINCIPLE-004 R2)
    checkpoint          record a checkpoint in the project's ledger
    complete            mark the project's active task completed
    clean               delete the project's temp buffers older than 60s
    guideline           add a rule to the project's guidelines (below the
                        principles)
    check               run every gate of a project (its Phase 4)
    fix                 restore missing project memory and README, refresh its
                        map, then check
    publish             upload the project to its own GitHub repository, named
                        in catalog title case (private by default)
    license             show or choose the project's license (ADR-214,
                        ADR-218)
    topics              show or set the GitHub topics a project records
    ui-id               detect or set whether a project has a screenshotable
                        UI (ADR-233)
    media               generate, review and apply project logos, social
                        previews and screenshots
    ui                  bound edits to one UI surface declared in
                        .aikit/ui.json
    reforge             audit Git history in 3/6/9 stages and repair evidence-
                        backed findings (Aegean Reforge)
    idea-catcher        validate, render and review the Idea Catcher register
                        shipped in idea_catcher/
    delegate            run an OpenCode sub-agent on a bounded brief

options:
  -h, --help            show this help message and exit
  --workspace DIR       AIKit checkout whose projects/ to use (default: this
                        one; for sandboxes)
"""
