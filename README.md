# Cursor Teams Source (Airbyte)

Airbyte connector for the [Cursor Teams Admin API](https://cursor.com/docs/account/teams/admin-api). It syncs team members, daily usage metrics, per member spend, and granular usage events into your warehouse.

## Status: superseded by the upstream Airbyte PR

This repo is the original prototype, kept for reference and archived. The connector now lives in [airbytehq/airbyte](https://github.com/airbytehq/airbyte) as PR [#82708, New Source: Cursor](https://github.com/airbytehq/airbyte/pull/82708). Use that for the maintained version and for issues or review comments.

## Why this exists

Cursor's dashboard and Admin API only expose a rolling window of usage and spend data. Once the window rolls past, that data is gone. This connector snapshots the window into permanent warehouse storage on every sync.

**Install now, history starts accruing now.** The connector cannot backfill anything older than the window Cursor still serves. Every day you wait is a day of usage and spend data you will never get back.

## Setup

1. In the Cursor dashboard, go to Settings > Admin > API Keys and create an Admin API key (it starts with `crsr_`).
2. In Airbyte, create a Cursor Teams source with:
   - **API Key**: the `crsr_` key. Auth is HTTP Basic with the key as username and an empty password; the connector handles this for you.
   - **Start Date**: `YYYY-MM-DD`. Dates older than Cursor's retention window simply return nothing, so today's date is a fine choice.
3. Schedule the connection to sync **daily**. The incremental streams use a lookback (2 days for `daily_usage`, 1 day for `usage_events`) so late arriving data from Cursor's hourly aggregation is picked up on the next sync.

## Streams

| Stream | Endpoint | Sync mode | Primary key | Notes |
|---|---|---|---|---|
| `members` | `GET /teams/members` | Full refresh | `email` | Current team roster |
| `daily_usage` | `POST /teams/daily-usage-data` | Incremental on `date` (epoch ms) | `date`, `email` | Per user per day metrics: lines, tabs, applies, requests by type, most used model |
| `spend` | `POST /teams/spend` | Full refresh (paginated) | `email` | Current billing cycle spend per member. Use an append destination mode to build a history of cycle snapshots |
| `usage_events` | `POST /teams/filtered-usage-events` | Incremental on `timestamp` (epoch ms string), paginated | `timestamp`, `userEmail`, `model` | Event level model usage, tokens, and cost |

## Cost fields are numbers, never integers

Cursor returns fractional cents, for example `spendCents: 9445.474115` and `chargedCents: 11.1869`. All cost fields (`spendCents`, `includedSpendCents`, `chargedCents`, `cursorTokenFee`, `requestsCosts`, `tokenUsage.totalCents`) are declared as JSON schema type `number`. Declaring them `integer` makes destinations silently null the values. The manifest carries inline comments on each field so nobody tidies them back to `integer`. The `canary/` check exists to catch exactly this regression.

## Rate limits and resilience

The Cursor Admin API is rate limited (20 to 60 requests per minute per team depending on the endpoint). The connector:

- runs with `concurrency_level: 1`
- retries HTTP 429, 500, 502, 503, and 504 with exponential backoff, up to 5 attempts
- requests 30 day windows per API call, matching the API's maximum range

## Canary

`canary/cost_field_canary.py` calls the live API and fails (exit 1) if any cost field comes back null or missing. A GitHub Actions workflow runs it monthly against the `CURSOR_API_KEY` repository secret. Run it manually with:

```bash
CURSOR_API_KEY=crsr_... python3 canary/cost_field_canary.py
```

## Local development

The manifest runs on the plain Airbyte CDK, no Docker needed:

```bash
python3 -m venv .venv && .venv/bin/pip install airbyte-cdk
echo '{"api_key": "crsr_...", "start_date": "2026-01-01"}' > secrets/config.json
```

```python
import sys
from airbyte_cdk.entrypoint import launch
from airbyte_cdk.sources.declarative.yaml_declarative_source import YamlDeclarativeSource
launch(YamlDeclarativeSource(path_to_yaml="manifest.yaml", config=..., catalog=None, state=None), sys.argv[1:])
```

Or import `manifest.yaml` straight into the Airbyte Connector Builder (Builder > New custom connector > Import a YAML manifest) and use the stream test panel.

## License

MIT
