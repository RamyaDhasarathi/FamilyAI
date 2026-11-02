"""The phone agent's local method: Qwen3.5 plans and checks, MAI-UI-2B finds where to tap -- both on this Mac's model
server. Ported from the collector app (Mobile-UI-Agent backend/src/services/orchestrator.js, grounding.js, screen.js and
the run bookkeeping of routes/agent2.js; decided 2 Nov 2026: "your Qwen + MAI-UI two-model method, alongside Claude").

Per step, Qwen (/decide: the screenshot, the elements, the step history, the run's memory, the plan) checks whether the
last step worked, copies facts the task needs into memory, says whether the current part of the plan is finished, and
gives ONE simple next instruction. The instruction becomes an action as cheaply as possible:
  open / type / scroll / back / home / wait  -> directly
  tap "<label>"                              -> the one element with that label
  anything else                              -> MAI-UI on the screenshot, moved onto the nearest element with the label
Finishing a part needs a strict second look first (/verify), over-ruled by measured evidence (the last scroll showed
nothing new, or as many items as the task asks were collected). A run plans once (/plan) and, at the end, Qwen turns its
memory into items (/extract).

Left out, as a collecting run never sends: the send-task checks (typing a list from memory, the final Send tap, invented
list items). Every action is still checked by phone_agent.check before the phone gets it.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import re

from familyos.collect import decide
from familyos.settings import settings

logger = logging.getLogger(__name__)

HISTORY_FOR_QWEN = 10
HISTORY_FOR_MAI_UI = 3
FAIL_LIMIT = 2
REPEATABLE = re.compile(r"^\s*(scroll|swipe|wait|press back|go back)\b", re.I)
CHECKER_LIMIT = 3
CHECKER_REFUSAL = re.compile(r"^checker: part not finished")
STALL_STEPS = 5
MAX_MEMORY = 60
TYPE_STEP = re.compile(r"^\s*(?:type|input|enter|write)\b", re.I)
QUOTED_TEXT = re.compile(r"[\"“]([\s\S]+)[\"”]")
TYPE_NEEDS_TEXT = ("Your type step had no text in double quotes. Give the EXACT text to type in double quotes "
                   "(e.g. type \"orders\").")


class Unavailable(RuntimeError):
    pass


# ── Model server calls ───────────────────────────────────────────────────────────────────────────────────────

async def _post(path: str, body: dict) -> dict:
    import httpx
    try:
        async with decide._model_lock(), httpx.AsyncClient(timeout=settings.collect_model_timeout_s) as client:
            r = await client.post(settings.collect_model_url.rstrip("/") + path, json=body)
    except httpx.TransportError as exc:
        raise Unavailable(f"model server unavailable: {exc}") from exc
    data = r.json() if r.content else {}
    if r.status_code >= 400 or not data.get("success"):
        raise RuntimeError(f"Qwen {path} failed: {(data.get('error') or {}).get('code') or r.status_code} "
                           f"{(data.get('error') or {}).get('message') or ''}".strip())
    return data


async def plan(task: str, apps: list[dict]) -> dict:
    """Qwen's first look: goals and ordered parts; the task as one part when that fails."""
    try:
        body = await _post("/plan", {"task": task, "apps": apps})
        parts = [p for p in body.get("parts") or [] if isinstance(p, dict) and p.get("goal")]
        if parts:
            return {"goals": body.get("goals") or [], "parts": parts, "current": 0, "partStart": 0, "memStart": 0}
    except Unavailable:
        raise
    except Exception as exc:  # noqa: BLE001 -- planning failed: the task is the plan
        logger.info("two_agent: planning failed, using the task as one part: %s", exc)
    return {"goals": [task], "parts": [{"goal": task, "app": "", "done_when": ""}], "current": 0, "partStart": 0, "memStart": 0}


async def _decide(**kw) -> dict:
    body = await _post("/decide", {
        "task": kw["task"], "accessibilityTree": kw["tree"], "screenshotBase64": kw["screenshot"] or "",
        "history": kw["history"], "memory": kw["memory"], "failed": kw["failed"], "currentApp": kw["current_app"] or "",
        "apps": kw["apps"], "note": kw.get("note") or "", "goals": kw["goals"], "plan": kw["plan"], "screenFacts": kw["facts"]})
    return {"done": bool(body.get("done")), "instruction": body.get("instruction") or "", "result": body.get("result") or "",
            "check": body.get("check") or "", "lastOk": body["last_ok"] if isinstance(body.get("last_ok"), bool) else None,
            "partDone": body.get("part_done") is True,
            "remember": [str(f) for f in body.get("remember") or [] if isinstance(f, (str, int, float))]}


