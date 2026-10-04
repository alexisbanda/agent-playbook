#!/usr/bin/env python3
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
    prompt = tool_input.get("prompt", "")
    model = tool_input.get("model")
    hook_mode = common.mode(config)

    if not common.active_run(root) or hook_mode == "off":
        common.log_event(root, payload, "subagent_launch", model=model, gated=False)
        common.emit(None)

    routing = route.load_routing()
    result = route.decide(prompt, model, config.get("profile", "reduced"), routing)
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
