#!/usr/bin/env python3
# Copyright (c) 2026 Alexis Banda. Todos los derechos reservados.
# Software propietario: uso sujeto a LICENSE, prohibida su redistribución.
"""PreToolUse (Agent|Task): enforces routing/routing.json on every subagent launch.

Only active while a run is open (.agent-playbook/active-run exists). Outside a run
it only records the launch. In mode "block" a forbidden launch is denied; in
"warn" it goes through with a warning; a missing model is always injected.
"""
import common
import route


def main():
    payload = common.read_input()
    root, config = common.load_context(payload)
    if not root:
        common.emit(None)

    tool_input = dict(payload.get("tool_input") or {})
    hook_mode = common.mode(config)
    runtime = payload.get("_runtime", "claude")
    profile = config.get("profile", "reduced")

    # Google Antigravity (agy) invoke_subagent passes {"Subagents": [{"Prompt": ..., "Model": ...}, ...]}
    if isinstance(tool_input.get("Subagents"), list):
        subagents = [dict(s) for s in tool_input["Subagents"]]
        if not common.active_run(root, payload.get("session_id")) or hook_mode == "off":
            for sub in subagents:
                common.log_event(root, payload, "subagent_launch", model=sub.get("Model"), gated=False)
            common.emit(None)

        routing = route.load_routing()
        injected = False
        blocked_messages = []
        for sub in subagents:
            prompt = sub.get("Prompt", "")
            model = sub.get("Model")
            result = route.decide(prompt, model, profile, routing, runtime="agy")
            common.log_event(
                root, payload, "model_gate",
                decision=result["decision"], mode=hook_mode, role=result["role"], klass=result["class"],
                requested=model, model=result["model"], override=result["override"], reason=result["reason"],
            )
            if result["decision"] == "inject":
                sub["Model"] = result["model"]
                injected = True
            elif result["decision"] == "block":
                blocked_messages.append(f"Gate de modelos: {result['reason']}. Ver routing/ROUTING.md del agent-playbook.")

        if blocked_messages:
            msg = " | ".join(blocked_messages)
            if hook_mode == "block":
                common.emit(common.pre_tool("deny", msg))
            common.emit(common.pre_tool(
                updated_input=dict(tool_input, Subagents=subagents) if injected else None,
                context=f"AVISO (modo warn) — {msg}",
            ))
        if injected:
            tool_input["Subagents"] = subagents
            common.emit(common.pre_tool(updated_input=tool_input))
        common.emit(None)

    prompt = tool_input.get("prompt", "")
    model = tool_input.get("model")

    if not common.active_run(root, payload.get("session_id")) or hook_mode == "off":
        common.log_event(root, payload, "subagent_launch", model=model, gated=False)
        common.emit(None)

    routing = route.load_routing()
    result = route.decide(prompt, model, profile, routing, runtime=runtime)
    common.log_event(
        root, payload, "model_gate",
        decision=result["decision"], mode=hook_mode, role=result["role"], klass=result["class"],
        requested=model, model=result["model"], override=result["override"], reason=result["reason"],
    )

    if result["decision"] == "inject":
        tool_input["model"] = result["model"]
        common.emit(common.pre_tool(updated_input=tool_input))

    if result["decision"] == "block":
        message = f"Gate de modelos: {result['reason']}. Ver routing/ROUTING.md del agent-playbook."
        if hook_mode == "block":
            common.emit(common.pre_tool("deny", message))
        common.emit(common.pre_tool(context=f"AVISO (modo warn) — {message}"))

    common.emit(None)


if __name__ == "__main__":
    common.run_safely(main)
