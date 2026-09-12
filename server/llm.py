"""LLM access for Aegis OTM.

Every model call in the project goes through llm_call(). That matters for
two reasons: swapping providers is a one-line change if credits or the
network fail, and MOCK=1 makes the whole agent layer run deterministically
with no API at all - which is what you rehearse and demo on.

Design rule worth stating to judges: the model never does arithmetic. It
decides which tool to call and writes the explanations. Every number in
the system comes from the verified Python in screen.py, probability.py
and maneuver.py.

Setup:
    pip install google-genai python-dotenv
    server/.env  ->  GEMINI_API_KEY=...

Run directly to self-test:  python llm.py
"""

import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
# Gemini deprecates model names fairly often and the API returns a 404
# naming the replacement. Override with LLM_MODEL in .env rather than
# editing this line.
MODEL = os.getenv("LLM_MODEL", "gemini-3.6-flash")
MOCK = os.getenv("MOCK_AGENTS", "0") == "1"

MAX_ROUNDS = 6            # tool-use round trips before we stop
_client = None
_call_count = 0


class LLMError(Exception):
    pass


# ------------------------------------------------------------- the client

def client():
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY not set - put it in server/.env, "
                           "or run with MOCK_AGENTS=1")
        from google import genai
        _client = genai.Client(api_key=key)
    return _client


def available():
    """True if we could make a real call right now."""
    if MOCK:
        return False
    if not os.getenv("GEMINI_API_KEY"):
        return False
    try:
        import google.genai  # noqa: F401
        return True
    except ImportError:
        return False


def call_count():
    return _call_count


# --------------------------------------------------------- tool plumbing

def to_gemini_tools(tool_schemas):
    """Convert our tool schemas into Gemini function declarations.

    Our schemas use the same {name, description, input_schema} shape as
    most providers, so this is the only provider-specific glue.
    """
    from google.genai import types
    decls = []
    for t in tool_schemas:
        decls.append(types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters_json_schema=t["input_schema"],
        ))
    return [types.Tool(function_declarations=decls)]


def llm_call(system, messages, tool_schemas=None, dispatch=None,
             max_rounds=MAX_ROUNDS, on_event=None):
    """Run a conversation, executing tool calls until the model stops.

    system        - system instruction string
    messages      - list of {"role": "user"|"model", "text": str}
    tool_schemas  - list of {name, description, input_schema}
    dispatch      - callable(name, args) -> dict, runs the actual tool
    on_event      - optional callable(dict) for streaming tool activity

    Returns {"text": str, "tool_calls": [...], "rounds": int}.
    """
    global _call_count

    if MOCK or not available():
        return mock_call(system, messages, tool_schemas, dispatch, on_event)

    from google.genai import types

    cfg = {"system_instruction": system}
    if tool_schemas:
        cfg["tools"] = to_gemini_tools(tool_schemas)
        # We dispatch tools ourselves so every call can be logged to the
        # event stream. The SDK's automatic mode would hide them.
        cfg["automatic_function_calling"] = \
            types.AutomaticFunctionCallingConfig(disable=True)

    contents = []
    for m in messages:
        contents.append(types.Content(
            role=m.get("role", "user"),
            parts=[types.Part.from_text(text=m["text"])]))

    all_calls = []
    rounds = 0

    for rounds in range(1, max_rounds + 1):
        _call_count += 1
        try:
            resp = client().models.generate_content(
                model=MODEL, contents=contents,
                config=types.GenerateContentConfig(**cfg))
        except Exception as e:
            msg = str(e)
            if "no longer available" in msg or "NOT_FOUND" in msg:
                raise LLMError(
                    f"model '{MODEL}' was rejected. The API usually names "
                    f"its replacement in the message below - set LLM_MODEL "
                    f"in server/.env to that name.\n  {msg}")
            raise LLMError(f"{type(e).__name__}: {e}")

        calls = resp.function_calls or []
        if not calls:
            return {"text": resp.text or "", "tool_calls": all_calls,
                    "rounds": rounds}

        # Echo the model's tool-call turn back into the transcript.
        contents.append(resp.candidates[0].content)

        parts = []
        for fc in calls:
            args = dict(fc.args or {})
            if on_event:
                on_event({"type": "tool_call", "name": fc.name, "args": args})

            if dispatch is None:
                result = {"error": "no dispatch function provided"}
            else:
                try:
                    result = dispatch(fc.name, args)
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}

            all_calls.append({"name": fc.name, "args": args,
                              "result": result})
            if on_event:
                on_event({"type": "tool_result", "name": fc.name,
                          "result": result})

            parts.append(types.Part.from_function_response(
                name=fc.name, response={"result": result}))

        contents.append(types.Content(role="user", parts=parts))

    return {"text": "stopped: tool-call round limit reached",
            "tool_calls": all_calls, "rounds": rounds}


