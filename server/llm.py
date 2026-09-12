"""LLM access for Aegis OTM.

<<<<<<< HEAD
Every model call in the project goes through llm_call(). That gives us
three things: swapping providers is one line of config, a failing
provider falls through to the next instead of killing the pipeline, and
MOCK=1 runs the whole agent layer deterministically with no model at all.

Providers:
  ollama  - local, unlimited, free. qwen3:8b on 8 GB of VRAM.
  gemini  - free tier, better reasoning, 20 requests per day per model.
  mock    - canned responses, no model. What you develop against.

Config in server/.env:
    LLM_PROVIDER=ollama
    LLM_MODEL=qwen3:8b
    OLLAMA_BASE_URL=http://localhost:11434/v1
    GEMINI_API_KEY=...
    GEMINI_MODEL=gemini-3.6-flash
    LLM_FALLBACK=gemini,mock
    MOCK_AGENTS=0

Design rule worth stating to judges: the model never does arithmetic. It
decides which tool to call and writes the explanation. Every number in
the system comes from the verified Python in screen.py, probability.py
and maneuver.py.

Run directly to self-test:  python llm.py
                            python llm.py ollama
                            python llm.py gemini
=======
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
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
"""

import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

<<<<<<< HEAD
PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
MOCK = os.getenv("MOCK_AGENTS", "0") == "1"

OLLAMA_MODEL = os.getenv("LLM_MODEL", "qwen3:8b")
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Tried in order when the primary provider errors. Ending in mock means
# the pipeline always completes, which matters mid-demo.
FALLBACK = [p.strip() for p in
            os.getenv("LLM_FALLBACK", "gemini,mock").split(",") if p.strip()]

MAX_ROUNDS = 6
_clients = {}
_call_count = 0
_last_provider = None
=======
PROVIDER = (os.getenv("LLM_PROVIDER") or "gemini").strip().lower()
if PROVIDER == "ollama":
    MODEL = (os.getenv("LLM_MODEL") or "llama3.1:8b").strip()
elif PROVIDER == "groq":
    MODEL = (os.getenv("LLM_MODEL") or "llama-3.3-70b-versatile").strip()
else:
    MODEL = (os.getenv("LLM_MODEL") or "gemini-3.5-flash").strip()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

MOCK = os.getenv("MOCK_AGENTS", "0") == "1"

MAX_ROUNDS = 6            # tool-use round trips before we stop
_client = None
_call_count = 0
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)


class LLMError(Exception):
    pass


<<<<<<< HEAD
def model_for(provider):
    return {"ollama": OLLAMA_MODEL, "gemini": GEMINI_MODEL,
            "mock": "mock"}.get(provider, provider)


# Kept as a module attribute because app.py and agents.py report it.
MODEL = model_for(PROVIDER)


def call_count():
    return _call_count


def last_provider():
    return _last_provider


# ------------------------------------------------------------- availability

def available(provider=None):
    provider = provider or PROVIDER
    if MOCK or provider == "mock":
        return provider == "mock"

    if provider == "ollama":
        try:
            import httpx
            from openai import OpenAI  # noqa: F401
            base = OLLAMA_BASE.rsplit("/v1", 1)[0]
            r = httpx.get(f"{base}/api/tags", timeout=2.0)
            names = [m["name"] for m in r.json().get("models", [])]
            return OLLAMA_MODEL in names
        except Exception:
            return False

    if provider == "gemini":
=======
# ------------------------------------------------------------- the client

def client():
    global _client
    if _client is None:
        if PROVIDER == "ollama":
            import groq
            _client = groq.Groq(base_url=OLLAMA_BASE_URL, api_key="ollama")
        elif PROVIDER == "groq":
            key = os.getenv("GROQ_API_KEY")
            if not key:
                raise LLMError("GROQ_API_KEY not set - put it in server/.env, "
                               "or run with MOCK_AGENTS=1")
            import groq
            _client = groq.Groq(api_key=key)
        else:
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
    if PROVIDER == "ollama":
        try:
            import groq  # noqa: F401
            return True
        except ImportError:
            return False
    elif PROVIDER == "groq":
        if not os.getenv("GROQ_API_KEY"):
            return False
        try:
            import groq  # noqa: F401
            return True
        except ImportError:
            return False
    else:
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
        if not os.getenv("GEMINI_API_KEY"):
            return False
        try:
            import google.genai  # noqa: F401
            return True
        except ImportError:
            return False

