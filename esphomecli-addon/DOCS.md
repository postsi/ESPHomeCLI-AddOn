# ESPHome CLI addon – Documentation

## What it does

This addon runs the **ESPHome CLI** in a container and exposes it over HTTP:

- **UI**: A web interface in the Home Assistant sidebar where you can paste YAML, validate it, and run build or flash as background jobs.
- **API**: REST endpoints so other addons, integrations, or `rest_command` can trigger validate/compile/upload/run/clean with pasted YAML.

No config files are stored on the addon; YAML is sent in each request and kept only in temporary files for the duration of the job.

## Options

The addon has no required options. Optional settings can be added later (e.g. API key, timeouts) via `config.yaml` `options` and `schema`.

## API usage from Home Assistant

Example `rest_command` to validate pasted YAML (replace `PASTED_YAML` with your config):

```yaml
rest_command:
  esphome_validate:
    url: "http://localhost:8099/api/validate"
    method: POST
    content_type: "application/json"
    payload: '{"yaml": "esphome:\n  name: test\n  platform: ESP32\n  board: nodemcu-32s"}'
```

Example to start a compile job and get `job_id`:

```yaml
rest_command:
  esphome_compile:
    url: "http://localhost:8099/api/compile"
    method: POST
    content_type: "application/json"
    payload: '{"yaml": "{{ yaml_content }}"}'
```

When the addon is used via Ingress (from the browser), requests go through Home Assistant and are already authenticated. When calling from the host (e.g. `rest_command`), use `http://localhost:8099` if the addon exposes the port in config, or the internal Docker hostname if calling from another addon.

## Flash target

For `upload` and `run`, the caller must supply `device` when needed, for example:

- OTA: `"device": "192.168.1.10"`
- Serial: `"device": "/dev/ttyUSB0"` (requires the addon to map the device)

If your addon needs to flash over serial, add `devices` or `uart: true` in the addon `config.yaml` and pass the appropriate device path in the API body.