async def _verify(**kw) -> dict:
    body = await _post("/verify", {
        "task": kw["task"], "part": kw["part"], "doneWhen": kw.get("done_when") or "", "memory": kw["memory"],
        "partSteps": kw["part_steps"], "screenFacts": kw["facts"], "accessibilityTree": kw["tree"],
        "screenshotBase64": kw["screenshot"] or "", "currentApp": kw["current_app"] or ""})
    return {"complete": body.get("complete") is True, "missing": body.get("missing") or "", "next": body.get("next") or ""}


async def extract(task: str, observations: list[str], schema: dict | None = None) -> object:
    body = await _post("/extract", {"task": task, "observations": observations, **({"schema": schema} if schema else {})})
    return body.get("data")


async def _mai_ui(instruction: str, history: list, obs: dict, apps: list[dict]) -> dict:
    import httpx
    shot = base64.b64decode(obs.get("screenshot") or "")
    if not shot:
        raise RuntimeError("MAI-UI needs a screenshot, and the phone sent none")
    form = {"prompt": instruction, "ui_tree": json.dumps(_plain_tree(obs)), "history": json.dumps(history),
            "current_app": obs.get("currentApp") or "", "apps": json.dumps(apps),
            "screen_width": str(int(obs.get("width") or 0)), "screen_height": str(int(obs.get("height") or 0))}
    try:
        async with decide._model_lock(), httpx.AsyncClient(timeout=settings.collect_model_timeout_s) as client:
            r = await client.post(settings.collect_model_url.rstrip("/") + "/analyze", data=form,
                                  files={"image": ("screen.jpg", shot, "image/jpeg")})
    except httpx.TransportError as exc:
        raise Unavailable(f"model server unavailable: {exc}") from exc
    body = r.json() if r.content else {}
    if r.status_code >= 400 or not body.get("success"):
        raise RuntimeError(f"MAI-UI returned no usable action: {(body.get('error') or {}).get('message') or r.status_code}")
    return body.get("action") or {}


def _plain_tree(obs: dict) -> list[dict]:
    """The tree as the model server reads it; a password field's text is never sent."""
    return [{"text": "" if n.get("password") else (n.get("text") or ""), "contentDescription": n.get("contentDescription") or "",
             "className": n.get("className") or "", "clickable": bool(n.get("clickable")), "scrollable": bool(n.get("scrollable")),
             "bounds": n.get("bounds") or {}} for n in obs.get("tree") or []]


# ── Bookkeeping (orchestrator.js, agent2.js) ─────────────────────────────────────────────────────────────────

def normalize_instruction(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\"'“”‘’.!]", "", str(s or "").lower())).strip()


def fact_key(f: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"^\s*[a-z][a-z ]{0,15}:\s*", "", str(f), flags=re.I).lower())[:40]


def add_to_memory(memory: list[str], facts: list[str]) -> list[str]:
    seen = {fact_key(f) for f in memory}
    added = []
    for fact in facts:
        k = fact_key(fact)
        if not k or k in seen or len(memory) >= MAX_MEMORY:
            continue
        memory.append(str(fact)[:500])
        seen.add(k)
        added.append(fact)
    return added


def plan_lines(p: dict, current: int) -> list[str]:
    out = []
    for i, part in enumerate(p.get("parts") or []):
        mark = "✓" if i < current else "▶" if i == current else "○"
        app = f" [{part['app']}]" if part.get("app") else ""
        when = f" — done when {part['done_when']}" if part.get("done_when") else ""
        out.append(f"{mark} {i + 1}. {part['goal']}{app}{when}")
    return out


def count_asked(*texts: str) -> int | None:
    for t in texts:
        m = (re.search(r"\b(?:last|latest|recent|newest|top|first)\s+(\d{1,3})\b", t or "", re.I)
             or re.search(r"\b(\d{1,3})\s+(?:most\s+)?(?:recent|latest|newest|last)\b", t or "", re.I))
        if m:
            return int(m.group(1))
    return None


def describe_action(a: dict | None) -> str:
    if not isinstance(a, dict):
        return ""
    kind = a.get("action")
    if kind == "tap":
        d = (a.get("target") or {}).get("description")
        return f'tapped "{d}"' if d else "tapped"
    return {"long_press": "long-pressed", "type": f'typed "{a.get("text")}"', "swipe": f"swiped {a.get('direction')}",
            "launch_app": f"opened {a.get('package')}", "press_back": "pressed back", "press_home": "pressed home",
            "wait": "waited", "done": "done"}.get(kind, kind or "")


