"""Mock 'APIM' in front of a canned Anthropic Messages / OpenAI Responses backend.

Validates JWTs like APIM validate-jwt (RS256, aud, iss, exp), logs everything the harness sends,
and supports fault injection through POST /_ctl.
"""
import asyncio
import json
import sys
import time

import jwt
from aiohttp import web

import common

PORT = 18080
LOGFILE = common.LOGS / "requests.jsonl"
STATE = {"force_status": None, "force_count": 0, "sse_delay_ms": 0, "seq": 0}
PUBKEY = common.private_key().public_key()
SKIP_HEADERS = {"authorization", "x-api-key"}


def unauthorized(msg):
    return web.json_response({"statusCode": 401, "message": msg}, status=401)


def check_auth(request):
    """Return (ok, info) where info is safe to log (never the raw token)."""
    authz = request.headers.get("Authorization", "")
    xkey = request.headers.get("x-api-key", "")
    info = {
        "authorization_scheme": authz.split(" ", 1)[0] if authz else None,
        "x_api_key_present": bool(xkey),
    }
    token = authz.split(" ", 1)[1] if authz.lower().startswith("bearer ") else None
    if token and xkey:
        info["x_api_key_equals_bearer"] = token == xkey
    if not token:
        info["result"] = "missing_bearer"
        return False, info
    if STATE.get("lenient"):
        # Real Entra tokens cannot be verified against the mock's key; accept any well-formed, unexpired JWT.
        try:
            c = jwt.decode(token, options={"verify_signature": False})
            if c.get("exp", 0) < time.time():
                info["result"] = "expired"
                return False, info
            info["result"] = "ok"
            info["claims"] = {"jti": str(c.get("uti") or token[-12:]), "iat": c.get("iat"), "exp": c["exp"],
                              "ttl_remaining": c["exp"] - int(time.time()), "aud": c.get("aud"), "ver": c.get("ver"),
                              "real_token": True, "token_chars": len(token)}
            return True, info
        except Exception:
            info["result"] = "invalid:lenient"
            return False, info
    try:
        claims = jwt.decode(
            token,
            PUBKEY,
            algorithms=["RS256"],
            audience=common.AUDIENCE,
            issuer=common.ISSUER,
            options={"require": ["exp", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        info["result"] = "expired"
        try:
            c = jwt.decode(token, options={"verify_signature": False})
            info["claims"] = {"jti": c.get("jti"), "exp": c.get("exp"), "ttl_remaining": c["exp"] - int(time.time())}
        except Exception:
            pass
        return False, info
    except jwt.InvalidTokenError as e:
        info["result"] = f"invalid:{type(e).__name__}"
        return False, info
    info["result"] = "ok"
    info["claims"] = {
        "jti": claims["jti"],
        "iat": claims["iat"],
        "exp": claims["exp"],
        "ttl_remaining": claims["exp"] - int(time.time()),
        "upn": claims.get("upn"),
    }
    return True, info


def summarize_body(path, body):
    out = {}
    try:
        data = json.loads(body) if body else {}
    except Exception:
        return {"unparsable": True, "bytes": len(body)}
    out["model"] = data.get("model")
    out["stream"] = data.get("stream")
    msgs = data.get("messages") or data.get("input") or []
    out["n_messages"] = len(msgs) if isinstance(msgs, list) else 1
    out["n_tools"] = len(data.get("tools") or [])
    out["tool_names"] = [t.get("name") or t.get("type") for t in (data.get("tools") or [])][:20]
    out["max_tokens"] = data.get("max_tokens") or data.get("max_output_tokens")
    last = None
    if isinstance(msgs, list) and msgs:
        m = msgs[-1]
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, str):
            last = c
        elif isinstance(c, list):
            last = " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") in ("text", "input_text"))
    out["last_text"] = (last or "")[:100]
    return out


def log(entry):
    common.LOGS.mkdir(exist_ok=True)
    with LOGFILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


async def sse(request, events):
    resp = web.StreamResponse(
        status=200, headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"}
    )
    await resp.prepare(request)
    for name, data in events:
        await resp.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
        if STATE["sse_delay_ms"]:
            await asyncio.sleep(STATE["sse_delay_ms"] / 1000)
    await resp.write_eof()
    return resp


def chunks(text):
    words = text.split(" ")
    return [w + (" " if i < len(words) - 1 else "") for i, w in enumerate(words)]


