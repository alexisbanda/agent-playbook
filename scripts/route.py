#!/usr/bin/env python3
"""Resolves which model a subagent launch may use, from routing/routing.json.

Pure decision logic shared by the model-gate hook (fase 3) and the tests.

CLI:
  route.py --header "ROLE: coder · CLASS: money" [--model opus] [--profile reduced]
  route.py --session-model claude-opus-5-5

Prints one JSON object. Exit code 0 for allow/inject, 2 for block.
"""
import argparse
import json
import os
import re
import sys

ROUTING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "routing", "routing.json")
CONFIG_PATH = os.path.join(".claude", "agent-playbook.json")

HEADER_RE = re.compile(r"ROLE:\s*([\w-]+)\s*[·|,;]\s*CLASS:\s*([\w-]+)", re.IGNORECASE)
OVERRIDE_RE = re.compile(r"^\s*OVERRIDE:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
HEADER_LINES = 3


def load_routing(path=ROUTING_PATH):
    with open(path) as fh:
        return json.load(fh)


def load_profile(config_path=CONFIG_PATH):
    try:
        with open(config_path) as fh:
            return json.load(fh).get("profile", "reduced")
    except (OSError, ValueError):
        return "reduced"


def parse_header(prompt):
    """Returns (role, class, override_reason). The header must be in the first lines."""
    head = "\n".join((prompt or "").splitlines()[:HEADER_LINES])
    match = HEADER_RE.search(head)
    override = OVERRIDE_RE.search(head)
    reason = override.group(1) if override else None
    if not match:
        return None, None, reason
    return match.group(1).lower(), match.group(2).lower(), reason


def tier_of(model, routing):
    """Maps an alias or a full model id to its tier, or None if unknown."""
    if not model:
        return None
    model = model.lower()
    for name, tier in routing["tiers"].items():
        if model in (tier["alias"], tier["model_id"]) or model.startswith(tier["model_id"]):
            return name
    for name, tier in routing["tiers"].items():
        if tier["alias"] in model:
            return name
    return None


def decide(prompt, model, profile, routing):
    """Returns a dict: decision (allow | inject | block), model, tier, role, class, reason, override."""
    role, klass, override = parse_header(prompt)
    result = {"role": role, "class": klass, "override": override, "profile": profile}

    def out(decision, reason, tier=None):
        alias = routing["tiers"][tier]["alias"] if tier else model
        return dict(result, decision=decision, reason=reason, tier=tier, model=alias)

    if profile not in routing["profiles"]:
        return out("block", f"perfil desconocido '{profile}'")
    rules = routing["profiles"][profile]

    if role is None:
        return out("block", "falta el encabezado 'ROLE: <rol> · CLASS: <clase>' en la primera línea del prompt")

    klass = rules["class_aliases"].get(klass, klass)
    result["class"] = klass
    if klass not in rules["classes"]:
        known = ", ".join(sorted(rules["classes"]))
        return out("block", f"clase '{klass}' no existe en el perfil {profile} (clases: {known})")
    rule = rules["classes"][klass]

    requested = tier_of(model, routing) if model else None
    if model and requested is None:
        return out("block", f"modelo '{model}' desconocido en routing.json")

    tier = requested or rule["default"]

    # Hard rule: never overridable.
    if role in routing["writer_roles"] and tier in routing["writer_forbidden_tiers"]:
        return out("block", f"el nivel {tier} nunca escribe código (rol {role})", tier)

    if requested is None:
        return out("inject", f"sin modelo: se inyecta el de la clase {klass}", tier)

    if requested not in rule["allowed"]:
        if override:
            return out("allow", f"OVERRIDE: {override}", requested)
        allowed = ", ".join(routing["tiers"][t]["alias"] for t in rule["allowed"])
        return out("block", f"la clase {klass} no permite {model} (permitidos: {allowed})", requested)

    return out("allow", "modelo permitido por la clase", requested)


def check_session(model, routing):
    tier = tier_of(model, routing)
    ok = tier in routing["session_tiers_accepted"]
    reason = "modelo de sesión aceptado" if ok else f"el modelo de sesión '{model}' no es de un nivel aceptado"
    return {"decision": "allow" if ok else "block", "tier": tier, "model": model, "reason": reason}


def missing_pins(routing, env=os.environ):
    return [t["pin_env"] for t in routing["tiers"].values() if not env.get(t["pin_env"])]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--header", help="Primeras líneas del prompt del subagente")
    parser.add_argument("--model", help="Modelo pedido (alias o id)")
    parser.add_argument("--profile", help="reduced | full (por defecto, el de .claude/agent-playbook.json)")
    parser.add_argument("--session-model", help="Comprueba el modelo de la sesión")
    parser.add_argument("--routing", default=ROUTING_PATH)
    args = parser.parse_args()

    routing = load_routing(args.routing)
    if args.session_model:
        result = check_session(args.session_model, routing)
    else:
        result = decide(args.header or "", args.model, args.profile or load_profile(), routing)
    result["missing_pins"] = missing_pins(routing)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(2 if result["decision"] == "block" else 0)


if __name__ == "__main__":
    main()
