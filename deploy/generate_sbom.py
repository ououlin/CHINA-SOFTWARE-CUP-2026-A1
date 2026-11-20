"""Generate a CycloneDX 1.5 SBOM from the active Python env and npm lockfile."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path


def python_components() -> list[dict]:
    components = []
    for dist in importlib.metadata.distributions():
        name = (dist.metadata.get("Name") or "unknown").strip()
        version = dist.version
        normalized = name.lower().replace("_", "-")
        components.append({
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{urllib.parse.quote(normalized)}@{urllib.parse.quote(version)}",
            "properties": [{"name": "runtime", "value": "python"}],
        })
    return components


def npm_components(lockfile: Path) -> list[dict]:
    if not lockfile.is_file():
        return []
    data = json.loads(lockfile.read_text(encoding="utf-8"))
    components = []
    for package_path, package in data.get("packages", {}).items():
        if not package_path or "node_modules/" not in package_path:
            continue
        name = package_path.rsplit("node_modules/", 1)[-1]
        version = str(package.get("version") or "unknown")
        encoded_name = urllib.parse.quote(name, safe="/").replace("@", "%40")
        components.append({
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:npm/{encoded_name}@{urllib.parse.quote(version)}",
            "properties": [{"name": "runtime", "value": "frontend-build"}],
        })
    return components


def build_sbom(lockfile: Path) -> dict:
    components = python_components() + npm_components(lockfile)
    components.sort(key=lambda item: (item["purl"], item["version"]))
    identity = "\n".join(item["purl"] for item in components)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, identity)}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "application",
                "name": "device-repair-knowledge-system",
                "version": "0.6.0",
            },
        },
        "components": components,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--lockfile", type=Path, default=root / "frontend" / "package-lock.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sbom = build_sbom(args.lockfile)
    args.output.write_text(
        json.dumps(sbom, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"SBOM components: {len(sbom['components'])}; output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
