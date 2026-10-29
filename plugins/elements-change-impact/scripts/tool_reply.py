"""Unwrap saved replies and Model Context Protocol text envelopes."""

import json


def unwrap_reply(value):
    value = value.get("response", value)
    if "content" in value:
        text = "".join(item["text"] for item in value["content"] if item.get("type") == "text")
        if "[TOOL DATA START]" in text:
            text = text.split("[TOOL DATA START]", 1)[1].split("[TOOL DATA END]", 1)[0].strip()
        value = json.loads(text)
    return value
