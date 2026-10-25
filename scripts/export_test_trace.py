"""Export observable first-turn test messages/tool I/O, excluding private reasoning.

Uses the OpenCode API, never edits the live OpenCode database. Exports only through
the first idle event so later unrelated prompts in the same session are not copied.
Generated analysis artifacts are private, Git-ignored runtime data.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote


def api(path):
    response = subprocess.run(["opencode", "api", "get", path], check=True, capture_output=True, text=True)
    return json.loads(response.stdout)


def sanitize(value):
    if isinstance(value, list):
        return [sanitize(item) for item in value if not isinstance(item, dict) or item.get("type") != "reasoning"]
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()
                if key.lower() not in {"native", "reasoning", "authorization", "api_key", "apikey", "access_token"}}
    if isinstance(value, str):
        return re.sub(r"Bearer\s+[A-Za-z0-9_.~+/-]{12,}", "Bearer [REDACTED]", value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", help="Explicit OpenCode session ID to export")
    args = parser.parse_args()
    if not re.fullmatch(r"ses_[A-Za-z0-9]+", args.session_id):
        parser.error("Invalid session ID")
    root = Path(__file__).resolve().parents[1] / "runtime" / "analysis" / args.session_id
    os.umask(0o077)
    root.mkdir(parents=True, exist_ok=False)
    messages, tools = [], []
    path = f"/api/session/{args.session_id}/message?limit=1&order=asc"
    for _ in range(200):
        page = api(path)
        if not page.get("data"):
            break
        for message in page["data"]:
            safe = sanitize(message)
            messages.append(safe)
            for part in safe.get("content", []):
                if part.get("type") == "tool":
                    tools.append({"message_id": safe["id"], **part})
        if any(message.get("type") == "idle" for message in page["data"]):
            break
        cursor = page.get("cursor", {}).get("next")
        if not cursor:
            break
        path = f"/api/session/{args.session_id}/message?limit=1&cursor=" + quote(cursor, safe="")
    else:
        raise RuntimeError("Unexpectedly long test; export stopped to avoid unrelated data")
    data = {"session_id": args.session_id, "exported_at": datetime.now(timezone.utc).isoformat(),
            "scope": "First test turn through first idle event; observable messages and tool I/O only",
            "exclusions": ["private reasoning", "native provider payloads", "obvious secret fields", "subsequent conversation turns"],
            "messages": messages}
    (root / "trace.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    (root / "tools.jsonl").write_text("".join(json.dumps(tool, ensure_ascii=False) + "\n" for tool in tools))
    lines = ["# Observable test execution", "", f"Session: `{args.session_id}`", "",
             "Private reasoning/native payloads are excluded. This is not a chain-of-thought export.", ""]
    for message in messages:
        stamp = message.get("time", {}).get("created")
        lines.append(f"## {message['type']} — {stamp}")
        if message.get("type") == "user":
            lines.append(message.get("text", ""))
        for part in message.get("content", []):
            if part.get("type") == "text":
                lines.append(part.get("text", ""))
            elif part.get("type") == "tool":
                lines.append(f"Tool: `{part.get('name')}`; status: `{part.get('state', {}).get('status')}`")
                lines.append("```json\n" + json.dumps(part.get("state", {}).get("input"), ensure_ascii=False, indent=2) + "\n```")
                lines.append("Full tool output is in trace.json / tools.jsonl.")
        lines.append("")
    (root / "timeline.md").write_text("\n".join(lines))
    print(json.dumps({"directory": str(root), "messages": len(messages), "tool_calls": len(tools),
                      "files": ["trace.json", "tools.jsonl", "timeline.md"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
