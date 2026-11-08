# Codebase Map & Symbol Catalog 🗺️

> **AUTO-GENERATED & VERIFIED BY `scripts/update_knowledge_base.py`**
> This document provides an automated, up-to-date registry of all modules, classes, and exported functions across this repository.

---

## 📊 Codebase Metrics
- **Total Python Modules**: `70`
- **Total Classes**: `163`
- **Total Top-Level Functions**: `1007`
- **Total Class Methods**: `1229`
- **Total Source Lines**: `46332`

---

## 📦 Modules & Exported Symbols

### [`aikit.py`](aikit.py)
> *AIKit entry point: `python aikit.py --help`. The commands live in scripts/aikit_cli.py.*

**Size**: `15` lines (`663` bytes)

---

### [`idea_catcher/__init__.py`](idea_catcher/__init__.py)
> *Idea Catcher: target registry, idea ledger, review ledger and generated register matrix.*

**Size**: `5` lines (`168` bytes)

---

### [`idea_catcher/__main__.py`](idea_catcher/__main__.py)
> *`python -m idea_catcher`: the module entry point.*

**Size**: `8` lines (`157` bytes)

---

### [`idea_catcher/auto_register.py`](idea_catcher/auto_register.py)
> *One-way compatibility re-export for the idea auto-registration engine.*

**Size**: `14` lines (`480` bytes)

---

### [`idea_catcher/claim_audit.py`](idea_catcher/claim_audit.py)
> *Advertised-module evidence for a real repository checkout.*

**Size**: `391` lines (`14494` bytes)

**Classes:**
- `class AuditError` - *The audit cannot run against the given repository or claim.*
- `class ModuleClaim`
- `class ClaimEvidence`

**Functions:**
- `def parse_claim(value)` - *Parse ``name=path`` or ``name=path:Symbol,other_symbol``.*
- `def claims_from_dossier(text)` - *Extract backticked repository paths from a dossier, with nearby symbols.*
- `def _looks_like_path(token)`
- `def _relative(repo, path)`
- `def _safe_path(repo, advertised)`
- `def _python_symbols(tree)`
- `def _symbols(path)`
- `def _is_stub(path)`
- `def _has_behaviour(path)`
- `def _walk_files(repo, max_files)`
- `def _find_symbol(repo, entrypoints, max_files)`
- `def audit_claims(repo_path, claims, *, commit, max_files)` - *Check every advertised module against a real checkout.*
- `def _count_artefacts(repo, max_files)`
- `def assess_ratio(repo_path, evidence, *, max_files)` - *Repository-level verdict merged from IDEA-500: implemented, brief, or docs-only.*
- `def render_summary(verdict)`
- `def render_table(evidence)`

---

### [`idea_catcher/concept_map.py`](idea_catcher/concept_map.py)
> *Deterministic concept co-occurrence map for the idea register.*

**Size**: `275` lines (`11432` bytes)

**Functions:**
- `def tokenize(text, stop)` - *Lowercase, split on punctuation, and drop short or boilerplate terms.*
- `def _doc_tokens(value)`
- `def build_cooccurrence(docs, min_df)` - *Count document-level co-occurrence for terms that appear in at least ``min_df`` docs.*
- `def clusters(graph, threshold)` - *Connected components of the edges at or above ``threshold``.*
- `def _normalise_concept(concept)`
- `def exact_duplicates(ideas)` - *Idea ids whose normalised concept strings are identical.*
- `def documents_from_root(root)` - *One token document per dossier, keyed by its relative path.*
- `def documents_from_ideas(ideas)` - *One token document per dossier, built from the idea concepts it registers.*
- `def target_overlap(ideas, docs)` - *Per target, the terms shared by at least two of its dossiers.*
- `def shared_pair_count(graph, threshold)`
- `def render_report(graph, clusters_, *, duplicates, target_overlap_, min_df, threshold, documents, limit)` - *Render the deterministic Markdown report.*
- `def write_report(path, text)` - *Write the generated report atomically.*

---

### [`idea_catcher/registry.py`](idea_catcher/registry.py)
> *Generate and validate the Idea Catcher register.*

**Size**: `2563` lines (`111408` bytes)

**Classes:**
- `class StatusSpec` - *One decision state: how it renders and what a recorded decision must carry.*
- `class TagSpec` - *One analysis tag: what it asserts and whether it competes with other verification tags.*
- `class RegistryError` - *A registry write was refused because the result would be invalid.*
- `class DossierSection` - *One idea section's routing metadata, including its optional source locator.*
- `class DossierEntry` - *A dossier section joined with the dossier path that declares it.*
- `class LockBusy` - *Another process holds the registry lock and the wait timed out.*

**Functions:**
- `def default_root()` - *The private register this AIKit checkout serves.*
- `def load_json(path)` - *Read one registry file, refusing a missing or non-object document by name.*
- `def write_text_atomic(path, text)` - *Write atomically: temp file in the same directory, fsync, then replace.*
- `def write_json(path, payload)` - *Write one registry JSON document atomically.*
- `def load_targets(root)`
- `def file_lock(path, *, timeout)` - *Hold an exclusive cross-process lock on ``path`` for the ``with`` block.*
- `def registry_lock(root, *, timeout)` - *Serialise one read-modify-write cycle over the registry.*
- `def now_iso()` - *UTC timestamp with second precision; injectable in tests via ``now`` args.*
- `def load_reviews(root)`
- `def empty_reviews()`
- `def target_ids(targets)`
- `def load_ideas(root)`
- `def parse_dossier_sections(text)` - *Map every ``### `IDEA-NNN`: Title`` heading (three or more digits) to its metadata.*
- `def parse_dossier_ideas(text)` - *Map every heading to (title, declared target); kept for narrow callers.*
- `def dossier_sources(root)` - *Map idea id -> (dossier relative path, target declared in that dossier).*
- `def dossier_duplicates(root)` - *Map every idea id declared in more than one dossier to those dossiers.*
- `def dossier_catalog(root)` - *Map idea id -> dossier path, title, declared target and source locator.*
- `def validate_targets(targets)`
- `def validate_idea(idea, targets, sources)`
- `def validate_tags(idea_id, tags)` - *Refuse unknown or repeated tags and more than one verification tag.*
- `def effective_tags(idea)` - *Stored tags, the implicit `unverified` default, and the decision status once one is made.*
- `def deferral_count(idea)` - *How many times a review has deferred this idea.*
- `def idea_number(idea_id)`
- `def reserved_ids(reviews)` - *Map every reserved idea number to the review that holds it.*
- `def free_idea_numbers(count, *, payload, reviews)` - *The lowest ``count`` numbers that are neither registered nor reserved.*
- `def validate_ideas(payload, targets, root, reviews)`
- `def badge(status)` - *Shields.io badge for one status; the alt text carries the decision state.*
- `def _cell(value)`
- `def _status_counts(ideas)`
- `def render_matrix(targets, payload, reviews)`
- `def matrix_matches(root, targets, payload, reviews)`
- `def write_matrix(root, targets, payload, reviews)` - *Render the matrix from already-loaded inputs and replace it atomically.*
- `def render_to_disk(root)` - *Refresh ``MATRIX.md`` from the register's three source documents.*
- `def add_target(root, *, target, require_path)`
- `def add_idea(root, *, dossier, target, impact, effort, idea_id, concept, review_id)` - *Register a dossier section as an idea, taking the title from the heading.*
- `def _history_entry(*, field, before, after, by, at, reason)`
- `def set_tags(root, idea_id, *, add, remove, by, reason)` - *Add and remove analysis tags; a new verification tag replaces the previous one.*
- `def _append_history(idea, status, *, at, by, reason)`
- `def _append_review(idea, *, verdict, evidence, by, at, files, commands, notes)`
- `def _apply_status(idea, *, status, reason, decided_at, decided_by, evidence, target, superseded_by, declared, record_deferral, deferrals_before, new_deferral)` - *Apply one decision to a loaded idea; return the effective status.*
- `def set_status(root, idea_id, *, status, reason, decided_at, decided_by, evidence, target, superseded_by)`
- `def review_idea(root, idea_id, *, verdict, evidence, by, notes, files, commands, status, reason, decided_at, superseded_by)` - *Record one second-pass review and apply its decision.*
- `def parse_idea_ids(message)` - *Every distinct IDEA-NNN token (three or more digits) in one commit message, sorted.*
- `def git_commits(repo_path, limit)` - *(sha, subject, body) for the newest commits, newest first.*
- `def register_from_commits(root, project, commits, dry_run)` - *Mark matching ideas Integrated; return one record per change.*
- `def register_from_repo(repo_path, project, root, limit, dry_run)` - *Scan one repository's commits and register matching IDEA-NNN references.*
- `def _parse_ts(value)`
- `def _lease_expired(review, now)`
- `def validate_reviews(payload, root, *, ideas_payload)`
- `def _release(review, now, reason)` - *Close a review and drop the idea numbers it had not consumed.*
- `def release_expired(root, *, now)` - *Abandon every active review whose lease has passed and release its ids.*
- `def review_start(root, *, slug, url, agent, lease_minutes, now, force, reserve, kind)` - *Claim one repository for analysis and reserve the idea numbers it will use.*
- `def review_finish(root, review_id, *, dossier, ideas, now)` - *Close an active review, giving it the next place in the review order.*
- `def review_abandon(root, review_id, *, reason, now)` - *Close an active review without counting it, recording why.*
- `def review_rows(payload, *, now)` - *One row per repository: review order, count, last review and current state.*
- `def classify_freshness(review, dossier_text, *, today, max_age_days)` - *Classify one review as current, aged, superseded or unknown.*
- `def stale_reviews(rows, root, *, today, max_age_days)` - *Return the non-current rows, oldest analysis first, with a ``freshness`` field.*
- `def list_ideas(payload, *, target, status, dossier, tag, include_rejected, include_duplicates, include_blocked)` - *Return the register rows matching the filters, in id order.*
- `def idea_history(payload, idea_id)` - *Return one idea's recorded changes, or refuse an unknown id.*
- `def proposed_by_target(payload)` - *Per target, how many ideas sit in each decision state.*
- `def _plus_minutes(now, minutes)`
- `def _report(errors)`
- `def add_commands(sub)` - *Declare every Idea Catcher command once, for either top-level CLI.*
- `def build_parser()`
- `def main(argv, root)`
- `def run(args, root)` - *Execute an already parsed command; shared with `python aikit.py idea-catcher`.*

---

### [`idea_catcher/upstream_check.py`](idea_catcher/upstream_check.py)
> *Read-only upstream revalidation for dossier headers.*

**Size**: `368` lines (`14318` bytes)

**Classes:**
- `class UpstreamError` - *The upstream API could not be reached or answered with an error.*

**Functions:**
- `def _header_text(text)`
- `def _field(text, label)`
- `def _first_tick(value)`
- `def normalise_licence(value)` - *Turn a messy header licence into one comparable SPDX-ish token.*
- `def _licence_key(value)`
- `def parse_header(text)` - *Read the three upstream facts from a dossier's opening block.*
- `def repo_from_url(url)` - *Return ``owner/name`` for a GitHub URL, or an empty string.*
- `def _is_missing(payload)`
- `def _nested(payload, *keys)`
- `def resolve_upstream(repo, fetch, *, commit)` - *Fetch the current facts for one repository with an injected fetch callable.*
- `def diff_upstream(recorded, current)` - *Classify the difference between the dossier and the live repository.*
- `def is_failure(result)` - *Only a licence change or a vanished repository fails ``--strict``.*
- `def render_report(results)` - *Render one compact table for the terminal.*
- `def _cache_path(cache_dir, repo)`
- `def _load_cache(path, today)`
- `def _store_cache(path, today, current)`
- `def run_revalidation(root, *, fetch, today, cache_dir, limit)` - *Check every dossier header, reusing a same-day cache and never editing a dossier.*
- `def github_fetch(url)` - *Default network fetch: stdlib only, optional token, polite timeout.*

---

### [`idea_catcher/version.py`](idea_catcher/version.py)
> *The single version constant shared by the package and its CLI.*

**Size**: `3` lines (`92` bytes)

---

### [`idea_catcher.py`](idea_catcher.py)
> *Idea Catcher entry point: `python idea_catcher.py --help`.*

**Size**: `9` lines (`189` bytes)

---

### [`reforge/__init__.py`](reforge/__init__.py)
> *Aegean Reforge: progressive Git history reviewing, safe repair and delivery.*

**Size**: `5` lines (`151` bytes)

---

### [`reforge/__main__.py`](reforge/__main__.py)
> *`python -m reforge`: the standalone entry point.*

**Size**: `8` lines (`146` bytes)

---

### [`reforge/analyzer.py`](reforge/analyzer.py)
> *Run an external analyzer over one Reforge review packet.*

**Size**: `133` lines (`5643` bytes)

**Functions:**
- `def _parts(command)`
- `def run_analyzer(root, packet, command, timeout)` - *Run one analyzer command; return its parsed answer and the file holding it.*

---

### [`reforge/audit.py`](reforge/audit.py)
> *Configurable progressive commit-window analysis with cross-commit interaction evidence.*

**Size**: `243` lines (`11412` bytes)

**Functions:**
- `def window_for_stage(stage, start, step, stop)` - *Window N: start + step*(N-1), capped by the run's stop (3,6,9 by default).*
- `def plan_next_stage(repo, run)` - *The next window for one run, its new commits and its already-audited overlap.*
- `def _prior_context(repo, plan, history)`
- `def _interaction(finding, prior)`
- `def supports_source(path)` - *Whether Reforge's AST detectors can analyse this path.*
- `def is_bookkeeping(path)` - *Reforge's own state, its backups and locks, and the task ledger it updates.*
- `def audit_window(repo, plan, history, skipped, reviewed, detections)` - *Walk the stage's files and optionally run the cheap rules over the lines it adds.*
- `def _ordered(findings)`
- `def summarize(findings)`

---

### [`reforge/cli.py`](reforge/cli.py)
> *The Reforge command grammar, shared by `python -m reforge` and `aikit.py reforge`.*

**Size**: `479` lines (`24013` bytes)

**Classes:**
- `class ReforgeArgumentParser` - *argparse whose usage errors carry the AIKit What/Why/Fix triad (PRINCIPLE-011).*
  - Method `.error(message)`

**Functions:**
- `def _add_run_selection(command)`
- `def _add_window_settings(command, defaults)`
- `def _add_review_options(command, findings, rules)`
- `def add_commands(subparsers)` - *Declare every Reforge command once, for either top-level CLI.*
- `def build_parser()`
- `def _report_error(error, as_json)`
- `def _run_line(run)`
- `def _print_runs(runs)`
- `def _print_findings(payload)`
- `def _start_payload(payload)`
- `def _print_review(report)` - *Say whether a reviewer answered the stage, and where its packet is.*
- `def _print_ledger(payload)` - *Say where the run was recorded: the ledger is how a cold start finds an open audit.*
- `def _workspace(args, root, gate_runner)`
- `def dispatch(args, aikit_root, project_root, gate_runner)` - *Run one parsed request; every failure is reported as a triad or a JSON envelope.*
- `def main(argv)`

---

### [`reforge/delivery.py`](reforge/delivery.py)
> *Explicit staging, conventional commit and never-forced push for accepted repairs.*

**Size**: `153` lines (`6196` bytes)

**Functions:**
- `def validate_message(message)`
- `def _paths_to_commit(root)`
- `def _scrub_push_output(output)` - *Redact credentials from push output before it reaches reports/logs.*
- `def _not_ignored(root, paths)` - *Drop paths git ignores; an ignored state file is local, not a commit failure.*
- `def commit_repairs(root, message, paths)` - *Stage exactly the repair paths, commit, and verify the commit holds them.*
- `def push_committed(root)` - *Push already-committed window(s) without staging anything new.*
- `def deliver(root, message, do_push, paths)` - *Commit only the reviewed repair paths plus the audit state, then optionally push.*

---

### [`reforge/detectors.py`](reforge/detectors.py)
> *AST detectors for the defect, security and reliability classes Reforge can evidence.*

**Size**: `326` lines (`15071` bytes)

**Classes:**
- `class Rule` - *Catalogue entry: what a code means and whether a safe repair exists.*
- `class _Visitor`
  - Method `.__init__(path, commit, lines)`
  - Method `.add(code, node, line, symbol, reproducible)`
  - Method `._visit_function(node)`
  - Method `.visit_FunctionDef(node)`
  - Method `.visit_AsyncFunctionDef(node)`
  - Method `.visit_ExceptHandler(node)`
  - Method `.visit_With(node)`
  - Method `.visit_AsyncWith(node)`
  - Method `.visit_BinOp(node)`
  - Method `.visit_Dict(node)`
  - Method `.visit_Try(node)`
  - Method `.visit_Subscript(node)`
  - Method `.visit_Assign(node)`
  - Method `.visit_AnnAssign(node)`
  - Method `._credential_assignment(targets, value, node)`
  - Method `.visit_Call(node)`
  - Method `.generic_visit(node)`

**Functions:**
- `def parse_source(source, path)` - *Parse with the running grammar; raises SyntaxError, never guesses a fix.*
- `def _dotted(node)`
- `def _snippet(lines, line)`
- `def _function_ranges(tree)`
- `def symbol_at(tree, line)` - *The innermost function or class containing `line`, for interaction evidence.*
- `def symbols_in_source(source)`
- `def allow_marker(lines, line)` - *Whether the project marked this line as a deliberate finding.*
- `def detect_source(path, source, commit)` - *Every rule hit in one file revision, deduplicated and ordered by line.*

---

### [`reforge/errors.py`](reforge/errors.py)
> *Actionable failures shared by the standalone CLI and the AIKit command.*

**Size**: `15` lines (`536` bytes)

**Classes:**
- `class ReforgeError` - *A request Reforge refused; carries the AIKit What/Why/Fix triad and exit code.*
  - Method `.__init__(message, why, fix, exit_code)`
  - Method `.triad()`

---

### [`reforge/git_history.py`](reforge/git_history.py)
> *Bounded Git reads used by the auditor, the repair review and delivery.*

**Size**: `282` lines (`10146` bytes)

**Functions:**
- `def _repo_key(repo)` - *A stable cache key for one checkout path.*
- `def run_git(repo, *args, timeout)` - *Run git with stdin closed and a timeout; returns (exit code, combined output).*
- `def is_git_repo(repo)`
- `def head_sha(repo)`
- `def commit_window(repo, limit)` - *The newest `limit` commits, newest first.*
- `def commit_info(repo, sha)`
- `def commit_count(repo)`
- `def _changed_files(repo_key, sha)`
- `def changed_files(repo, sha)` - *(status, relative path) pairs a commit changed; root commits included.*
- `def _added_lines(repo_key, sha, path)`
- `def added_lines(repo, sha, path)` - *Line numbers a commit adds to `path`, from a zero-context diff.*
- `def _changed_files_range(repo_key, base, head)`
- `def changed_files_range(repo, base, head)` - *(status, path) for the net change between two commits; `base` empty means `head` is a root.*
- `def _added_lines_range(repo_key, base, head, path)`
- `def added_lines_range(repo, base, head, path)` - *Line numbers the whole stage (`base`..`head`) adds to `path`, as it stands at `head`.*
- `def range_diff(repo, base, head, path)` - *The net diff of one path across a whole stage, with three lines of context.*
- `def _added_from_diff(diff_text)` - *Line numbers a zero-context diff adds, read from its hunk headers.*
- `def _parent_sha(repo_key, sha)`
- `def parent_sha(repo, sha)` - *The first parent of `sha`, or an empty string for a root commit.*
- `def _file_at(repo_key, sha, path)`
- `def file_at(repo, sha, path)` - *One file's complete text at a commit, or None when it did not exist there.*
- `def worktree_diff(repo, paths)`
- `def status_paths(repo)` - *Changed tracked paths, including both sides of a rename, from NUL-delimited porcelain.*
- `def untracked_paths(repo)`
- `def diff_paths(diff_text)` - *Paths in a unified diff, in first-seen order.*
- `def commit_paths(repo, sha)`
- `def stage_and_commit(repo, paths, message)` - *Explicit `git add -- <paths>` then commit; never stages the whole tree.*
- `def push(repo)` - *Adaptive, never forced push: set the upstream once when origin exists.*
- `def dirty_paths(repo)` - *Tracked and untracked paths that differ from HEAD, for delivery refusal.*

---

### [`reforge/ledger.py`](reforge/ledger.py)
> *Record Reforge progress in the audited repository's AIKit task ledger.*

**Size**: `128` lines (`5476` bytes)

**Functions:**
- `def ledger_path(root)` - *The ledger `root` already has, or None; Reforge never creates one for a foreign repository.*
- `def ledger_relative(root)` - *The ledger's repo-relative path when it exists, for the queue of paths Reforge may dirty.*
- `def ledger_artifacts(root)` - *The ledger plus the `.bak` and `.lock` siblings AIKit's atomic writer leaves beside it.*
- `def _describe(stage, description)`
- `def record_event(root, run_id, stage, description, files, status, agent)` - *Append one checkpoint for `run_id`; returns what happened instead of raising.*
- `def stage_files(findings, skipped)` - *Paths a stage touched or could not read: the ledger's `files_affected` for that entry.*

---

### [`reforge/locking.py`](reforge/locking.py)
> *A per-project advisory lock so one project never runs two Reforge operations at once.*

**Size**: `74` lines (`3031` bytes)

**Functions:**
- `def lock_path(root)` - *The lock inside the audited root itself, resolved so one repository has one lock.*
- `def run_lock(root, wait_seconds)` - *Hold the project's run lock; refuse immediately when another process already holds it.*

---

### [`reforge/model.py`](reforge/model.py)
> *Immutable values shared by Reforge's audit, repair, persistence and CLI layers.*

**Size**: `118` lines (`3185` bytes)

**Classes:**
- `class CommitInfo` - *One commit in the window Reforge is auditing.*
- `class Finding` - *An evidence-backed problem introduced by an audited commit.*
  - Method `.key()` - *Stable identity for a finding inside one audit stage.*
  - Method `.as_dict()`
- `class Repair` - *One repair Reforge made, or deliberately skipped, for a finding.*
  - Method `.as_dict()`
- `class StagePlan` - *The progressive history window for one audit stage of one named run.*
  - Property `.has_new_commits`
  - Method `.as_dict()`

---

### [`reforge/pipeline.py`](reforge/pipeline.py)
> *Orchestrates one independent audit run, its safe repairs and their verification.*

**Size**: `1064` lines (`53041` bytes)

**Functions:**
- `def finding_from_dict(item)`
- `def repair_from_dict(item)`
- `def _scanner(label, text)`
- `def _stop_value(stop)`
- `def _is_safe_relative(relative)` - *Only repo-relative paths may be snapshotted, restored or repaired.*
- `def _is_safe_under_root(root, relative)` - *Relative plus symlink check: the resolved path must stay under root.*
- `def _snapshot(root, findings, extra_paths)`
- `def _restore(root, snapshots)` - *Restore snapshotted bytes; returns paths that could not be restored.*
- `def _relative_inside(root, path)` - *The repository-relative form of a supplied file, or an empty string when it is outside.*
- `def _preexisting_dirty(root, ignore)` - *Paths already dirty before Reforge repairs; its own state and artifacts are excluded.*
- `def _owned_repairs(last)` - *Paths Reforge repaired itself, excluding targets that were dirty before the repair.*
- `def _check_commit_targets(root, targets, allow_dirty, deliver, ignore, owned)` - *Refuse a commit whose target file already held work Reforge did not make.*
- `def _fingerprint(path)`
- `def _execute_repairs(root, findings, add_tests, run_tests, test_command, gate_runner, extra_allowed, preexisting)`
- `def _payload(root, mode, plan, run, findings, repairs, tests, gates, skipped, ledger, reviewed, review, delivery, delivery_lines)`
- `def _review_error(run, pending)`
- `def _plan_from_last(run, last)` - *Rebuild the stage a `fix` must apply, from the run and its last audit entry.*
- `def _collect_review(root, plan, reviewed, findings_file, packet, method)` - *Write the review packet and load the reviewer's answer, if one was supplied.*
- `def _serialize_review(report)` - *The small JSON-safe form of a review kept in state and printed by the CLI.*
- `def _note_stage(root, run, plan, entry, findings, skipped)` - *Mirror one stage into the repository's task ledger so cold start can see the audit.*
- `def _delivery_message(run_id, stage, repaired)` - *Conventional message shared by the stage-close hook (no caller variants).*
- `def _publish_backlog(root, state, run)` - *Push previously verified-but-unpushed windows before auditing the next one.*
- `def _close_window(root, state, run, entry, commit_paths, do_commit, do_push)` - *Commit and push one verified window; empty windows never commit.*
- `def _note_review(root, run, stage, review)` - *Mirror a host review into the task ledger, including the completion it may unlock.*
- `def run_pipeline(root, mode, add_tests, run_tests, test_command, gate_runner, allow_dirty, run_id, start, step, stop, rules, findings_file, packet, deliver, do_push)` - *Audit the next stage (`audit`), repair the last one (`fix`), or do both (`run`).*
- `def review_stage(root, run_id, stage, findings_file, method)` - *Record a host or analyzer review of any retained stage, including an older one.*
- `def analyze_stage(root, run_id, stage, command, timeout)` - *Run the configured analyzer over one stage packet, then record its answer as the review.*
- `def start_audit(root, start, step, stop)` - *Create a new independent run, refusing while another run is still active.*
- `def stop_audit(root, run_id)`
- `def resume_audit(root, run_id)`
- `def configure_audit(root, run_id, start, step, stop)`
- `def runs_payload(root)`
- `def status_payload(root)`
- `def report_payload(root)`

---

### [`reforge/repair.py`](reforge/repair.py)
> *Smallest-safe automatic repairs, generated regression tests and repair verification.*

**Size**: `487` lines (`21277` bytes)

**Classes:**
- `class _Edit`
- `class _MutableDefault`

