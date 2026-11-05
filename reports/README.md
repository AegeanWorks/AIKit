# Reports inbox (local-only, git-ignored via .git/info/exclude)

Drop analysis, scan, review and literature reports here for triage.
Lifecycle, no exceptions:

1. **Triage** — read the report, cross-check every claim against the
   idea-catcher register (`python idea_catcher.py ideas`, `reviews`,
   per-idea `review_log`) and the current trees.
2. **Register** — record what is worth keeping with the register's own
   commands (`review-idea --verdict ...`, `add-idea` after writing the
   `### \`IDEA-NNN\`` dossier section, `review-finish` for repo reviews).
   Backdate with `--decided-at` when registering a past report's verdicts
   and attribute with `--by report:<filename>`.
3. **Delete** — remove the report file once its content is in the register
   or judged not worth keeping. Reports rot fast (trees move on); a stale
   report that stays looks authoritative and is not.

Do not commit this folder. Do not let files accumulate here: an inbox with
17 files is a backlog, not an archive. If a report's content matters, it
belongs in `.idea-catcher/` (dossiers, ideas, reviews) — nowhere else.
