# REPORT_POLICY.md — SAMBPS DTaaS Progress Report Rules

## Cadence
- **Daily:** `PROGRESS_YYYY-MM-DD.md`
- **Weekly (Sunday):** `PROGRESS_WEEK_WNN.md` (diff of 7 daily files)
- **Monthly (1st):** `PROGRESS_MONTH_YYYY-MM.md` (diff of 4 weekly rollups)

## Per-run contract (daily)
<!-- 2026-04-24: step-4 TR-87 folder-existence clause removed. Per-TR folder checks are out of scope for the report contract; TR-86..TR-100 coverage is tracked in RESEARCH_PLAN_TR86_TR100.md. -->
1. Walk `/root/phd_thesis` recursively (never stop at depth 1 — R-04 regression).
2. Read authoritative sources in priority order:
   - (a) `04_code/sambp/digital_twin/PROGRESS.yaml`
   - (b) `03_technical_reports/TR_INDEX.md`
   - (c) `03_technical_reports/tr_namespace_map.yaml`
   - (d) `04_code/sambp/digital_twin/ISSUES.md`
   - (e) `01_strategy/ROADMAPS/RESEARCH_PLAN_TR86_TR100.md`
3. Reconcile PROGRESS.yaml rows with on-disk TR folders; flag mismatches.
4. Sanity checks (fail-safe if any fails): PROGRESS.yaml parses; ISSUES.md non-empty;
   ≥1 TR complete; TR_INDEX.md active-row count == 91;
   tr_namespace_map.yaml YAML-valid.
5. If today's report already exists, **PREPEND** a run-N addendum (never overwrite).
6. Update `STATUS_SNAPSHOT.yaml`; bump `last_run_ts`, `runs_today`, `interactive_touches_today`.
7. Regenerate `STATUS_DASHBOARD_EMBEDDED.html`.
8. Required sections (in order): Folder snapshot · Plan-vs-reality TR table (91 active + 9 backlog) ·
   v0.1 evidence · v0.2 issues · Critical path · Rolling 7/30-day plan · Risks (R-01..R-18) · Diff-from-previous.
9. Autonomous rules: no Slack/email/MCP writes. Files only.

## Output path
`/root/phd_thesis/SAMBPS DTaaS/progress_reports/` (authoritative; Cowork reflects)

## Fail-safe
If any sanity check fails, write a minimal `PROGRESS_YYYY-MM-DD.md` recording the failure and stop.
Preserving history beats forcing a green run.