def history_lines(steps: list[dict]) -> list[str]:
    out = []
    for s in steps[-HISTORY_FOR_QWEN:]:
        mark = " ✓" if s.get("ok") is True else " ✗" if s.get("ok") is False else ""
        did = describe_action(s.get("action"))
        reason, instr = s.get("reason") or "", s.get("instruction") or ""
        why = f" ({reason.splitlines()[0][:120]})" if reason and instr and reason != instr else ""
        out.append(f"{instr.splitlines()[0]} -> {did}{why}{mark}" if instr else f"{did}{mark}")
    return out


def failed_instructions(steps: list[dict]) -> dict[str, dict]:
    failed: dict[str, dict] = {}
    for s in steps:
        instr = s.get("instruction") or ""
        if s.get("ok") is not False or not instr or REPEATABLE.search(instr):
            continue
        entry = failed.setdefault(normalize_instruction(instr), {"text": instr, "count": 0})
        entry["count"] += 1
    return failed


def resolve_open_app(instruction: str, apps: list[dict]) -> str | None:
    m = re.match(r"^\s*(?:open|launch|go to|start)\s+(?:the\s+)?(.+?)(?:\s+app)?\s*$", instruction or "", re.I)
    if not m:
        return None
    want = m.group(1).strip().lower()
    for a in apps or []:
        label = (a.get("label") or "").strip().lower()
        if label and (label == want or (len(label) >= 3 and (label in want or want in label))):
            return a.get("package")
    return None


def resolve_direct_action(instruction: str) -> dict | None:
    t = re.sub(r"[.!]+$", "", str(instruction or "").strip())
    m = re.match(r"^(?:type|input)\s+([\s\S]+)$", t, re.I)
    if m:
        text = re.sub(r"^([\"'])([\s\S]*)\1$", r"\2", m.group(1).strip()).replace("\\n", "\n").strip()
        return {"action": "type", "text": text} if text else None
    if re.match(r"^(?:press|tap|go|navigate|hit)?\s*back$", t, re.I) or re.search(r"\bgo back\b", t, re.I):
        return {"action": "press_back"}
    if re.match(r"^(?:press|tap|go)?\s*home$", t, re.I) or re.search(r"\bgo home\b", t, re.I):
        return {"action": "press_home"}
    if re.match(r"^wait\b", t, re.I):
        return {"action": "wait"}
    m = re.search(r"\bscroll\s+(up|down|left|right)\b", t, re.I)
    if m:                                       # "scroll down" shows what is below: a finger swipe UP
        return {"action": "swipe", "direction": {"down": "up", "up": "down"}.get(m.group(1).lower(), m.group(1).lower())}
    m = re.search(r"\bswipe\s+(up|down|left|right)\b", t, re.I)
    if m:
        return {"action": "swipe", "direction": m.group(1).lower()}
    return None


# ── Grounding (grounding.js) and screen facts (screen.js) ─────────────────────────────────────────────────────

ANDROID_INPUT = re.compile(r"^(EditText|AutoCompleteTextView|SearchView|SearchAutoComplete)$")
TAP_VERB = re.compile(r"^\s*(?:tap|click|press|select|choose|open|long[\s-]?press)\s+(?:on\s+)?(?:the\s+)?", re.I)
MAX_SNAP_DISTANCE = 0.15


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _box(n: dict) -> list[int] | None:
    b = n.get("bounds") or {}
    vals = [b.get("left"), b.get("top"), b.get("right"), b.get("bottom")]
    return vals if all(isinstance(v, (int, float)) for v in vals) else None


def _contains(o: list, i: list) -> bool:
    return o[0] <= i[0] and o[1] <= i[1] and o[2] >= i[2] and o[3] >= i[3]


def label_from_instruction(instruction: str) -> tuple[str, bool] | None:
    s = str(instruction or "")
    q = re.search(r"[\"“]([^\"”]{1,120})[\"”]", s) or re.search(r"(?:^|[\s(])['‘]([^'’]{1,120})['’](?=$|[\s,.;:)!?])", s)
    if q:
        return q.group(1).strip(), True
    if not TAP_VERB.search(s):
        return None
    rest = re.sub(r"\s+(?:button|tab|icon|link|option)$", "", re.sub(r"[.!]+$", "", TAP_VERB.sub("", s, count=1)), flags=re.I).strip()
    if not rest or len(rest.split()) > 4:
        return None
    return rest, False