**Functions:**
- `def _lines(text)`
- `def _newline(text)` - *The file's own line ending, so a repair never rewrites untouched lines.*
- `def _offset(lines, line, column)`
- `def _default_constructor(node)`
- `def _locate(tree, finding)`
- `def _call_name(node)`
- `def _bare_except_edit(text, lines, node)`
- `def _yaml_edit(text, lines, node)`
- `def _remove_keyword(text, lines, node, name)`
- `def _mutable_default_edits(lines, located, newline)`
- `def _edits_for(text, finding, tree)`
- `def _apply_edits(text, edits)`
- `def _secret_hits(label, text)`
- `def _write_text(path, text, newline)` - *Write a repair through AIKit's shared atomic writer (PRINCIPLE-013).*
- `def _test_method_name(code, path)`
- `def _test_body(code, relative)`
- `def regression_test_path(root)`
- `def _add_regression_tests(root, repairs)`
- `def _is_safe_relative(relative)` - *Only repo-relative paths may be repaired (defense in depth, see pipeline).*
- `def _is_safe_under_root(root, relative)` - *Relative plus symlink check: the resolved path must stay under root.*
- `def repair_findings(root, findings, add_tests)` - *Apply safe repairs per file, then add one regression test per repaired rule and file.*
- `def apply_text_patches(root, findings)` - *Apply reviewed exact replacements, one per finding, only when each is unambiguous.*
- `def repair_paths(repairs, root)` - *The source and test paths a repair touched, for an explicit commit and patch review.*

---

### [`reforge/review.py`](reforge/review.py)
> *The review packet: the change a stage makes, and the findings a reviewer returns.*

**Size**: `619` lines (`26763` bytes)

**Functions:**
- `def _stage_base(repo, plan)` - *The commit just before the stage, so one diff shows the whole stage as it now stands.*
- `def _new_paths(repo, plan)` - *Paths at least one new commit touched; files only an earlier stage changed stay out.*
- `def _new_added_lines(repo, plan, path)` - *Lines the stage's new commits add to a path, ignoring an earlier stage's lines.*
- `def _changed_paths(repo, plan)` - *(head, path) for every readable text file the new commits changed, once each.*
- `def _binary_paths(repo, plan)` - *Changed paths that cannot be reviewed as text, named so the packet is honest about them.*
- `def _commit_diff(repo, sha, path)` - *One commit's hunks for a path, against its first parent (root commits included).*
- `def _split_hunks(diff, sha, path)` - *Split one commit's file diff into stable hunk records for the packet and attribution.*
- `def _stage_hunks(repo, plan, scrub)` - *Every hunk in every new commit, oldest first, with stable IDs and optional redaction.*
- `def _scrub(text)` - *The diff with credential-shaped spans redacted, and how many detectors fired.*
- `def _fence_data(text)` - *Wrap repository-derived text in a random-id data fence.*
- `def packet_text(repo, plan, files)` - *The full hunk-by-hunk review packet for one stage, and credential spans masked.*
- `def packet_path(root, plan)` - *Where the packet for this stage is written, inside the git-ignored state folder.*
- `def _write_text(path, text)` - *Write a generated packet through a temp file and an atomic replace.*
- `def write_packet(root, plan, files)` - *Write the packet and return (path, redacted span count).*
- `def _json_payload(text)` - *The first JSON value in the answer, tolerating a code fence or a short explanation.*
- `def read_findings_file(path)` - *Read a findings file, refusing one larger than the answer cap or holding no JSON.*
- `def _patch_problem(repo, relative, old, new, touched)` - *Why a proposed replacement cannot be applied, or an empty string when it can.*
- `def _line_set(text)` - *Every non-blank line of a file, stripped, for verifying a quoted evidence line.*
- `def _hunk_lines(hunk)` - *The added and removed line bodies of one hunk, without the diff prefixes.*
- `def _attestation_problem(item, hunk, notes)` - *Why one `reviewed_hunks` entry does not attest this hunk, or an empty string.*
- `def coverage_for_payload(repo, plan, payload)` - *Check that every packet hunk carries a verbatim quote and a distinct note.*
- `def findings_from_payload(repo, payload, plan, files)` - *Validate a findings answer against the stage; returns (findings, rejected reasons).*
- `def merge_findings(proven, reviewed)` - *Rule findings first, then review findings the rules did not already name.*

---

### [`reforge/state.py`](reforge/state.py)
> *Persistent audit runs, written atomically and isolated per project.*

**Size**: `807` lines (`33329` bytes)

**Functions:**
- `def state_path(root)`
- `def is_reforge_artifact(relative)` - *Backups, temp files and locks belong to Reforge, not to the reviewed patch.*
- `def new_state()` - *A fresh state with mirrored top-level fields for schema-1 readers and reports.*
- `def _now()`
- `def validate_settings(start, step, stop)` - *A run's window plan: start >= 2, step >= 1, and an optional stop at or past start.*
- `def _stage_key(entry)`
- `def sync_last_audit(run)` - *Point the run's history at its last audit entry after a later `fix` wrote it.*
- `def _mirror(state, run)`
- `def create_run(state, start, step, stop)` - *Add one independent audit run and make it active; its history starts empty.*
- `def _find_by_id(state, run_id)`
- `def find_run(state, run_id)` - *The named run, else the active one, else the most recent; None when there is none.*
- `def current_run(state, run_id)`
- `def _migrate_v1(data)` - *A schema-1 state becomes run-1 without losing its stage, commits or history.*
- `def load_state(root)` - *Read the state; a missing file is fresh, schema 1 migrates in memory, corrupt is refused.*
- `def save_state(root, data)` - *Persist through AIKit's atomic writer under its advisory lock.*
- `def new_delivery(empty)` - *Per-window ship record; `pushed` is True only after `push()` returns 0.*
- `def entry_from_stage(plan, findings, repairs, tests, gates, skipped, reviewed, review)` - *One stage's durable record; `skipped` names binary files and `reviewed` counts the rest.*
- `def _entry_applied(entry)`
- `def _entry_verified(entry)` - *A stage that reached `record_stage` with passing gates; rollback already excluded failures.*
- `def _delivery_of(entry)`
- `def _stage_candidates(run)` - *History plus last_audit deduplicated by stage; last_audit wins on collision.*
- `def find_unpushed_verified(run)` - *Verified stages with applied repairs that were committed but never pushed.*
- `def find_uncommitted_verified(run)` - *Verified stages with applied repairs that were never committed.*
- `def mark_delivered(root, state, run, stage, delivery)` - *Record one stage's push hash in history and last_audit, then persist.*
- `def run_complete(run, window, total_commits)`
- `def completion_total(run, live)` - *The repository commit count that closes an unlimited run: live first, then the stored one.*
- `def settle_run(run, state, total_commits, *, reopen)` - *The one completed/active transition, shared by every entry point.*
- `def pending_reviews(run)` - *Every retained stage whose review object explicitly says it is not reviewed.*
- `def review_is_ready(run)` - *True when every retained stage has no explicit pending review.*
- `def finalize_review(root, state, run, total_commits)` - *Settle the run after a review and persist its mirror in one write.*
- `def record_review(root, state, run, stage, review, total_commits)` - *Attach a host review to one retained stage, then settle the run's status.*
- `def record_stage(root, state, run, entry, total_commits)` - *Advance one run, remember its audited SHAs, and settle it when the window is done.*
- `def mark_repairs(root, state, run, repairs)` - *Mark repaired findings in the run's last audit so `fix` is idempotent.*
- `def unrepaired_findings(run)`
- `def pending_fixable(run)` - *Findings an agent still has to repair before another stage may start.*
- `def stop_run(root, state, run)`
- `def resume_run(root, state, run)`
- `def update_settings(root, state, run, start, step, stop)` - *Change a run's step/stop; start may change only before its first stage.*
- `def run_summary(run)`
- `def runs_summary(state)`

---

### [`reforge/textdetect.py`](reforge/textdetect.py)
> *Structural review of changed text files that need no language front end.*

**Size**: `113` lines (`4311` bytes)

**Functions:**
- `def is_text(source)` - *Whether a file revision can be reviewed as text instead of skipped as binary.*
- `def _snippet(lines, line)`
- `def _finding(code, path, line, lines, commit)`
- `def _conflict_markers(path, lines, commit)`
- `def _invalid_json(path, source, lines, commit)`
- `def _invalid_toml(path, source, lines, commit)`
- `def _unclosed_fence(path, lines, commit)`
- `def detect_text(path, source, commit)` - *Every proven defect in one text file revision, ordered by line.*

---

### [`reforge/verification.py`](reforge/verification.py)
> *Patch review, repair re-checks and bounded test execution.*

**Size**: `99` lines (`4307` bytes)

**Functions:**
- `def _shell(command)`
- `def _run_bounded(argv, cwd, timeout)` - *Run a command with a timeout that tears down its whole process tree.*
- `def run_test_command(command, cwd, timeout)` - *Run a project command with stdin closed and the whole process tree bounded.*
- `def python_command(*args)`
- `def default_test_command(root)` - *The repository's own unittest discovery when it has tests; never a guessed runner.*
- `def recheck_repairs(root, repairs)` - *Every repaired rule must be absent from the file it was repaired in.*
- `def review_patch(root, allowed_paths, scanner)` - *Review the actual diff: only intended paths, no credential-shaped added line.*

---

### [`reforge/version.py`](reforge/version.py)
> *The single version constant shared by the package, its CLI and the archived standalone repository.*

**Size**: `3` lines (`128` bytes)

---

### [`reforge.py`](reforge.py)
> *Standalone Aegean Reforge entry point: `python reforge.py --help`.*

**Size**: `9` lines (`187` bytes)

---

### [`scripts/aikit_cli.py`](scripts/aikit_cli.py)
> *`aikit` command line: create, attach, list, report on, check, fix and delegate for the projects*

**Size**: `1562` lines (`78871` bytes)

**Functions:**
- `def failure_tail(output)`
- `def _register_delivered_ideas(project_path, project_name)` - *Register ideas named by the project's delivered commits; raises on a bad register.*
- `def _report_registered_ideas(project_path, project_name)` - *Best-effort registration after a push; delivery already succeeded, so never fail it.*
- `def _sync_dossier(project_path, project_name)` - *Best-effort dossier catalogue sync after a publish; the publish itself already succeeded.*
- `def resolve_gates(project)`
- `def run_gates(path, gates)`
- `def present_project(name, workspace)` - *The registered project `name`, refusing one whose folder or record is gone.*
- `def project_is_clean(audit, open_ui_task)` - *Whether the project's tree and ledger are delivery-ready, decided once for every surface.*
- `def test_command_topic(test_command)` - *The language topic a known test runner implies, or None for a custom command.*
- `def publish_topics(recorded)` - *The AI-chosen topics `publish` sets, validated; AIKit adds no tag on its own (ADR-236).*
- `def license_summary(project)` - *One line on the project's license tier for `status` (ADR-214).*
- `def project_payload(project)` - *The project half of a `--json` report: what `status` prints as its header lines.*
- `def error_envelope(error)` - *The stable `--json` failure shape shared by every project command (ADR-167, ADR-172).*
- `def print_guidelines(project)` - *The project's own rules, with their rank, in every cold-start report (PRINCIPLE-004 R2).*
- `def cmd_new(args)`
- `def cmd_attach(args)`
- `def cmd_list(args)`
- `def cmd_status(args)`
- `def cmd_resume(args)`
- `def cmd_guideline(args)`
- `def cmd_checkpoint(args)`
- `def cmd_complete(args)`
- `def cmd_clean(args)`
- `def project_baseline_errors(project, audit)` - *The delivery baseline `--strict` requires; ordinary check reports these as warnings.*
- `def default_topic_warning(project)` - *The default-only topic warning, or None when the project has a domain topic.*
- `def ui_review_waiver(project_root)` - *The project rule that waives the person in a UI review, or None (ADR-310).*
- `def _named_guideline(line)`
- `def cmd_check(args)`
- `def cmd_push(args)` - *Gated push: a discoverable alias for `check --push`.*
- `def cmd_fix(args)` - *Repair what AIKit can repair mechanically, then run the gates: everything left is the*
- `def cmd_publish(args)`
- `def cmd_archive(args)` - *Move a project to `projects/archive/` and archive its GitHub repository.*
- `def cmd_license(args)`
- `def _write_project_topics(project, topics, source)`
- `def _topic_error(exc)`
- `def cmd_topics(args)` - *Let an AI choose GitHub topics; validate, record and optionally apply them (ADR-236).*
- `def cmd_ui_id(args)` - *Detect or manually set a project's UI identifier (ADR-233).*
- `def cmd_media(args)` - *Generate, review and apply brand/screenshot media (ADR-235).*
- `def cmd_reforge(args)` - *Reach Aegean Reforge through AIKit's registry, gates and persistence.*
- `def cmd_idea_catcher(args)` - *Reach the private Idea Catcher register that ships with AIKit.*
- `def cmd_delegate(args)`
- `def cmd_ui(args)` - *Bound a UI task to one declared surface and keep it inside that contract.*
- `def main(argv)`

---

### [`scripts/aikit_help.py`](scripts/aikit_help.py)
> *Generated top-level CLI help for the `--help` fast path (ADR-180).*

**Size**: `57` lines (`3284` bytes)

---

### [`scripts/aikit_parser.py`](scripts/aikit_parser.py)
> *The `aikit` command-line grammar: its parser and the Why/Fix triad for usage errors.*

**Size**: `313` lines (`21778` bytes)

**Classes:**
- `class TriadArgumentParser` - *argparse whose usage errors carry Why/Fix like every other AIKit error.*
  - Method `.error(message)`

**Functions:**
- `def report_error(error)` - *Print the error triad to stderr and return its exit code.*
- `def build_parser()`

---

### [`scripts/check_project_hygiene.py`](scripts/check_project_hygiene.py)
> *Project hygiene scan (PRINCIPLE-003 R4, PRINCIPLE-010, PRINCIPLE-011 R3, PRINCIPLE-000 R5).*

**Size**: `818` lines (`39920` bytes)

**Classes:**
- `class Finding` - *One violation, addressed to the line a developer must change.*
  - Method `.render()` - *The one-line report form: `path:line [rule] message`.*

**Functions:**
- `def _keyword(call, name)` - *The value of `call`'s keyword `name`, or None when the call omits it.*
- `def _true_literal(node)` - *Whether the expression is the literal `True` (a name called `True` cannot exist).*
- `def _subprocess_aliases(tree)` - *Local name -> imported subprocess member, so aliases keep their original call name.*
- `def _subprocess_name(call, aliases)` - *The subprocess member a call invokes, whether module-qualified or imported by name.*
- `def _subprocess_call(node, aliases)` - *The node as a `subprocess` call (module-qualified or imported by name), else None.*
- `def check_banned_calls(rel, tree)` - *PRINCIPLE-003 R4 and PRINCIPLE-010: calls that lose quoting or execute data as code.*
- `def _scope_walk(scope)` - *Walk one function (or the module) without descending into nested functions.*
- `def _parents(tree)`
- `def _enclosing_scope(node, parents)`
- `def _bounded_wait(scope)` - *Variable names and direct call nodes in one scope whose Popen wait carries a timeout.*
- `def _popen_targets(scope, call)` - *Names a Popen call is assigned to in one scope, including `with ... as name`.*
- `def check_subprocess_calls(rel, tree)` - *PRINCIPLE-003 R4 and PRINCIPLE-010: portable, bounded, list-passed subprocess calls.*
- `def check_environ_index(rel, tree)` - *PRINCIPLE-011 R3: a hard-indexed environment variable crashes where it is unset.*
- `def _open_mode(call)` - *The literal mode of an open() call, or None when binary-ness is not decidable.*
- `def _is_open_call(node)` - *Whether the node is a builtin `open(...)` or an object's `.open(...)` method call.*
- `def check_open_calls(rel, tree)` - *PRINCIPLE-003 R4 and PRINCIPLE-010: text mode needs an explicit encoding and a with block.*
- `def check_silent_except(rel, tree)` - *PRINCIPLE-000 R5: a handler that discards the error and does nothing hides the failure.*
- `def _docstring_ids(tree)` - *Ids of docstring constants: prose may name any path without baking it into behaviour.*
- `def _call_head(node)` - *The called function's final name: `Path` for Path(...), `join` for os.path.join(...).*
- `def _direct_arguments(call)` - *Positional and keyword argument expressions of a call.*
- `def check_absolute_paths(rel, tree)` - *PRINCIPLE-003 R4: a machine-specific path reaching file access breaks every other machine.*
- `def check_asset_source(rel, source)` - *PRINCIPLE-003 R3: a static asset that loads from a third party is a hidden dependency.*
- `def _marked(lines, line, rule)` - *Whether a deliberated `hygiene: allow` marker excuses this finding.*
- `def check_python_source(rel, source)` - *Every Python finding in one source text; findings on `hygiene: allow` lines are dropped.*
- `def _read_source(rel, path)` - *The file's UTF-8 text, or the finding that replaces it (PRINCIPLE-000 R5: no silent skip).*
- `def _is_root_test_module(path)` - *Whether `path` is a test module at the project root, where default runners import it.*
- `def _is_root_readme(path)` - *Whether `path` is the project's own README at the repository root.*
- `def _artifact_rule(path)` - *The tracked-artifact rule and message for `path`, or None when it is ordinary source.*
- `def classify_artifacts(tracked, untracked)` - *Artifact findings from git's tracked and untracked-non-ignored path lists.*
- `def _git_paths(root, args)` - *The NUL-separated path list from one bounded git call, or the finding that replaced it.*
- `def scan_artifacts(root)` - *Artifact findings for one git work tree, read-only and sorted (PRINCIPLE-014 R4).*
- `def scan_tree(root, artifacts)` - *Every hygiene finding under `root` in stable order. Generated and vendored directories are*
- `def run_scan(root, artifacts)` - *Scan `root` and print the report; the process exit code (PRINCIPLE-012 R4: terse).*
- `def main(argv)` - *Parse `--workspace` and run; argument misuse returns 2 with the Why/Fix triad.*

---

### [`scripts/check_reachability.py`](scripts/check_reachability.py)
> *Invariant Reachability Shield (PRINCIPLE-014 Rule 7)*

**Size**: `382` lines (`17139` bytes)

**Functions:**
- `def parse_module(path)` - *Parse a module once per content. Every analysis below walks the same files, and parsing each*
- `def module_nodes(path)` - *Every node of the module, walked once per parsed tree: references, state keys and literals*
- `def production_modules(root)` - *Production source files whose reachability is audited (excludes this checker itself).*
- `def collect_definitions(files)` - *Map every top-level function name to the module that defines it.*
- `def collect_references(files)` - *Every name referenced in production code, however it is reached.*
- `def find_unreachable(files)` - *Functions defined in production code with no production reference outside themselves and no allowlist entry.*
- `def collect_state_keys(files)` - *Literal string keys read via `.get("k")` or `["k"]`, and keys written as dict literals,*
- `def find_phantom_keys(files)` - *State keys read by production code that no production code ever writes.*
- `def run_check(verbose)` - *Audit reachability and key round-trips, reporting tersely (PRINCIPLE-012 Rule 4).*

---

### [`scripts/check_secrets.py`](scripts/check_secrets.py)
> *Secret & Sensitive Data Hygiene Scanner (PRINCIPLE-019)*

**Size**: `913` lines (`43908` bytes)

**Classes:**
- `class BaselineError` - *The baseline file is missing or refuses its own schema (IDEA-1132).*

**Functions:**
- `def shannon_entropy(value)` - *Bits of entropy per character; random credentials score high, English prose low.*
- `def is_strongly_allowlisted(line)` - *An explicit pragma or an unambiguous placeholder suppresses every detector.*
- `def is_weakly_allowlisted(line)` - *A hint like "example" suppresses only the low-confidence entropy fallback.*
- `def pragma_scope(line)` - *The detector names a scoped pragma excuses, or None for a bare pragma or none.*
- `def pragma_has_reason(line)` - *Whether an allow-secret pragma carries an inline `-- reason` (PRINCIPLE-019 R5).*
- `def detector_in_scope(detector, scope)` - *Whether a finding label is excused by a scoped pragma's names.*
- `def scan_text(label, text)` - *Return (label, line_no, detector, excerpt) for every finding in a blob of text.*
- `def looks_random(value)` - *A token shaped like a generated key: mixed case and digits, and high entropy. Hex digests*
- `def _encoded_candidates(line)` - *Up to two decodable candidates from one line (IDEA-1133 bound).*
- `def _to_text(raw)` - *Bytes to text for the encoded pass; empty when not plausibly text.*
- `def _decode_candidate(token)` - *One bounded base64/hex decode; empty when not decodable text.*
- `def scan_encoded_passes(label, lineno, line, scope)` - *Bounded decoded-payload findings for one line (IDEA-1133).*
- `def redact(line, start, end)` - *The line with the secret span cut to its first 4 characters plus `***` (PRINCIPLE-019 R4).*
- `def scrub_text(text)` - *`text` with every credential-shaped span replaced by `[REDACTED]`, and the detectors hit.*
- `def should_skip(path_str)`
- `def git_output(args, repo)`
- `def scan_staged(gaps, repo)` - *Scan staged content only - the surface about to become permanent history.*
- `def scan_diff(diff, default_label)` - *Every added line of a unified diff, labelled by its file. Pure: removed lines are history*
- `def scan_commits(rev_range, gaps, repo)` - *Every line the commits in `rev_range` add: what a push uploads. The working tree is not, so a*
- `def iter_tracked_files(gaps, repo, include_self)`
- `def scan_all(gaps, repo)`
- `def scan_agent_memory(gaps, repo)` - *PRINCIPLE-019 Rule 3: agent working memory is tracked output. The ledger's free-text impact*
- `def fingerprint_finding(label, detector, excerpt)` - *Stable identity of one finding (IDEA-1132).*
- `def _baseline_detector_names()` - *Detectors a baseline entry may name: pattern plus encoded-pattern twins plus emitted entropy labels.*
- `def _is_valid_baseline_detector(detector)` - *Whether a baseline entry detector names a real finding label.*
- `def load_baseline(path, *, today)` - *Read and validate a baseline file; closed schema (IDEA-1132).*
- `def apply_baseline(findings, baseline, *, today)` - *Split findings against the baseline (IDEA-1132); pure, no I/O.*
- `def run_scan(mode, target, verbose, repo, commits, baseline)` - *Scan the requested surface plus agent memory, reporting tersely (PRINCIPLE-012 R4).*

---

### [`scripts/check_test_budgets.py`](scripts/check_test_budgets.py)
> *Test Tier Budget Gate (PRINCIPLE-010 Rule 6, PRINCIPLE-014 Rule 3)*

**Size**: `306` lines (`13383` bytes)

**Classes:**
- `class TierResult` - *One tier's measured outcome; frozen so a report cannot edit what was measured.*
  - Property `.per_test_ms`
  - Property `.budget_ms`
  - Property `.inside_budget`

**Functions:**
- `def _failure_tail(output)` - *The last bounded slice of a failed tier's output, without its trailing blank lines.*
- `def _print_failure_tail(tail)` - *Print a bounded failure slice between rules, or nothing when the tail is empty.*
- `def _decode_stream(stream)`
- `def parse_tier_output(output)` - *The count and duration unittest prints, or None when it never got that far.*
- `def default_runner(module, timeout)` - *Run one tier the way the runbook documents it, so the gate measures the real command.*
- `def run_tier(module, runner, attempts, retry_delay)` - *Measure one tier, or None when its output carried no summary. A green run over the ceiling is*
- `def budget_errors(results)` - *One line per tier that is over its ceiling; empty when every tier fits.*
- `def run_check(runner, verbose, retry_delay, sequential)`

---

### [`scripts/delegate_transcript.py`](scripts/delegate_transcript.py)
> *Append-only JSONL transcript for sub-agent delegation (S-E).*

**Size**: `208` lines (`9375` bytes)

**Functions:**
- `def _scrub_data(obj)` - *Scrub every string inside `obj` (keys are ours, values may be theirs).*
- `def _sha(text)`
- `def append_event(path, kind, data)` - *Append one scrubbed event; returns the stored event (with `seq`/`ts`).*
- `def append_request(path, role, prompt, file, model, timeout, output_format)` - *Log a delegate invocation (prompt scrubbed, plus len+sha for replay audit).*
- `def append_result(path, exit_code, output, duration_s)` - *Log a delegate outcome (output scrubbed, plus len+sha for identical-verdict proof).*
- `def _load_events(path)` - *Parse every line; raises ValueError with Why/Fix on the first corrupt line.*
- `def verify_transcript(path)` - *Check schema/seq/order/kinds/secrets; (True, detail) or (False, Why/Fix detail).*
- `def replay_transcript(path)` - *Return the recorded (exit_code, output) without invoking any runner.*

---

### [`scripts/disruption_help.py`](scripts/disruption_help.py)
> *Generated top-level help for the disruption-recovery `--help` fast path (ADR-180).*

**Size**: `61` lines (`3770` bytes)

---

### [`scripts/disruption_recovery.py`](scripts/disruption_recovery.py)
> *Disruption Recovery & Task Progress Ledger (PRINCIPLE-006, PRINCIPLE-013)*

**Size**: `2160` lines (`102828` bytes)

**Classes:**
- `class UnsupportedLedgerVersion` - *A ledger declares a schema this build cannot read (PRINCIPLE-013 R4, PRINCIPLE-016 R5).*
  - Method `.__init__(path, found, supported)`
- `class LedgerOwnershipError` - *A write to a task another identified agent owns, refused before anything changed (ADR-209).*
  - Method `.__init__(task_id, owner, agent, since)`

