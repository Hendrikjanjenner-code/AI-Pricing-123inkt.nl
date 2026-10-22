---
name: Async middleware and database pool starvation
description: Avoid synchronous database waits on the request event loop, including metering.
---

Async request middleware must not perform synchronous SQLAlchemy work directly on the event loop. Offload the entire operation, including session creation and closure, to a worker thread. Metering's actor lookup and rate-cache miss can also access the database.

**Why:** When all request-pool connections are checked out, a synchronous middleware checkout blocks the event loop. Existing requests cannot finish their dependency cleanup and release connections, turning ordinary load into repeated pool timeouts and blank authenticated screens. Login and health requests were affected as well.

**How to apply:** Keep database sessions thread-local to the offloaded operation; do not pass live sessions across threads. Test that a deliberately blocked authorization or metering lookup does not block an independent health request. Increasing the connection pool alone does not fix this dependency cycle.
