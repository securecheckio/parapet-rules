# parapet-rules

Ready-to-use **JSON rule feeds** for [Parapet](https://github.com/securecheckio/parapet). Parapet’s proxy loads them from HTTP and refreshes them on a schedule.

**If you only want to turn protection on:** add the feed URLs to Parapet’s `config.toml` (see [Example](#example-configtoml) below). You do **not** need to read the rest of this file.

---

## Pick a feed (one URL per category)


| URL path (under `community/`) | When to use it                                  |
| ----------------------------- | ----------------------------------------------- |
| `core-protection.json`        | No third-party API keys; pattern rules only.    |
| `helius-protection.json`      | You have a Helius API key.                      |
| `jupiter-protection.json`     | You have a Jupiter API key.                     |
| `rugcheck-protection.json`    | You have a Rugcheck API key.                    |
| `ai-agent-protection.json`    | AI agents / flowstate-style patterns.            |
| `advanced-patterns.json`      | CPI depth + instruction-padding patterns.       |
| `trading-bot-alerts.json`     | Alert-first patterns for trading-style traffic. |


There is **no** single “download everything” URL on purpose: you choose which categories to load. List each one as its own `[[rule_feeds.sources]]` entry.

**Hosted copies**

- Pages: `https://parapet-rules.securecheck.io/` (landing page + links) and `https://parapet-rules.securecheck.io/community/<filename>` for each feed
- Raw GitHub: `https://raw.githubusercontent.com/securecheckio/parapet-rules/main/community/<filename>`

The static site root is built from `pages/index.html` in this repo (copied in the Pages workflow).

Full Parapet options (timing, multiple sources, etc.): [Rule Feeds documentation](https://github.com/securecheckio/parapet/blob/main/docs/RULE_FEEDS.md).

---

## Example `config.toml`

```toml
[rule_feeds]
enabled = true
poll_interval = 3600

[[rule_feeds.sources]]
url = "https://parapet-rules.securecheck.io/community/core-protection.json"
name = "parapet-community-core"
priority = 5
min_interval = 300
```

Add more `[[rule_feeds.sources]]` blocks for other categories if you need them.

---

## Customize, combine, override

- **Fork / clone** this repo if you want to edit JSON yourself. Host the changed files over **HTTPS** (fork raw URL, internal static host, etc.) and point `url` at your copy.
- **Several URLs at once** is normal: community feeds + your own JSON on another domain.
- **Same rule in two feeds:** Parapet merges on the rule’s `**id` string**. The feed with the **lower `priority` number wins** (e.g. `0` beats `5`). Put your overrides in a small-priority feed without changing upstream.

---

## `integration-examples/`

Example JSON for **your** hosted override feeds. Not published as Parapet “community” feeds.

---

## For contributors (rule JSON in `community/`)

- `**id`** — Must match `community-<slug>` (see validator). That single string is Parapet’s merge key and is enough to mark “from this community pack” and avoid colliding with unrelated rules elsewhere.
- `**metadata**` — Optional. Use it for severity, notes, tuning hints, etc. CI only checks shape when `metadata` is present; it does not require extra numeric identifiers beyond `id`.
- **Uniqueness** — Each `id` must appear in **at most one** file under `community/` (enforced in CI).

**Condition `field` values** (e.g. `token_instructions:…`) describe what to read from analyzers; they are not the same thing as rule `id`.

Validate locally: `python3 scripts/validate_community_feeds.py`

---

MIT — see `LICENSE`.