def find_label_targets(label: str, quoted: bool, tree: list[dict], w: int, h: int) -> list[dict]:
    want = _norm(label)
    if not want:
        return []

    def visible(b):
        return b and b[2] > b[0] and b[3] > b[1] and b[2] > 0 and b[3] > 0 and (not w or b[0] < w) and (not h or b[1] < h)
    nodes = [n for n in tree if visible(_box(n)) and not ANDROID_INPUT.match(n.get("className") or "")]
    labels = lambda n: [x for x in (_norm(n.get("text")), _norm(n.get("contentDescription"))) if x]  # noqa: E731
    named = [n for n in nodes if want in labels(n)]
    if not named and quoted and len(want) >= 12:
        named = [n for n in nodes if any(lb.startswith(want) or (len(lb) >= 12 and want.startswith(lb)) for lb in labels(n))]
    boxes = [_box(n) for n in named]
    return [n for i, n in enumerate(named)
            if not any(j != i and _contains(o, boxes[i]) and (not _contains(boxes[i], o) or j < i) for j, o in enumerate(boxes))]


def center_point(n: dict, w: int, h: int) -> dict:
    b = _box(n)
    return {"x": round((max(b[0], 0) + min(b[2], w)) / 2 / w, 4), "y": round((max(b[1], 0) + min(b[3], h)) / 2 / h, 4)}


def tap_by_label(instruction: str, tree: list[dict], w: int, h: int) -> tuple[dict | None, list[dict]]:
    named = label_from_instruction(instruction)
    if not named or not w or not h:
        return None, []
    targets = find_label_targets(named[0], named[1], tree, w, h)
    if len(targets) != 1:
        return None, targets
    kind = "long_press" if re.match(r"^\s*long[\s-]?press\b", instruction, re.I) else "tap"
    return {"action": kind, "target": {"description": named[0], "point": center_point(targets[0], w, h)}}, targets


def snap_to_nearest(action: dict, targets: list[dict], w: int, h: int) -> tuple[dict, bool]:
    point = (action.get("target") or {}).get("point") if action.get("action") in ("tap", "long_press") else None
    if not point or not targets or not w or not h:
        return action, False
    px, py = point["x"] * w, point["y"] * h
    if any(b[0] <= px <= b[2] and b[1] <= py <= b[3] for b in (_box(n) for n in targets)):
        return action, False
    best = min(((center_point(n, w, h), ) for n in targets), key=lambda c: math.hypot(c[0]["x"] * w - px, c[0]["y"] * h - py))[0]
    if math.hypot(best["x"] * w - px, best["y"] * h - py) > MAX_SNAP_DISTANCE * h:
        return action, False
    return {**action, "target": {**action["target"], "point": best}}, True


def screen_labels(tree: list[dict]) -> list[str]:
    return [lb for lb in ((n.get("text") or n.get("contentDescription") or "").strip() for n in tree or []) if lb]


def label_similarity(a: list[str], b: list[str]) -> float:
    if not a and not b:
        return 1.0
    counts: dict[str, int] = {}
    for x in a:
        counts[x] = counts.get(x, 0) + 1
    common = 0
    for x in b:
        if counts.get(x):
            common += 1
            counts[x] -= 1
    return common / max(len(a), len(b))


def _last_scroll(steps: list[dict], part_start: int, tree: list[dict]) -> tuple[int, bool]:
    part = steps[part_start:]
    scrolls = [i for i, s in enumerate(part) if (s.get("action") or {}).get("action") == "swipe"
               and (s.get("action") or {}).get("direction") in ("up", "down")]
    if not scrolls:
        return 0, False
    i = scrolls[-1]
    after = part[i + 1]["tree"] if i + 1 < len(part) else tree
    return len(scrolls), label_similarity(screen_labels(part[i].get("tree") or []), screen_labels(after)) >= 0.9


def list_end_reached(steps: list[dict], part_start: int, tree: list[dict]) -> bool:
    return _last_scroll(steps, part_start, tree)[1]


def screen_facts(steps: list[dict], part_start: int, tree: list[dict]) -> list[str]:
    facts = ["A scrollable list/area is on screen." if any(n.get("scrollable") for n in tree) else "Nothing on this screen is scrollable."]
    count, same = _last_scroll(steps, part_start, tree)
    if not count:
        facts.append("You have not scrolled yet in this part — more items may be further down."
                     if any(n.get("scrollable") for n in tree) else "You have not scrolled in this part.")
        return facts
    facts.append(f"You scrolled {count} time{'s' if count > 1 else ''} in this part; "
                 + ("the last scroll did NOT change the screen — the end of the list was reached." if same
                    else "the last scroll showed new items, so there may be more below."))
    return facts