<<<<<<< HEAD
    return False


def providers_status():
    """What is reachable right now. Shown by /api/agents/status."""
    return {
        "configured": PROVIDER,
        "mock_forced": MOCK,
        "ollama": {"model": OLLAMA_MODEL, "available": available("ollama")},
        "gemini": {"model": GEMINI_MODEL, "available": available("gemini")},
        "fallback_chain": FALLBACK,
        "calls_made": _call_count,
        "last_used": _last_provider,
    }


# ---------------------------------------------------------------- ollama

def ollama_client():
    if "ollama" not in _clients:
        from openai import OpenAI
        # Ollama ignores the key but the client insists on one.
        _clients["ollama"] = OpenAI(base_url=OLLAMA_BASE, api_key="ollama")
    return _clients["ollama"]


def to_openai_tools(tool_schemas):
    return [{"type": "function",
             "function": {"name": t["name"],
                          "description": t["description"],
                          "parameters": t["input_schema"]}}
            for t in tool_schemas]


def strip_thinking(text):
    """Remove qwen3's <think> blocks.

    Qwen3 is a reasoning model and emits its chain of thought before the
    answer. Unstripped, a paragraph of internal monologue lands in the
    live agent feed.
    """
    if not text:
        return ""
    while "<think>" in text and "</think>" in text:
        head, rest = text.split("<think>", 1)
        _, tail = rest.split("</think>", 1)
        text = head + tail
    return text.strip()


def call_ollama(system, messages, tool_schemas, dispatch, max_rounds,
                on_event):
    global _call_count

    # /no_think keeps qwen3 from spending its budget on reasoning we then
    # throw away. Agent turns here are short and tool-driven.
    msgs = [{"role": "system", "content": system + "\n\n/no_think"}]
    for m in messages:
        role = "assistant" if m.get("role") == "model" else "user"
        msgs.append({"role": role, "content": m["text"]})

    kwargs = {"model": OLLAMA_MODEL, "messages": msgs}
    if tool_schemas:
        kwargs["tools"] = to_openai_tools(tool_schemas)

    all_calls = []
    for rounds in range(1, max_rounds + 1):
        _call_count += 1
        try:
            resp = ollama_client().chat.completions.create(**kwargs)
        except Exception as e:
            raise LLMError(f"ollama: {type(e).__name__}: {e}")

        msg = resp.choices[0].message
        calls = msg.tool_calls or []

        if not calls:
            return {"text": strip_thinking(msg.content),
                    "tool_calls": all_calls, "rounds": rounds,
                    "provider": "ollama"}

        msgs.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name,
                                         "arguments": c.function.arguments}}
                           for c in calls],
        })

        for c in calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if on_event:
                on_event({"type": "tool_call", "name": c.function.name,
                          "args": args})

            if dispatch is None:
                result = {"error": "no dispatch function provided"}
            else:
                try:
                    result = dispatch(c.function.name, args)
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}

            all_calls.append({"name": c.function.name, "args": args,
                              "result": result})
            if on_event:
                on_event({"type": "tool_result", "name": c.function.name,
                          "result": result})

            msgs.append({"role": "tool", "tool_call_id": c.id,
                         "content": json.dumps(result, default=str)})

        kwargs["messages"] = msgs

    return {"text": "stopped: tool-call round limit reached",
            "tool_calls": all_calls, "rounds": max_rounds,
            "provider": "ollama"}


# ---------------------------------------------------------------- gemini

def gemini_client():
    if "gemini" not in _clients:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY not set")
        from google import genai
        _clients["gemini"] = genai.Client(api_key=key)
    return _clients["gemini"]


def to_gemini_tools(tool_schemas):
    from google.genai import types
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name=t["name"], description=t["description"],
            parameters_json_schema=t["input_schema"])
        for t in tool_schemas])]


def call_gemini(system, messages, tool_schemas, dispatch, max_rounds,
                on_event):
    global _call_count
