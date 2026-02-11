#!/usr/bin/env python3
"""
Find an available port and start uvicorn. Avoids conflict with esphome-hassio base image services.
Tries: 1) Supervisor API (when ingress_port is 0), 2) free port in range 9080-9099.
"""
import os
import socket
import sys
import urllib.request

# Port range to try (avoid 6052, 8099, 8098 used by base image)
PORT_RANGE = range(9080, 9100)


def get_port_from_supervisor() -> int | None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    try:
        req = urllib.request.Request(
            "http://supervisor/addons/self/info",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            import json
            data = json.load(r)
            port = data.get("data", {}).get("ingress_port")
            if isinstance(port, int) and port > 0:
                return port
    except Exception:
        pass
    return None


def find_free_port() -> int:
    for port in PORT_RANGE:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No free port in range {PORT_RANGE.start}-{PORT_RANGE.stop - 1}")


def main():
    port = get_port_from_supervisor()
    if port is None:
        port = find_free_port()
        print(f"No Supervisor port; using first free port: {port}", flush=True)
    else:
        print(f"Using Supervisor-assigned port: {port}", flush=True)
    os.execve(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)],
        os.environ,
    )


if __name__ == "__main__":
    main()
