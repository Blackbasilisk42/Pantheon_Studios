# Pantheon Studios — Immutable Authority Rules

> **BINDING DOCUMENT — READ ONLY**
> This file defines non-negotiable constraints that govern all system behavior,
> including the Autonomous Learning Engine. No module, script, learned heuristic,
> or automated process may contradict, bypass, weaken, or override these rules.
> The learning engine loads this file at runtime and discards any proposed
> adjustment that touches a protected category.

---

## RULE 1 — Human-in-the-Loop (HITL) Approval Is Mandatory

All content generated, staged, or modified by any automated process **MUST**
enter `queue/pending/` and await explicit human approval before any further
distribution or publication step is taken.

**FORBIDDEN ACTIONS:**
- auto-publish, autonomous publishing, skip approval, bypass queue
- Move content from `queue/pending/` to `queue/approved/` without human review
- Trigger any publisher without prior human sign-off
- Schedule or time-delay publishing to avoid the approval step

No learned weight, prompt adjustment, trend signal, or automation trigger may
remove, shorten, or circumvent the human review gate.

---

## RULE 2 — Master Killswitch Is Absolute

The `KILLSWITCH_ACTIVE` flag in `.system_state.json` represents an immediate,
unconditional halt of all automated operations. It cannot be bypassed under any
circumstances.

**FORBIDDEN ACTIONS:**
- disable killswitch, bypass killswitch, override killswitch, ignore killswitch
- Write `KILLSWITCH_ACTIVE = False` from any background or learning process
- Detect killswitch state and route around it
- Spawn child processes or threads to continue work after killswitch activation

The killswitch may only be toggled by the authenticated human operator through
the Control Panel UI.

---

## RULE 3 — Operational Stealth and Privacy Are Absolute

The system must never disclose, log, transmit, or expose identifying information
about users, operations, or internal infrastructure to external parties.

**FORBIDDEN ACTIONS:**
- disclose personal data, PII, personal information, user identity
- transmit credentials, API keys, tokens, passwords, secrets to external endpoints
- log IP addresses, device fingerprints, or behavioral metadata to external services
- include operational metadata in any externally visible output
- expose internal file paths, module names, or system architecture externally

---

## RULE 4 — Core Security Modules Are Immutable

No learning process, automated script, or generated content may modify, replace,
weaken, or extend the following protected modules:

- `modules/security_manager.py`
- `modules/system_state.py`
- `modules/approval_gate.py`
- `lore/immutable_rules.md` (this file)

**FORBIDDEN ACTIONS:**
- modify security_manager, rewrite security module, patch approval_gate
- alter system_state, change killswitch logic, edit immutable_rules
- override authority hierarchy, escalate privileges, grant new permissions
- disable stealth controls, disable header rotation, disable PII scrubbing

---

## RULE 5 — Learning Scope Is Restricted to Style and Narrative Structure

The Autonomous Learning Engine is authorized **only** to adjust:
- Narrative structure weights (bullet lists, hooks, tone, format)
- Content style preferences derived from approved/rejected queue patterns
- Public trend signals related to storytelling and content formatting

**FORBIDDEN LEARNING TARGETS:**
- Security configurations, authentication, cryptography
- Network routing, HTTP headers beyond User-Agent rotation scope
- Queue logic, approval workflows, publishing triggers
- Any parameter in `modules/system_state.py` or `modules/security_manager.py`
- User identity data, account credentials, or access controls

---

_Last reviewed: 2026-08-10_
_Authority: Human Operator (Pantheon Studios)_
_This document is enforced programmatically by `modules/learning_engine.py` at runtime._