=======

def call_count():
    return _call_count


# --------------------------------------------------------- tool plumbing

def to_gemini_tools(tool_schemas):
    """Convert our tool schemas into Gemini function declarations."""
    from google.genai import types
    decls = []
    for t in tool_schemas:
        decls.append(types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters_json_schema=t["input_schema"],
        ))
    return [types.Tool(function_declarations=decls)]


def to_groq_tools(tool_schemas):
    """Convert our tool schemas into OpenAI/Groq function tool specs."""
    tools = []
    for t in tool_schemas:
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            }
        })
    return tools


def llm_call_groq(system, messages, tool_schemas=None, dispatch=None,
                   max_rounds=MAX_ROUNDS, on_event=None):
    """Execution loop for Groq OpenAI-compatible function calling API."""
    global _call_count
    c = client()

    groq_msgs = [{"role": "system", "content": system}]
    for m in messages:
        groq_msgs.append({"role": m.get("role", "user"), "content": m["text"]})

    groq_tools = to_groq_tools(tool_schemas) if tool_schemas else None
    all_calls = []

    for rounds in range(1, max_rounds + 1):
        _call_count += 1
        kw = {"model": MODEL, "messages": groq_msgs}
        if groq_tools:
            kw["tools"] = groq_tools
            kw["tool_choice"] = "auto"

        try:
            resp = c.chat.completions.create(**kw)
        except Exception as e:
            raise LLMError(f"Groq API Error: {type(e).__name__}: {e}")

        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)

        if not tool_calls:
            return {"text": msg.content or "", "tool_calls": all_calls, "rounds": rounds}

        groq_msgs.append(msg)

        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except Exception:
                fn_args = {}

            if on_event:
                on_event({"type": "tool_call", "name": fn_name, "args": fn_args})

            if dispatch is None:
                res_data = {"error": "no dispatch function provided"}
            else:
                try:
                    res_data = dispatch(fn_name, fn_args)
                except Exception as e:
                    res_data = {"error": f"{type(e).__name__}: {e}"}

            all_calls.append({"name": fn_name, "args": fn_args, "result": res_data})
            if on_event:
                on_event({"type": "tool_result", "name": fn_name, "result": res_data})

            groq_msgs.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(res_data, default=str),
            })

