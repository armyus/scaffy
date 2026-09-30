"""Quick smoke tests for the JSON parser and session cache."""
import json
import re
import sys

# ── Inline the two helper functions ────────────────────────────────
def _normalise_keys(d):
    return {
        "concept": str(d.get("concept", "Concept Overview")).strip(),
        "analogy": str(d.get("analogy", "")).strip(),
        "example": str(d.get("example", "")).strip(),
        "code":    str(d.get("code", "")).strip(),
    }

def _parse_llm_json(raw):
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return _normalise_keys(parsed)
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not match:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return _normalise_keys(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    result = {}
    for key in ("concept", "analogy", "example", "code"):
        pat = rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"'
        m = re.search(pat, raw, re.DOTALL)
        if m:
            result[key] = m.group(1).replace('\\"', '"').replace("\\n", "\n")
    if result:
        return _normalise_keys(result)

    return {
        "concept": "Concept Overview",
        "analogy": raw.strip() or "(no output)",
        "example": "",
        "code": "",
    }


# ── Session cache helpers ──────────────────────────────────────────
session_history = []

def _find_cached(snippet):
    snippet_lower = snippet.lower().strip()
    for entry in reversed(session_history):
        cached_lower = entry["snippet"].lower().strip()
        if snippet_lower == cached_lower:
            return entry["result"]
        shorter, longer = sorted([snippet_lower, cached_lower], key=len)
        if shorter and shorter in longer and len(shorter) >= 0.6 * len(longer):
            return entry["result"]
    return None


# ═══════════════════════════════════════════════════════════════════
#  TESTS
# ═══════════════════════════════════════════════════════════════════

passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


print("=== Parser Tests ===")

# 1. Clean JSON
r = _parse_llm_json('{"concept":"Attention","analogy":"Library lookup","example":"Q@K","code":"x=1"}')
check("Clean JSON - concept", r["concept"] == "Attention")
check("Clean JSON - has all keys", all(k in r for k in ("concept","analogy","example","code")))

# 2. JSON surrounded by text
r = _parse_llm_json('Here is my answer:\n{"concept":"ReLU","analogy":"Gate","example":"max(0,x)","code":"f=max(0,x)"}\nDone.')
check("Surrounded JSON - concept", r["concept"] == "ReLU")

# 3. Total garbage → fallback
r = _parse_llm_json("I cannot help with that.")
check("Garbage fallback - concept default", r["concept"] == "Concept Overview")
check("Garbage fallback - raw in analogy", "cannot" in r["analogy"])

# 4. Empty string
r = _parse_llm_json("")
check("Empty input - analogy fallback", r["analogy"] == "(no output)")

# 5. Partial key extraction (last-resort regex)
raw = 'blah "concept": "Softmax", and "analogy": "Probability distributor" blah'
r = _parse_llm_json(raw)
check("Regex key extraction - concept", r["concept"] == "Softmax")
check("Regex key extraction - analogy", r["analogy"] == "Probability distributor")


print("\n=== Cache Tests ===")

# Exact match
session_history.clear()
session_history.append({"snippet": "Hello world", "result": {"concept": "cached"}})
check("Exact match cache hit", _find_cached("Hello world") is not None)
check("Exact match case insensitive", _find_cached("hello WORLD") is not None)

# Substring match (>= 60%)
session_history.clear()
session_history.append({"snippet": "The softmax function normalizes inputs", "result": {"concept": "softmax"}})
check("Substring cache hit", _find_cached("softmax function normalizes") is not None)

# No match
check("No cache for unrelated", _find_cached("quantum entanglement basics") is None)


print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
