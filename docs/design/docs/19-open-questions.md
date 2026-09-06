# Open Questions

1. Should the first implementation be Python-only or support a second runtime?
2. Which graph database, if any, is justified? Start with JSON/SQLite unless scale proves otherwise.
3. How much semantic analysis should be LLM-based versus deterministic?
4. Which GitHub API abstraction should be used?
5. How should credentials be provisioned across Claude Code/Codex/Cursor?
6. Should the HTML report be fully static or include a small local API?
7. What minimum plugin SDK should be stable at v1?
8. How should research freshness be represented?
9. How should license compatibility be scored?
10. Which security scanners should be first-party integrations?
11. How should runtime telemetry be incorporated before declaring something unused?
12. What is the minimal canonical capability schema that can survive ecosystem changes?
13. `analysis/update_intelligence.py::assess_impact` only reaches `UpdateVerdict.UPDATE_RECOMMENDED` when the capability/dependency/interface/installation dimensions are all resolved on *both* the current and available `ComponentState` (`unknown_dimensions` must be empty). Verified against the actual code: no `ComponentUpdateProvider` (`pypi`/`npm`/`crates_io`/`go_proxy`/`maven_central`) ever populates `capabilities`/`interfaces`/`dependencies` on the `AvailableState` it returns, and `build_current_state` never populates any of the four on the current-side `ComponentState` either (not even `runtime_requirements`, despite `pypi`/`npm` populating it on the *available* side) — so `unknown_dimensions` is never empty and `UPDATE_RECOMMENDED` is effectively unreachable for every dependency, in every ecosystem, today (confirmed across every `si check-updates` run in this project's own live-validation history: never once `update_recommended`, always `review_required`/`unknown`/`no_update_available`). Populating the *available* side's `dependencies` is a straightforward parse of metadata each provider's own API response already includes (PyPI's `info.requires_dist`, npm's `dependencies` object, crates.io's per-version dependency list) — the harder, still-open design question is the *current* side: doing this right needs a "fetch metadata for an arbitrary already-known version" capability (not just "fetch latest"), which no `ComponentUpdateProvider` exposes yet and would mean extending that Protocol across all five providers. Left open rather than guessed at: is `REVIEW_REQUIRED`-by-default actually the intended conservative posture here (consistent with this project's evidence-first philosophy), or a genuine gap worth the cross-provider protocol change to close?
