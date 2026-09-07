"""Inspect a stored mesh through REST without printing credentials or measurements."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

import requests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pulse-ep-check-mesh", description=__doc__)
    parser.add_argument("--map-id", type=int, required=True)
    parser.add_argument(
        "--base-url", default=os.environ.get("PULSE_EP_BASE_URL", "http://127.0.0.1:5000")
    )
    parser.add_argument("--username", default=os.environ.get("PULSE_EP_USERNAME"))
    parser.add_argument("--scalar-name")
    parser.add_argument("--distance", type=float, default=5.0)
    parser.add_argument("--representation", choices=("raw", "display"), default="raw")
    args = parser.parse_args(argv)
    if not args.username:
        parser.error("set PULSE_EP_USERNAME or pass --username")
    password = os.environ.get("PULSE_EP_PASSWORD") or getpass.getpass("Password: ")
    if not password:
        parser.error("a password is required")
    base_url = args.base_url.rstrip("/")
    try:
        login = requests.post(
            f"{base_url}/login_user",
            json={"username": args.username, "password": password},
            timeout=60,
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        response = requests.get(
            f"{base_url}/get_mesh_data",
            params={
                "map_id": args.map_id,
                "representation": args.representation,
                "scalar_name": args.scalar_name,
                "distance": args.distance,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        mesh = data["mesh_data"]
        summary = {
            "map_id": args.map_id,
            "representation": args.representation,
            "response_keys": sorted(data),
            "mesh_keys": sorted(mesh),
            "vertices": len(mesh["vertices"]),
            "triangles": len(mesh["faces"]),
            "scalar_name": data.get("scalar_name"),
            "scalar_fields": sorted(mesh.get("scalar_fields", {})),
            "measurement_points": len(data.get("point_data", {}).get("coordinates", [])),
        }
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        # Error bodies or request URLs can contain sensitive data.
        print(
            f"Mesh inspection failed ({type(exc).__name__}). Check the service and map ID.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
