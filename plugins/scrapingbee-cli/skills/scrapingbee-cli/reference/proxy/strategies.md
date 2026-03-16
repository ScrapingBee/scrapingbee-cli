# Proxy strategies

ScrapingBee uses rotating proxies by default. For blocked or throttled requests, escalate in this order.

## Escalation

1. **Default** — No proxy flags. Rotating proxy; 1 credit without JS, 5 with JS.
2. **Premium** — **`--premium-proxy true`**. Residential-like; 10 credits without JS, 25 with JS. Use when the site blocks rotating IPs.
3. **Stealth** — **`--stealth-proxy true`**. Highest success; **75 credits per request**. Use when premium is still blocked. Requires JS; some features (custom headers/cookies, timeout) not supported with stealth. Use space-separated values only (e.g. `--premium-proxy true`), not `=value`.

**Geolocation:** With premium or stealth, add **`--country-code XX`** (ISO 3166-1, e.g. `us`, `de`, `gb`).

**Own proxy:** **`--own-proxy user:pass@host:port`** to use your proxy with ScrapingBee rendering.

## Credit costs (per request)

| Setup | No JS | With JS |
|-------|--------|--------|
| Rotating (default) | 1 | 5 |
| Premium | 10 | 25 |
| Stealth | — | 75 |

Use **`--verbose`** (before or after command) to see `Spb-Cost` header.

## Automatic escalation

Use **`--escalate-proxy true`** to let the CLI auto-escalate through proxy tiers on failure (default -> premium -> stealth). This overrides `--premium-proxy` / `--stealth-proxy` and retries automatically — no manual intervention needed.

## When to try what

- **429 / 403 / empty or captcha** → Retry with `--premium-proxy true` (and optionally `--country-code`).
- **Still blocked** → Retry with `--stealth-proxy true`. Ensure `--render-js` is not disabled.
- **Consistent IP (e.g. login)** → **`--session-id N`** (same integer for all requests; 0–10000000). Same IP ~5 minutes.
