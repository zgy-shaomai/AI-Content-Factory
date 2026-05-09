"""
Phase 0 quality gate.

Checks that the handoff package is importable, internally consistent, and does
not rely on hidden demo shortcuts. This is intentionally dependency-free.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "n8n"
NODE_REF_RE = re.compile(r"\$\(\s*['\"]([^'\"]+)['\"]\s*\)")


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def load_json(path: Path, errors: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(errors, f"{path}: JSON parse failed: {exc}")
        return None


def check_workflow(path: Path, errors: list[str]) -> None:
    data = load_json(path, errors)
    if not data:
        return

    nodes = data.get("nodes") or []
    names = [node.get("name") for node in nodes]
    name_set = set(names)
    if len(names) != len(name_set):
        fail(errors, f"{path}: duplicate node names")

    for node in nodes:
        name = node.get("name", "<unnamed>")
        node_type = node.get("type", "")
        params = node.get("parameters") or {}

        if node_type == "n8n-nodes-base.executeCommand":
            fail(errors, f"{path}: executeCommand is not allowed in Phase 0 workflow: {name}")

        if node_type == "n8n-nodes-base.postgres":
            for obj in walk(params):
                if "queryParams" in obj:
                    fail(errors, f"{path}: postgres node uses legacy queryParams: {name}")
                if "additionalFields" in obj:
                    fail(errors, f"{path}: postgres node uses legacy additionalFields: {name}")
            if "query" in params and not (params.get("options") or {}).get("queryReplacement"):
                fail(errors, f"{path}: postgres node missing options.queryReplacement: {name}")

        if node_type == "n8n-nodes-base.webhook":
            mode = params.get("responseMode")
            has_respond = any(n.get("type") == "n8n-nodes-base.respondToWebhook" for n in nodes)
            if mode == "responseNode" and not has_respond:
                fail(errors, f"{path}: webhook responseNode without RespondToWebhook node")

    for source, groups in (data.get("connections") or {}).items():
        if source not in name_set:
            fail(errors, f"{path}: connection source node missing: {source}")
        for channel_groups in groups.values():
            for group in channel_groups:
                for edge in group:
                    target = edge.get("node")
                    if target not in name_set:
                        fail(errors, f"{path}: connection target node missing: {target}")

    for text in iter_strings(data):
        for ref in NODE_REF_RE.findall(text):
            if ref not in name_set:
                fail(errors, f"{path}: expression references missing node: {ref}")


def check_compose(errors: list[str]) -> None:
    prod = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    local = (ROOT / "deploy" / "docker-compose.local.yml").read_text(encoding="utf-8")
    if "n8nio/n8n:latest" in prod + local:
        fail(errors, "docker-compose uses n8n:latest; pin N8N_VERSION")
    if "n8n-worker:" not in prod:
        fail(errors, "production docker-compose queue mode requires n8n-worker service")
    if "WEBHOOK_URL: https://${API_HOST}/" not in prod:
        fail(errors, "production WEBHOOK_URL must use API_HOST, not N8N_HOST")


def check_docs(errors: list[str]) -> None:
    banned = ["假装", "客户不会注意到"]
    for path in ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for phrase in banned:
            if phrase in text:
                fail(errors, f"{path}: banned demo wording found: {phrase}")

    required = [
        ROOT / "docs" / "phase-0-charter.md",
        ROOT / "docs" / "acceptance-rubric.md",
        ROOT / "docs" / "model-matrix.md",
        ROOT / "docs" / "risk-register.md",
    ]
    for path in required:
        if not path.is_file():
            fail(errors, f"missing governance doc: {path}")


def check_smoke_script(errors: list[str]) -> None:
    text = (ROOT / "schemas" / "smoke-test.sh").read_text(encoding="utf-8")
    if "F:/" in text or "飞飞这边的事情" in text:
        fail(errors, "schemas/smoke-test.sh contains hardcoded local path")
    if "export CONTAINER_NAME ROOT_DIR" not in text:
        fail(errors, "schemas/smoke-test.sh must export CONTAINER_NAME and ROOT_DIR")


def main() -> int:
    errors: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.json")):
        check_workflow(path, errors)
    check_compose(errors)
    check_docs(errors)
    check_smoke_script(errors)

    if errors:
        print("QUALITY GATE FAILED")
        for item in errors:
            print(f"- {item}")
        return 1
    print("QUALITY GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

