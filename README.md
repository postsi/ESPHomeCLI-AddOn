# ESPHomeCLI AddOn

Home Assistant addon that exposes the **ESPHome CLI** through a web API and a sidebar UI. Other addons, integrations, or automations can call validate, compile, upload, and run using pasted YAML—no file storage on the addon. Jobs run asynchronously; the UI shows in-progress and completed jobs with logs.

## Features

- **Web API**: REST endpoints for `validate`, `compile`, `upload`, `run`, and `clean` with pasted YAML in the request body.
- **Async jobs**: Each long-running action returns a `job_id`; poll `GET /api/jobs/{id}` for status and logs.
- **Sidebar UI**: Opens from the Home Assistant sidebar (panel). Paste YAML, set optional device for flash, then Validate / Build / Flash.
- **No YAML storage**: The addon uses temporary files per job and does not persist configs; callers (e.g. your integration) handle storage.
- **HA auth**: Addon uses `auth_api`; UI is served via Ingress so only logged-in HA users can access it.

## Installation

1. In Home Assistant: **Settings** → **Add-ons** → **Add-on store** → **⋮** → **Repositories**.
2. Add this repository URL:  
   `https://github.com/postsi/ESPHomeCLI-AddOn`
3. Install the **ESPHome CLI** addon and start it.
4. The **ESPHome CLI** entry appears in the sidebar; open it to use the UI.

## Building the addon image

The addon is built from the ESPHome Docker image (so the `esphome` CLI is available). To build and push the image yourself (e.g. for your own repo):

- **Option A – Local build (for testing)**  
  From the repo root:
  ```bash
  cd esphomecli-addon
  docker build -t ghcr.io/postsi/esphomecli-addon:1.0.0 .
  ```
  The `version` in `esphomecli-addon/config.yaml` must match the Docker image tag (e.g. 1.0.0) so Home Assistant pulls the correct image.

- **Option B – GitHub Actions**  
  Use the [Home Assistant Add-on Build](https://github.com/hassio-addons/addon-base) workflow or a custom workflow that builds the image from `esphomecli-addon/Dockerfile` and pushes it to your container registry. Set `image: ghcr.io/postsi/esphomecli-addon` in `config.yaml` and tag the built image with the addon `version` (e.g. `1.0.0`).

## API summary

Base URL when using the addon: the addon is reached via Ingress (same origin as the UI) or, from the host, at `http://localhost:8099` if the port is mapped.

| Method | Endpoint | Body | Response |
|--------|----------|------|----------|
| GET | `/api/health` | — | `{ "status": "ok" }` |
| POST | `/api/validate` | `{ "yaml": "..." }` | `{ "valid": true/false, ... }` (sync) |
| POST | `/api/compile` | `{ "yaml": "...", "substitutions": {}, "only_generate": false }` | `{ "job_id": "..." }` |
| POST | `/api/upload` | `{ "yaml": "...", "device": "192.168.1.10", "upload_speed": 460800 }` | `{ "job_id": "..." }` |
| POST | `/api/run` | `{ "yaml": "...", "device": "...", "no_logs": false }` | `{ "job_id": "..." }` |
| POST | `/api/clean` | `{ "yaml": "..." }` | `{ "job_id": "..." }` |
| GET | `/api/jobs` | — | `{ "jobs": [ { "job_id", "type", "status", ... } ] }` |
| GET | `/api/jobs/{job_id}` | — | `{ "type", "status", "logs", "error", ... }` |

Flash target (`device`) is always provided by the caller (IP or serial port).

## Repository structure

```
ESPHomeCLI-AddOn/
├── repository.yaml          # Add-on repository config
├── README.md
└── esphomecli-addon/
    ├── config.yaml          # Addon config (ingress, panel_icon, panel_title)
    ├── build.yaml           # Build-from ESPHome image
    ├── Dockerfile
    ├── run.sh               # Optional entrypoint
    └── app/
        ├── main.py          # FastAPI app + job runner
        ├── requirements.txt
        └── static/
            └── index.html   # Ingress UI
```

## License

MIT