def count_tool_results(data):
    n = 0
    for m in data.get("messages") or []:
        c = m.get("content")
        if isinstance(c, list):
            n += sum(1 for p in c if isinstance(p, dict) and p.get("type") == "tool_result")
    return n


async def anthropic_tool_turn(request, data, seq, n, name="Bash", args=None):
    """Scripted tool_use so a single claude -p session spans several requests."""
    model = data.get("model", "unknown")
    tool_id = f"toolu_mock{seq}"
    cmd = json.dumps(args if args is not None else {"command": f"echo step{n + 1}"})
    msg = {
        "id": f"msg_mock{seq}", "type": "message", "role": "assistant", "model": model, "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1},
    }
    events = [
        ("message_start", {"type": "message_start", "message": msg}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "tool_use", "id": tool_id, "name": name, "input": {}}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "input_json_delta", "partial_json": cmd}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                           "usage": {"output_tokens": 12}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return await sse(request, events)


async def anthropic_messages(request, body, seq):
    data = json.loads(body)
    model = data.get("model", "unknown")
    text = f"MOCK-OK model={model} seq={seq}"
    tool_names = {t.get("name") for t in data.get("tools") or []}
    if tool_names:
        if STATE.get("turn_delay_s"):
            await asyncio.sleep(STATE["turn_delay_s"])
        done = count_tool_results(data)
        mcp = STATE.get("mcp_call")
        if mcp and data.get("stream") and done < 1:
            target = next((n for n in tool_names if n and (n == mcp or n.endswith("__" + mcp))), None)
            if target:
                return await anthropic_tool_turn(request, data, seq, 0, name=target, args={})
        if "Bash" in tool_names and done < STATE.get("tool_turns", 0) and data.get("stream"):
            return await anthropic_tool_turn(request, data, seq, done)
    if not data.get("stream"):
        return web.json_response(
            {
                "id": f"msg_mock{seq}",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": f"msg_mock{seq}",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            },
        ),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("ping", {"type": "ping"}),
    ]
    for c in chunks(text):
        events.append(
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": c}})
        )
    events += [
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 8}},
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return await sse(request, events)


def count_fn_outputs(data):
    return sum(1 for i in (data.get("input") or []) if isinstance(i, dict) and i.get("type") == "function_call_output")


async def openai_function_turn(request, data, seq, n, name=None, args_json=None, namespace=None):
    model = data.get("model", "unknown")
    if name:
        item = {"type": "function_call", "id": f"fc_mock{seq}", "call_id": f"call_mock{seq}", "name": name,
                "arguments": args_json or "{}", "status": "completed"}
        if namespace:
            item["namespace"] = namespace
        base = {"id": f"resp_mock{seq}", "object": "response", "model": model, "created_at": int(time.time())}
        usage = {"input_tokens": 10, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 8,
                 "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 18}
        return await sse(request, [
            ("response.created", {"type": "response.created", "response": {**base, "status": "in_progress", "output": []}}),
            ("response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": {**item, "arguments": "", "status": "in_progress"}}),
            ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}),
            ("response.completed", {"type": "response.completed", "response": {**base, "status": "completed", "output": [item], "usage": usage}}),
        ])
    schema = next((t for t in data["tools"] if t.get("name") == "exec_command"), {})
    props = (schema.get("parameters") or {}).get("properties", {})
    key = "cmd" if "cmd" in props else ("command" if "command" in props else "cmd")
    args = {key: f"echo step{n + 1}"} if key == "cmd" else {key: f"echo step{n + 1}"}
    item = {"type": "function_call", "id": f"fc_mock{seq}", "call_id": f"call_mock{seq}", "name": "exec_command",
            "arguments": json.dumps(args), "status": "completed"}
    base = {"id": f"resp_mock{seq}", "object": "response", "model": model, "created_at": int(time.time())}
    usage = {"input_tokens": 10, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 8,
             "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 18}
    events = [
        ("response.created", {"type": "response.created", "response": {**base, "status": "in_progress", "output": []}}),
        ("response.output_item.added", {"type": "response.output_item.added", "output_index": 0,
                                        "item": {**item, "arguments": "", "status": "in_progress"}}),
        ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}),
        ("response.completed", {"type": "response.completed",
                                "response": {**base, "status": "completed", "output": [item], "usage": usage}}),
    ]
    return await sse(request, events)