def llm_call_ollama(system, messages, tool_schemas=None, dispatch=None,
                    max_rounds=MAX_ROUNDS, on_event=None):
    """Execution loop for Ollama native OpenAI-compatible function calling API."""
    global _call_count
    import json
    import urllib.request
    import urllib.error

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/chat/completions"

    ollama_msgs = [{"role": "system", "content": system}]
    for m in messages:
        ollama_msgs.append({"role": m.get("role", "user"), "content": m["text"]})

    tools = to_groq_tools(tool_schemas) if tool_schemas else None
    all_calls = []

    for rounds in range(1, max_rounds + 1):
        _call_count += 1
        payload = {
            "model": MODEL,
            "messages": ollama_msgs,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise LLMError(f"Ollama API Error: {type(e).__name__}: {e}")

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls")

        if not tool_calls:
            return {"text": msg.get("content") or "", "tool_calls": all_calls, "rounds": rounds}

        ollama_msgs.append(msg)

        for tc in tool_calls:
            fn = tc.get("function", {})
            fn_name = fn.get("name")
            fn_args = fn.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except Exception:
                    fn_args = {}

            if on_event:
                on_event({"type": "tool_call", "name": fn_name, "args": fn_args})

            if dispatch is None:
                res_data = {"error": "no dispatch function provided"}
            else:
                try:
                    res_data = dispatch(fn_name, fn_args)
                except Exception as e:
                    res_data = {"error": f"{type(e).__name__}: {e}"}

            all_calls.append({"name": fn_name, "args": fn_args, "result": res_data})
            if on_event:
                on_event({"type": "tool_result", "name": fn_name, "result": res_data})

            ollama_msgs.append({
                "role": "tool",
                "tool_call_id": tc.get("id", f"call_{rounds}"),
                "content": json.dumps(res_data, default=str),
            })

    return {"text": "stopped: tool-call round limit reached", "tool_calls": all_calls, "rounds": rounds}


def llm_call(system, messages, tool_schemas=None, dispatch=None,
             max_rounds=MAX_ROUNDS, on_event=None):
    """Run a conversation, executing tool calls until the model stops."""
    global _call_count

    if MOCK or not available():
        return mock_call(system, messages, tool_schemas, dispatch, on_event)

    if PROVIDER == "ollama":
        return llm_call_ollama(system, messages, tool_schemas, dispatch, max_rounds, on_event)

    if PROVIDER == "groq":
        return llm_call_groq(system, messages, tool_schemas, dispatch, max_rounds, on_event)


>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
    from google.genai import types

    cfg = {"system_instruction": system}
    if tool_schemas:
        cfg["tools"] = to_gemini_tools(tool_schemas)
<<<<<<< HEAD
        # We dispatch tools ourselves so every call reaches the event
        # stream; the SDK's automatic mode would hide them.
        cfg["automatic_function_calling"] = \
            types.AutomaticFunctionCallingConfig(disable=True)

    contents = [types.Content(role=m.get("role", "user"),
                              parts=[types.Part.from_text(text=m["text"])])
                for m in messages]

    all_calls = []
    for rounds in range(1, max_rounds + 1):
        _call_count += 1
        try:
            resp = gemini_client().models.generate_content(
                model=GEMINI_MODEL, contents=contents,
=======
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
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
                config=types.GenerateContentConfig(**cfg))
        except Exception as e:
            msg = str(e)
            if "no longer available" in msg or "NOT_FOUND" in msg:
                raise LLMError(
<<<<<<< HEAD
                    f"gemini: model '{GEMINI_MODEL}' rejected - the error "
                    f"usually names its replacement. Set GEMINI_MODEL in "
                    f".env.\n  {msg}")
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                raise LLMError(f"gemini: daily quota exhausted (free tier "
                               f"is 20 requests per model per day)")
            raise LLMError(f"gemini: {type(e).__name__}: {e}")
=======
                    f"model '{MODEL}' was rejected. The API usually names "
                    f"its replacement in the message below - set LLM_MODEL "
                    f"in server/.env to that name.\n  {msg}")
            raise LLMError(f"{type(e).__name__}: {e}")
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)

        calls = resp.function_calls or []
        if not calls:
            return {"text": resp.text or "", "tool_calls": all_calls,
<<<<<<< HEAD
                    "rounds": rounds, "provider": "gemini"}

=======
                    "rounds": rounds}

        # Echo the model's tool-call turn back into the transcript.
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
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
<<<<<<< HEAD
            "tool_calls": all_calls, "rounds": max_rounds,
            "provider": "gemini"}


# ------------------------------------------------------------------ mock
=======
            "tool_calls": all_calls, "rounds": rounds}


# ------------------------------------------------------------------- mock
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)

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


<<<<<<< HEAD
def mock_args(schema):
    """Plausible arguments from a JSON schema, guessed from field names so
    the event feed reads sensibly."""
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


def call_mock(system, messages, tool_schemas, dispatch, max_rounds,
              on_event):
    """Deterministic stand-in. Still calls a tool and still emits events,
    so the orchestrator and the UI behave identically to a real run."""
=======
def mock_call(system, messages, tool_schemas=None, dispatch=None,
              on_event=None):
    """Deterministic stand-in. Calls the first available tool once so the
    event stream and the orchestrator behave identically to a real run."""
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
    agent = "UNKNOWN"
    for name in MOCK_REPLIES:
        if name in (system or "").upper():
            agent = name
            break

<<<<<<< HEAD
    all_calls = []
    if tool_schemas and dispatch:
        t = tool_schemas[0]
        args = mock_args(t["input_schema"])
=======
    # Extract target CDM ID if present in prompt text
    cdm_id = None
    if messages:
        txt = messages[0].get("text", "")
        import re
        m = re.search(r"CDM-\d+", txt)
        if m:
            cdm_id = m.group(0)

    all_calls = []
    if tool_schemas and dispatch:
        t = tool_schemas[0]
        args = mock_args(t["input_schema"], cdm_id=cdm_id)
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
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

