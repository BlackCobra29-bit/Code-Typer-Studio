"""Deterministic reveal schedule shared by HTML, GIF and MP4."""
from __future__ import annotations
import re


def build_timeline(highlight: dict, options) -> dict:
    speed = max(4, min(250, options.speed_ms))
    line_pause = max(0, min(1200, options.line_pause_ms))
    time = max(0, min(5000, options.start_delay_ms))
    chars, events = [], []
    for line_no, tokens in enumerate(highlight["lines"]):
        offset = 0
        for token in tokens:
            for char in token["content"]:
                chars.append({"text": char, "line": line_no, "column": offset,
                              "color": token["color"], "fontStyle": token["fontStyle"]})
                offset += 1
        if line_no < len(highlight["lines"]) - 1:
            chars.append({"text": "\n", "line": line_no, "column": offset,
                          "color": highlight["foreground"], "fontStyle": 0})
    source = "".join(c["text"] for c in chars)
    if options.typing_mode == "token":
        groups = []
        for line_no, tokens in enumerate(highlight["lines"]):
            groups.extend(token["content"] for token in tokens if token["content"])
            if line_no < len(highlight["lines"]) - 1:
                groups.append("\n")
    elif options.typing_mode == "line":
        groups = re.findall(r"[^\n]*\n|[^\n]+$", source)
    elif options.typing_mode == "word":
        groups = re.findall(r"\n|[^\S\n]+|\w+|[^\w\s]", source)
    else:
        groups = list(source)
    count = 0
    for group in groups:
        count += len(group)
        events.append({"at": round(time, 3), "count": count})
        variation = 0.82 + ((count * 17 + ord(group[-1])) % 11) * 0.036
        delay = speed * variation
        if options.typing_mode in {"word", "token"}:
            delay *= max(1.5, min(5, len(group) * 0.65))
        elif options.typing_mode == "line":
            delay = max(160, len(group) * speed * 0.35)
        if group.endswith("\n"):
            delay += line_pause
        elif group.isspace():
            delay *= 0.32
        elif group[-1] in ",;:":
            delay += speed * 2.5
        elif group[-1] in ")]}":
            delay += speed * 1.5
        time += delay
    previous = 0
    for event in events:
        for char in chars[previous:event["count"]]:
            char["at"] = event["at"]
        previous = event["count"]
    end = events[-1]["at"] if events else time
    return {"chars": chars, "events": events, "typingEnd": end,
            "duration": max(650, end + 1500), "fadeMs": 150, "cursorEaseMs": 70}