# ── One step (decideTwoAgent) ────────────────────────────────────────────────────────────────────────────────

async def step(state: dict, obs: dict) -> dict:
    """The next action for one screen. `state` = {goal, steps, memory, plan, apps, own_app}; returns
    {action, instruction, reason, ok, lastOk, remember, planCurrent, partStart, stop}."""
    goal, steps, memory, p, apps = state["goal"], state["steps"], state["memory"], state["plan"], state["apps"]
    tree, current_app = obs.get("tree") or [], obs.get("currentApp") or ""
    w, h = int(obs.get("width") or 0), int(obs.get("height") or 0)
    parts = p.get("parts") or []
    current = min(p.get("current", 0), len(parts))
    start_part, part_start, mem_start = current, p.get("partStart", 0), p.get("memStart", 0)
    facts = screen_facts(steps, part_start, tree)
    checker_note, confirmed_done = "", False
    failed = [f"{f['text']} (failed {f['count']} times)" for f in failed_instructions(steps).values() if f["count"] >= FAIL_LIMIT]

    async def ask(note: str | None = None) -> dict:
        return await _decide(task=goal, tree=_plain_tree(obs), screenshot=obs.get("screenshot"), history=history_lines(steps),
                             memory=memory, failed=failed, current_app=current_app, apps=apps, note=note,
                             goals=p.get("goals") or [], plan=plan_lines(p, current), facts=facts)

    def keep_answer(d: dict) -> None:
        if d["done"] and d["result"] and not re.match(r"^\s*need:", d["result"], re.I) and not d["remember"]:
            d["remember"] = [d["result"]]

    def advance(d: dict) -> None:
        nonlocal current
        if d["partDone"] and current == start_part and current < len(parts):
            current += 1

    async def reask(d: dict, note: str) -> dict:
        nd = await ask(note)
        keep_answer(nd)
        nd["remember"] = [*d.get("remember", []), *nd["remember"]]
        advance(nd)
        return nd

    recent = steps[part_start:][-STALL_STEPS:]
    stalled = bool(memory) and len(recent) == STALL_STEPS and all(s.get("memoryCount") == len(memory) for s in recent)
    d = await ask(f"The last {STALL_STEPS} steps collected nothing new and MEMORY already holds {len(memory)} items. If MEMORY "
                  "covers what the ▶ current part needs, set part_done (or done). Otherwise do something different — e.g. read "
                  "the list already on screen and keep the items whose dates fit; don't keep re-filtering." if stalled else None)
    keep_answer(d)

    refusals = sum(1 for s in steps[part_start:] if CHECKER_REFUSAL.match(s.get("reason") or ""))
    finishing = (d["partDone"] or d["done"]) and not re.match(r"^\s*need:", d["result"], re.I)
    if finishing and refusals < CHECKER_LIMIT:
        part = parts[current] if current < len(parts) else {"goal": goal, "done_when": ""}
        check = None
        try:
            check = await _verify(task=goal, part=part["goal"], done_when=part.get("done_when"), memory=[*memory, *d["remember"]],
                                  part_steps=[f"{(s.get('instruction') or '').splitlines()[0] if s.get('instruction') else ''} -> "
                                              f"{describe_action(s.get('action'))}" for s in steps[part_start:]],
                                  facts=facts, tree=_plain_tree(obs), screenshot=obs.get("screenshot"), current_app=current_app)
        except Unavailable:
            raise
        except Exception as exc:  # noqa: BLE001 -- the checker failed: go by the planner
            logger.info("two_agent: verify failed, going by the planner: %s", exc)
        if check and not check["complete"] and list_end_reached(steps, part_start, tree):
            check = None
        asked = count_asked(part["goal"], goal)
        if check and not check["complete"] and asked:
            known = {f.lower().strip() for f in memory}
            fresh = len([f for f in d["remember"] if f.lower().strip() not in known])
            if len(memory) - mem_start + fresh >= asked:
                check = None
        confirmed_done = check is None or check["complete"]
        if check and not check["complete"]:
            checker_note = f"checker: part not finished — {check['missing'] or 'something is missing'}"
            hint = f" (it suggests: {check['next']})" if check["next"] else ""
            d = await reask(d, f"A strict check says the current part is NOT finished: {check['missing'] or 'something is missing'}"
                               f"{hint}. Continue the current part with one "
                               "real step. Ads, sponsored and recommended items are never part of the data.")
            d = {**d, "done": False, "partDone": False}
    advance(d)

    if d["done"] and not re.match(r"^\s*need:", d["result"], re.I):
        open_parts = parts[current + 1:]
        if open_parts and current == start_part:
            current += 1
        if open_parts:
            d = await reask(d, f"You said the task is done, but these parts are not finished: "
                               f"{'; '.join(x['goal'] for x in open_parts)}. Continue with the ▶ current part.")

    if not d["done"] and current_app and resolve_open_app(d["instruction"], apps) == current_app:
        name = next((a.get("label") for a in apps if a.get("package") == current_app), current_app)
        d = await reask(d, f'You are already in {name} — "open {name}" does nothing (the app resumes on this same page). '
                           "Move within the app instead: press back, or tap what leads to what you need.")
        if not d["done"] and resolve_open_app(d["instruction"], apps) == current_app:
            d = {**d, "instruction": "press back"}

    if not d["done"] and parts and current >= len(parts) and (start_part >= len(parts) or confirmed_done):
        d = await reask(d, "Every part of the plan is finished. Reply done now, with the result (list the data the task asked for).")
        if not d["done"]:
            d = {**d, "done": True, "result": "Finished. Collected:\n" + "\n".join(f"{i + 1}. {f}" for i, f in enumerate(memory))
                 if memory else "Task finished."}

    if not d["done"] and TYPE_STEP.match(d["instruction"]) and not QUOTED_TEXT.search(d["instruction"]):
        d = await reask(d, TYPE_NEEDS_TEXT)
        if not d["done"] and TYPE_STEP.match(d["instruction"]) and not QUOTED_TEXT.search(d["instruction"]):
            d = {**d, "instruction": "wait"}

    verdict = {"check": d["check"], "lastOk": d["lastOk"], "remember": d["remember"], "planCurrent": current,
               "partStart": len(steps) if current != start_part else part_start}
    if d["done"]:
        result = d["result"] or "Task finished."
        return {**verdict, "action": {"action": "done", "result": result}, "reason": result, "instruction": ""}

    instruction = d["instruction"]
    prev = steps[-1] if steps else None
    judged = [*steps[:-1], {**prev, "ok": d["lastOk"]}] if prev and prev.get("ok") is None and d["lastOk"] is not None else steps
    again = failed_instructions(judged).get(normalize_instruction(instruction))
    if again and again["count"] >= FAIL_LIMIT:
        return {**verdict, "action": {"action": "wait"}, "reason": instruction, "instruction": instruction,
                "stop": f'"{again["text"]}" didn\'t work {again["count"]} times and the planner tried it again.'}
    base = {**verdict, "reason": checker_note or instruction, "instruction": instruction}

    launch = resolve_open_app(instruction, apps)
    if current_app == state.get("own_app") and not launch and not re.match(r"^\s*(?:press|go)\s+home\b", instruction, re.I):
        target = state.get("package")
        return {**base, "action": {"action": "launch_app", "package": target} if target else {"action": "press_home"}}
    if launch:
        return {**base, "action": {"action": "launch_app", "package": launch}}
    direct = resolve_direct_action(instruction)
    if direct:
        return {**base, "action": direct}

    action, targets = tap_by_label(instruction, tree, w, h)
    if action:
        return {**base, "action": action}

    try:
        action = await _mai_ui(instruction, [{**s["action"], "reason": s.get("instruction") or s.get("reason")}
                                             for s in steps[-HISTORY_FOR_MAI_UI:] if s.get("action")], obs, apps)
    except Unavailable:
        raise
    except Exception as exc:  # noqa: BLE001 -- one unusable answer is a failed step, not a failed run
        return {**base, "action": {"action": "wait"}, "reason": f'could not do "{instruction}": {str(exc)[:120]}', "ok": False}
    if action.get("action") == "done":
        return {**base, "action": {"action": "wait"}, "reason": f'could not do "{instruction}" (the UI model answered instead of acting)', "ok": False}
    if re.match(r"^\s*(?:tap|click|long[\s-]?press)\b", instruction, re.I) and action.get("action") in ("press_back", "press_home"):
        return {**base, "action": {"action": "wait"}, "reason": f'could not find "{instruction}" on screen', "ok": False}
    action, _ = snap_to_nearest(action, targets, w, h)
    return {**base, "action": action}
