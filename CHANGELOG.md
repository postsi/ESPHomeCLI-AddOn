# Changelog

## [1.0.2] – 2025-02-11

### Added

- Request logging: every request logs method, path, and Ingress-related headers to addon log.
- Startup log: DATA_DIR and UI routes.
- Catch-all GET handler: serve UI for any unhandled path and log the path (aids 404 diagnosis).

## [1.0.1] – 2025-02-11

### Fixed

- Ingress 404: serve UI at `/api/hassio_ingress/...` path so the sidebar panel loads.
- Frontend API URLs now relative to panel URL so API calls work when loaded via Ingress.
- Docker build: use `ghcr.io/esphome/esphome-hassio` base and `uv pip install` (match official ESPHome addon).

## [1.0.0] – 2025-02-11

### Added

- Initial release.
- Web API: `POST /api/validate`, `/api/compile`, `/api/upload`, `/api/run`, `/api/clean`; `GET /api/jobs`, `/api/jobs/{id}`, `/api/health`.
- Async job queue (in-memory); temp YAML per job, no persistent storage.
- Ingress UI: paste YAML, device field for flash, Validate / Build / Flash buttons, jobs list with status and logs.
- Sidebar entry via `panel_icon` and `panel_title` in addon config.
- `auth_api` enabled for future token validation.
