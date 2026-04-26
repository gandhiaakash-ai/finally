# FinAlly E2E Tests

Playwright end-to-end suite that exercises the deployed app container
against the deterministic LLM mock + simulated market data.

## Run

From the repo root:

```bash
docker compose -f test/docker-compose.test.yml up \
  --abort-on-container-exit --exit-code-from runner --build
```

The compose file:

- builds the production image from `../Dockerfile`
- starts the app with `LLM_MOCK=true` and no `MASSIVE_API_KEY`
- runs the Playwright suite in `mcr.microsoft.com/playwright:v1.48.0-jammy`
  so the production image stays free of browser deps

Artifacts (HTML report, JUnit XML, traces, screenshots, video) are
written under `test/playwright-report/`, `test/results/`, and
`test/test-results/`.

## Selector contract

The frontend must attach the `data-testid` attributes listed in
`support/selectors.ts`. These are the only selectors used by the suite —
do not break them without coordinating with the integration-tester.
