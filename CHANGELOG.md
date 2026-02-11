# Changelog

## [1.0.0] – 2025-02-11

### Added

- Initial release.
- Web API: `POST /api/validate`, `/api/compile`, `/api/upload`, `/api/run`, `/api/clean`; `GET /api/jobs`, `/api/jobs/{id}`, `/api/health`.
- Async job queue (in-memory); temp YAML per job, no persistent storage.
- Ingress UI: paste YAML, device field for flash, Validate / Build / Flash buttons, jobs list with status and logs.
- Sidebar entry via `panel_icon` and `panel_title` in addon config.
- `auth_api` enabled for future token validation.