async def openai_responses(request, body, seq):
    data = json.loads(body)
    model = data.get("model", "unknown")
    text = f"MOCK-OK model={model} seq={seq}"
    if data.get("tools"):
        sch = next((t for t in data["tools"] if t.get("name") == "exec_command"), None)
        if sch and not (common.LOGS / "codex_exec_command_schema.json").exists():
            (common.LOGS / "codex_exec_command_schema.json").write_text(json.dumps(sch, indent=1))
        if STATE.get("turn_delay_s"):
            await asyncio.sleep(STATE["turn_delay_s"])
        done = count_fn_outputs(data)
        mcp = STATE.get("mcp_call")
        if mcp and data.get("stream") and (done < 1 or STATE.get("mcp_late")) and not STATE.get("mcp_fired"):
            names = [t.get("name") for t in data["tools"] if t.get("name")]
            ns_of = {}
            for t in data["tools"]:  # MCP tools may be nested under namespaced tool groups
                for sub in (t.get("tools") or []):
                    if sub.get("name"):
                        names.append(sub["name"])
                        ns_of[sub["name"]] = t.get("name")
                if t.get("tools") and not (common.LOGS / "codex_namespace_tool.json").exists() and "azure" in str(t.get("name")):
                    (common.LOGS / "codex_namespace_tool.json").write_text(json.dumps(t, indent=1)[:6000])
            target = next((n for n in names if n == mcp or n.endswith("__" + mcp) or n.endswith(mcp)), None)
            STATE["mcp_seen_tools"] = [n for n in names if "azure" in n.lower() or "subscription" in n.lower()][:10]
            (common.LOGS / "last_tool_names.json").write_text(json.dumps(names))
            if target:
                if STATE.get("mcp_late"):
                    STATE["mcp_fired"] = True
                return await openai_function_turn(request, data, seq, 0, name=target, args_json="{}", namespace=ns_of.get(target))
        if sch and done < STATE.get("tool_turns", 0) and data.get("stream"):
            return await openai_function_turn(request, data, seq, done)
    rid, mid = f"resp_mock{seq}", f"msg_mock{seq}"
    item_done = {
        "type": "message",
        "id": mid,
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }
    usage = {
        "input_tokens": 10,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": 8,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 18,
    }
    base = {"id": rid, "object": "response", "model": model, "created_at": int(time.time())}
    if not data.get("stream"):
        return web.json_response({**base, "status": "completed", "output": [item_done], "usage": usage})
    events = [
        ("response.created", {"type": "response.created", "response": {**base, "status": "in_progress", "output": []}}),
        (
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {"type": "message", "id": mid, "role": "assistant", "status": "in_progress", "content": []},
            },
        ),
        (
            "response.content_part.added",
            {
                "type": "response.content_part.added",
                "item_id": mid,
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            },
        ),
    ]
    for c in chunks(text):
        events.append(
            (
                "response.output_text.delta",
                {"type": "response.output_text.delta", "item_id": mid, "output_index": 0, "content_index": 0, "delta": c},
            )
        )
    events += [
        (
            "response.output_text.done",
            {"type": "response.output_text.done", "item_id": mid, "output_index": 0, "content_index": 0, "text": text},
        ),
        (
            "response.content_part.done",
            {
                "type": "response.content_part.done",
                "item_id": mid,
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text", "text": text, "annotations": []},
            },
        ),
        ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item_done}),
        (
            "response.completed",
            {"type": "response.completed", "response": {**base, "status": "completed", "output": [item_done], "usage": usage}},
        ),
    ]
    return await sse(request, events)


