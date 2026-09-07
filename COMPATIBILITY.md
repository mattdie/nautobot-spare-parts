# Compatibility

## Verified

| Nautobot | Python | Status | How |
|---|---|---|---|
| 3.0.11 | 3.12 | Verified | Full test suite (121 tests) plus an end-to-end API smoke test, run in `networktocode/nautobot:3.0.11-py3.12` |

3.0.11 is the version running in the EEN test cluster, which is why it is the
pinned target in `development/dev.env` and in CI.

## Declared range

`min_version = "3.0.0"`, `max_version = "3.99"`.

## Not supported: Nautobot 2.x

Earlier releases of this app claimed 2.0–3.x support. That claim was not true
and is now removed:

- The UI templates target Nautobot 3's Bootstrap 5 markup. On Nautobot 2 (which
  is Bootstrap 3) they render, but badly.
- Several pages were broken on *every* version until this release — the low
  stock dashboard, list search, and the transactions API all returned HTTP 500 —
  so "tested with 2.1.7 / 2.3.16" cannot have been accurate.
- Nothing in the app was ever run against 2.x by anyone who could confirm it.

If 2.x support is needed, the work is: re-check the `nautobot.apps.*` imports,
convert the templates back to Bootstrap 3 classes (or branch on version), and
run the suite against a 2.4 container by changing `NAUTOBOT_VERSION` in
`development/dev.env`. The test suite is the thing that makes that answerable.

## Testing another version yourself

```bash
# development/dev.env
NAUTOBOT_VERSION=3.1.3
PYTHON_VER=3.12
```

```bash
./dev wipe && ./dev up && ./dev test && ./dev seed && ./dev smoke
```

If all four are clean, that version works. Please open a PR updating the table
above with what you ran.

## Reporting a problem

Include:

- `nautobot-server --version`
- the app version
- the full traceback
- what you clicked or POSTed
