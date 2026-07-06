---
name: SSRF validator ValueError trap
description: Why UnsafeURLError must never be raised inside an `except ValueError` block in the connectors SSRF validator.
---

`UnsafeURLError` subclasses `ValueError`. The connector SSRF validator parses IP
addresses with `ipaddress.ip_address(...)`, which raises `ValueError` for
domain names — so that parsing is wrapped in `try/except ValueError`.

**The trap:** if you `raise UnsafeURLError(...)` *inside* one of those
`try/except ValueError` blocks, the very `except ValueError` you rely on for the
domain-name fallback silently swallows the block. Result: the validator returns
None and every private/loopback/metadata target is allowed through — SSRF
protection is fully disabled while looking correct.

**Rule:** keep IP *parsing* (which may raise ValueError) strictly separate from
*raising* UnsafeURLError. Collect candidate IPs first inside the try/except, then
raise UnsafeURLError in a plain loop afterwards.

**How to apply:** any change to `validate_external_url` in
`artifacts/api-server/connectors/net.py`. Regression check:
`validate_external_url` must block `127.0.0.1`, `localhost`, `169.254.169.254`,
`10.x`, `192.168.x`, `[::1]` and pass public hosts. Redirect safety lives in
`safe_get` (redirects disabled; every hop re-validated) — don't reintroduce
`httpx follow_redirects=True` for user-supplied feed URLs.
