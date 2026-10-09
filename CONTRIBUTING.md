# Contributing

Thanks for helping improve this A-share company-analysis skill.

## Scope

- **Product path = A-share only** (Shanghai / Shenzhen / Beijing). Do not reintroduce US/HK collectors or Tushare as a runtime dependency.
- Keep the v8 judgment chain (five nodes, `assemble_report_v8`, `lint_v8`, dual reviewers, `--review` / `--compare`).
- Data changes go through `scripts/a_share_collector.py` + `scripts/providers/` with provenance and honest empty-table semantics.

## Dev setup

```bash
python -m pip install -r scripts/requirements.txt
python -m scripts.check_env
python -m unittest discover -s scripts/tests -t . -v
```

Optional live smoke (rate-limited free sources):

```bash
CA_NETWORK_TESTS=1 python -m unittest \
  scripts.tests.test_a_share_p0.TestNetworkSmoke \
  scripts.tests.test_a_share_p1.TestNetworkP1Smoke -v
```

Optional GitHub Actions: copy [`docs/optional-network-nightly.workflow.yml`](./docs/optional-network-nightly.workflow.yml) to `.github/workflows/network-nightly.yml` (needs a token/app with `workflow` scope to land via PR).

## Pull requests

1. Branch from `main`; keep PRs focused (one phase / one concern).
2. Add or update unit tests for bridge / merge / provenance / compare A-share gates.
3. Update `CHANGELOG.md` under a dated section.
4. Do not commit tokens, cache dumps, or full `output/` runs.
5. If you touch free-source scrapers, document gap behavior in `docs/data-sources-compliance.md`.

## Explicit gaps (do not “fix” with silence)

Until a stable free per-stock API exists, keep these as `deferred` / `partial` with notes:

- `stk_managers`, `stk_rewards`, `top_inst`

Writing「无高管 / 无薪酬 / 无机构席位」from an empty deferred table is a bug.

## Code of conduct (lightweight)

Be precise in reviews; prefer failing loud with provenance over silent empty tables. No investment advice in commit messages or docs beyond the skill’s existing disclaimers.