# ------------------------------------------------------------------- mock

MOCK_REPLIES = {
    "TRACKER": "Catalog is current. {n} objects loaded, median tracking "
               "data age under 12 hours. No anomalies.",
    "SCREENER": "Screened the asset against the full catalog. The closest "
                "approach is the top-ranked conjunction; all others are "
                "further out and lower risk.",
    "PLANNER": "Evaluated the burn grid. The recommended option is the "
               "cheapest burn that increases separation while keeping "
               "collision probability under the target.",
    "COORDINATOR": "The secondary object is non-maneuverable debris, so no "
                   "negotiation is required. Publishing the manoeuvre "
                   "intent to the shared ledger.",
}


def mock_call(system, messages, tool_schemas=None, dispatch=None,
              on_event=None):
    """Deterministic stand-in. Calls the first available tool once so the
    event stream and the orchestrator behave identically to a real run."""
    agent = "UNKNOWN"
    for name in MOCK_REPLIES:
        if name in (system or "").upper():
            agent = name
            break

    all_calls = []
    if tool_schemas and dispatch:
        t = tool_schemas[0]
        args = mock_args(t["input_schema"])
        if on_event:
            on_event({"type": "tool_call", "name": t["name"], "args": args})
        try:
            result = dispatch(t["name"], args)
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {e}"}
        all_calls.append({"name": t["name"], "args": args, "result": result})
        if on_event:
            on_event({"type": "tool_result", "name": t["name"],
                      "result": result})

    text = MOCK_REPLIES.get(agent, "Mock response.")
    if "{n}" in text:
        text = text.replace("{n}", "19232")
    return {"text": text, "tool_calls": all_calls, "rounds": 1, "mock": True}


def mock_args(schema):
    """Plausible arguments from a JSON schema, for the mock path.

    Guesses from the field name so the event feed reads sensibly rather
    than showing a CDM id in a field called 'group'.
    """
    out = {}
    props = (schema or {}).get("properties", {})
    for name in (schema or {}).get("required", []):
        spec = props.get(name, {})
        low = name.lower()

        if "default" in spec:
            out[name] = spec["default"]
        elif spec.get("enum"):
            out[name] = spec["enum"][0]
        elif spec.get("type") == "number":
            out[name] = 50.0 if "km" in low else 1.0
        elif spec.get("type") == "integer":
            out[name] = 72 if "hour" in low else 1
        elif spec.get("type") == "boolean":
            out[name] = False
        elif "cdm" in low or low.endswith("_id") or low == "id":
            out[name] = "CDM-0001"
        elif "norad" in low or "asset" in low:
            out[name] = "25544"
        else:
            out[name] = "all"
    return out


if __name__ == "__main__":
    print(f"provider  : {PROVIDER}")
    print(f"model     : {MODEL}")
    print(f"mock mode : {MOCK}")
    print(f"available : {available()}")

    if not available():
        print("\nNo key or SDK, so running the mock path.")
        print("  pip install google-genai python-dotenv")
        print("  echo GEMINI_API_KEY=... > .env")

    # A toy tool so the round trip is visible end to end.
    tools = [{
        "name": "get_object_count",
        "description": "Return how many objects are in the tracked catalog.",
        "input_schema": {
            "type": "object",
            "properties": {
                "group": {"type": "string",
                          "description": "Catalog group, or 'all'."},
            },
            "required": ["group"],
        },
    }]

    def dispatch(name, args):
        if name == "get_object_count":
            return {"count": 19232, "group": args.get("group", "all")}
        return {"error": f"unknown tool {name}"}

    events = []
    try:
        out = llm_call(
            system="You are TRACKER, an agent that monitors space object "
                   "catalog health. Use the tools available. Never do "
                   "arithmetic yourself. Answer in one sentence.",
            messages=[{"role": "user",
                       "text": "How many objects are we tracking?"}],
            tool_schemas=tools,
            dispatch=dispatch,
            on_event=events.append,
        )
    except LLMError as e:
        print(f"\nLLM call failed:\n  {e}")
        print("\nThe mock path still works, so nothing is blocked:")
        print("  $env:MOCK_AGENTS = \"1\"")
        raise SystemExit(1)

    print(f"\nrounds     : {out['rounds']}")
    print(f"tool calls : {len(out['tool_calls'])}")
    for c in out["tool_calls"]:
        print(f"  {c['name']}({json.dumps(c['args'])}) -> "
              f"{json.dumps(c['result'])}")
    print(f"\nreply:\n  {out['text']}")
    print(f"\napi calls made: {call_count()}")