async def openai_chat_completions(request, body, seq):
    """Minimal OpenAI Chat Completions (streaming and non-streaming) for clients that do not use the Responses API."""
    data = json.loads(body)
    model = data.get("model", "unknown")
    text = f"MOCK-OK model={model} seq={seq}"
    cid = f"chatcmpl-mock{seq}"
    created = int(time.time())
    if not data.get("stream"):
        return web.json_response({
            "id": cid, "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
        })
    resp = web.StreamResponse(status=200, headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
    await resp.prepare(request)
    mcp = STATE.get("mcp_call")
    if mcp and data.get("tools") and not any(m.get("role") == "tool" for m in data.get("messages", [])) and not STATE.get("mcp_fired"):
        tnames = [(t.get("function") or {}).get("name") for t in data["tools"]]
        STATE["mcp_seen_tools"] = [n for n in tnames if n][:10]
        (common.LOGS / "last_tool_names.json").write_text(json.dumps(tnames))
        target = next((n for n in tnames if n and (n == mcp or n.endswith(mcp))), None)
        if target:
            STATE["mcp_fired"] = True
            tc = {"index": 0, "id": f"call_mock{seq}", "type": "function", "function": {"name": target, "arguments": "{}"}}
            for d, fin in (({"role": "assistant", "content": None, "tool_calls": [tc]}, None), ({}, "tool_calls")):
                await resp.write(("data: " + json.dumps({"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                                  "choices": [{"index": 0, "delta": d, "finish_reason": fin}]}) + "\n\n").encode())
            await resp.write(b"data: [DONE]\n\n")
            await resp.write_eof()
            return resp

    def chunk(delta, finish=None):
        return "data: " + json.dumps({"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                                      "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}) + "\n\n"

    await resp.write(chunk({"role": "assistant", "content": ""}).encode())
    for c in chunks(text):
        await resp.write(chunk({"content": c}).encode())
        if STATE["sse_delay_ms"]:
            await asyncio.sleep(STATE["sse_delay_ms"] / 1000)
    await resp.write(chunk({}, "stop").encode())
    await resp.write(b"data: [DONE]\n\n")
    await resp.write_eof()
    return resp


ROUTES = {
    ("POST", "/anthropic/v1/messages"): anthropic_messages,
    ("POST", "/openai/v1/responses"): openai_responses,
    ("POST", "/openai/v1/chat/completions"): openai_chat_completions,
}


async def handler(request):
    path = request.path
    if path == "/_ctl":
        if request.method == "POST":
            STATE.update(await request.json())
        return web.json_response(STATE)
    if path == "/jwks.json":
        return web.json_response(common.jwks())
    STATE["seq"] += 1
    seq = STATE["seq"]
    body = await request.read()
    key = (request.method, path)
    entry = {
        "seq": seq,
        "ts": time.time(),
        "method": request.method,
        "path": path,
        "query": dict(request.query),
        "headers": {k.lower(): v for k, v in request.headers.items() if k.lower() not in SKIP_HEADERS},
        "body": summarize_body(path, body) if body else None,
    }
    handler_fn = ROUTES.get(key)
    if handler_fn is None:
        if path.endswith("/count_tokens") and request.method == "POST":
            ok, info = check_auth(request)
            entry.update(auth=info, status=200 if ok else 401, route="count_tokens")
            log(entry)
            return web.json_response({"input_tokens": 10}) if ok else unauthorized("Unauthorized.")
        if request.method == "GET" and path.endswith("/models"):
            ok, info = check_auth(request)
            entry.update(auth=info, status=200 if ok else 401, route="models")
            log(entry)
            if not ok:
                return unauthorized("Unauthorized.")
            if "/openai/" in path:
                return web.json_response({"object": "list", "data": [
                    {"id": "gpt-test", "object": "model", "created": 1700000000, "owned_by": "mock"},
                    {"id": "gpt-test-2", "object": "model", "created": 1700000000, "owned_by": "mock"}]})
            return web.json_response({"data": [{"id": "claude-test", "type": "model", "display_name": "Test"}], "has_more": False})
        entry.update(auth=check_auth(request)[1], status=404, route="unknown")
        log(entry)
        return web.json_response({"statusCode": 404, "message": "Resource not found"}, status=404)
    ok, info = check_auth(request)
    entry["auth"] = info
    entry["route"] = path
    if STATE["force_count"] > 0 and STATE["force_status"]:
        STATE["force_count"] -= 1
        entry["status"] = STATE["force_status"]
        entry["forced"] = True
        log(entry)
        return web.json_response({"statusCode": STATE["force_status"], "message": "forced"}, status=STATE["force_status"])
    if not ok:
        entry["status"] = 401
        log(entry)
        return unauthorized("Unauthorized. Access token is missing or invalid.")
    entry["status"] = 200
    log(entry)
    return await handler_fn(request, body, seq)


def main():
    common.LOGS.mkdir(exist_ok=True)
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.router.add_route("*", "/{tail:.*}", handler)
    web.run_app(app, host="127.0.0.1", port=PORT, print=lambda *_: None)


if __name__ == "__main__":
    sys.exit(main())