<<<<<<< HEAD
    text = MOCK_REPLIES.get(agent, "Mock response.").replace("{n}", "19232")
    return {"text": text, "tool_calls": all_calls, "rounds": 1,
            "provider": "mock", "mock": True}


BACKENDS = {"ollama": call_ollama, "gemini": call_gemini, "mock": call_mock}


# ------------------------------------------------------------- entry point

def llm_call(system, messages, tool_schemas=None, dispatch=None,
             max_rounds=MAX_ROUNDS, on_event=None, provider=None):
    """Run a conversation, executing tool calls until the model stops.

    Tries the requested provider, then each entry in LLM_FALLBACK. The
    chain normally ends in mock, so a pipeline mid-demo completes even if
    every model is unreachable.

    Returns {"text", "tool_calls", "rounds", "provider"}.
    """
    global _last_provider

    if MOCK:
        chain = ["mock"]
    else:
        chain = [provider or PROVIDER]
        chain += [p for p in FALLBACK if p not in chain]

    errors = []
    for name in chain:
        fn = BACKENDS.get(name)
        if fn is None:
            errors.append(f"{name}: unknown provider")
            continue
        if name != "mock" and not available(name):
            errors.append(f"{name}: not reachable")
            continue

        try:
            out = fn(system, messages, tool_schemas, dispatch, max_rounds,
                     on_event)
            _last_provider = name
            if errors and on_event:
                on_event({"type": "tool_result", "name": "provider_fallback",
                          "result": {"used": name, "skipped": errors}})
            return out
        except LLMError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {e}")

    raise LLMError("all providers failed:\n  " + "\n  ".join(errors))


if __name__ == "__main__":
    import sys
    import time

    want = sys.argv[1].lower() if len(sys.argv) > 1 else None

    print("provider status")
    for k, v in providers_status().items():
        print(f"  {k}: {v}")

=======
    text = MOCK_REPLIES.get(agent, "Mock response.")
    if "{n}" in text:
        text = text.replace("{n}", "19232")
    return {"text": text, "tool_calls": all_calls, "rounds": 1, "mock": True}


def mock_args(schema, cdm_id=None):

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
            out[name] = cdm_id or "CDM-0001"
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
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
    tools = [{
        "name": "get_object_count",
        "description": "Return how many objects are in the tracked catalog.",
        "input_schema": {
            "type": "object",
<<<<<<< HEAD
            "properties": {"group": {"type": "string",
                                     "description": "Catalog group, or 'all'."}},
=======
            "properties": {
                "group": {"type": "string",
                          "description": "Catalog group, or 'all'."},
            },
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
            "required": ["group"],
        },
    }]

    def dispatch(name, args):
        if name == "get_object_count":
            return {"count": 19232, "group": args.get("group", "all")}
        return {"error": f"unknown tool {name}"}

<<<<<<< HEAD
    print(f"\ncalling ({want or PROVIDER})...")
    t0 = time.time()
=======
    events = []
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
    try:
        out = llm_call(
            system="You are TRACKER, an agent that monitors space object "
                   "catalog health. Use the tools available. Never do "
<<<<<<< HEAD
                   "arithmetic yourself. Answer in one plain sentence.",
            messages=[{"role": "user",
                       "text": "How many objects are we tracking?"}],
            tool_schemas=tools, dispatch=dispatch, provider=want)
    except LLMError as e:
        print(f"\nfailed:\n  {e}")
        raise SystemExit(1)

    print(f"\nprovider   : {out['provider']}")
    print(f"rounds     : {out['rounds']}")
    print(f"elapsed    : {time.time() - t0:.1f}s")
=======
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
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
    print(f"tool calls : {len(out['tool_calls'])}")
    for c in out["tool_calls"]:
        print(f"  {c['name']}({json.dumps(c['args'])}) -> "
              f"{json.dumps(c['result'])}")
<<<<<<< HEAD
    print(f"\nreply:\n  {out['text']}")
=======
    print(f"\nreply:\n  {out['text']}")
    print(f"\napi calls made: {call_count()}")
>>>>>>> 7f1f9b5 (feat(server): Implement SGP4 propagation engine, J2 Kepler solver, and FastAPI backend)