**Functions:**
- `def empty_ledger()` - *A fresh in-memory ledger; load_ledger() never creates the file for this.*
- `def workspace_ledger_path(workspace)` - *The ledger of `workspace`: `<workspace>/.aikit/task_ledger.json` for a project AIKit builds,*
- `def get_ledger_path(custom_dir)` - *Return path to task ledger, creating parent directories if needed.*
- `def file_lock(lock_path, timeout_seconds, poll_interval)` - *Cross-platform cooperative advisory lock (PRINCIPLE-013).*
- `def locked_ledger(ledger_file, timeout_seconds, poll_interval)` - *Serialize a full read-modify-write cycle on the task ledger (PRINCIPLE-013 Rule 3).*
- `def fsync_dir(dir_path)` - *Flush a directory entry so a completed `os.replace` survives power loss (PRINCIPLE-013 R1).*
- `def check_disk_headroom(target_dir, min_mb)` - *Check whether sufficient disk headroom exists before writing (PRINCIPLE-013).*
- `def ledger_version_supported(version)` - *Whether this build can read a ledger declaring `version`: an int from 1 to the current schema.*
- `def validate_ledger_version(data, path)` - *Refuse a ledger whose declared schema this build does not read (PRINCIPLE-013 R4).*
- `def _read_ledger_file(path)` - *Parse one ledger file, validate its version, then normalize it in memory.*
- `def _quarantine_ledger(path)` - *Move a corrupt ledger aside without overwriting an earlier quarantine in the same second.*
- `def migrate_ledger_schema(data)` - *Ensure recovered or loaded ledger conforms to current schema specification (PRINCIPLE-013).*
- `def _replace_with_retries(tmp_path, file_path, max_retries)` - *Replace with a Windows lock-contention retry loop (PRINCIPLE-013 R2).*
- `def _rotate_shadow_backup(file_path)` - *Keep the last durable content as `<file>.bak` before the replace (PRINCIPLE-013 R1).*
- `def _atomic_write(file_path, mode, writer, *, newline, backup, max_retries, min_headroom_mb)` - *Write through a temp file, fsync, shadow backup and durable replace (PRINCIPLE-013 R1/R2).*
- `def atomic_write_json(file_path, data, max_retries, min_headroom_mb)` - *Atomically write JSON data using fsync, shadow backup, and temporary replacement (PRINCIPLE-013).*
- `def atomic_write_text(file_path, text, newline, backup, max_retries, min_headroom_mb)` - *Atomically write UTF-8 text with the same durability guarantees as JSON (PRINCIPLE-013).*
- `def atomic_write_bytes(file_path, data, backup, max_retries, min_headroom_mb)` - *Atomically write raw bytes with the same durability guarantees as JSON (PRINCIPLE-013).*
- `def load_ledger(ledger_file)` - *Safely load the task ledger with startup self-healing (PRINCIPLE-013).*
- `def prune_checkpoints(checkpoints, active_task_id, max_history)` - *Prune checkpoints to maintain a bounded rolling memory window (PRINCIPLE-004).*
- `def task_plan_checkpoint(task_checkpoints)` - *The task's plan (PRINCIPLE-004 R1): its latest Phase 2 checkpoint whose description starts*
- `def _refuse_newer_ledger_on_disk(path)` - *Re-check both slots under the lock before replacing either (PRINCIPLE-013 R3).*
- `def save_ledger(ledger, ledger_file, max_history, _locked)` - *Save the task ledger atomically to disk with bounded rolling history (PRINCIPLE-004).*
- `def resolve_phase_num(phase, explicit_num)` - *Resolve lifecycle phase number 1..5 for compaction orientation (PRINCIPLE-002).*
- `def unquote_git_path(path)` - *A path as git printed it, back as the real name.*
- `def porcelain_entries(porcelain_output)` - *`(XY, path)` for each entry of `git status --porcelain` output; a rename or copy is reported*
- `def classify_git_status(porcelain_output)` - *Classify `git status --porcelain` v1 output into disruption categories (PRINCIPLE-006 R2).*
- `def resolve_active_phase(active_task, default)` - *Read the recorded lifecycle phase of a task (PRINCIPLE-002 R4, PRINCIPLE-004 R2).*
- `def repo_relative(path)` - *A path as the ledger stores it (PRINCIPLE-012 R5): repository-relative with `/` separators*
- `def resolve_agent(explicit, env)` - *The agent a ledger write is attributed to (ADR-209): `--agent`, else `AIKIT_AGENT`, else the*
- `def agent_history(checkpoints, active)` - *Who worked on a task, in order: `started by A; continued by B` (ADR-209). The chain the active*
- `def _claim(active, agent, take_over)` - *Check that `agent` may write the in-progress task `active`; returns the previous owner when the*
- `def record_checkpoint(task_id, phase, description, files_affected, status, ledger_file, phase_num, why, benefits, risks, mitigation, handoff, agent, take_over)` - *Record an atomic micro-checkpoint in the task ledger (PRINCIPLE-002, PRINCIPLE-006, PRINCIPLE-007).*
- `def mark_task_completed(task_id, ledger_file, agent, take_over)` - *Mark the active task completed (locked, PRINCIPLE-013 R3). Returns False, changing nothing,*
- `def reset_active_task(reason, ledger_file, agent, take_over)` - *Abandon or reset the active in-progress or suspended task in the ledger (locked,*
- `def suspend_active_task(reason, ledger_file, agent, take_over)` - *Pause the active task without abandoning it (ADR-219). The plan, phase and handoff stay in the*
- `def resumable_tasks(ledger)` - *Tasks whose latest checkpoint is `suspended` or `superseded`, newest first (ADR-219).*
- `def resume_task(task_id, ledger_file, agent)` - *Reactivate a suspended or superseded task at its recorded phase (ADR-219). A checkpoint is*
- `def _reraise(error)`
- `def sweep_files(workspace_dir, pattern)` - *Files under `workspace_dir` matching `pattern`, pruning `SWEEP_PRUNED_DIRS` while walking, so a*
- `def clean_dangling_temp_files(workspace_dir, min_age_seconds)` - *Purge orphaned *.tmp_* files left by interrupted writes (PRINCIPLE-006 R6, PRINCIPLE-013).*
- `def git_porcelain_status(workspace)` - *Default git adapter: run `git status --porcelain -z` in `workspace` (bounded, PRINCIPLE-010 R3).*
- `def run_disruption_audit(workspace_dir, git_status)` - *Execute a comprehensive pre-flight disruption audit (PRINCIPLE-006, PRINCIPLE-007).*
- `def append_file_list(lines, title, files, cap)` - *Append a titled file list of at most `cap` entries, so a huge tree stays bounded (PRINCIPLE-004 R5).*
- `def audit_body_lines(audit)` - *Findings shared by --audit and --resume, so neither report hides what the other shows.*
- `def format_audit_report(audit)` - *Generate human and AI-readable disruption recovery audit report.*
- `def format_resume_report(audit)` - *The one cold-start report (PRINCIPLE-004 R2): every --audit finding, then where to resume.*
- `def validate_conventional_commit(message)` - *Validate that a commit message conforms to Conventional Commits (PRINCIPLE-018).*
- `def _ast_without_docstrings(source)` - *AST dump with docstrings removed; comments and formatting never reach the AST.*
- `def classify_change(path, old, new)` - *Return (track, reason) for one changed file. Pure: no I/O.*
- `def classify_track(changes)` - *Classify a change set into Track A, B or C (PRINCIPLE-002 R3). Pure: no I/O.*
- `def collect_working_changes(workspace)` - *Read every changed, staged or untracked file versus HEAD (git adapter for --track).*
- `def report_operational_error(exc_type, exc, tb)` - *`sys.excepthook` for the CLI (PRINCIPLE-011 R6, PRINCIPLE-013 R2/R5): an operational failure*
- `def validate_argv(argv)` - *Return unrecognized options, skipping values of known value-taking flags (PRINCIPLE-011).*
- `def parse_handoff(text)` - *One `--handoff` string as `{key: value}`, plus the reasons it is unusable.*
- `def impact_errors(description, phase_num, fields, has_prior_impact)` - *PRINCIPLE-007 R6: a task's first plan checkpoint (Phase 2, `--desc` starting `[1/`) carries the*
- `def missing_impact_warning(task_id, phase_num, has_prior_impact, has_impact_now)` - *PRINCIPLE-007 R1: a Track C task records its impact assessment before its first edit. A task*
- `def scrub_checkpoint_text(desc, impact, redact, handoff)` - *The checkpoint's free text, scrubbed when `redact` is set, plus the detectors that fired.*
- `def checkpoint_command(task_id, phase, phase_num, desc, impact, ledger_file, redact, handoff, agent, take_over)` - *Record a checkpoint behind the PRINCIPLE-007 R1/R6 impact gate; returns the exit code. The one*
- `def report_ownership(error)` - *Print the triad for a refused write to another agent's task; returns exit code 1.*
- `def argv_value_errors(argv)` - *Value flags given without a value, or with an invalid one (PRINCIPLE-003 R6). These used to*

---

### [`scripts/dogfood.py`](scripts/dogfood.py)
> *Operational Dogfooding Runner (PRINCIPLE-015)*

**Size**: `672` lines (`30499` bytes)

**Functions:**
- `def sanitized_env(base)` - *Child env without code-injection vectors (S-A F1/F2).*
- `def cwd_inside_repo(cwd)` - *Whether `cwd` resolves inside the AIKit checkout (dogfood must never run there).*
- `def terminate_process_tree(proc)` - *Kill a process and all of its children (PRINCIPLE-015 Rule 2).*
- `def supervised(argv, cwd, env)` - *RAII supervisor: guarantees recursive teardown even if the body raises. `argv` is a list, or*
- `def sandbox_jail()` - *Ephemeral workspace outside the repository and outside host user directories*
- `def run_cli(script, args, cwd)` - *Invoke a CLI as a real binary with stdin closed (PRINCIPLE-015 Rule 3 EOF safety).*
- `def _is_transient_fixture(path)` - *Transient test scaffolding invisible to the blast hash (Stage 4 CHECK convention).*
- `def _hash_file_contents(path)` - *SHA-256 of a dirty file's bytes, streamed; unreadable files hash stably.*
- `def snapshot_tree()` - *Working-tree snapshot: the hashed status entries plus {path: content-sha}.*
- `def fingerprint_of(snapshot)` - *SHA-256 over a snapshot in status order; None propagates git-unavailable.*
- `def repo_fingerprint()` - *Content fingerprint of the repository working tree, or None when git is unavailable.*
- `def diff_snapshots(before, after)` - *Added/removed/modified paths between two snapshots; empty when identical.*
- `def blast_verdict(before_hash, after_hash, before_snap, after_snap)` - *Blast-radius verdict with evidence: (clean, detail, differing paths).*
- `def track_golden_lifecycle(jail, log)` - *Track 1 (PRINCIPLE-015 Rule 5): a complete create -> modify -> retrieve lifecycle driven*
- `def track_chaos_perturbation(jail, log)` - *Track 2 (PRINCIPLE-015 Rule 5): hostile perturbations. Each must fail cleanly with no*
- `def track_readonly_gates(jail, log, runner)` - *Track 3: the two freshness gates the delivery triad depends on must run read-only from an*
- `def track_help_startup_budget(jail, log)` - *Track 4: every entrypoint must answer --help safely and inside the PRINCIPLE-010 R5*
- `def _run_track(name, fn, jail)` - *Run one track with its own log; a crashing track is a failing track, never a crashing run.*
- `def run_dogfood(verbose, keep_sandbox)` - *Execute every dogfood track and emit a terse dashboard (PRINCIPLE-015 Rule 7).*

---

### [`scripts/dossier_sync.py`](scripts/dossier_sync.py)
> *Keep the AegeanWorks dossier catalogue in step with a published project (PRINCIPLE-016).*

**Size**: `457` lines (`19908` bytes)

**Functions:**
- `def dossier_root(explicit)` - *The dossier checkout, or None when this workspace does not carry one.*
- `def repository_slug(url)` - *(owner, repository) from a GitHub origin URL, else None.*
- `def _today()`
- `def _write(path, text)`
- `def _write_if_changed(path, text)` - *Write only when the bytes would differ, so a no-op sync reports nothing.*
- `def github_facts(name)` - *The repository's live GitHub facts, read through the `gh` CLI publish already requires.*
- `def catalogue_category(project_path, topics, description)` - *The dossier category from the project's license kind and its own words.*
- `def build_entry(name, facts, description)` - *The metadata entry the dossier records, in the catalogue's own key order.*
- `def _load_json(path)`
- `def _dump_json(data)`
- `def _upsert_metadata(dossier, entry)`
- `def _upsert_snapshot(dossier, entry)`
- `def _upsert_license(dossier, name, family)`
- `def _escape(value)`
- `def _attribute(value)`
- `def _card(entry, family, category, mark)`
- `def _upsert_card(dossier, entry, family, category)`
- `def _mark(name)`
- `def _inline_digest(body)`
- `def _refresh_inline_hash(page, old_body, new_body)` - *Replace the old inline-script CSP hash, so the rewritten JSON-LD stays allowed.*
- `def _upsert_jsonld(dossier, entry, family, category)`
- `def _upsert_readme(dossier, entry, category)`
- `def _upsert_catalogue_set(dossier, name)`
- `def sync_entry(dossier, entry, family, category)` - *Upsert one catalogue entry everywhere the dossier records it; return changed files.*
- `def _refresh_media(dossier, name)` - *Rebuild the dossier's schema-2 media for one repository; the workflow retries on push.*
- `def sync_published(project_path, project_name, dossier)` - *Bring the dossier catalogue in line with a published project; never raises for a skip.*

---

### [`scripts/evidence_outcome.py`](scripts/evidence_outcome.py)
> *Shared no-evidence outcome model (IDEA-1118).*

**Size**: `47` lines (`1582` bytes)

**Functions:**
- `def outcome_for_counts(observed, failures)` - *The shared verdict for a counted observation.*
- `def no_evidence_message(what, reason)` - *The Why/Fix lines for an inconclusive refusal (PRINCIPLE-011 R8).*
- `def is_refusal(outcome)` - *Whether an outcome must refuse to pass (fail-closed).*

---

### [`scripts/evidence_policy.py`](scripts/evidence_policy.py)
> *Evidence policy over step attestations (IDEA-1169).*

**Size**: `162` lines (`7221` bytes)

**Classes:**
- `class PolicyError` - *The policy text names no known policy.*

**Functions:**
- `def parse_policy(text)` - *Parse a policy word into (kind, n); closed vocabulary (IDEA-1169).*
- `def evidence_hash(text)` - *Short stable digest of a step's evidence tail (IDEA-1169).*
- `def attest(step, outcome, evidence, envelope)` - *One step attestation: what ran, its shared-model outcome, its evidence.*
- `def evaluate(policy_text, attestations, *, envelope_keys, verify_sealed)` - *Evaluate attestations under the named policy (IDEA-1169).*

---

### [`scripts/git_guard.py`](scripts/git_guard.py)
> *Local publish guard: block raw git pushes so only `aikit.py publish` uploads.*

**Size**: `283` lines (`10065` bytes)

**Functions:**
- `def _config_value(raw)` - *A git config value as git reads it: quotes removed, and ; or # outside quotes ends it.*
- `def _config_hooks_path(config, seen)` - *core.hooksPath from one git config file, following include.path files.*
- `def _local_hooks_path(project_root)` - *core.hooksPath from the repository-local .git/config, without spawning git.*
- `def _global_hooks_path()` - *core.hooksPath from the global and system config files, without spawning git.*
- `def _git_config_value(project_root, key)` - *Read one git config value, or None when it is unset or git cannot run.*
- `def hook_path(project_root)` - *The repository's pre-push hook path, or None when the folder is not a git repo.*
- `def install_pre_push_hook(project_root, project_name)` - *Install the guard and return its path, or None when there is no git repository.*
- `def is_guard_installed(project_root)` - *Whether the project's pre-push hook is the AIKit guard.*
- `def publish_environment()` - *Mark the current process as an authorised AIKit publish.*
- `def _hook_script(project_name)`
- `def _read_text(path)`

---

### [`scripts/marked_blocks.py`](scripts/marked_blocks.py)
> *Generated text inside a file the user owns, fenced by `<!-- aegean:<name>:start -->` and*

**Size**: `40` lines (`1749` bytes)

**Functions:**
- `def markers(name)` - *The start and end comments of block `name`; HTML comments, so a rendered README hides them.*
- `def block_span(text, name)` - *Where block `name` starts and ends in `text`, markers included; None unless both are in order.*
- `def fenced(name, body)` - *`body` between the markers of block `name`, one per line, without a trailing newline.*
- `def replace_block(text, name, body)` - *`text` with block `name` holding `body` and nothing outside it changed; None when it has no block.*

---

### [`scripts/project_archive.py`](scripts/project_archive.py)
> *Archive a project: move it to ``projects/archive/`` and mark its GitHub repository archived.*

**Size**: `568` lines (`29460` bytes)

**Functions:**
- `def _is_archive_banner(line)` - *Whether a line is the notice this module inserts, not a project description.*
- `def _visible_text(raw)` - *Markdown/HTML line reduced to visible text; media-only lines reduce to empty.*
- `def _triad(what, why, fix)`
- `def archive_dir(workspace)` - *The folder archived projects live in: ``projects/archive/`` (git-ignored via ``projects/``).*
- `def archived_destination(workspace, name, to)` - *Where ``name`` moves to: ``to`` when given, else ``projects/archive/<name>``.*
- `def validate_archive_move(src, dst)` - *The refusal triad when ``src`` cannot move to ``dst``, else None.*
- `def archive_notice(reason, date_str)` - *The one-paragraph banner ``update_readme_for_archive`` inserts after the description.*
- `def update_readme_for_archive(readme_path, reason, date_str)` - *Insert the archive banner after the README description; idempotent.*
- `def archive_github_description(original, override)` - *The GitHub description for an archived repo: ``[ARCHIVED] <original>`` within 350 chars.*
- `def _default_runner(argv, cwd)`
- `def _attached_path(workspace)`
- `def _forget_or_move_attached(workspace, name, src, dst)` - *Keep ``attached.json`` true after the move: forget inside-``projects/`` targets, else repoint.*
- `def _record_archived_config(project_path, reason, date_str, repo, description)` - *Record the archive in ``.aikit/project.json`` without touching other keys.*
- `def archive_project(project_path, name, reason, workspace, to, description, offline, allow_dirty, runner, date_str)` - *Move ``project_path`` to the archive and archive its GitHub repository.*
- `def is_archived(project_path)` - *Whether ``.aikit/project.json`` records this project as archived.*

---

### [`scripts/project_artwork.py`](scripts/project_artwork.py)
> *Image-model brand artwork for projects (ADR-239).*

**Size**: `546` lines (`30187` bytes)

**Functions:**
- `def _hex_rgb(value)`
- `def _rgba(value, alpha)`
- `def _art_prompt(name, description, motif, palette)`
- `def model_key()`
- `def _model_headers()`
- `def _download_url(url, output, attempts)`
- `def _palette_words(palette)`
- `def _logo_model_prompt(name)`
- `def _social_model_prompt(name)`
- `def _local_description(root, name, fallback)`
- `def generate_model_brand(project_root, name, force, parts, seed_offset, description, tags, kind)` - *Render the requested parts with the online image model (ADR-239/240/241).*
- `def _download(url, output, attempts)`
- `def _throttle()`
- `def fetch_artwork(project_root, name, description)` - *Generate and store this project's hero image; retries transient model failures.*
- `def _monogram(name)`
- `def _display_name(name)`
- `def _wrap_words(text, max_chars, max_lines)`
- `def _lockup(title, max_lines)`
- `def _logo_html(name, art)`
- `def _chips_html(tags)`
- `def _social_html(name, art, description, kind, tags)`
- `def compose_brand(project_root, name, description, tags, kind)` - *Render the final 512px logo and 1280x640 social card over the generated artwork.*
- `def generate_brand(project_root, name, description, tags, kind, force, refresh_art)` - *Fetch image-model artwork, compose PNG brand assets, and mark them for review.*

---

### [`scripts/project_brand.py`](scripts/project_brand.py)
> *Project-specific brand artwork: one motif, palette and composition per project.*

**Size**: `553` lines (`33446` bytes)

**Functions:**
- `def _catalog()`
- `def _hex(hue, saturation, lightness)`
- `def _fallback_palette(name)`
- `def brand_spec(name)` - *The authored motif/palette/composition for a project, with a stable fallback.*
- `def _display_name(name)`
- `def _monogram(name)`
- `def _wrap(text, width, limit)` - *Greedy word wrap that marks a clipped card instead of ending mid-sentence.*
- `def _motif_body(motif, accent, accent2, monogram)`
- `def _motif(motif, accent, accent2, cx, cy, scale, opacity, monogram)`
- `def logo_svg(name)` - *A 512px square identity: project motif, unique palette, monogram and AegeanWorks mark.*
- `def _chip_width(label)`
- `def _chips(tags, x, y)`
- `def _chips_centered(tags, y, center)`
- `def social_svg(name, kind, description, repo_url, tags)` - *A 1280x640 social card with a layout chosen for this project, not a shared template.*

---

### [`scripts/project_compat.py`](scripts/project_compat.py)
> *AI-compat scaffold and proof for generated projects (Track 2, now).*

**Size**: `440` lines (`19677` bytes)

**Functions:**
- `def _error(message, why, fix)`
- `def minimal_png_rgb(red, green, blue)` - *A valid 1x1 RGB PNG, stdlib-only, for scaffolded screenshot placeholders.*
- `def minimal_png(variant)` - *Legacy single-channel placeholder; prefer ``minimal_png_rgb`` for pairs.*
- `def _inventory_template(kind)`
- `def _demo_template(kind)`
- `def scaffold_compat(root, kind)` - *Write compat files for `headless` or `ui`; returns the compat record.*
- `def load_compat(root)` - *Load and validate the project's compat record.*
- `def inventory_lines(output)` - *Sorted, deduplicated non-empty inventory lines.*
- `def _run(cmd, root, timeout)`
- `def _delta_lines(output)` - *Sorted WORLD-DELTA lines; the seeded-replay identity check compares these.*
- `def emit_evidence(root, cause, gate, artifact)` - *Append one cause -> gate -> artifact link to the scaffolded evidence file.*
- `def compass_report(findings)` - *Quality-as-compass: scores are info, only missing evidence fails.*
- `def verify_compat(root, runner)` - *Prove the scaffolded project is drivable; returns findings (empty is clean).*
- `def build_parser()`
- `def main(argv)`

---

### [`scripts/project_gates.py`](scripts/project_gates.py)
> *Project gates: the checks a project's own configuration declares, run as its Phase 4 (ADR-122).*

**Size**: `305` lines (`13563` bytes)

**Classes:**
- `class Gate` - *A named check and the shell command that runs it; `source` says where it came from.*
- `class GateResult` - *One gate's outcome; `returncode` is -1 when the gate could not start or timed out.*
  - Property `.passed`

**Functions:**
- `def _tracked_snapshot(root)` - *Content hashes of the dirty tracked files, or None when git cannot answer.*
- `def _rewritten_paths(before, after)` - *Tracked paths whose content identity changed between two snapshots.*
- `def _python_gates(root)`
- `def _node_gates(root)`
- `def _go_gates(root)`
- `def guidelines_gate(project_root)` - *The built-in guidelines and quality scan of the project's repository.*
- `def hygiene_gate(project_root)` - *The built-in hygiene scan of the project's source and static assets (ADR-137).*
- `def secrets_gate(project_root)` - *The built-in secret scan of the project's repository.*
- `def compat_gate(project_root)` - *The built-in AI-compat proof for generated projects (ADR-315).*
- `def resolve_gates(project)` - *The project's gates in run order: test, detected extras, mechanics test/bench,*
- `def run_shell(command, cwd, timeout)` - *Run `command` through the platform shell with stdin closed; on timeout the whole process*
- `def run_gates(project_root, gates, runner, timeout, snapshotter)` - *Run every gate, even after a failure, so one report lists all of them.*
- `def failure_tail(output, lines)` - *The last `lines` non-empty lines of a gate's output, where its error normally is.*

---

### [`scripts/project_license.py`](scripts/project_license.py)
> *Project license tiers (ADR-214).*

**Size**: `323` lines (`15908` bytes)

**Classes:**
- `class LicenseState`

**Functions:**
- `def render_restricted_license(name, since, since_commit)` - *The canonical All Rights Reserved notice, filled for a project restricted from its cutoff on.*
- `def license_state(project_root)` - *The project's tier, personal-license kind and version: the restriction, else what LICENSE says.*
- `def suggest_license(project_root)` - *What an AI should choose for this project, with the current file and the evidence.*
- `def _with_license_section(text, section)` - *`text` (LF) naming `section`'s license. AIKit owns only the paragraph between the*
- `def _licensed_readme(text, newline, kind, assets_manifest)` - *`text` with its tree's LICENSE line and License section naming the chosen personal license.*
- `def apply_license_kind(project_root, name, kind)` - *Switch a personal-tier project to software (AL-1.1), game (AGL-1.1) or science (ASL-1.1)*
- `def public_remote_refusal(project_root, name, runner)` - *The error that stops a push of a restricted project, or None. Only a remote GitHub reports as*
- `def _restricted_readme(text, newline)` - *`text` with its tree's licensing lines and its License section switched to the restricted tier.*
- `def restrict_project(project_root, name, today, runner)` - *Move a project to the restricted tier at its current commit; returns the recorded state. A*

---

### [`scripts/project_media.py`](scripts/project_media.py)
> *Project brand and screenshot media pipeline (ADR-235).*

**Size**: `909` lines (`40804` bytes)

**Classes:**
- `class _QuietHandler` - *Serve one capture directory without writing request logs.*
  - Method `.log_message(fmt, *args)`

**Functions:**
- `def media_path(root)`
- `def _head(root)`
- `def _description(root, name)`
- `def _palette(name)`
- `def _logo_svg(name)`
- `def _social_svg(name, kind, description, repo_url, tags)`
- `def _browser()`
- `def served_html(source)` - *Yield an HTTP URL for an HTML page, or its file URL for any other asset.*
- `def capture_html(source, output, width, height)` - *Render a local SVG/HTML file with the installed browser, bounded by a timeout.*
- `def jpeg_size(path)`
- `def image_size(path)`
- `def png_size(path)`
- `def _validate_svg(path, title)`
- `def _review_record(reviewer, method, notes, score)`
- `def load_media(root)`
- `def dossier_logo_is_placeholder(manifest)` - *True when a dossier media manifest still points at the generated fallback card.*
- `def media_blockers(root, dossier)` - *Assets that still need a review before a new project may be published.*
- `def save_media(root, data)`
- `def _asset(path, commit, status)`
- `def seed_media_assets(project_root, name, force, capture_png)` - *Generate candidate logo/social assets and a pending manifest; never touches the README.*
- `def capture_screenshot(project_root, name, url, viewport, force)` - *Capture a UI project at HEAD and register the image as pending review.*
- `def _parse_viewport(value)`
- `def _surface(root, url, name)`
- `def _find_asset(data, kind, index)`
- `def review_media(project_root, kind, decision, reviewer, method, notes, score, index)` - *Validate the asset, then record an approve/reject decision with its evidence.*
- `def name_of(root)`
- `def _approved(asset)` - *True only for a reviewed, approved asset entry; a missing entry is simply not approved.*
- `def _copy_media(source, target)`
- `def apply_media(project_root, name, dossier, readme_only)` - *Copy approved assets into the dossier and reference them from the project README.*
- `def _badge_row(project_root, repo)` - *License and AIKit badges under the banner; AegeanWorks keeps its own badge set.*
- `def _update_readme(readme, repo, data, shots)`
- `def audit_media(project_root, dossier)` - *Check the manifest, files, commit stamps, dossier links and README references.*
- `def media_status(project_root)`

---

### [`scripts/project_publish.py`](scripts/project_publish.py)
> *Publish a project to its own GitHub repository (ADR-134).*

**Size**: `355` lines (`17392` bytes)

**Functions:**
- `def run_command(argv, cwd)` - *Default runner: the command's exit code and combined output; -1 when it cannot start.*
- `def _triad(what, why, fix)`
- `def _clean_markdown_line(raw)` - *Strip markdown formatting, badges, and html tags from a single line.*
- `def extract_readme_description(project_root)` - *Extract a single-line summary from the project's README.md for GitHub (author case kept).*
- `def _fit_description(text)` - *`text` within GitHub's 350 characters; the 200 used before cut what `new --description`*
- `def hide_url_credentials(text)` - *`text` with the user-info of every URL in it replaced by `***` (PRINCIPLE-019 R4).*
- `def config_value(raw)` - *A git config value as git reads it: quotes removed, and a `;` or `#` outside quotes ends it.*
- `def get_project_repo_url(project_root, runner)` - *The URL of the project's 'origin' remote with any credential in it hidden, or None.*
- `def push_range(project_root, run)` - *The commits a push uploads: those past the upstream, or the whole history without one.*
- `def scan_refusal(project_root, rev_range, run)` - *Scan every line the commits in `rev_range` add, the exact content a push uploads; returns the*
- `def auto_push_project(project_root, name, runner)` - *Push unpushed commits of a published project to its remote origin (PRINCIPLE-018: adaptive push).*
- `def apply_topics(project_root, topics, run)` - *Set `topics` on the project's repository; returns the report lines. The repository already*
- `def publish_project(project_root, name, public, runner, topics, owner, description)` - *Upload the project's commits to its own GitHub repository; returns (exit code, report).*

---

### [`scripts/project_registry.py`](scripts/project_registry.py)
> *Project registry: the projects AIKit builds (cockpit model, ADR-119).*

**Size**: `1259` lines (`58985` bytes)

**Classes:**
- `class ProjectError` - *A request AIKit cannot carry out, with its reason and remedy (PRINCIPLE-011 R6).*
  - Method `.__init__(message, why, fix, exit_code)`
- `class Stack` - *A toolchain detected in a project folder and the command that runs its tests.*
- `class Project` - *A registered project as `aikit list` reports it.*

**Functions:**
- `def license_topics(kind, restricted)` - *The GitHub topics that name a project's license tier, kept out of automatic AI choice.*
- `def title_case(text)` - *A display title from a project name: words capitalised, small joining words left lower unless*
- `def repository_name(name)` - *The GitHub repository name for a project: each hyphen- or underscore-delimited word takes a*
- `def license_choice(kind)` - *The catalog entry for `kind`, or a ProjectError naming the three choices.*
- `def detect_license_kind(project_root)` - *The domain an AI should pick a license for, from the project's own markers. Strong markers*
- `def render_project_readme(name, test_command, description, licensed, integrated, license_kind, license_version, assets_manifest, reuse, compat)` - *A README whose structure passes PRINCIPLE-005's audit, with a `<FILL:` prerequisite marker: the*
- `def license_header_match(first_line)` - *The `(kind, version)` a LICENSE first line names, including an archived legacy header.*
- `def seed_readme(project_root, name, test_command, description, licensed, integrated, license_kind, compat)` - *Write the template README when the project has none; returns whether it did. `new` and `fix`*
- `def migrate_aikit_links(project_root)` - *Rewrite the pre-move AIKit URL in the README to the current one; returns whether it did. Run*
- `def add_aikit_badge(project_root)` - *Put the AIKit Integrated badge under the README's title, or at its top without one; returns*
- `def validate_description(description)` - *The description stripped, or None; one line of 10-350 characters (GitHub's limit is 350).*
- `def normalize_topics(topics)` - *`aikit` then each topic lowercased, without repeats; refuses what GitHub would refuse.*
- `def seed_assets_manifest(project_root, kind)` - *Write the asset/data manifest `new --kind game|science` needs, so the license boundary has a*
- `def _reuse_licenses_dir(project_root)` - *The directory that holds the REUSE license texts.*
- `def _reuse_keeps_project_annotations(path, identifier)` - *Whether `REUSE.toml`'s blanket annotation already names `identifier`.*
- `def write_reuse_metadata(project_root, identifier, copyright_notice)` - *Write `LICENSES/<identifier>.txt` (or the project's existing `licenses/` directory) and a*
- `def seed_reuse(project_root, kind, version)` - *Write the machine-readable REUSE metadata for a project: a `LICENSES/LicenseRef-<key>.txt`*
- `def seed_license(project_root, kind)` - *Copy the chosen personal Aegean license into a new project (ADR-199, ADR-214, ADR-218).*
- `def seed_commercial(project_root)` - *Copy AIKit's canonical COMMERCIAL.md into a new project (ADR-212, ADR-214).*
- `def _tree_entry_name(line)` - *The exact top-level name a README tree line lists, or None for a nested or prose line.*
- `def reconcile_readme_tree(project_root, runner)` - *Auto-reconcile top-level tracked files omitted from the README tree block (PRINCIPLE-005 R5).*
- `def _python_test(root)`
- `def node_scripts(root)` - *The `scripts` map of the project's `package.json`; empty when absent or unreadable.*
- `def node_runner(root)` - *The package manager the project's lockfile names: pnpm, yarn, or npm by default.*
- `def _node_test(root)`
- `def _gradle_test(root)`
- `def _cpp_test(root)` - *The project's canonical test entry: its own native script when present, else CTest.*
- `def _fixed(command)`
- `def detect_stacks(root)` - *Every stack whose marker file sits in the project's top folder (polyglot repos list several).*
- `def validate_name(name)` - *Reject names that are not one portable folder name.*
- `def projects_dir(workspace)`
- `def config_path(project_root)`
- `def load_config(project_root)` - *A project's `.aikit/project.json`; a missing, unreadable or newer file is an error.*
- `def is_game_project(config)` - *Whether the project's own metadata classifies it as a game.*
- `def mechanics_errors(project_root, config)` - *Validate an optional mechanics contract: a headless core and the command that tests it.*
- `def _ensure_gitignore(project_root)` - *Append the transient-state patterns the project's `.gitignore` does not yet list.*
- `def write_memory(project_root, name, test_command, topics)` - *Create the project's `.aikit/project.json`, `.aikit/decisions.md` and `.aikit/task_ledger.json`*
- `def _attached_path(workspace)`
- `def load_attached(workspace)` - *Attached project folders by name; an unreadable file is an error, not an empty list.*
- `def _registered_names(workspace, attached)` - *Name to folder for every project; `attached` spares a second read of `attached.json`.*
- `def _run_git(project_root, *args)`
- `def _git_start(project_root)` - *`git init`, then commit the project's memory and instructions so a new project starts clean.*
- `def create_project(name, test_command, workspace, git_start, description, topics, license_kind)` - *Create `projects/<name>/` as a new git repository whose first commit holds the project's*
- `def attach_project(folder, name, test_command, workspace)` - *Register an existing folder as a project; returns (name, folder, memory_created). The folder's*
- `def _build_project(name, path, attached)`
- `def list_projects(workspace)` - *Every registered project, sorted by name; a vanished attached folder is reported, not dropped.*
- `def find_project(name, workspace)` - *The registered project called `name`; only that project's folder is inspected.*
- `def project_guidelines(project_root)` - *The project's rule lines (`- **G-NNN** (source): rule`), oldest first; [] when it has none.*
- `def add_guideline(project_root, rule, source)` - *Append one rule to the project's guidelines and return its new ID. Whatever the guidelines*
- `def latest_decision(project_root)` - *The last `### ADR-NNN: ...` heading in the project's decision register, if any.*

---

### [`scripts/project_topics.py`](scripts/project_topics.py)
> *GitHub topic policy (ADR-234, revised by ADR-236): an AI agent chooses the tags; AIKit validates,*

**Size**: `306` lines (`13859` bytes)

**Functions:**
- `def _read_readme(root)`
- `def _license_tags(root)`
- `def _has_token(text, token)`
- `def hint_tags(project_root, description)` - *Possible tags for the AI to consider; the agent decides and may ignore all of them.*
- `def ai_brief(project_root, name, recorded, current)` - *The bounded evidence an AI agent needs to choose the final tags.*
- `def _dedupe(tags)`
- `def _dedupe_raw(tags)`
- `def validate_choice(project_root, recorded, current, chosen, replace, remove)` - *Validate an AI addition to the existing tags; valid older tags are never dropped.*
- `def choice_from_payload(payload)` - *Accept `{"topics": [...], "remove": [...]}` or a bare list; anything else is refused.*
- `def read_choice_file(path)`
- `def repo_slug(project_root, name)` - *`owner/repo` from the project's origin, else the conventional AegeanWorks name.*
- `def github_topics(slug, runner)` - *Read the repository's live topics; ([], error) when GitHub cannot be reached.*
- `def apply_topics(slug, add, remove, runner)` - *Add and remove topics in two explicit calls; a failure is reported, never hidden.*
- `def topic_audit(current, recorded)` - *Audit the live/recorded lists without choosing anything for the agent.*

---

### [`scripts/project_ui.py`](scripts/project_ui.py)
> *Project UI identifier (ADR-233): does this project have a user interface a screenshot can show?*

**Size**: `402` lines (`16342` bytes)

**Functions:**
- `def _scan_files(root)`
- `def _read_small(path, limit)`
- `def _is_small(path, limit)` - *Size guard that survives a file vanishing between scan and check.*
- `def _safe_rel(root, rel)` - *A compat screenshot path confined to the project tree, else None.*
- `def _compat_ui_kind(root, kind, evidence)` - *Merge a compat UI contract into the detected kind, best effort.*
- `def _package_dependencies(root)`
- `def _python_dependency_text(root)`
- `def _evidence(paths, root, limit)`
- `def _html_files(files, root)`
- `def detect_ui(project_root, respect_manual)` - *Classify a project's interface, with the marker files that justify the answer.*
- `def write_ui_identity(project_root, result)` - *Persist the identifier atomically, preserving the rest of the project's memory.*
- `def set_ui_manual(project_root, has_ui, kind)` - *Record an explicit human/agent decision; `auto` clears it on the next detection.*
- `def auto_ui(project_root)`
- `def refresh_ui_identifier(project_root)` - *Re-detect after UI work; a UI command or capture proves a screenshotable surface exists.*
- `def ui_payload(project_root)`
- `def _surface_paths(project_root, evidence)` - *The smallest practical surface: detected entry files plus a source tree if one exists.*
- `def adopt_ui(project_root, test_command)` - *Adopt a detected UI project into the bounded UI contract, without guessing a proof.*

---

### [`scripts/proof_corpus.py`](scripts/proof_corpus.py)
> *Witness-keyed proof corpus with replay and pruning (IDEA-1156).*

**Size**: `342` lines (`15028` bytes)

**Functions:**
- `def canonical_bytes(payload)` - *One canonical byte form for any JSON payload (matches the envelope).*
- `def witness_key(receipt)` - *Content hash binding a receipt to its evidence (IDEA-1156 witness).*
- `def entry_path(corpus, key)` - *Filesystem path of one corpus entry (hex key, no traversal).*
- `def _atomic_write_json(path, value)` - *Write one corpus entry with the shared PRINCIPLE-013 durability contract.*
- `def store(receipt, corpus, *, envelope, now)` - *File a receipt under its witness key (IDEA-1156); returns key, path.*
- `def load(corpus, key)` - *Read one entry by witness key; None when absent or unreadable.*
- `def list_entries(corpus)` - *Every readable entry, oldest first (IDEA-1156 pruning order).*
- `def prune(corpus, keep)` - *Delete oldest entries past the cap (IDEA-1156); returns deleted keys.*
- `def _accepts_pass_to_pass(prove_fn)` - *Whether the prover accepts a `pass_to_pass` keyword (S-F contract).*
- `def replay(entry, *, prove_fn, repo)` - *Re-prove a stored entry and compare verdicts (IDEA-1156); never raises.*
- `def build_parser()`
- `def _read_json(path)`
- `def main(argv)`

---

### [`scripts/proof_envelope.py`](scripts/proof_envelope.py)
> *Signed commit-proof envelope (IDEA-1168).*

**Size**: `232` lines (`9939` bytes)

**Classes:**
- `class EnvelopeError` - *The envelope could not be sealed or read.*

**Functions:**
- `def canonical_bytes(payload)` - *One canonical byte form for any JSON payload (IDEA-1168).*
- `def default_keys()` - *Key ring from the environment (IDEA-1168 custody: env only).*
- `def seal(payload, *, key, keyid, ttl_seconds, now)` - *Seal a receipt payload into a signed envelope (IDEA-1168).*
- `def verify(envelope, *, keys, now)` - *Verify a sealed envelope (IDEA-1168); fail-closed, never raises.*
- `def build_parser()`
- `def _read_json(path)`
- `def _write_json(path, value)`
- `def main(argv)`

---

### [`scripts/proof_gate.py`](scripts/proof_gate.py)
> *Prove that a declared test fails on the base tree and passes on the current tree.*

**Size**: `877` lines (`36743` bytes)

**Classes:**
- `class ProofError` - *The proof could not be set up; the exit code is 2.*

**Functions:**
- `def mock_only_test_methods(source_text, file_label)` - *Names of `test_*` methods whose assertions are all mock echoes.*
- `def run_command(argv, cwd, timeout)` - *A command's exit code and combined output; 124 on timeout, 127 when it cannot start.*
- `def module_name(test)` - *The dotted module name for a repository-relative test path.*
- `def test_argv(test)` - *The unittest command for one test module, run from the tree root.*
- `def classify_run(code, output)` - *Classify one test run as passed, assertion, error or timeout.*
- `def tail(output, lines)` - *The last ``lines`` non-empty output lines, bounded for a JSON record.*
- `def _operator_span(left, right, lines, token)` - *The (line, start, end) span of an operator between two same-line operands.*
- `def mutations_for_source(text, file_label, limit)` - *Deterministic, bounded mutants for single-line operators in one source file.*
- `def mutant_key(mutant)` - *The stable waiver key for one mutant.*
- `def apply_mutation(text, mutant)` - *Apply one mutant to its source text.*
- `def _copy_repo(repo, destination)` - *Copy the working tree without Git metadata, project checkouts, or generated bulk.*
- `def _run_declared_tests(tree, tests, timeout, runner)`
- `def mutation_suite(repo, tree, *, tests, sources, limit, min_killed, waive, timeout, runner)` - *Generate bounded mutants in a copy of the tree and score them with the declared tests.*
- `def _git(repo, *args, timeout)`
- `def _resolve_base(repo, base, timeout)`
- `def _copy_tests(repo, worktree, tests)` - *Copy each declared test into the base worktree and return its repo-relative path.*
- `def prove(repo, *, base, tests, pass_to_pass, sources, mutants, min_killed, require_mutation, waive, timeout, runner)` - *Run the declared tests on the base and current trees and return the proof record.*
- `def _sha256_file(path)` - *SHA-256 of one file, or empty when unreadable (IDEA-1202 manifest).*
- `def tree_manifest(repo, paths)` - *Content hashes of declared paths, repo-relative, sorted (IDEA-1202).*
- `def gate_digest()` - *Hashes of the gate's own logic files (IDEA-1202 gate digest).*
- `def dirty_paths(repo)` - *Porcelain dirty paths, or None when git cannot answer (IDEA-1202 policy).*
- `def write_receipt(result, dest)` - *Persist a reproducible proof receipt beside the in-memory result (IDEA-1202).*
- `def render_text(result)` - *A terse human report for the CLI.*
- `def build_parser()`
- `def main(argv)`

---

### [`scripts/subagent_delegate.py`](scripts/subagent_delegate.py)
> *Sub-agent delegation: run one OpenCode sub-agent on a bounded brief (ADR-126, ADR-128).*

**Size**: `282` lines (`14828` bytes)

**Functions:**
- `def delegate_kill_path(workspace)` - *Default kill-file location for `workspace` (S-D F2).*
- `def delegate_killed(workspace, target)` - *A present kill file in workspace or target memory, else None (S-D F2).*
- `def load_opencode_config(path)` - *The OpenCode configuration; its `providers` declare which Gemini models are free-tier.*
- `def is_free_model(model, config)` - *Whether `model` (`provider/name`) costs nothing to call: an OpenCode `-free` or OpenRouter*
- `def subagent_roles(agents_dir)` - *The roles OpenCode can run: one per profile in `.opencode/agents/` (the single source).*
- `def _triad(what, why, fix)`
- `def opencode_command(runner_bin, role, prompt, file, model)` - *The `opencode run` argv for one headless sub-agent call.*
- `def direct_executable(found)` - *The program to start for `found`: the executable an npm `.cmd` shim forwards to when it exists,*
- `def _run_supervised(cmd, cwd, timeout)`
- `def delegate_subagent(role, prompt, file, project_name, model, timeout, output_format, runner, workspace, transcript_path)` - *Run `role` on `prompt` in AIKit or in project `project_name`; returns (exit code, report).*
- `def answer_text(stdout)` - *The sub-agent's own words from OpenCode's `--format json` event stream: the `text` parts in*

---

### [`scripts/sync_licenses.py`](scripts/sync_licenses.py)
> *Synchronize AIKit's pinned license copies with the canonical aegean-licensing repository.*

**Size**: `211` lines (`8188` bytes)

**Functions:**
- `def _normalize(text)`
- `def _read_text(path)`
- `def _digest(path)`
- `def _write_text(path, text)` - *Atomic write with a same-directory temp file, fsync and replace (PRINCIPLE-013).*
- `def expected_pin(source)` - *The PIN.json content the source tree should produce.*
- `def check_licenses(source, target)` - *Return every drift or tamper finding; empty means the pinned copies are consistent. When*
- `def sync_licenses(source, target)` - *Copy every canonical text into the target and rewrite PIN.json.*
- `def build_parser()` - *The full parser; imported lazily so the top-level help stays under the startup budget.*
- `def main(argv)`

---

### [`scripts/sync_principles.py`](scripts/sync_principles.py)
> *Principles Auto-Sync Tool (PRINCIPLE-017)*

**Size**: `893` lines (`44456` bytes)

**Functions:**
- `def is_generated_target(text)` - *True when `text` carries this tool's generated-file header (current or legacy).*
- `def estimate_tokens(text)` - *Estimate tokens as chars // 4.*
- `def fsync_dir(dir_path)` - *Flush the directory entry so a completed os.replace survives power loss (PRINCIPLE-013 R1).*
- `def load_tier_1b_domain_rules(domain_path)` - *Load project-specific domain rules from .agents/rules/domain.md if present (PRINCIPLE-001, PRINCIPLE-017).*
- `def append_domain_rules(lines, domain_rules)` - *Helper to append Tier 1B domain rules to prompt targets.*
- `def parse_principles(agents_file, strict)` - *Parse the principle SSOT, enforce strict schema validation, reject duplicate IDs, and verify monotonic lifecycle progression.*
- `def _parse_principles_uncached(content, strict)` - *Parsing and validation proper; see parse_principles().*
- `def render_readme_table(principles)` - *One table per lifecycle phase: ID, title and capsule, exactly as `GUIDELINES.md` states them.*
- `def sync_readme_table(readme_text, principles)` - *`readme_text` with its generated table refreshed, or None when it has no markers.*
- `def validate_triad_consistency(principles, readme_file)` - *Verify the documentation triad's public leg: README.md lists every principle (PRINCIPLE-017).*
- `def render_claude_agent(role, profile)` - *The Claude Code profile for `role`: the role's own description and instructions, unchanged,*
- `def tier1_title(title)` - *Drop a trailing parenthetical subtitle in Tier 1; the full title stays in Tier 2.*
- `def render_tier1_target(heading, principles, domain_rules)` - *Render one always-injected Tier 1 target (PRINCIPLE-001 R1/R3, PRINCIPLE-017 R2).*
- `def audit_tier1_budget(principles, domain_rules)` - *Enforce the Tier 1 context budget on every target (PRINCIPLE-001 R4/R6/R9).*
- `def sync_all(check_only, exit_on_mismatch, domain_path, readme_file)` - *Generate every always-injected Tier 1 target from the principle SSOT.*
- `def involved_principles(principles, text)` - *Compute which principles a situation involves (PRINCIPLE-001 R3), identically for every agent.*
- `def principle_sections(ssot_text)` - *Each `### PRINCIPLE-NNN:` section's text, ending at the next heading of level 2 or 3.*
- `def citing_principles(ssot_text, pid)` - *The principles a change to `pid` must be checked against (PRINCIPLE-000 R3): those whose*
- `def _adr_blocks(decisions)` - *ADR ID -> its text, for every `### ADR-NNN:` heading.*
- `def checklist_sections(ssot_text)` - *Extract Pre-Flight and Post-Flight checklist text if present.*
- `def changed_principles(old_text, new_text)` - *Principles whose `### PRINCIPLE-NNN:` section or governed checklists differ (PRINCIPLE-000 R3).*
- `def _is_clause_boundary(combined, index)` - *Whether a labeled principle at ``index`` starts a new reasoned clause.*
- `def _clause_after(combined, pid, window)` - *One cited ID's clause, cut before the next labeled principle.*
- `def _needs_reasoning(clause)` - *Whether one cited-ID clause states a falsifiable reason, not just a name.*
- `def cross_check_errors(old_text, new_text, old_decisions, new_decisions)` - *PRINCIPLE-000 R3 made decidable: every principle whose section changed since the last commit*
- `def git_head_text(rel_path)` - *`rel_path` as committed at HEAD, or None when git, a commit or the file is missing.*
- `def print_help()` - *Print command line usage for sync_principles.py.*

---

### [`scripts/ui_contract.py`](scripts/ui_contract.py)
> *Bounded UI-surface edits against a committed `.aikit/ui.json` contract (opt-in).*

**Size**: `782` lines (`38517` bytes)

**Classes:**
- `class UiContract` - *One project's committed UI contract: surfaces, protected paths, commands and limits.*

**Functions:**
- `def finding_code(message)` - *The stable code for one verify/finish finding; unknown prose is `ui.other`.*
- `def findings_payload(findings)` - *JSON-safe findings with stable codes and the original human message.*
- `def _error(message, why, fix, exit_code)`
- `def _tail(output)`
- `def _valid_pattern(pattern)`
- `def _path_list(raw, field)`
- `def scaffold_contract(root, surface, fast, paths, snapshot)` - *Write a conservative contract for one surface (ADR-168, `aikit ui init`).*
- `def load_contract(root)` - *Load and validate the project's committed UI contract.*
- `def _is_bookkeeping(path)`
- `def parse_status(text)` - *(XY, path) pairs from `git status --porcelain=v1 -z`, renames expanded to both paths.*
- `def _git(root, args, git_io)`
- `def _git_ok(root, args, git_io)`
- `def _tracked(root, git_io)`
- `def _changes(root, git_io)`
- `def surface_digest(root, patterns, git_io)` - *A SHA-256 over every current file in a surface, path and content, for evidence binding.*
- `def _head(root, git_io)`
- `def _default_shell_runner()`
- `def _run_fast(contract, root, runner)`
- `def _run_snapshot(contract, root, runner)`
- `def _task_path(root)`
- `def read_task(root)` - *The open UI task record, refusing a missing or unreadable one.*
- `def _task_error(message, fix)`
- `def begin(root, surface, git_io, shell_runner)` - *Open a bounded task for one named surface, from a clean, green baseline.*
- `def _diff_lines(root, baseline, git_io)`
- `def _line_count(path)`
- `def _budget_findings(root, changes, contract, task, git_io)`
- `def _added_lines(root, changes, baseline, surface, git_io)` - *(path, line number, text) for every line added inside the task's surface.*
- `def verify(root, git_io, shell_runner)` - *Check the open task's scope, contract, baseline, budget and proof commands.*
- `def allowed_removal_entries(task)` - *One task's allowed removals as `{"pattern": ..., "reason": ...}` records.*
- `def allow(root, pattern, reason)` - *Record one intended inventory removal pattern and its reason on the open task.*
- `def _read_history(root)` - *Read the append-only UI history; a missing file is empty, a malformed one is an error.*
- `def surface_evidence_errors(root, git_io)` - *Surfaces whose current files do not match any finished task's recorded digest.*
- `def _append_history(root, task, reviewer, git_io)` - *Append the finished task's evidence to the project's UI history (ADR-161, ADR-169).*
- `def finish(root, git_io, shell_runner, reviewed, reviewer)` - *Close a task only after a successful verify, a recorded review and its evidence.*
- `def abort(root, git_io)` - *Restore only the surface to its baseline, preserving and reporting everything else.*
- `def status(root, git_io)` - *The open task, its baseline and the paths changed under it right now.*

---

### [`scripts/ui_proof.py`](scripts/ui_proof.py)
> *Mechanical UI proofs for the opt-in UI guard (ADR-160).*

**Size**: `97` lines (`3896` bytes)

**Functions:**
- `def matches_pattern(path, patterns)` - *One relative path against contract patterns; `dir/**` covers the tree.*
- `def snapshot_lines(output)` - *Sorted, deduplicated non-empty lines of a UI inventory dump.*
- `def inventory_findings(baseline, current, allowed)` - *Removed inventory entries are findings unless an allowed pattern matches.*
- `def style_findings(added, theme_paths)` - *Hardcoded color and font literals in added surface lines are findings.*

---

### [`scripts/update_knowledge_base.py`](scripts/update_knowledge_base.py)
> *Codebase Knowledge Base Auto-Updater & Validator (PRINCIPLE-016)*

**Size**: `1241` lines (`58669` bytes)

**Functions:**
- `def fsync_dir(dir_path)` - *Flush the directory entry so a completed os.replace survives power loss (PRINCIPLE-013 R1).*
- `def write_generated_file(file_path, content, newline)` - *Atomically persist generated text file (flush + fsync + os.replace + fsync_dir) (PRINCIPLE-013 R1).*
- `def render_signature(node, drop_self)` - *Render a complete call signature from an AST function node (PRINCIPLE-003, PRINCIPLE-016).*
- `def parse_source(content, filename)` - *`ast.parse` at the minimum supported grammar (PRINCIPLE-003 R7), cached by content.*
- `def extract_python_symbols(file_path, strict)` - *Parse a python file with AST and extract docstrings, classes, and functions (PRINCIPLE-003).*
- `def _extract_symbols_uncached(file_path, content, strict)` - *AST extraction proper; see extract_python_symbols().*
- `def gitignored_kept_python(root)` - *Python files explicitly re-included by a root `.gitignore` negation.*
- `def gitignored_top_dirs(root)` - *The top-level directories `root/.gitignore` excludes by name. Git never tracks them, so their*
- `def find_python_files(root)` - *Every Python file under `root`, skipping `IGNORE_DIRS`. Ignored directories are pruned while*
- `def build_digest(rows, max_lines, max_chars, map_name)` - *`path  <lines>L <classes>C <functions>F  purpose` per module, within both budgets, shared-code*
- `def digest_rows(root)` - *One digest row per Python module under `root`, from the AST extractor the map uses.*
- `def generate_codebase_map(root, strict)` - *Generate the markdown content for knowledge/codebase_map.md with AST validation (PRINCIPLE-003).*
- `def validate_knowledge_links(knowledge_dir)` - *Verify that all relative file links in knowledge/INDEX.md physically exist on disk (PRINCIPLE-016).*
- `def audit_adr_register(decisions)` - *ADR IDs must be unique and consecutive (PRINCIPLE-016 R3, PRINCIPLE-000 R3). Two sessions that*
- `def check_codebase_map_freshness(knowledge_dir, root, strict)` - *Check if codebase_map.md accurately reflects current codebase AST (PRINCIPLE-016).*
- `def update_and_validate(knowledge_dir, root, strict)`
- `def _names(nodes)` - *Bare names of decorators or base classes (`abc.abstractmethod` -> `abstractmethod`).*
- `def audit_lazy_code(source, rel)` - *PRINCIPLE-007 R3 as a gate: a `TODO`/`FIXME`/`XXX`/`HACK` comment marker, a `# type: ignore`*
- `def _is_stub(fn)` - *A body (after any docstring) that is only `pass`, `...` or `raise NotImplementedError`.*
- `def audit_architecture(modules)` - *The parts of PRINCIPLE-009 and PRINCIPLE-010 every module can be checked against: no*
- `def check_architecture(root)` - *`audit_architecture` over every Python file the codebase map covers.*
- `def report_architecture(errors)` - *Print architecture findings with the remediation triad (PRINCIPLE-011 R6); True when clean.*
- `def check_lazy_code(root)` - *`audit_lazy_code` over every Python file the codebase map covers.*
- `def report_lazy_code(errors)` - *Print lazy-code findings with the remediation triad (PRINCIPLE-011 R6); True when clean.*
- `def quick_reference_errors(readme)` - *The structure PRINCIPLE-005 R1 states, not just its words: a heading, then inside its section*
- `def parse_readme_tree(readme)` - *Paths in the first ```text block after "What's Inside" (PRINCIPLE-005 R5), relative to the*
- `def audit_readme(readme, tracked, exists, script_source)` - *Every PRINCIPLE-005 rule a program can decide, as one error per violation. Pure: the caller*
- `def script_reference_sources(tracked)` - *The tracked files whose `python <path>.py` references must resolve: code and instructions.*
- `def audit_script_references(sources, exists)` - *One error per `python <path>.py` naming a file that does not exist, as `file:line`. Pure. A*
- `def tracked_files(root)` - *`git ls-files` for `root` (bounded, PRINCIPLE-010 R3), or None when git is unavailable.*
- `def check_script_references(root)` - *Run `audit_script_references` over `root`'s tracked sources; None when git is unavailable.*
- `def report_script_references(errors)` - *Print dead `python <path>.py` references with Why/Fix (PRINCIPLE-011 R6); True when clean.*
- `def check_readme(root)` - *Run `audit_readme` on `root`, listing tracked files with git (bounded, PRINCIPLE-010 R3).*
- `def report_readme(errors)` - *Print README findings with the remediation triad (PRINCIPLE-011 R6); True when clean.*
- `def guideline_errors(text)` - *Problems in a project's `.aikit/guidelines.md`: over the size limit, a line under `## Rules`*
- `def memory_dir(root)` - *Where `root` keeps its map and decisions: a project's `.aikit/`, else `knowledge/`.*
- `def check_workspace(root)` - *Every read-only audit of `--check`, for AIKit or for a project it builds: the codebase map*
- `def _validate_argv(argv, known, help_text)` - *Short-circuit on --help and reject unknown flags with exit 2 (PRINCIPLE-011, PRINCIPLE-015).*

---

### [`scripts/verify_commit.py`](scripts/verify_commit.py)
> *Post-Commit Verification (PRINCIPLE-018 Rule 7)*

**Size**: `732` lines (`35256` bytes)

**Functions:**
- `def run_command(argv, cwd, timeout)` - *A command's exit code and combined output; -1 when it could not start or timed out.*
- `def gate_commands(secret_range)` - *The gates PRINCIPLE-018 R3 names, as they run inside the worktree, each with its own bound.*
- `def _string_list(value, field, *, required)` - *Validate one declaration list; return stripped strings.*
- `def _valid_scope_pattern(pattern)` - *A relative glob that cannot escape the repository (mirrors ui_contract).*
- `def _scope_list(value, field)` - *Validate one optional scope allowlist; absent means unenforced.*
- `def _scope_int(value, field)` - *Validate one optional scope budget; 0/absent means unenforced.*
- `def _scope_exempt(path)` - *Whether `path` (repo-relative, forward slashes) sits outside scope.*
- `def _glob_match(path, pattern)` - *Recursive glob: `**` spans zero or more segments, `*?[]` stay in-segment.*
- `def _scope_match(path, patterns)` - *Whether one repo-relative path matches any allowlist glob.*
- `def scope_errors(declaration, files, added_lines)` - *Scope failures for one declaration against changed files and diff size.*
- `def _numstat_total(output)` - *Added plus deleted lines across a `git diff --numstat` output.*
- `def commit_files_and_lines(ref, repo, run)` - *Changed files and changed lines for one commit.*
- `def proof_command_from_declaration(declaration, *, worktree, parent, script)` - *Build the proof-gate command from a parsed `.aikit/proof.json` object.*
- `def scope_step(worktree, ref, repo, run)` - *Scope verdict for a commit carrying `.aikit/proof.json`; None when absent.*
- `def proof_gate_command(worktree, ref, run)` - *The declared proof command for a commit, or None when no declaration exists.*
- `def scanned_range(repo, ref, run)` - *The commits this verification covers, as resolved SHAs: everything past the upstream when one*
- `def shrunk_files(sizes, ratio, min_bytes)` - *Each path, from (old, new) sizes, that fell below `ratio` of an old size of at least `min_bytes`.*
- `def tree_sizes(ref, repo, run)` - *Blob sizes in `ref`'s tree by path; empty when git cannot list it.*
- `def shrink_warnings(ref, repo, run)` - *`[WARN]` lines for files `ref` cut below half their parent size, with Why/Fix; none for a root*
- `def recovery_fix(ref, resolved, repo, run)` - *The Fix line for a commit that fails on its own, chosen by where that commit is.*
- `def stage_commit(repo, run)` - *A commit object for exactly what is staged, without touching any ref.*
- `def verify_staged(repo, runner, policy)` - *Verify the staged index on its own (IDEA-1116); returns (exit code, report).*
- `def verify_commit(ref, repo, runner, policy)` - *Run every gate against `ref` checked out on its own; returns (exit code, report lines).*

---

### [`tests/test_auto_register.py`](tests/test_auto_register.py)
> *Unit tests for automatic idea registration from commit messages.*

**Size**: `129` lines (`6015` bytes)

**Classes:**
- `class TestAutoRegister`
  - Method `.setUp()`
  - Method `.test_commit_reference_marks_the_matching_idea_integrated()`
  - Method `.test_running_twice_is_idempotent()`
  - Method `.test_a_different_target_is_untouched()`
  - Method `.test_body_references_are_read_and_dry_run_does_not_write()`
  - Method `.test_idea_ids_are_deduplicated()`
  - Method `.test_git_log_records_are_parsed_without_spawning()`
  - Method `.test_a_git_timeout_is_a_reported_value_error()`
  - Method `.test_a_dry_run_does_not_write_the_matrix()`
  - Method `.test_a_corrupt_register_is_reported_instead_of_ignored()`
- `class TestIdeaIdWidth` - *The register must keep accepting ids after the three-digit range is exhausted.*
  - Method `.test_four_digit_commit_references_are_parsed()`
  - Method `.test_four_digit_dossier_heading_is_catalogued()`
  - Method `.test_four_digit_matrix_row_is_recognized()`
  - Method `.test_four_digit_idea_id_is_valid()`

**Functions:**
- `def make_register(root, status, target)`

---

### [`tests/test_integration.py`](tests/test_integration.py)
> *Integration & Operational Dogfooding Tier (PRINCIPLE-014, PRINCIPLE-015).*

**Size**: `2211` lines (`113888` bytes)

**Classes:**
- `class TestParallelAgentSafety` - *Multi-process reproduction of the lost-update race (PRINCIPLE-013 R3).*
  - Method `.setUp()`
  - Method `.test_parallel_checkpoints_do_not_lose_updates()`
  - Method `.test_no_lock_artifacts_survive_concurrent_writes()`
- `class TestGitStatusGrounding` - *Empirical grounding of the porcelain parser against real `git` output (PRINCIPLE-003 R1).*
  - Method `.test_parser_offsets_match_real_git_output()`
  - Method `.test_conflict_audit_reports_block_rather_than_clean()`
- `class TestCommitValidatorCli` - *Conventional Commit validator exercised as a real binary (PRINCIPLE-018 R1).*
  - Method `._run(message)`
  - Method `.test_valid_message_exits_zero()`
  - Method `.test_invalid_message_exits_one_with_reason()`
- `class TestOperationalDogfooding` - *Dual-Track CLI Dogfooding & Zero-Blast-Radius Chaos Test (PRINCIPLE-015).*
  - Method `._porcelain()` - *Return the working-tree state, or None when git is unavailable.*
  - Method `.setUpClass()`
  - Method `.test_ephemeral_sandbox_isolation()`
  - Method `.test_golden_path_help_contract()`
  - Method `.test_chaos_unknown_flag_rejected_with_remediation_triad()`
  - Method `.test_dogfood_matrix_leaves_zero_blast_radius()`
- `class TestWorkspaceIsolation` - *`disruption_recovery.py` anchors its ledger to the repository, not the working directory, so*
  - Method `.setUp()`
  - Method `._ledger_cli(*args)`
  - Method `.test_workspace_flag_redirects_the_ledger()`
  - Method `.test_workspace_without_value_is_refused()`
  - Method `.test_audit_and_resume_honour_the_workspace()`
  - Method `.test_resume_and_checkpoint_refuse_a_newer_ledger()`
- `class TestDogfoodRunner` - *The operational dogfood runner is itself a shipped surface (PRINCIPLE-015), so it carries*
  - Method `.setUpClass()`
  - Method `.test_dogfood_run_passes_every_track()`
  - Method `.test_dogfood_reports_tersely()`
  - Method `.test_dogfood_covers_golden_and_chaos_tracks()`
  - Method `.test_dogfood_emits_no_unhandled_traceback()`
  - Method `.test_dogfood_writes_its_declared_log()`
  - Method `.test_dogfood_leaves_tracked_content_untouched()`
  - Method `.test_dogfood_cli_contract()`
- `class TestInvolvedCli` - *`sync_principles.py --involved` is the authoritative answer to PRINCIPLE-001 R3.*
  - Method `._run(*args)`
  - Method `.test_lists_involved_principles_one_per_line()`
  - Method `.test_text_after_involved_is_never_parsed_as_options()`
  - Method `.test_missing_text_is_misuse()`
  - Method `.test_citing_lists_the_cross_principle_set_and_rejects_unknown_ids()`
- `class TestTrackCli` - *`disruption_recovery.py --track` reads real git state (PRINCIPLE-002 R3).*
  - Method `.test_track_follows_the_actual_diff()`
- `class TestCallSiteCommand` - *PRINCIPLE-003 R2's exact command must work for every name kind it covers, flags included.*
  - Method `.test_command_finds_a_flag()`
- `class TestAstGateCli` - *PRINCIPLE-003 R7: the gate halts with file and line, never a raw traceback.*
  - Method `.test_syntax_error_halts_cleanly()`
  - Method `.test_workspace_cli_check_detects_violations_and_passes_when_clean()`
- `class TestRepositoryCodebaseMap` - *PRINCIPLE-016 live invariant. Integration tier with the other whole-repository scans: mapping*
  - Method `.test_codebase_map_freshness_gate()`
- `class TestProofGate` - *IDEA-956: a declared test must fail on the base tree and pass on the current tree.*
  - Method `.setUp()`
  - Method `._git(*args)`
  - Method `._proof(base, tests)`
  - Method `.test_a_test_that_fails_on_base_and_passes_now_is_proof()`
  - Method `.test_a_mutation_killed_by_the_declared_test_counts()`
  - Method `.test_a_test_that_already_passed_on_base_is_not_proof()`
- `class TestSuiteHygiene` - *PRINCIPLE-014 R3 and R5 made mechanical (ADR-099). Integration tier: it parses the*
  - Method `.setUpClass()`
  - Method `.test_every_test_method_asserts()`
  - Method `.test_no_test_module_imports_a_network_library()`
  - Method `.test_no_test_is_a_mock_only_echo()`
- `class TestProjectCompatProof` - *Track 2 now: scaffolded projects drive and verify with zero project tooling.*
  - Method `.test_headless_scaffold_verifies_with_real_subprocesses()`
  - Method `.test_ui_scaffold_verifies_screenshots_and_hooks()`
  - Method `.test_seeded_scripted_failure_is_a_finding_then_clean_passes()`
- `class TestRepositoryReachability` - *PRINCIPLE-014 R7 live invariant over the whole repository. Integration tier with the other*
  - Method `.test_this_repository_passes_the_shield()`
  - Method `.test_allowlist_entries_still_exist()`
- `class TestRepositorySecretHygiene` - *PRINCIPLE-019 live invariant. Integration tier: the scan shells out to `git ls-files`.*
  - Method `.test_this_repository_is_clean()`
- `class TestReadmeDriftShield` - *PRINCIPLE-005 live invariant. Integration tier: completeness shells out to `git ls-files`.*
  - Method `.test_this_readme_matches_the_tracked_tree()`
- `class TestTierBudgetDiscipline` - *Structural enforcement of the two-tier test budget (PRINCIPLE-010 R6, PRINCIPLE-014 R3).*
  - Method `.test_unit_tier_spawns_no_processes_and_never_sleeps()`
  - Method `.test_unit_tier_guards_itself_against_spawns()`
  - Method `.test_integration_tier_bounds_every_spawn()`
- `class TestGateCommandLineBreaks` - *A trailing newline is not a second step, so it still runs (ADR-183).*
  - Method `.test_a_trailing_newline_still_runs_the_command()`
- `class TestReportedPathsAreRealPaths` - *Git quotes spaces and non-ASCII letters; what AIKit reports must name real files (ADR-189).*
  - Method `.test_the_audit_reports_paths_that_exist()`
  - Method `.test_the_audit_reads_nul_separated_status_and_a_real_rename()`
  - Method `.test_a_project_gate_prints_a_non_ascii_path_as_utf8()`
- `class TestSecretScanSeesNonAsciiPaths` - *git quotes a non-ASCII path ("\305\237ifre.txt") unless told otherwise, so `--all` read a*
  - Method `.make_repo()`
  - Method `.scan(repo, mode)`
  - Method `.test_all_scans_a_tracked_file_whose_name_is_not_ascii()`
  - Method `.test_staged_findings_name_a_non_ascii_file()`
- `class TestAikitHelpFastPath` - *`python aikit.py --help` must not load the command layer (PRINCIPLE-010 R5, ADR-180).*
  - Method `.test_help_uses_only_the_generated_help_module()`
  - Method `.test_a_real_command_still_loads_the_command_layer()`
- `class TestProjectCreation` - *`aikit new` makes a separate git repository with its memory (ADR-119).*
  - Method `.test_new_project_is_its_own_clean_repository_with_its_own_ledger()`
- `class TestProjectSelfCheck` - *`aikit fix` repairs what it can, `aikit check` applies AIKit's guidelines (ADR-124, ADR-128).*
  - Method `.test_fix_then_check_and_the_guidelines_gate_reads_the_readme()`
- `class TestProjectHygieneGate` - *The hygiene gate runs inside `aikit check` and fails the project on real findings (ADR-137).*
  - Method `.test_check_passes_clean_and_fails_on_a_third_party_asset()`
  - Method `.test_artifact_scan_reads_a_real_untracked_file_list()`
  - Method `.test_artifact_scan_is_scoped_to_a_subdirectory_workspace()`
- `class TestUiContractGate` - *The UI guard bounds real git changes and proves what it renders (ADR-158, ADR-160).*
  - Method `.setUpClass()`
  - Method `.tearDownClass()`
  - Method `.setUp()`
  - Method `._canned_runner(command, cwd, timeout)` - *ADR-154 pattern: exercise the contract in-process; one real spawn is covered elsewhere.*
  - Method `.test_bounds_edits_and_abort_restores_only_the_surface()`
  - Method `.test_snapshot_proof_and_style_lint_gate_a_real_edit()`
- `class TestProjectSecretScan` - *`check_secrets.py --workspace` scans a project's repository, not AIKit's (ADR-121).*
  - Method `.test_scan_reads_the_projects_staged_changes_and_ledger()`
- `class TestProjectGateShell` - *Gates run through the platform shell in the project folder (ADR-122).*
  - Method `.test_shell_keeps_quotes_and_reports_exit_codes()`
  - Method `.test_a_gate_that_rewrites_tracked_files_fails()`
- `class TestProjectPublishLifecycle` - *Publishing visibility and check --no-push with real processes and git checkouts (ADR-134, ADR-135).*
  - Method `.test_project_status_list_repo_and_check_no_push()`
- `class TestProjectPolicyCLI` - *PRINCIPLE-014: the UI, topic and media commands reach the registry and write real files.*
  - Method `.test_ui_topic_and_media_commands_round_trip()`
- `class TestReforgeHistory` - *PRINCIPLE-014: progressive history auditing and repair against real Git commits.*
  - Method `.git(root, *args)`
  - Method `.repository(defects)`
  - Method `.simple_repository(commits)` - *A small clean history for window/run tests that do not need repairs.*
  - Method `.one_commit_repository(source)` - *One commit with one Python file, for a repair test that needs no long history.*
  - Method `.test_stage_one_repairs_and_records_evidence()`
  - Method `.test_a_second_fix_offers_the_reviewed_patch_for_commit()`
  - Method `.test_an_audited_project_records_its_run_in_the_task_ledger()`
  - Method `.test_a_failing_test_rolls_the_repair_back()`
  - Method `.test_projects_run_concurrently_and_a_locked_project_refuses_again()`
  - Method `.test_a_commit_refuses_a_target_that_was_dirty_when_repaired()`
  - Method `.test_the_packet_shows_each_commit_hunk_in_order()`
  - Method `.test_a_findings_file_adds_and_applies_a_validated_fix()`
  - Method `.test_per_window_push_records_hash_and_resume_knows()`
  - Method `.test_network_failure_leaves_verified_but_unpushed_and_resume_pushes()`
  - Method `.test_empty_window_commits_nothing()`
  - Method `.test_aikit_reforge_status_reaches_the_registry_and_state()`
- `class TestIdeaCatcherCli` - *PRINCIPLE-011: `aikit.py idea-catcher` reaches the private register in one command.*
  - Method `.test_status_reads_the_register_named_by_the_root_override()`
- `class TestIdeaAutoRegistration` - *The CLI, the private register and the generated matrix move together.*
  - Method `.register()`
  - Method `.test_sync_cli_registers_and_refreshes_the_matrix()`
  - Method `.test_repo_scan_refreshes_the_matrix()`
  - Method `.test_delivered_registration_is_best_effort()`
  - Method `.test_check_push_reports_registered_ideas()`
  - Method `.test_publish_reports_registered_ideas_only_after_success()`
- `class TestTstringsNeedPython314` - *T-strings (PEP 750) tokenize only on 3.14+; on the 3.13 floor they are a*
  - Method `.uses_tstring(src)`
  - Method `.test_the_check_flags_tstrings_and_nothing_else()`
  - Method `.test_no_tstring_in_aikit_needs_python_314()`
- `class TestPublishGuardHook` - *The installed hook actually blocks a raw push and allows AIKit's push.*
  - Method `.test_hook_blocks_raw_push_and_allows_aikit_publish()`
- `class TestProjectTrackingBoundary` - *Projects are independent repositories; AIKit tracks none of their files.*
  - Method `.test_no_project_files_are_tracked()`

**Functions:**
- `def _sh_path()` - *The POSIX shell Git uses for hooks, including Git for Windows' bundled sh.*
- `def review_attestations(packet)` - *One valid quote and note per packet hunk, for tests that need a complete answer.*
- `def complete_readme(project_root)` - *Fill a seed README's `<FILL:` marker the way a project's first commit must (ADR-138).*
- `def remove_tree(path)` - *Remove a test tree even when copied `.git` objects kept their read-only bit (Windows).*
- `def setUpModule()` - *Create one committed project template; repo copies are cheaper than git init+commit.*
- `def tearDownModule()`
- `def copy_project(kit)` - *A fresh copy of the committed template at `<kit>/projects/app`.*

---

### [`tests/test_kit.py`](tests/test_kit.py)
> *Automated Test Suite for Portable Agent Kit (PRINCIPLE-011, PRINCIPLE-016)*

**Size**: `15080` lines (`821151` bytes)

**Classes:**
- `class TestPrincipleSync` - *Verifies that all 20 principles are maintained and synchronized (PRINCIPLE-001, PRINCIPLE-017).*
  - Method `.test_parse_all_principles()`
  - Method `.test_monotonic_lifecycle_phase_alignment()`
  - Method `.test_targets_in_sync_and_budgeted()`
  - Method `.test_agent_facing_role_texts_match_gate_limits()`
  - Method `.test_principle_003_anti_hallucination_capsule()`
  - Method `.test_principle_004_compaction_resilience_capsule()`
  - Method `.test_principle_005_cold_start_capsule()`
  - Method `.test_principle_006_disruption_capsule()`
  - Method `.test_principle_014_regression_shield_capsule()`
  - Method `.test_principle_015_operational_dogfooding_capsule()`
  - Method `.test_principle_016_knowledge_base_capsule()`
  - Method `.test_principle_017_auto_sync_capsule()`
  - Method `.test_principle_018_git_workflow_capsule()`
  - Method `.test_principle_000_meta_principle_capsule()`
  - Method `.test_guideline_targets_freshness_gate()`
  - Method `.test_triad_consistency_gate()`
  - Method `.test_checklists_cover_every_principle()`
  - Method `.test_no_stale_principle_counts_in_docs()`
  - Method `.test_principle_count_constants_agree()`
  - Method `.test_adopter_readme_without_principles_is_not_drift()`
  - Method `.test_aikit_readme_lists_every_principle_strictly()`
  - Method `.test_single_ssot_and_generated_agents_md()`
  - Method `.test_principle_schema_strictness()`
  - Method `.test_only_level_two_headings_set_the_phase()`
  - Method `.test_last_principle_block_stops_at_next_section()`
  - Method `.test_tier_1b_domain_rules_injection()`
  - Method `.test_domain_rules_template_validity()`
  - Method `.test_readme_cold_start_orientation_and_script_parity()`
- `class TestScriptReferenceGate` - *IDEA-406: every `python <path>.py` in AIKit's code and instructions names an existing file.*
  - Method `.audit(sources)`
  - Method `.test_a_reference_to_an_existing_script_passes()`
  - Method `.test_a_moved_entry_point_fails_with_its_file_and_line()`
  - Method `.test_an_allow_marker_on_the_line_or_the_line_above_exempts_it()`
  - Method `.test_history_tests_and_other_repositories_are_not_scanned()`
- `class TestCodebaseDigest` - *IDEA-005: one bounded read orients an agent; a cut is stated, never silent.*
  - Method `.test_every_module_is_listed_with_its_size_symbols_and_purpose()`
  - Method `.test_shared_code_comes_first_and_a_cut_is_stated()`
  - Method `.test_the_character_budget_holds_and_output_is_deterministic()`
- `class TestMarkedBlocks` - *IDEA-398: a generator rewrites only the text between its markers in a user-owned file.*
  - Method `.test_a_replacement_changes_nothing_outside_the_markers()`
  - Method `.test_a_missing_or_reversed_pair_is_not_a_block()`
  - Method `.test_fenced_output_round_trips()`
- `class TestPrinciple005ReadmeGate` - *PRINCIPLE-005: every README rule a program can decide is decided by `audit_readme`.*
  - Method `.audit(readme, tracked, exists)`
  - Method `.test_a_correct_readme_passes()`
  - Method `.test_aikit_commands_without_their_grammar_file_fail_loudly()`
  - Method `.test_a_project_without_aikit_py_still_skips_the_command_check()`
  - Method `.test_check_readme_uses_utf8_with_replace_on_git_listing()`
  - Method `.test_tree_paths_and_directories()`
  - Method `.test_a_dead_tree_path_fails()`
  - Method `.test_a_missing_top_level_entry_fails()`
  - Method `.test_a_tracked_file_deleted_in_the_working_copy_need_not_be_listed()`
  - Method `.test_an_expanded_directory_must_be_complete_and_a_collapsed_one_need_not()`
  - Method `.test_documented_commands_must_exist()`
  - Method `.test_size_labels_and_tree_are_required()`
  - Method `.test_a_prose_mention_is_not_the_tree_heading()`
  - Method `.test_quick_reference_is_checked_by_structure_not_words()`
  - Method `.test_the_adopter_template_fails_unfilled_and_passes_filled()`
- `class TestGeneratedReadmeTable` - *PRINCIPLE-005 R4 / PRINCIPLE-017 R4: README's principle table is generated (ADR-076).*
  - Method `.test_table_groups_by_phase_and_escapes_cells()`
  - Method `.test_only_the_block_between_markers_is_rewritten()`
  - Method `.test_this_readme_table_is_generated_and_fresh()`
- `class TestPrinciple007Tooling` - *PRINCIPLE-007 R3 and R6 as checks every model meets the same way (ADR-079).*
  - Method `.test_first_plan_needs_the_whole_assessment()`
  - Method `.test_reaching_phase_3_without_an_assessment_warns()`
  - Method `.test_only_the_first_plan_checkpoint_is_checked()`
  - Method `.test_lazy_code_markers_stubs_and_unnamed_suppressions_fail()`
  - Method `.test_protocols_abstract_methods_and_named_suppressions_pass()`
- `class TestArchitectureGate` - *PRINCIPLE-009's checkable parts (ADR-082).*
  - Method `.test_junk_drawers_fat_roles_and_cycles_fail()`
  - Method `.test_untimed_subprocess_and_unmanaged_open_fail()`
  - Method `.test_method_style_open_outside_with_fails_and_os_open_passes()`
  - Method `.test_raw_environ_reads_fail_and_writes_and_getenv_pass()`
  - Method `.test_focused_names_narrow_roles_and_one_way_imports_pass()`
- `class TestKnowledgeBaseWorkspaceAudits` - *PRINCIPLE-016 and PRINCIPLE-011 R8: update_knowledge_base audits external project workspaces.*
  - Method `.setUp()`
  - Method `.test_workspace_audits_lazy_code_architecture_and_adr_register()`
  - Method `.test_clean_workspace_passes_lazy_and_architecture()`
  - Method `.test_aikit_dir_is_ignored_by_python_file_discovery()`
  - Method `.test_write_generated_file_persists_atomically()`
  - Method `.test_workspace_codebase_map_freshness()`
- `class TestSecretBaselineAndRuleSchema` - *PRINCIPLE-019 R2 and PRINCIPLE-017 R1 (ADR-092).*
  - Method `.test_gitignore_holds_every_baseline_pattern_the_rule_lists()`
  - Method `.test_a_rule_without_audience_is_rejected()`
- `class TestRuleNumberParity` - *Every number a rule states equals the constant the code enforces (ADR-113). The budget moved*
  - Method `.test_rule_numbers_match_code_constants()`
- `class TestAgentOwnership` - *Every ledger write names its agent, and an agent cannot write another agent's task without an*
  - Method `.setUp()`
  - Method `.test_every_write_names_its_agent()`
  - Method `.test_another_agent_cannot_write_an_owned_task()`
  - Method `.test_a_take_over_records_who_continued()`
  - Method `.test_an_unidentified_owner_is_claimed_with_a_record()`
  - Method `.test_the_agent_is_named_explicitly_or_by_its_host()`
  - Method `.test_replacing_another_agents_task_records_whose_it_was()`
  - Method `.test_history_of_a_task_older_than_attribution()`
  - Method `.test_who_continued_survives_checkpoint_pruning()`
  - Method `.test_a_refused_write_prints_no_warning()`
  - Method `.test_only_a_bad_agent_name_is_reported_as_one()`
  - Method `.test_checkpoint_command_reports_the_owner_and_the_take_over()`
- `class TestRuntimeFloorConsistency` - *The declared runtime floor agrees across code, README, principles and CI (ADR-340).*
  - Method `.test_floor_is_three_thirteen_everywhere()`
- `class TestCiContractGuards` - *The CI misuse probe must run under `set -e` (ADR-347).*
  - Method `.test_cli_contract_probe_is_guarded()`
  - Method `.test_ci_supplies_the_identity_committing_tests_need()`
- `class TestPythonFileDiscovery` - *`find_python_files` prunes ignored directories relative to the root (ADR-115).*
  - Method `.test_a_repository_under_an_ignored_name_is_still_scanned()`
  - Method `.test_top_level_directories_the_root_gitignore_lists_are_skipped()`
  - Method `.test_top_level_wildcard_gitignore_prunes_the_directory()`
  - Method `.test_negated_python_file_under_ignored_dir_is_kept()`
  - Method `.test_this_repository_ignores_references()`
  - Method `.test_this_repository_ignores_article_drafts()`
  - Method `.test_this_repository_ignores_kilo_state()`
  - Method `.test_kilo_state_is_pruned_from_python_discovery()`
  - Method `.test_temporary_python_buffers_are_not_catalogued()`
- `class TestOpenCodePermissionBoundaries` - *PRINCIPLE-008 R6 / PRINCIPLE-009 R6 (ADR-116): replay OpenCode v2's documented evaluation*
  - Method `.decide(rules, action, resource)`
  - Method `.setUpClass()`
  - Method `.test_protected_files_and_destructive_commands_are_denied_to_every_subagent()`
  - Method `.test_ordinary_push_requires_confirmation_and_force_stays_denied()`
  - Method `.test_each_subagent_edits_only_its_own_area()`
  - Method `.test_read_only_subagents_cannot_write_through_the_shell()`
- `class TestKnowledgeCitations` - *PRINCIPLE-016 R2 drift made mechanical (ADR-101): citations in living documents resolve.*
  - Method `.test_every_rule_citation_names_an_existing_rule()`
  - Method `.test_required_documents_equal_the_ones_principle_016_names()`
  - Method `.test_audit_ledger_labels_predictions_as_predictions()`
  - Method `.test_every_benchmark_row_names_its_source_or_says_unverified()`
  - Method `.test_every_code_name_a_knowledge_document_cites_exists()`
- `class TestChaosCoverage` - *PRINCIPLE-013 R7 (ADR-086, ADR-148): each named fault has a test that drives it. The map holds*
  - Method `.test_every_named_fault_has_a_test()`
- `class TestDogfoodFingerprint` - *The blast-radius hash reads only paths git status names, but still sees dirty content.*
  - Method `.test_verbose_trace_reconfigures_legacy_console_encoding()`
  - Method `.test_dirty_content_changes_fingerprint_with_identical_status()`
  - Method `.test_rename_entry_hashes_the_new_path_and_consumes_the_old()`
  - Method `.test_fingerprint_reads_dirty_content_across_chunks()`
  - Method `.test_transient_fixtures_are_invisible_to_blast_radius()`
  - Method `.test_blast_diff_names_added_removed_and_modified_paths()`
  - Method `.test_blast_diff_reports_staged_state_change_without_content_change()`
  - Method `.test_blast_verdict_passes_clean_and_fails_loud_with_paths()`
  - Method `.test_repo_fingerprint_matches_snapshot_hash()`
  - Method `.test_readonly_gates_retry_a_timeout_once_then_pass()`
  - Method `.test_readonly_gates_still_fail_on_double_timeout()`
  - Method `.test_readonly_gates_never_retry_a_real_failure()`
- `class TestSandboxHardening` - *S-A F1/F2: supervised() must not leak code-injection env; run_cli() must not run inside the repo.*
  - Method `.test_sanitized_env_drops_injection_vars()`
  - Method `.test_supervised_scrubs_child_env()`
  - Method `.test_run_cli_refuses_repo_cwd()`
- `class TestAdrRegister` - *PRINCIPLE-016 R3 / PRINCIPLE-000 R3: ADR IDs are unique and consecutive (ADR-069).*
  - Method `.register(*numbers)`
  - Method `.test_consecutive_ids_pass()`
  - Method `.test_a_duplicate_fails()`
  - Method `.test_a_gap_fails()`
  - Method `.test_this_register_is_clean()`
  - Method `.test_commented_template_is_not_an_entry()`
- `class TestPrinciple005Unambiguity` - *PRINCIPLE-005 must say the same thing to every model: exact labels, triggers and homes.*
  - Method `.setUpClass()`
  - Method `.test_rules_contain_no_hedge_words()`
  - Method `.test_every_rule_names_its_audience()`
  - Method `.test_rule_labels_are_the_ones_the_gate_checks()`
  - Method `.test_every_trigger_and_home_is_defined()`
  - Method `.test_checklists_match_the_rules()`
- `class TestPrinciple000Unambiguity` - *PRINCIPLE-000 must pass its own R7: every meta-rule is decidable, none licenses skipping.*
  - Method `.setUpClass()`
  - Method `.test_r7_word_list_is_the_hedge_list()`
  - Method `.test_principle_000_obeys_its_own_r7()`
  - Method `.test_every_rule_names_its_audience()`
  - Method `.test_every_meta_rule_is_decidable()`
  - Method `.test_second_pass_definitions()`
  - Method `.test_citing_set_is_computed_from_sections_only()`
  - Method `.test_r3_completeness_is_decided_by_the_gate()`
  - Method `.test_cross_check_reason_is_per_id()`
  - Method `.test_cross_check_reason_cuts_every_labeled_clause()`
  - Method `.test_cross_check_group_verdict_covers_a_bare_id_list()`
  - Method `.test_capsule_does_not_license_skipping_procedure()`
  - Method `.test_rule_changes_carry_a_cross_principle_check()`
- `class TestPrinciple006Unambiguity` - *PRINCIPLE-006 must say the same thing to every model: when to commit, what to do with failing work.*
  - Method `.setUpClass()`
  - Method `.test_rules_contain_no_hedge_words()`
  - Method `.test_every_rule_names_its_audience()`
  - Method `.test_every_duty_is_defined()`
  - Method `.test_no_second_home_for_rules_owned_elsewhere()`
- `class TestPrinciple007Unambiguity` - *PRINCIPLE-007 must say the same thing to every model: fixed fields, fixed labels, a scope test.*
  - Method `.setUpClass()`
  - Method `.test_rules_contain_no_hedge_words()`
  - Method `.test_every_rule_names_its_audience()`
  - Method `.test_rules_match_the_checks()`
  - Method `.test_no_ban_contradicts_principle_000_r5()`
  - Method `.test_capsule_states_the_mechanisms()`
- `class TestRewrittenPrincipleWording` - *One data-driven check for every principle rewritten to a single reading (PRINCIPLE-000 R7):*
  - Method `.setUpClass()`
  - Method `.test_rewritten_principles_have_one_reading()`
- `class TestPrinciple001Unambiguity` - *PRINCIPLE-001 must say the same thing to every model. These tests make that mechanical:*
  - Method `.setUpClass()`
  - Method `.test_rules_contain_no_hedge_words()`
  - Method `.test_every_rule_names_its_audience()`
  - Method `.test_rules_use_normative_keywords()`
  - Method `.test_tier1_header_mirrors_r3_triggers_and_r1_precedence()`
  - Method `.test_every_agent_rule_reaches_tier1()`
  - Method `.test_every_tier1_target_names_the_operational_runbook()`
  - Method `.test_the_runbook_index_is_bounded_and_its_topic_files_are_mirrored()`
  - Method `.test_tier1_header_does_not_repeat_the_generator_name()`
  - Method `.test_precedence_never_contradicts_another_principle()`
  - Method `.test_open_terms_are_defined()`
  - Method `.test_involvement_is_deterministic()`
  - Method `.test_common_words_do_not_involve_principles()`
  - Method `.test_single_id_placeholder()`
  - Method `.test_tool_neutral_retrieval()`
- `class TestPrinciple002Unambiguity` - *PRINCIPLE-002 must give every model the same track, the same phase gates and the same*
  - Method `.setUpClass()`
  - Method `._rule(pid, number)`
  - Method `.test_rules_contain_no_hedge_words()`
  - Method `.test_every_rule_names_its_audience()`
  - Method `.test_open_decisions_are_defined()`
  - Method `.test_cross_references_resolve()`
  - Method `.test_p001_precedence_points_at_this_r5()`
  - Method `.test_checklists_are_in_principle_order()`
- `class TestPrinciple003Unambiguity` - *PRINCIPLE-003 must give every model the same grounding steps and the same answer to "is this*
  - Method `.setUpClass()`
  - Method `.test_rules_contain_no_hedge_words()`
  - Method `.test_every_rule_names_its_audience()`
  - Method `.test_ambiguity_split_is_decided_by_one_question()`
  - Method `.test_open_terms_are_defined()`
  - Method `.test_cross_references_resolve()`
  - Method `.test_every_external_program_the_scripts_run_is_declared()`
  - Method `.test_no_silent_broad_exception_handlers()`
  - Method `.test_user_facing_commands_use_python_not_py()`
  - Method `.test_unmeasurable_disk_space_is_announced()`
  - Method `.test_unreadable_backup_is_announced()`
  - Method `.test_failed_audit_scan_is_never_reported_clean()`
  - Method `.test_ast_gate_rejects_syntax_newer_than_the_minimum()`
  - Method `.test_no_standard_library_apis_newer_than_the_minimum()`
  - Method `.test_scripts_follow_platform_parity()`
- `class TestPrinciple004Unambiguity` - *PRINCIPLE-004 must name where each kind of state is written and how it is read back, so no*
  - Method `.setUpClass()`
  - Method `.test_rules_contain_no_hedge_words()`
  - Method `.test_every_rule_names_its_audience()`
  - Method `.test_every_kind_of_state_has_one_home()`
  - Method `.test_no_second_resumption_procedure()`
  - Method `.test_one_cold_start_command_everywhere()`
  - Method `.test_fifteen_line_limit_has_one_owner()`
  - Method `.test_no_unobservable_obligation()`
  - Method `.test_resume_never_says_ready_over_uncommitted_files()`
  - Method `.test_report_file_lists_are_bounded()`
  - Method `.test_schemas_are_not_sent_to_adrs()`
  - Method `.test_active_task_is_bounded_and_keeps_its_plan()`
  - Method `.test_parse_handoff_reads_the_declared_keys()`
  - Method `.test_parse_handoff_requires_next_and_refuses_an_unknown_key()`
  - Method `.test_parse_handoff_is_bounded_and_ignores_empty_segments()`
  - Method `.test_checkpoint_command_rejects_a_malformed_handoff_before_writing()`
  - Method `.test_checkpoint_command_scrubs_the_handoff_like_other_free_text()`
  - Method `.test_resume_prints_the_handoff_and_its_next_action()`
  - Method `.test_resume_keeps_the_generic_next_action_without_a_handoff()`
  - Method `.test_handoff_round_trips_through_a_version_1_ledger()`
  - Method `.test_plan_checkpoints_carry_a_versioned_text_digest()`
  - Method `.test_parse_handoff_keeps_colons_inside_a_value()`
  - Method `.test_checkpoint_refuses_a_credential_in_free_text_unless_redacting()`
  - Method `.test_checkpoint_scrubs_the_description_too()`
  - Method `.test_resume_prints_the_plan()`
  - Method `.test_revised_plan_replaces_the_old_one_and_answers_do_not()`
  - Method `.test_cli_never_replaces_a_missing_value_with_a_default()`
  - Method `.test_completing_a_task_that_is_not_active_changes_nothing()`
- `class TestLifecycleToolSemantics` - *PRINCIPLE-002 delegates decisions to commands; each command must mean what the rule says.*
  - Method `.test_bare_digit_phase_is_that_phase()`
  - Method `.test_resume_stays_in_the_recorded_phase_on_a_clean_tree()`
  - Method `.test_audit_ignores_the_ledger()`
  - Method `.test_p002_names_one_resume_line_and_defines_cold_start()`
  - Method `.test_caches_never_leak_or_go_stale()`
  - Method `.test_every_command_in_the_rules_exists()`
- `class TestTrackClassification` - *PRINCIPLE-002 R3: the track is computed, so every model assigns the same one.*
  - Method `.test_no_changes_is_track_a()`
  - Method `.test_documentation_is_track_b()`
  - Method `.test_comment_and_docstring_edits_are_track_b()`
  - Method `.test_logic_change_is_track_c()`
  - Method `.test_rule_text_and_generated_files_are_track_c()`
  - Method `.test_config_tests_and_new_python_are_track_c()`
  - Method `.test_unplanned_files_criterion_is_gone()`
  - Method `.test_highest_track_wins()`
  - Method `.test_rename_source_is_classified_with_the_new_path()`
- `class TestSyncWriteSafety` - *ADR-048. Sync now writes AGENTS.md, which older layouts used as the hand-authored rule source,*
  - Method `.setUp()`
  - Method `._sync(check_only)`
  - Method `._written_targets()`
  - Method `.test_oversized_domain_rules_report_the_triad()`
  - Method `.test_clean_sandbox_generates_every_target()`
  - Method `.test_hand_authored_file_is_never_overwritten()`
  - Method `.test_protection_is_all_or_nothing()`
  - Method `.test_legacy_generated_target_is_upgraded()`
  - Method `.test_unmigrated_layout_gets_migration_guidance_not_a_traceback()`
  - Method `.test_generated_marker_detection()`
- `class TestTier1ContextBudget` - *PRINCIPLE-001 R6/R9. Always-injected rules cost context on every turn in every IDE, so the*
  - Method `.test_every_target_is_within_the_token_target()`
  - Method `.test_token_overage_blocks_rather_than_warns()`
  - Method `.test_shipped_domain_template_syncs_within_budget()`
  - Method `.test_universal_rules_reserve_full_tier1b_headroom()`
  - Method `.test_headroom_breach_is_detected()`
  - Method `.test_advisory_warning_cannot_shadow_a_violation()`
  - Method `.test_token_estimate_is_conservative()`
  - Method `.test_grep_anchor_contract_survives_in_every_target()`
  - Method `.test_capsules_retain_their_mechanisms_after_condensation()`
- `class TestSecretHygieneScanner` - *PRINCIPLE-019. Secret leakage is the one defect class with no clean rollback, so the scanner*
  - Method `.test_findings_never_echo_the_secret()`
  - Method `.test_detects_the_widened_prefixed_credential_shapes()`
  - Method `.test_scrub_text_replaces_every_credential_and_names_the_detectors()`
  - Method `.test_subagent_answer_text_scrubs_credentials_from_the_stream()`
  - Method `.test_subagent_answer_text_leaves_clean_output_unchanged()`
  - Method `.test_scrub_text_leaves_clean_prose_byte_identical()`
  - Method `.test_prose_keeps_its_digests_and_identifiers()`
  - Method `.test_a_scan_that_skipped_a_surface_never_reports_clean()`
  - Method `.test_detects_known_credential_shapes()`
  - Method `.test_does_not_flag_indirection_or_placeholders()`
  - Method `.test_weak_allowlist_cannot_veto_a_pattern_match()`
  - Method `.test_weak_allowlist_still_suppresses_entropy_fallback()`
  - Method `.test_encoded_pass_detects_base64_and_hex_payloads_bounded()`
  - Method `.test_expiring_owner_bound_baseline_acknowledges_and_lapses()`
  - Method `.test_baseline_file_mode_suppresses_owned_findings()`
  - Method `.test_baseline_rejects_never_emitted_encoded_entropy()`
  - Method `.test_baseline_entropy_value_needs_a_variable_name()`
  - Method `.test_explicit_pragma_suppresses_everything()`
  - Method `.test_a_reasonless_pragma_excuses_nothing()`
  - Method `.test_a_scoped_pragma_suppresses_only_the_named_detector()`
  - Method `.test_scoped_pragma_covers_the_entropy_fallbacks_by_canonical_name()`
  - Method `.test_every_detector_has_a_vocabulary_entry()`
  - Method `.test_entropy_separates_random_from_prose()`
  - Method `.test_agent_memory_free_text_is_scanned()`
  - Method `.test_gitignore_carries_the_credential_baseline()`
  - Method `.test_rule_and_doc_files_are_scanned_except_the_scanner_itself()`
  - Method `.test_all_scan_includes_the_scanner_file()`
- `class TestInvariantReachabilityShield` - *PRINCIPLE-014 R7. A passing test proves a mechanism works, never that it is used. These*
  - Method `.setUp()`
  - Method `._write(name, source)`
  - Method `.test_detects_capability_with_zero_production_call_sites()`
  - Method `.test_detects_self_recursive_function_with_no_external_callers()`
  - Method `.test_detects_state_key_read_with_no_producer()`
  - Method `.test_key_with_a_producer_is_not_flagged()`
  - Method `.test_a_key_produced_only_by_setdefault_is_not_flagged()`
  - Method `.test_a_producer_hidden_in_a_comprehension_is_flagged()`
  - Method `.test_production_modules_skips_underscore_fixtures()`
- `class TestContinuousVerificationGate` - *The CI workflow must enforce the same gates the principles declare, using the same*
  - Method `.setUpClass()`
  - Method `.test_workflow_exists()`
  - Method `.test_workflow_runs_every_declared_gate()`
  - Method `.test_workflow_commands_match_documented_commands()`
  - Method `.test_workflow_covers_posix_and_windows()`
  - Method `.test_workflow_is_bounded_and_least_privileged()`
  - Method `.test_workflow_asserts_pristine_tree()`
  - Method `.test_workflow_yaml_has_no_unquoted_colon_scalars()`
  - Method `.test_workflow_uses_no_tabs()`
- `class TestDisruptionRecovery` - *Verifies atomic write, disruption ledger, and crash recovery (PRINCIPLE-006, PRINCIPLE-013).*
  - Method `.setUp()`
  - Method `.tearDown()`
  - Method `.test_atomic_write_and_load()`
  - Method `.test_bounded_rolling_ledger_pruning()`
  - Method `.test_self_healing_quarantine_corrupted_json()`
  - Method `.test_self_healing_recovery_from_shadow_backup()`
  - Method `.test_advisory_file_lock()`
  - Method `.test_disk_headroom_check()`
  - Method `.test_a_full_disk_refuses_the_write_and_keeps_the_old_state()`
  - Method `.test_schema_migration_backward_compatibility()`
  - Method `.test_zero_byte_power_loss_truncation_quarantine()`
  - Method `.test_newer_ledger_is_refused_without_mutation()`
  - Method `.test_newer_backup_is_not_used_when_primary_is_missing()`
  - Method `.test_legacy_ledger_is_migrated_in_memory_only()`
  - Method `.test_invalid_ledger_versions_are_refused()`
  - Method `.test_a_later_build_reads_and_upgrades_an_older_valid_ledger()`
  - Method `.test_a_later_build_writes_an_older_valid_ledger_as_current()`
  - Method `.test_a_later_build_still_refuses_invalid_and_newer_versions()`
  - Method `.test_refusal_names_the_versions_this_build_reads()`
  - Method `.test_an_invalid_version_is_not_blamed_on_a_different_aikit()`
  - Method `.test_resume_report_blocks_a_newer_ledger()`
  - Method `.test_save_refuses_a_newer_ledger_on_disk()`
  - Method `.test_save_refuses_a_newer_backup()`
  - Method `.test_save_refuses_an_unreadable_ledger_instead_of_overwriting_it()`
  - Method `.test_save_does_not_write_after_lock_timeout()`
  - Method `.test_noop_completion_does_not_rewrite_the_ledger()`
  - Method `.test_an_io_error_is_reported_not_quarantined()`
  - Method `.test_corruption_is_still_quarantined_and_recovered()`
  - Method `.test_replace_retries_lock_contention_but_not_a_full_disk()`
  - Method `.test_failed_replace_keeps_the_old_ledger_and_removes_temp()`
  - Method `.test_record_checkpoint_and_complete()`
  - Method `.test_dangling_temp_file_detection()`
  - Method `.test_format_resume_report()`
  - Method `.test_reset_active_task()`
  - Method `.test_clean_dangling_temp_files()`
  - Method `.test_non_git_workspace_detection()`
  - Method `.test_checkpoint_with_impact_assessment()`
  - Method `.test_audit_and_resume_reports_with_impact_assessment()`
  - Method `.test_hierarchical_milestone_indexing()`
  - Method `.test_dynamic_re_decomposition_on_discovery()`
  - Method `.test_conventional_commit_validation()`
  - Method `.test_milestone_tags_are_well_formed_and_bounded()`
  - Method `.test_unverified_override_names_gates_on_its_last_line()`
  - Method `.test_unwritable_ledger_reports_the_triad_not_a_traceback()`
  - Method `.test_ledger_stores_repository_relative_paths()`
  - Method `.test_lock_retries_through_windows_delete_pending_permission_error()`
  - Method `.test_switching_from_an_in_progress_task_records_it_as_superseded()`
  - Method `.test_suspend_and_resume_task_keeps_the_plan_and_phase()`
  - Method `.test_a_suspended_task_can_be_reset_without_resuming_it()`
  - Method `.test_a_superseded_task_is_offered_for_resumption()`
- `class TestKnowledgeBase` - *Verifies AST parsing and documentation completeness (PRINCIPLE-003, PRINCIPLE-016).*
  - Method `.test_core_docs_exist()`
  - Method `.test_update_and_validate_runs()`
  - Method `.test_codebase_map_freshness_stale_detection()`
  - Method `.test_ast_symbol_extraction()`
  - Method `.test_ast_distinguishes_properties_from_methods()`
  - Method `.test_ast_strict_mode_fails_on_syntax_error()`
  - Method `.test_link_integrity_shield()`
- `class TestConcurrencyAndResumptionCorrectness` - *Red-green defect pins for four invariants that reported green while broken in production*
  - Method `.setUp()`
  - Method `.test_locked_ledger_serializes_read_modify_write()`
  - Method `.test_locked_ledger_surfaces_contention_instead_of_writing_unprotected()`
  - Method `.test_resume_reports_the_phase_actually_recorded()`
  - Method `.test_resume_never_recommends_an_earlier_phase()`
  - Method `.test_resolve_active_phase_honours_legacy_and_label_fallbacks()`
  - Method `.test_fsync_dir_is_safe_and_platform_portable()`
  - Method `.test_ledger_paths_accept_strings_without_raw_tracebacks()`
- `class TestPorcelainClassification` - *Exhaustive table-driven coverage of `git status --porcelain` v1 classification*
  - Method `.test_every_porcelain_state_is_classified()`
  - Method `.test_no_real_state_is_silently_dropped()`
  - Method `.test_conflict_states_carry_their_code_for_diagnostics()`
  - Method `.test_ignored_and_blank_lines_are_skipped()`
  - Method `.test_empty_output_is_clean()`
  - Method `.test_nul_separated_status_parses_a_rename_whose_names_contain_an_arrow()`
  - Method `.test_paths_git_quotes_are_reported_as_the_real_names()`
  - Method `.test_paths_with_spaces_survive_classification()`
- `class TestAstSignatureFidelity` - *The symbol catalog is what agents consult before verifying call-sites (PRINCIPLE-004 R3), so*
  - Method `.setUp()`
  - Method `._probe(source)`
  - Method `.test_async_functions_and_methods_are_catalogued()`
  - Method `.test_full_signature_includes_varargs_kwonly_and_posonly()`
  - Method `.test_self_and_cls_are_dropped_from_method_signatures_only()`
  - Method `.test_generated_map_renders_async_keyword()`
- `class TestProjectRegistry` - *Projects live outside AIKit's state and carry their own `.aikit/` memory (ADR-119).*
  - Method `.setUp()`
  - Method `.make_folder(*files)`
  - Method `.test_detects_every_stack_and_its_test_command()`
  - Method `.test_npm_placeholder_is_not_a_test_command()`
  - Method `.test_detects_python_from_test_folder_and_top_level_script()`
  - Method `.test_detects_cpp_with_cmake_and_project_test_script()`
  - Method `.test_detects_cpp_with_native_test_script_preference()`
  - Method `.test_detects_cpp_with_ctest_preset_when_no_project_script()`
  - Method `.test_detects_node_from_lockfile_without_inventing_a_command()`
  - Method `.test_name_must_be_one_portable_segment()`
  - Method `.test_name_is_not_a_windows_device()`
  - Method `.test_attach_writes_memory_once_and_lists_the_project()`
  - Method `.test_override_beats_detection_and_missing_folder_is_reported()`
  - Method `.test_attach_refuses_folders_overlapping_the_kit()`
  - Method `.test_projects_folder_is_discovered_without_the_attached_file()`
  - Method `.test_corrupt_attached_file_is_an_error_not_an_empty_list()`
  - Method `.test_failed_git_init_leaves_no_half_made_project()`
  - Method `.test_new_project_starts_licensed_described_tagged_and_linked_to_aikit()`
  - Method `.test_attach_adds_the_integrated_badge_under_the_title()`
  - Method `.test_a_folder_is_attached_under_one_name_only()`
  - Method `.test_the_badge_is_added_once_and_only_to_a_readme()`
  - Method `.test_a_legacy_badge_link_is_rewritten_instead_of_duplicated()`
  - Method `.test_a_readme_holding_both_urls_loses_the_legacy_one()`
  - Method `.test_migrate_aikit_links_keeps_line_endings_and_is_idempotent()`
  - Method `.test_fix_migrates_a_pre_move_badge_link()`
  - Method `.test_fix_seeds_an_attached_projects_readme_with_the_integrated_badge()`
  - Method `.test_new_project_without_description_keeps_a_fill_marker()`
  - Method `.test_description_and_topics_are_checked_before_anything_is_created()`
  - Method `.test_titles_are_title_cased_and_descriptions_keep_their_case()`
  - Method `.test_repository_names_capitalise_each_word()`
  - Method `.test_game_and_science_projects_seed_their_own_license()`
  - Method `.test_license_suggestion_reads_markers_and_switches_the_pinned_text()`
  - Method `.test_reuse_metadata_reuses_an_existing_lowercase_licenses_directory()`
  - Method `.test_reuse_metadata_prefers_an_exact_uppercase_licenses_directory()`
  - Method `.test_license_switch_keeps_the_readme_tree_contiguous()`
  - Method `.test_license_switch_labels_a_bare_license_tree_line()`
  - Method `.test_license_switch_replaces_a_differently_titled_license_section()`
  - Method `.test_a_note_the_user_adds_to_the_license_section_survives_a_later_switch()`
  - Method `.test_a_license_1_0_project_is_still_recognized_and_offered_an_upgrade()`
  - Method `.test_archived_game_and_science_headers_still_map_to_their_kind()`
  - Method `.test_topics_command_records_what_the_ai_chooses()`
  - Method `.test_publish_license_auto_applies_and_stops_before_upload()`
  - Method `.test_first_commit_holds_commercial_md()`
  - Method `.test_pinned_license_texts_match_their_recorded_digests()`
  - Method `.test_every_personal_license_has_a_patent_grant_notice_and_catalog_entry()`
  - Method `.make_licensed_project(name)`
  - Method `.approve_media(folder, name)`
  - Method `.git_head(commit, returncode)`
  - Method `.test_restrict_swaps_the_license_records_the_cutoff_and_drops_commercial_terms()`
  - Method `.test_restrict_twice_keeps_the_first_cutoff()`
  - Method `.test_restrict_without_a_commit_changes_nothing()`
  - Method `.test_restrict_appends_a_license_section_to_a_readme_without_one()`
  - Method `.test_restrict_rewrites_a_license_entry_that_is_last_in_the_tree()`
  - Method `.test_cli_license_reports_then_restricts_with_a_checklist()`
  - Method `.test_published_topics_are_the_ai_choice_not_an_inference()`
  - Method `.test_ai_topic_choice_is_validated_and_never_auto_filled()`
  - Method `.test_license_suggest_on_a_restricted_project_is_read_only()`
  - Method `.test_switching_a_license_seeds_missing_commercial_terms()`
  - Method `.test_publish_refuses_the_template_description_placeholder()`
  - Method `.test_publish_seeds_missing_brand_candidates_before_refusing_review()`
  - Method `.test_publish_refuses_a_repository_without_recorded_topics()`
  - Method `.test_publish_refuses_case_variants_of_the_default_tag()`
  - Method `.test_publish_accepts_recorded_topics_and_applies_them()`
  - Method `.test_status_reports_the_license_tier()`
  - Method `.test_a_restricted_project_pushes_only_to_a_private_remote()`
  - Method `.test_check_push_refuses_a_restricted_project_with_a_public_origin()`
  - Method `.test_publish_public_refuses_a_restricted_project()`
  - Method `.test_cli_new_takes_a_description_and_topics()`
  - Method `.test_new_project_ignores_bytecode_and_has_a_clean_adr_template()`
  - Method `.test_git_identity_failure_is_an_error_not_a_warning()`
  - Method `.test_cli_reports_triad_and_exit_codes()`
  - Method `.test_a_filesystem_error_is_reported_with_a_remedy()`
  - Method `.test_project_memory_holds_ledger_and_decisions()`
  - Method `.test_a_stray_dot_aikit_folder_does_not_reclassify_aikit()`
  - Method `.test_status_names_unknown_and_missing_projects()`
  - Method `.test_fix_cli_reports_triad_on_unknown_project()`
  - Method `.run_cli(*argv)` - *`aikit` in-process against this test's kit; returns (exit code, stdout, stderr).*
  - Method `.test_media_art_cli_forwards_the_force_flag()`
  - Method `.stale(path)`
  - Method `.test_fix_restores_memory_and_readme_and_removes_only_stale_buffers()`
  - Method `.test_fix_adopts_a_detected_ui_contract()`
  - Method `.test_fix_reconciles_omitted_tracked_files_in_readme_tree()`
  - Method `.test_fix_reconciles_a_name_that_is_a_substring_of_another_entry()`
  - Method `.test_fix_seeds_brand_media_candidates_and_warns_once_on_default_topics()`
  - Method `.test_fix_warns_when_brand_candidates_cannot_be_written()`
  - Method `.test_attach_warns_when_brand_candidates_cannot_be_written()`
  - Method `.test_fix_warns_when_the_media_manifest_cannot_be_read()`
  - Method `.test_fix_applies_approved_media_to_readme_when_missing()`
  - Method `.test_attach_seeds_local_brand_candidates_when_missing()`
  - Method `.test_check_warns_on_uninitialized_media_and_default_topics()`
  - Method `.test_check_warns_when_a_game_project_has_only_license_topics()`
  - Method `.test_project_ledger_commands_keep_the_impact_gate()`
  - Method `.test_workspace_is_explicit_never_the_working_directory()`
  - Method `.test_new_with_publish_flag_calls_publish_project()`
  - Method `.test_new_generates_review_pending_media_before_any_publish()`
  - Method `.test_status_displays_repo_url()`
  - Method `.test_status_exit_code_tracks_dirty_state_without_changing_plain_status()`
  - Method `.test_status_json_reports_the_same_readiness_as_the_exit_code()`
  - Method `.test_status_json_honors_exit_code_when_both_flags_are_given()`
  - Method `.test_status_treats_a_corrupt_ledger_as_unclean_on_both_surfaces()`
  - Method `.test_status_json_returns_the_error_envelope_for_an_unknown_project()`
  - Method `.test_resume_json_carries_the_audit_and_the_guidelines_count()`
  - Method `.test_new_public_without_publish_is_a_usage_error()`
  - Method `.test_aikit_ledger_commands_name_the_agent_and_guard_its_task()`
  - Method `.test_new_publish_without_description_is_a_usage_error()`
  - Method `.test_check_pushes_only_when_asked()`
  - Method `._gate_result()`
  - Method `.test_dirty_check_skips_auto_push_and_strict_fails()`
  - Method `.test_conflicted_check_skips_auto_push_and_strict_fails()`
  - Method `.test_open_ui_task_check_skips_auto_push_and_strict_fails()`
  - Method `.test_strict_requires_a_codebase_map()`
  - Method `.test_ui_adoption_writes_a_contract_and_requires_it()`
  - Method `.test_ui_adoption_does_not_invent_a_proof()`
  - Method `.test_a_mechanics_contract_is_validated_and_becomes_a_gate()`
  - Method `.test_ui_required_blocks_strict_and_publish_without_a_contract()`
  - Method `.test_publish_requires_a_usable_sentence_cased_readme_description()`
  - Method `.test_ui_verify_json_emits_stable_codes()`
  - Method `.test_ui_init_writes_the_react_vite_pilot_contract()`
  - Method `.test_ui_evidence_and_json_error_paths()`
  - Method `.test_ui_finish_blocked_only_by_review_says_so_and_offers_no_revert()`
  - Method `.test_ui_finish_with_a_contract_finding_keeps_the_contract_advice()`
  - Method `.test_ui_finish_prints_every_allowed_removal_and_its_reason()`
  - Method `.test_ui_init_generic_override_from_cli()`
  - Method `.test_rendered_readme_uses_a_project_test_command()`
  - Method `.test_run_git_uses_utf8_encoding_with_replacement()`
- `class TestProjectGates` - *A project's Phase 4 is the gates its own config declares, plus the secret scan (ADR-122).*
  - Method `.setUp()`
  - Method `.project(files, gates)`
  - Method `.names(project)`
  - Method `.test_gates_come_only_from_the_projects_own_config()`
  - Method `.test_built_in_scans_are_always_present_and_last()`
  - Method `.test_project_json_adds_replaces_and_disables_gates()`
  - Method `.test_invalid_gate_config_is_refused()`
  - Method `.test_compat_gate_appears_only_when_compat_record_exists()`
  - Method `.test_mechanics_bench_becomes_a_gate_only_when_declared()`
  - Method `.test_every_gate_runs_after_a_failure()`
  - Method `.test_a_gate_that_rewrites_tracked_files_fails()`
  - Method `.test_a_gate_that_changes_nothing_passes_as_before()`
  - Method `.test_without_a_snapshot_there_is_no_rewrite_verdict()`
  - Method `.test_a_failing_gate_keeps_its_code_and_gains_the_rewrite_note()`
  - Method `.test_rewritten_paths_compares_content_hashes()`
  - Method `.test_snapshot_consumes_rename_sources_and_hashes_targets()`
  - Method `.test_snapshot_consumes_copy_sources_and_hashes_targets()`
  - Method `.test_snapshot_marks_unreadable_files_without_failing()`
  - Method `.test_snapshot_returns_none_when_git_cannot_answer()`
- `class TestProjectHygieneScan` - *The hygiene scan decides from the AST and from lines what the project gates could not (ADR-137).*
  - Method `.rules(source)`
  - Method `.test_allow_marker_is_read_on_the_line_above_the_finding()`
  - Method `.test_subprocess_rules_are_decidable()`
  - Method `.test_only_imported_subprocess_names_count()`
  - Method `.test_startup_and_file_rules()`
  - Method `.test_any_handler_that_only_discards_is_flagged()`
  - Method `.test_absolute_paths_only_when_they_reach_file_access()`
  - Method `.test_inline_allow_marker_needs_a_reason()`
  - Method `.test_a_typed_allow_marker_scopes_suppression_to_its_rule()`
  - Method `.test_binary_path_open_is_not_flagged_for_encoding()`
  - Method `.test_environ_subscript_writes_are_not_reads()`
  - Method `.test_every_emitted_rule_code_is_registered()`
  - Method `.test_asset_urls_skip_loopback_namespaces_and_marked_lines()`
  - Method `.test_scan_tree_skips_vendored_dirs_and_reports_unreadable_files()`
  - Method `.test_scan_tree_prunes_root_gitignored_dirs()`
  - Method `.test_artifact_classifier_flags_root_tests_outputs_and_source()`
  - Method `.test_artifact_scan_reports_missing_git_without_a_traceback()`
  - Method `.test_artifact_classifier_flags_tracked_caches_and_temporary_state()`
  - Method `.test_artifact_classifier_flags_an_untracked_project_readme()`
  - Method `.test_artifact_classifier_keeps_bookkeeping_and_normal_source()`
- `class TestGateCommandsHaveOneLine` - *Windows `cmd /c` runs only the first line of a command, so `exit 0\nexit 7` reported success*
  - Method `.test_a_nul_inside_a_command_is_refused_instead_of_crashing()`
  - Method `.test_a_line_break_inside_a_command_is_refused_without_running_it()`
- `class TestAnnotationsResolveOnEverySupportedPython` - *Python 3.14 evaluates annotations only when they are read (PEP 649); Python 3.13,*
  - Method `.test_every_annotation_in_scripts_names_something_defined()`
- `class TestAikitHelpFastPath` - *`python aikit.py --help` parses with scripts/aikit_parser.py alone, so it must stay light*
  - Method `.test_parser_constants_match_the_modules_they_mirror()`
  - Method `.test_parser_module_imports_only_the_standard_library_at_top_level()`
  - Method `.test_generated_help_matches_the_grammar()`
  - Method `.test_sync_licenses_generated_help_matches_its_parser()`
  - Method `.test_disruption_help_matches_the_module()`
  - Method `.test_cli_reexports_the_parser_so_existing_callers_keep_working()`
- `class TestPushCommand` - *`aikit push` is a thin, discoverable alias for the gated `check --push`.*
  - Method `.test_push_parses_and_routes_to_gated_check()`
- `class FakeGit` - *A tiny git_io stand-in for the UI guard's unit tests; no subprocess is spawned.*
  - Method `.__init__(status, head, tracked, diff)`
  - Method `.__call__(root, args)`
- `class TestUiContract` - *The UI guard's decidable parts: patterns, porcelain, contract loading and task records.*
  - Method `.setUp()`
  - Method `.write_contract(**overrides)`
  - Method `.test_patterns_scope_surfaces_and_protected_paths()`
  - Method `.test_finding_codes_are_stable()`
  - Method `.test_scaffold_generic_override_skips_stack_detection()`
  - Method `.test_scaffold_writes_a_valid_react_vite_contract()`
  - Method `.test_empty_surface_still_requires_evidence()`
  - Method `.test_surface_evidence_requires_a_matching_finished_task()`
  - Method `.test_scaffold_refuses_a_non_react_stack()`
  - Method `.test_porcelain_renames_expand_and_bookkeeping_is_ignored()`
  - Method `.test_contract_accepts_a_utf8_bom_from_windows_editors()`
  - Method `.test_contract_rejects_escaping_paths_and_bad_schema()`
  - Method `.test_contract_parses_snapshot_and_style_fields()`
  - Method `.test_contract_rejects_bad_snapshot_and_style_fields()`
  - Method `.test_begin_records_the_baseline_snapshot()`
  - Method `.test_begin_refuses_a_failing_or_empty_snapshot()`
  - Method `.test_begin_refuses_an_unknown_surface_before_touching_git()`
  - Method `.test_corrupt_task_record_names_the_abort_remedy()`
  - Method `.test_cli_parses_every_ui_action()`
  - Method `.test_verify_flags_protected_paths_and_a_moved_baseline()`
  - Method `.test_finish_closes_only_a_green_task()`
  - Method `.test_a_red_fast_command_increments_strikes_and_blocks_finish()`
  - Method `.write_snapshot_contract()`
  - Method `.test_verify_flags_a_lost_control_in_the_snapshot_proof()`
  - Method `.test_allow_records_intended_removals_and_verify_passes()`
  - Method `.test_verify_flags_style_literals_outside_the_theme()`
  - Method `.test_finish_requires_a_recorded_human_review()`
  - Method `.test_finish_appends_each_completed_task_to_history()`
  - Method `.test_finish_refuses_to_destroy_an_unreadable_history_file()`
- `class TestUiProof` - *The UI guard's mechanical proofs: inventory diffs and style drift (ADR-160).*
  - Method `.test_snapshot_lines_sort_strip_and_deduplicate()`
  - Method `.test_inventory_findings_flag_removed_entries_only()`
  - Method `.test_inventory_findings_honor_allowed_removal_patterns()`
  - Method `.test_style_findings_flag_hardcoded_literals_outside_theme_paths()`
  - Method `.test_style_findings_skip_font_properties_whose_value_is_a_token()`
  - Method `.test_style_findings_are_off_without_declared_theme_paths()`
- `class TestProjectsStayOutOfKitState` - *AIKit's map, gates and sweeps never read a project's files (ADR-119).*
  - Method `.test_codebase_scan_and_sweeps_prune_projects_and_bulk_trees()`
  - Method `.test_generated_bulk_directories_agree_across_walkers()`
  - Method `.test_git_ignores_projects()`
- `class TestSubagentDelegation` - *`aikit delegate`: bounded OpenCode sub-agent runs (ADR-126, ADR-128).*
  - Method `.setUp()`
  - Method `.runner(returncode, stdout, stderr, effect)`
  - Method `.delegate(role, prompt, **kwargs)`
  - Method `.test_the_brief_is_always_the_message()`
  - Method `.shim(with_exe)` - *An npm-style `opencode.cmd` that forwards to a real executable, as npm installs it.*
  - Method `.test_a_cmd_shim_runs_its_executable_never_cmd_exe()`
  - Method `.test_a_cmd_shim_without_its_executable_refuses_shell_characters()`
  - Method `.test_roles_are_the_opencode_profiles()`
  - Method `.test_refuses_empty_brief_unknown_project_and_missing_file()`
  - Method `.test_runs_opencode_headless_with_the_brief()`
  - Method `.test_json_report()`
  - Method `.test_json_and_failure_reports_scrub_credentials()`
  - Method `.test_a_changed_ledger_is_reported_and_never_overwritten()`
  - Method `.test_timeout_is_reported()`
- `class TestDelegateTranscript` - *S-E: every delegate run writes an append-only JSONL transcript; replay returns the identical verdict.*
  - Method `.setUp()`
  - Method `.runner(returncode, stdout, stderr)`
  - Method `.test_transcript_round_trip_returns_the_identical_verdict()`
  - Method `.test_transcript_scrubs_secrets_before_writing()`
  - Method `.test_transcript_append_refuses_when_the_lock_times_out()`
  - Method `.test_replay_refuses_a_corrupt_transcript()`
- `class TestDelegateBudgets` - *S-D/S-B: bounded invocation — 16k prompt cap and a global kill file (ExternalTermination pattern).*
  - Method `.setUp()`
  - Method `.runner()`
  - Method `.test_overlong_prompt_is_refused_before_running()`
  - Method `.test_kill_file_refuses_before_running()`
  - Method `.test_short_prompt_without_kill_file_still_runs()`
- `class TestEvidencePolicy` - *IDEA-1169: a named policy decides step attestations; fail always wins.*
  - Method `.test_closed_vocabulary_rejects_unknown_policy()`
  - Method `.test_hardening_never_raises_on_malformed_inputs()`
  - Method `.test_require_all_needs_every_pass_and_refuses_empty()`
  - Method `.test_quorum_counts_passes_but_never_outvotes_a_fail()`
  - Method `.test_sealed_attestation_is_decided_by_envelope_verification()`
  - Method `.test_verify_commit_accepts_a_policy_and_keeps_default_verdicts()`
- `class TestProofCorpus` - *IDEA-1156: receipts file under content witness keys; replay compares verdicts.*
  - Method `._receipt(**overrides)`
  - Method `.test_witness_key_is_stable_and_content_bound()`
  - Method `.test_witness_key_omits_empty_pass_to_pass_for_compat()`
  - Method `.test_store_lists_and_prunes_oldest_first()`
  - Method `.test_replay_matches_verdicts_and_refuses_without_evidence()`
  - Method `.test_replay_does_not_mask_unrelated_type_errors()`
- `class TestStagedTree` - *IDEA-1116: --staged proves the index via write-tree/commit-tree, never the tree.*
  - Method `._runner(staged, commit_tree_ok)`
  - Method `.test_staged_index_verifies_as_its_own_detached_commit()`
  - Method `.test_empty_index_refuses_inconclusive()`
  - Method `.test_unreadable_index_reports_instead_of_passing()`
  - Method `.test_failing_gate_names_the_staged_context()`
- `class TestPassToPass` - *S-F: optional pass-to-pass frame — neighbors must hold on base and current.*
  - Method `._repo()`
  - Method `._runner(repo, keep_current)`
  - Method `._prove(keep_current, with_p2p)`
  - Method `.test_p2p_holds_alongside_fail_to_pass()`
  - Method `.test_broken_p2p_fails_the_proof()`
  - Method `.test_absent_p2p_keeps_the_old_contract()`
- `class TestDelegateSchema` - *S-B: pre-execution schema validation — unknown enums never spawn (ValidationNode pattern).*
  - Method `.test_unknown_output_format_is_refused_before_running()`
- `class TestProjectGuidelines` - *A project's own rules, below AIKit's principles (PRINCIPLE-001 R4, PRINCIPLE-000 R6, ADR-129).*
  - Method `.setUp()`
  - Method `.rules(*lines)`
  - Method `.test_memory_starts_with_the_template_which_passes_the_audit()`
  - Method `.test_audit_names_each_broken_rule()`
  - Method `.test_add_numbers_rules_and_refuses_an_override()`
  - Method `.test_cold_start_commands_print_the_rules_and_their_rank()`
- `class TestClaudeSubagents` - *Claude Code sub-agents generated from AIKit's role profiles (PRINCIPLE-012 R8, ADR-131).*
  - Method `.tools(role)`
  - Method `.test_every_role_exists_for_both_hosts()`
  - Method `.test_profile_is_generated_from_the_one_role_text()`
  - Method `.test_read_only_roles_cannot_write()`
  - Method `.test_role_text_is_host_neutral_and_names_both_ledgers()`
  - Method `.test_no_agent_may_edit_a_task_ledger()`
- `class TestFreeModelPolicy` - *Sub-agents run only on free models (PRINCIPLE-012 R8, ADR-132).*
  - Method `.test_policy_names_free_and_paid_models()`
  - Method `.test_benchmark_doc_names_each_roles_configured_model()`
  - Method `.test_every_role_and_the_default_run_on_a_free_model()`
  - Method `.test_delegate_refuses_a_paid_model_before_running_anything()`
  - Method `.test_gemini_key_comes_only_from_the_environment()`
  - Method `.test_text_report_keeps_only_the_answer()`
  - Method `.test_a_key_split_across_a_concatenation_is_still_caught()`
  - Method `.test_commit_diffs_are_scanned_line_by_line_with_their_file()`
  - Method `.test_commit_scan_asks_for_merge_diffs()`
  - Method `.test_scan_commits_reads_a_merge_resolution_line()`
  - Method `.test_merge_scan_deduplicates_the_same_hunk()`
  - Method `.test_scanner_catches_a_bare_gemini_key()`
- `class TestPublishGuard` - *Direct `git push` is blocked unless the process is `aikit publish` (ADR-341).*
  - Method `.test_install_writes_guard_and_preserves_an_existing_hook()`
  - Method `.test_a_failed_guard_write_keeps_the_existing_hook()`
  - Method `.test_a_failed_guard_replace_restores_the_existing_hook()`
  - Method `.test_no_git_repository_is_a_no_op()`
  - Method `.test_core_hooks_path_is_respected()`
  - Method `.test_global_core_hooks_path_is_respected()`
  - Method `.test_windows_system_hooks_path_is_respected()`
  - Method `.test_programdata_system_hooks_path_is_a_fallback()`
  - Method `.test_install_system_config_wins_over_programdata()`
  - Method `.test_programdata_fills_a_missing_install_config_key()`
  - Method `.test_system_config_env_override_is_respected()`
  - Method `.test_included_config_hooks_path_is_respected()`
  - Method `.test_create_project_installs_the_guard()`
  - Method `.test_publish_environment_sets_and_restores()`
  - Method `.test_publish_project_installs_the_guard_before_pushing()`
- `class TestProjectPublish` - *`aikit publish`: a project in its own GitHub repository, private unless asked (ADR-134).*
  - Method `.runner(**replies)` - *A scripted stand-in for git, gh and the secret scan; records every call.*
  - Method `.made(word)`
  - Method `.test_new_repository_is_private_scanned_first_and_pushed()`
  - Method `.test_public_only_when_asked()`
  - Method `.test_existing_remote_is_pushed_never_recreated_or_forced()`
  - Method `.test_an_existing_upstream_scans_only_the_commits_it_pushes()`
  - Method `.test_auto_push_installs_the_guard_before_uploading()`
  - Method `.test_auto_push_reports_a_guard_install_failure()`
  - Method `.test_auto_push_scans_the_commits_it_pushes_and_refuses_a_finding()`
  - Method `.test_refusals_upload_nothing()`
  - Method `.test_secret_refusal_is_not_masked_by_a_push_named_workspace()`
  - Method `.test_uncommitted_work_is_named_in_the_report()`
  - Method `.test_extract_readme_description_finds_first_paragraph_and_truncates()`
  - Method `.test_extract_readme_description_survives_a_byte_order_mark()`
  - Method `.test_extract_readme_description_skips_a_url_only_paragraph()`
  - Method `.test_extract_readme_description_skips_a_paragraph_of_links()`
  - Method `.test_a_short_first_sentence_does_not_shrink_a_long_description()`
  - Method `.test_extract_readme_description_cuts_at_a_sentence_or_word_boundary()`
  - Method `.test_get_project_repo_url()`
  - Method `.test_repo_url_reads_the_config_as_git_does()`
  - Method `.test_repo_url_never_shows_credentials()`
  - Method `.test_push_reports_never_show_credentials()`
  - Method `.test_publish_sets_the_readme_description_and_recorded_topics()`
  - Method `.test_publish_can_create_the_repository_inside_an_organization()`
  - Method `.test_new_repository_takes_the_catalog_title_case()`
  - Method `.test_a_topic_failure_after_upload_is_a_note()`
  - Method `.test_publish_passes_extracted_description()`
  - Method `.test_auto_push_project()`
  - Method `.test_auto_push_is_authorized_for_the_publish_guard()`
- `class TestProjectArchive` - *`aikit archive`: retire a project locally and on GitHub with an archived README.*
  - Method `.make_project(tmp, name, description)`
  - Method `.runner(**replies)`
  - Method `.test_banner_goes_after_description_and_is_idempotent()`
  - Method `.test_banner_ignores_casual_archived_mention()`
  - Method `.test_banner_goes_after_description_when_media_block_precedes_it()`
  - Method `.test_existing_archive_banner_is_not_the_description()`
  - Method `.test_github_description_prefixes_archived_once()`
  - Method `.test_destination_defaults_to_projects_archive()`
  - Method `.test_move_refuses_existing_destination()`
  - Method `.test_offline_archive_moves_and_records_config()`
  - Method `.test_dirty_tree_refused_without_allow()`
  - Method `.test_online_archive_pushes_banner_edits_description_and_archives()`
  - Method `.test_online_archive_refuses_when_banner_commit_fails()`
  - Method `.test_archive_needs_reason_and_description()`
  - Method `.test_registry_finds_projects_inside_archive()`
- `class TestLicenseSync` - *The pinned license copies must not drift from the canonical texts or the catalog.*
  - Method `._source(source)`
  - Method `.test_sync_records_text_and_catalog_digests_and_check_detects_drift()`
  - Method `.test_sync_preserves_crlf_line_endings()`
- `class TestTestTierBudgetGate` - *PRINCIPLE-010 R6: both tier budgets are measured by a gate instead of assumed.*
  - Method `.fake_runner(table)`
  - Method `.ok(tests, seconds)`
  - Method `.gate(table, retry_delay)`
  - Method `.test_parse_reads_the_count_and_duration_unittest_prints()`
  - Method `.test_a_tier_over_its_per_test_average_fails_and_names_the_tier()`
  - Method `.test_a_load_skewed_first_run_is_measured_once_more()`
  - Method `.test_a_real_regression_fails_both_runs_and_reports_both()`
  - Method `.test_parallel_and_sequential_modes_agree_and_keep_order()`
  - Method `.test_a_red_tier_is_not_retried()`
  - Method `.test_both_tiers_inside_budget_pass_and_report_the_average()`
  - Method `.test_a_failing_tier_fails_the_gate_whatever_its_speed()`
  - Method `.test_a_failing_tier_prints_the_failing_test_name()`
  - Method `.test_unparseable_tier_output_fails_instead_of_reporting_zero()`
  - Method `.test_every_test_module_in_the_repository_has_a_budget()`
  - Method `.test_budget_errors_is_silent_when_every_tier_fits()`
  - Method `.test_a_tier_that_overruns_its_bound_fails_cleanly_instead_of_raising()`
  - Method `.test_a_timed_out_tier_prints_the_test_that_stalled()`
  - Method `.test_the_real_runner_reports_a_timeout_as_output()`
  - Method `.test_timeout_runner_normalizes_mixed_partial_stream_types()`
- `class TestChecklistWording` - *PRINCIPLE-000 R7 bans hedge words in "every rule added or changed", but the slices the*
  - Method `.setUpClass()`
  - Method `.test_checklists_contain_no_hedge_words()`
  - Method `.test_every_checklist_item_cites_a_principle()`
- `class TestPostCommitVerification` - *PRINCIPLE-018 R7: the commit itself is verified, not the tree it was tested in (ADR-149).*
  - Method `.runner(failing, worktree_fails, pushed, remote_contains)` - *A scripted git/gate stand-in; records every call so order and cwd can be asserted.*
  - Method `.ran(fragment)`
  - Method `.test_a_file_cut_below_half_its_size_is_flagged_and_small_or_growing_ones_are_not()`
  - Method `.test_shrink_exempt_matches_basename_only()`
  - Method `.test_a_shrinking_commit_warns_without_failing_unless_the_message_says_shrink_ok()`
  - Method `.test_a_gate_that_times_out_is_reported_instead_of_raised()`
  - Method `.test_the_tiers_gate_gets_room_for_all_three_tiers()`
  - Method `.test_a_green_commit_passes_and_every_gate_runs_in_the_worktree()`
  - Method `.test_a_proof_declaration_builds_the_bounded_gate_command()`
  - Method `.test_proof_gate_command_reads_the_declaration_and_parent()`
  - Method `.test_a_proof_declaration_with_unknown_keys_is_refused()`
  - Method `.test_min_killed_flag_follows_the_schema_default()`
  - Method `.test_scope_keys_are_optional_but_validated()`
  - Method `.test_scope_errors_name_outside_files_and_broken_budgets()`
  - Method `.test_numstat_counts_binary_files_as_single_line_changes()`
  - Method `.test_a_proof_declaration_without_tests_or_required_sources_is_refused()`
  - Method `.test_verify_commit_runs_a_declared_proof_gate()`
  - Method `.test_verify_commit_fails_when_the_declared_proof_gate_fails()`
  - Method `.test_the_secret_scan_reads_the_unpushed_range_as_resolved_shas()`
  - Method `.test_the_scanned_range_is_what_this_verification_covers()`
  - Method `.test_a_failing_gate_is_named_with_the_undo_that_fits_an_unpushed_commit()`
  - Method `.test_a_pushed_commit_is_told_to_fix_forward_not_to_reset()`
  - Method `.test_a_commit_pushed_without_an_upstream_is_not_told_to_reset()`
  - Method `.test_a_commit_that_is_not_head_is_not_told_to_reset_head()`
  - Method `.test_the_worktree_is_removed_even_when_a_gate_fails()`
  - Method `.test_a_worktree_that_cannot_be_made_is_reported_not_passed()`
  - Method `.test_a_ref_that_is_no_commit_is_refused()`
- `class TestReforgeCore` - *PRINCIPLE-014: Aegean Reforge's detectors, repairs, state and sync stay fast and grounded.*
  - Method `.root()`
  - Method `.repair(source, add_tests)`
  - Method `.test_detectors_cover_the_supported_defect_classes()`
  - Method `.test_a_bare_except_is_repaired_and_rechecked()`
  - Method `.test_a_mutable_default_is_replaced_and_gets_a_regression_test()`
  - Method `.test_yaml_shell_and_verify_are_repaired_together()`
  - Method `.test_a_repaired_finding_is_not_reported_or_repaired_twice()`
  - Method `.test_an_uneditable_finding_is_not_also_marked_repaired()`
  - Method `.test_a_crlf_repair_keeps_every_line_ending()`
  - Method `.test_a_failed_repair_restores_the_exact_bytes()`
  - Method `.test_the_generated_mutable_default_test_covers_constructor_defaults()`
  - Method `.test_a_syntax_error_is_evidenced_and_marked_reproducible()`
  - Method `.test_stage_windows_follow_the_documented_progression()`
  - Method `.test_interaction_evidence_marks_a_prior_symbol_or_repair_as_a_regression()`
  - Method `.test_state_round_trips_and_refuses_a_newer_schema()`
  - Method `.test_a_structural_run_entry_is_refused_by_name()`
  - Method `.test_the_parser_declares_the_shared_reforge_commands()`
  - Method `.test_delivery_refuses_a_non_conventional_message()`
  - Method `.test_a_finding_serializes_every_evidence_field()`
  - Method `.test_no_test_command_is_invented_for_an_empty_repository()`
  - Method `.test_test_commands_run_under_the_process_tree_supervisor()`
  - Method `.test_a_timed_out_test_command_tears_down_the_process_tree()`
  - Method `.project(name, readme)`
  - Method `.test_ui_identity_detects_web_game_and_cli_projects()`
  - Method `.test_ui_size_guard_survives_vanishing_files()`
  - Method `.test_compat_ui_contract_upgrades_cli_service_to_web()`
  - Method `.test_ui_work_refreshes_the_identifier()`
  - Method `.test_refresh_keeps_the_checked_date_when_the_identifier_is_unchanged()`
  - Method `.test_ui_identity_can_be_set_manually_and_reported()`
  - Method `.test_the_ai_brief_supplies_evidence_but_chooses_nothing()`
  - Method `.test_ai_choice_is_added_on_top_and_never_auto_filled()`
  - Method `.test_every_catalog_project_has_a_unique_palette_and_artwork()`
  - Method `.test_ai_art_prompts_and_monograms_are_project_specific()`
  - Method `.test_model_brand_requires_an_environment_key()`
  - Method `.test_model_brand_reports_the_assets_it_wrote()`
  - Method `.test_model_brand_keeps_approved_assets_without_force()`
  - Method `.test_model_brand_regenerates_social_when_only_the_logo_is_approved()`
  - Method `.test_generate_brand_does_not_fetch_artwork_twice()`
  - Method `.test_compose_brand_rejects_off_spec_dimensions()`
  - Method `.test_reseeding_media_leaves_no_backup_files_in_the_project()`
  - Method `.test_applying_media_leaves_no_backup_files_in_the_project_or_dossier()`
  - Method `.test_the_asset_disclosure_is_specific_and_honest()`
  - Method `.test_html_capture_is_served_over_http()`
  - Method `.test_media_blockers_are_empty_without_a_manifest()`
  - Method `.test_display_name_uses_the_catalog_override()`
  - Method `.test_model_key_requires_an_environment_value()`
  - Method `.test_new_projects_get_license_topic_metadata()`
  - Method `.test_media_candidates_are_pending_until_reviewed_and_applied()`
  - Method `.test_audit_media_and_blockers_flag_generated_dossier_placeholder()`
  - Method `.test_aegeanworks_keeps_its_own_badge_set()`
  - Method `.test_apply_media_refuses_a_dossier_manifest_it_does_not_own()`
  - Method `.test_apply_media_supports_readme_only_flag()`
  - Method `.test_apply_media_readme_only_refuses_a_project_without_a_readme()`
  - Method `.test_a_repository_without_a_ledger_records_nothing_and_does_not_fail()`
  - Method `.test_aikit_ledger_is_found_even_though_reforge_created_dot_aikit()`
  - Method `.test_a_stage_checkpoint_is_appended_without_becoming_the_active_task()`
  - Method `.test_a_completed_stage_is_not_offered_as_resumable()`
  - Method `.test_a_documented_hygiene_allow_marker_suppresses_a_finding()`
  - Method `.test_a_marker_two_lines_away_does_not_suppress()`
  - Method `.test_ledger_artifacts_cover_the_backup_its_writer_leaves()`
  - Method `.test_audit_window_reviews_text_and_skips_only_binary()`
  - Method `.test_text_review_flags_a_committed_conflict_marker()`
  - Method `.test_text_review_validates_json_and_toml()`
  - Method `.test_text_review_flags_an_unclosed_markdown_fence()`
  - Method `.test_text_review_does_not_mix_fence_styles()`
  - Method `.test_a_project_without_a_shared_banner_is_not_asked_for_badges()`
  - Method `.test_media_review_refuses_an_unresolvable_screenshot_commit()`
  - Method `.test_window_settings_are_configurable_and_capped_by_stop()`
  - Method `.test_runs_stop_resume_and_create_independent_histories()`
  - Method `.test_raising_the_stop_reopens_a_completed_run()`
  - Method `.test_update_settings_reopens_a_completed_run_with_a_pending_review()`
  - Method `.test_update_settings_keeps_a_completed_unlimited_run_at_the_end_of_history()`
  - Method `.test_live_completion_total_wins_over_the_stored_count()`
  - Method `.test_a_later_fix_refreshes_the_history_entry_too()`
  - Method `.test_schema_one_migrates_to_an_independent_first_run()`
  - Method `.test_only_fixable_unrepaired_findings_block_the_next_stage()`
  - Method `.test_an_unreviewed_stage_blocks_progress_and_completion()`
  - Method `.test_finalize_review_reads_the_reloaded_history_entry()`
  - Method `.test_an_unlimited_run_completes_at_the_end_of_history()`
  - Method `.test_reviewing_an_unlimited_partial_window_does_not_complete_run()`
  - Method `.test_an_unlimited_run_completes_when_prior_windows_cover_history()`
  - Method `.test_a_historical_unreviewed_stage_blocks_a_completed_run()`
  - Method `.test_a_historical_review_completes_the_run_when_every_stage_is_covered()`
  - Method `.test_a_review_answer_must_name_every_packet_hunk()`
  - Method `.test_a_fix_persists_the_review_status_in_the_run_history()`
  - Method `.test_settings_validate_and_cannot_rewrite_a_used_start()`
  - Method `.test_an_active_review_is_refused_before_git_or_a_next_stage()`
  - Method `.test_the_parser_declares_run_management_commands()`
  - Method `.test_a_findings_file_that_is_not_json_is_refused()`
  - Method `.test_an_ignored_state_file_is_not_a_commit_failure()`
  - Method `.test_a_commit_refuses_a_dirty_finding_target()`
  - Method `.test_a_review_packet_is_never_committed_as_reviewed_work()`
  - Method `.test_the_parser_declares_the_findings_option()`
  - Method `.stage_plan()` - *A minimal stage plan for packet and findings tests.*
  - Method `.test_a_packet_skips_files_only_prior_commits_changed()`
  - Method `.test_the_packet_reviews_each_commit_hunk_in_order()`
  - Method `.test_the_packet_fences_repository_data_as_untrusted()`
  - Method `.test_each_packet_gets_a_fresh_data_fence()`
  - Method `.test_a_hostile_commit_subject_stays_inside_the_data_fence()`
  - Method `.test_a_guessed_fence_tag_cannot_close_the_random_fence()`
  - Method `.test_the_packet_redacts_a_credential_before_an_agent_reads_it()`
  - Method `.test_a_review_answer_is_validated_against_the_stage()`
  - Method `.test_a_finding_can_name_the_commit_and_hunk_it_reviewed()`
  - Method `.test_review_coverage_requires_a_quote_and_a_distinct_note()`
  - Method `.test_a_deletion_only_hunk_is_attested_by_a_removed_line()`
  - Method `.test_a_blank_deletion_hunk_accepts_blank_line_marker()`
  - Method `.test_a_blank_addition_hunk_accepts_blank_line_marker()`
  - Method `.test_an_oversized_findings_answer_is_refused()`
  - Method `.test_a_pure_deletion_hunk_has_no_new_lines()`
  - Method `.test_independent_runs_write_different_packet_paths()`
  - Method `.test_a_review_improvement_is_its_own_category()`
  - Method `.test_a_review_patch_must_overlap_a_line_the_stage_added()`
  - Method `.test_an_empty_review_answer_is_valid()`
  - Method `.test_a_review_patch_applies_only_when_it_is_unambiguous()`
- `class TestIdeaCatcherShip` - *PRINCIPLE-014: Idea Catcher ships complete and keeps its register private.*
  - Method `.test_the_root_override_selects_a_register()`
  - Method `.test_the_parser_declares_the_status_command_without_a_repo_group()`
  - Method `.test_the_standalone_sync_layer_is_gone()`
  - Method `.test_the_stale_matrix_hint_names_a_command_that_exists()`
  - Method `.test_the_deep_checked_tag_is_part_of_the_vocabulary()`
- `class TestIdeaCatcherHiddenListing` - *PRINCIPLE-007: rejected and duplicate ideas leave the default target listing.*
  - Method `._idea(idea_id, status, tags)`
  - Method `._payload()`
  - Method `._register()`
  - Method `.test_list_ideas_hides_rejected_and_duplicate_by_default()`
  - Method `.test_list_ideas_can_include_each_hidden_kind()`
  - Method `.test_explicit_status_or_tag_still_lists_that_kind()`
  - Method `.test_a_rejected_duplicate_is_shown_by_either_include_flag()`
  - Method `.test_status_counts_the_full_register()`
  - Method `.test_cli_hides_both_and_reports_the_count()`
  - Method `.test_cli_can_include_each_hidden_kind()`
  - Method `.test_cli_json_hides_both_by_default()`
  - Method `.test_cli_json_can_show_the_full_audit_view()`
- `class TestIdeaCatcherBlockedPolicy` - *PRINCIPLE-007: a second deferral blocks an idea permanently.*
  - Method `._idea(idea_id, status, *, superseded_by)`
  - Method `._register()`
  - Method `.test_blocked_is_part_of_the_status_vocabulary()`
  - Method `.test_a_second_direct_deferral_blocks_and_keeps_the_audit_trail()`
  - Method `.test_a_legacy_deferred_idea_blocks_on_its_second_deferral()`
  - Method `.test_a_blocked_idea_refuses_review()`
  - Method `.test_a_blocked_idea_refuses_a_status_change()`
  - Method `.test_a_superseded_idea_refuses_review()`
  - Method `.test_a_superseded_idea_refuses_a_status_change()`
  - Method `.test_a_superseded_idea_accepts_repointing_to_another_canonical()`
  - Method `.test_auto_registration_does_not_reopen_a_superseded_idea()`
  - Method `.test_review_idea_defer_twice_blocks()`
  - Method `.test_review_idea_blocks_a_legacy_deferred_row()`
  - Method `.test_review_idea_confirmed_preserves_the_existing_decision()`
  - Method `.test_validation_rejects_blocked_without_two_deferrals()`
  - Method `.test_list_ideas_hides_blocked_by_default()`
  - Method `.test_cli_review_idea_reports_the_block()`
  - Method `.test_status_counts_blocked_rows_in_the_target_total()`
  - Method `.test_cli_ideas_can_include_blocked()`
  - Method `.test_auto_registration_does_not_reopen_a_blocked_idea()`
  - Method `.test_review_idea_requires_evidence()`
- `class TestProofGateHelpers` - *IDEA-956: the fail-to-pass classifier and path helpers are deterministic.*
  - Method `.test_classify_run_distinguishes_assertions_from_errors()`
  - Method `.test_test_argv_names_one_test_module()`
  - Method `.test_tail_bounds_a_long_run()`
  - Method `.test_mutations_for_source_finds_supported_operators()`
  - Method `.test_mutant_key_is_stable_for_a_waiver()`
  - Method `.test_proof_runs_pin_pythonhashseed()`
  - Method `.test_apply_mutation_uses_the_exact_operator_span()`
  - Method `.test_mutations_skip_multiline_and_chained_expressions()`
  - Method `.test_copy_tests_refuses_missing_and_outside_paths()`
  - Method `.test_only_assertion_failures_count_as_kills()`
  - Method `.test_a_mutant_that_breaks_syntax_is_an_error_not_a_kill()`
  - Method `.test_every_generated_mutant_reparses()`
  - Method `.test_a_waiver_must_bind_to_a_generated_mutant()`
  - Method `.test_mutation_sources_cannot_escape_the_repository()`
  - Method `.test_mutation_copy_prunes_dependency_and_generated_trees()`
  - Method `.test_mock_only_detector_flags_a_pure_mock_echo()`
  - Method `.test_mock_only_detector_passes_mixed_and_observable_tests()`
  - Method `.test_mock_only_detector_refuses_unparseable_source()`
- `class TestProjectCompatHelpers` - *Track 2 now: scaffold and proof helpers are pure, deterministic, stdlib-only.*
  - Method `.test_minimal_png_has_a_valid_signature()`
  - Method `.test_inventory_lines_sort_and_dedupe()`
  - Method `.test_scaffold_headless_writes_no_screenshots_but_hooks()`
  - Method `.test_verify_fails_on_missing_deltas_with_an_injected_runner()`
  - Method `.test_verify_passes_on_clean_with_an_injected_runner()`
  - Method `.test_verify_ui_requires_screenshots_but_headless_does_not()`
  - Method `.test_seeded_replay_fires_when_same_seed_diverges()`
  - Method `.test_seeded_replay_passes_on_identical_deltas()`
  - Method `.test_evidence_and_bench_files_are_structural_not_thresholds()`
  - Method `.test_emit_evidence_appends_a_cause_gate_artifact_link()`
  - Method `.test_ui_scaffold_writes_distinct_before_after_screenshots()`
  - Method `.test_ui_verify_fires_on_byte_identical_screenshots()`
  - Method `.test_ui_verify_fires_on_layout_controls_missing_from_inventory()`
- `class ReuseMetadataTest` - *A same-license refresh must not erase project-specific annotations.*
  - Method `.setUpClass()`
  - Method `.tearDownClass()`
  - Method `.setUp()`
  - Method `.test_the_same_identifier_preserves_project_annotations()`
  - Method `.test_a_new_identifier_replaces_the_metadata()`
  - Method `.test_an_asset_annotation_does_not_satisfy_the_blanket()`
  - Method `.test_a_missing_license_refuses_the_write()`
- `class TestReforgeAnalyzer` - *The external analyzer adapter: packet/answer paths, failures and CLI wiring.*
  - Method `.setUp()`
  - Method `.test_command_receives_packet_and_answer_paths()`
  - Method `.test_an_oversized_analyzer_answer_is_a_typed_error()`
  - Method `.test_a_timeout_is_a_typed_error()`
  - Method `.test_a_nonzero_exit_is_a_typed_error()`
  - Method `.test_invalid_json_is_a_typed_error()`
  - Method `.test_an_empty_command_is_refused()`
  - Method `.test_the_analyze_command_declares_its_analyzer()`
  - Method `.test_analyze_stage_reviews_the_latest_packet()`
- `class TestDossierCatalogueSync` - *The publish hook upserts every dossier artefact and stays idempotent (ADR-308).*
  - Method `.setUp()`
  - Method `._write(relative, text)`
  - Method `._write_fixture()`
  - Method `._entry(name, **changes)`
  - Method `._snapshot()`
  - Method `.test_sync_entry_writes_every_catalogue_artifact()`
  - Method `.test_sync_entry_is_idempotent_and_updates_metadata_in_place()`
  - Method `.test_repository_slug_parses_github_origin_forms()`
  - Method `.test_build_entry_refuses_a_repository_without_language()`
  - Method `.test_sync_published_skips_a_foreign_origin_and_an_absent_dossier()`
  - Method `.test_sync_published_keeps_a_private_repository_out_of_the_public_catalogue()`
  - Method `.test_sync_entry_refreshes_the_inline_script_hash_in_the_csp()`
  - Method `.test_sync_published_writes_the_catalogue_from_github_facts()`
- `class TestNoEvidenceRefusal` - *IDEA-1118: empty evidence is inconclusive, never a pass.*
  - Method `.test_shared_outcome_model_refuses_zero_observations()`
  - Method `.test_mutation_suite_with_no_mutants_is_inconclusive()`
  - Method `.test_hygiene_empty_tree_is_inconclusive_not_ok()`
  - Method `.test_claim_audit_zero_claims_is_inconclusive()`
  - Method `.test_upstream_diff_marks_skipped_inconclusive_and_fails_strict()`
- `class TestProofReceipt` - *IDEA-1202: persisted receipt binds verdict to tree manifest and gate digest.*
  - Method `.test_tree_manifest_hashes_declared_files_sorted()`
  - Method `.test_write_receipt_records_dirty_and_digests()`
  - Method `.test_receipt_cli_flag_writes_file()`
- `class TestProofEnvelope` - *IDEA-1168: canonical HMAC envelope seals a receipt; verify fails closed.*
  - Method `.test_seal_then_verify_passes()`
  - Method `.test_canonical_form_is_key_order_independent()`
  - Method `.test_tampered_payload_fails_not_inconclusive()`
  - Method `.test_expired_and_unknown_key_are_inconclusive()`
  - Method `.test_empty_key_refuses_to_seal()`
- `class TestVerifyPushV4SafeFixes` - *Regression pins for the verify-push-v4 window (last-3-push review).*
  - Method `.test_evidence_sealed_without_keys_is_inconclusive()`
  - Method `.test_evidence_verifier_crash_is_fail()`
  - Method `.test_evidence_parse_policy_rejects_non_string()`
  - Method `.test_proof_entry_path_lowercases()`
  - Method `.test_proof_prune_rejects_non_int()`
  - Method `.test_proof_witness_key_tolerates_non_list()`
  - Method `.test_ui_safe_rel_rejects_traversal()`
  - Method `.test_ui_is_small_boundary()`
  - Method `.test_verify_string_list_rejects_flags()`
  - Method `.test_secrets_baseline_detector_validation()`
  - Method `.test_archive_reason_validation()`
  - Method `.test_archive_is_archived_tolerates_corrupt()`
  - Method `.test_reforge_registry_includes_review_analyze()`
  - Method `.test_delivery_scrub_redacts_url_credentials()`
- `class TestVerify6PushSafeFixes` - *Regression pins for the verify-6push window (last-6-push review).*
  - Method `.test_reforge_resume_refuses_active_hijack()`
  - Method `.test_reforge_settle_reopen_refuses_active_hijack()`
  - Method `.test_pipeline_relative_inside_tolerates_runtime_error()`
  - Method `.test_pipeline_restore_reports_failures()`
  - Method `.test_archive_fill_allows_valid_override()`
  - Method `.test_archive_readme_crlf_and_title()`
  - Method `.test_ui_surface_paths_rejects_traversal()`
  - Method `.test_proof_replay_reports_p2p_unchecked()`
- `class TestVerify9PushSafeFixes` - *Regression pins for the verify-9push window (last-9-push review).*
  - Method `.test_baseline_rejects_long_expiry()`
  - Method `.test_archive_online_refuses_missing_banner()`
  - Method `.test_archive_reason_secret_refused()`
  - Method `.test_reforge_settings_start_guard()`
  - Method `.test_reforge_load_state_validates_run_types()`
  - Method `.test_reforge_validate_rejects_bool_windows()`
  - Method `.test_reforge_load_state_rejects_bad_start_stop()`
  - Method `.test_archive_dossier_failure_never_fails_archive()`
  - Method `.test_reforge_settings_stop_normalized()`
  - Method `.test_reforge_snapshot_restore_skip_traversal()`
  - Method `.test_archive_banner_scan_failure_refuses()`
- `class TestVerify3PushSafeFixes` - *Regression pins for the verify-3push window (last-3-push review).*
  - Method `.test_archive_title_ignores_hashtag()`
  - Method `.test_archive_already_archived_json_shape()`
  - Method `.test_proof_store_rejects_circular()`
  - Method `.test_ui_surface_rejects_symlink_escape()`
  - Method `.test_stop_value_zero_string_and_bool()`
  - Method `.test_update_settings_rejects_bool_and_corrupt_stage()`
  - Method `.test_baseline_detector_uses_top_level_re()`
  - Method `.test_reforge_under_root_rejects_symlink_escape()`
  - Method `.test_archive_title_handles_atx_levels()`
  - Method `.test_archive_already_archived_rejects_unrelated_error()`
  - Method `.test_update_settings_rejects_float_windows()`
  - Method `.test_repair_findings_reports_unsafe_path()`
- `class TestVerifyFollowupHardening` - *Regression pins for the followup verify pass (zero-norm, bool-stop, archive, UI).*
  - Method `.test_stop_value_normalizes_all_zero_forms()`
  - Method `.test_update_settings_normalizes_zero_string_forms()`
  - Method `.test_update_settings_fails_closed_on_corrupt_start()`
  - Method `.test_bool_stop_never_counts_as_bounded()`
  - Method `.test_archive_unarchived_json_not_swallowed()`
  - Method `.test_ui_fixed_paths_reject_symlink_escape()`
  - Method `.test_mutable_default_repair_has_no_priority_field()`
  - Method `.test_plan_from_last_keeps_corrupt_zero_visible()`
  - Method `.test_ui_safe_rel_survives_resolve_failure()`
  - Method `.test_archive_validate_survives_resolve_failure()`
  - Method `.test_run_complete_zero_stop_stays_unbounded()`

**Functions:**
- `def _refuse_spawn(popen_self, args, *unused_args, **unused_kwargs)`
- `def setUpModule()`
- `def tearDownModule()`
- `def not_a_git_repo(workspace)` - *In-process stand-in for `git status` in a non-repository: exactly what real git returns*

---
