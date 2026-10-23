Python 3 / raw sockets (epoll via `selectors`) / psycopg 3 / bcrypt / PyJWT — `Front: direct`.

Hexagonal structure: pure domain rules, Protocol ports, inbound socket-adapter (non-blocking epoll loop with per-connection request buffering and byte-exact keep-alive) and outbound pg/crypto adapters, wired in `main.py`.

- Bounded psycopg pool (5–30) against Postgres `max_connections = 100`
- All 19 Conduit endpoints per the reference SQL (capped counts, tag/author/favorited filters, lateral-join feed, transactional article+tags insert)
- Real security: fresh bcrypt cost-10 verify per login, HS256 + `exp` verified on every request, no caching
- Conformance: **197/197 steps PASS** via `just test`

Toolchain: `build.sh` creates a project venv from `constraints.txt` (fully pinned incl. transitives); `install.sh` apt-fetches python3-venv/libpq; `start.sh` runs the foreground server. Justfile recipes: `test`, `venv`, `lint`, `check`, `paths`.
