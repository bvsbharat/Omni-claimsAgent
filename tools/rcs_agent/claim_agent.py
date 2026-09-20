"""ClaimPilot FNOL agent brain.

A slot-filling personal-auto First Notice of Loss (FNOL) agent driven by Amazon
Bedrock (Claude Sonnet 4.6). Each turn, the model is given the conversation so
far + the slots collected, and returns STRICT JSON:

    {
      "reply": "<message to send the customer>",
      "slots":  {"what": ..., "when": ..., "where": ..., "damage": ...},
      "photo_received": true|false,
      "ready_to_file": true|false
    }

The Lambda handler owns the channel (RCS) and the side effects (vision on the
photo, claim-number generation, confirmation card). This module is pure logic:
given history + state + optional image assessment, produce the next step.

Slots collected for a minimal personal-auto FNOL claim:
  - what   : what happened (collision, theft, weather, vandalism, ...)
  - when   : date/time of the incident
  - where  : location of the incident
  - damage : description of the damage (augmented by photo vision)
A photo is requested but optional. Once what/when/where/damage are known, the
agent files the claim and returns a claim number.
"""
from __future__ import annotations

import json
import os
import random
import string
from typing import Any

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("CLAIM_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

# Amazon Bedrock Guardrail (prompt-injection, abuse, PII). Applied to every
# converse() call so untrusted customer input can't jailbreak the agent or leak PII.
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID", "")
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "1")

_bedrock = boto3.client("bedrock-runtime", region_name=REGION)

SLOTS = ["what", "when", "where", "damage"]


def _guardrail_kwargs() -> dict:
    """Return the guardrailConfig kwarg for converse() if a guardrail is set."""
    if not GUARDRAIL_ID:
        return {}
    return {"guardrailConfig": {
        "guardrailIdentifier": GUARDRAIL_ID,
        "guardrailVersion": GUARDRAIL_VERSION,
    }}

SYSTEM_PROMPT = """\
You are ClaimPilot, an AI assistant that helps a customer file a personal auto \
insurance First Notice of Loss (FNOL) claim over a chat channel (RCS).

Tone: warm, calm, reassuring, concise. Chat-sized messages (1-2 short sentences).
Ask for ONE thing at a time. Acknowledge what the customer just said before asking \
the next question.

AI DISCLOSURE: On your FIRST message of a conversation only, briefly disclose you are \
an AI assistant (e.g., start with "I'm ClaimPilot, an AI assistant —"). This satisfies \
AI-transparency expectations (e.g., EU AI Act Article 50). Do not repeat the disclosure \
on later turns.

You must collect these slots, in roughly this order:
- what:   what happened (e.g., collision, rear-ended, theft, hail, vandalism)
- when:   date and/or time of the incident
- where:  location of the incident (city/road/intersection is fine)
- damage: description of the damage to the vehicle

A photo of the damage is helpful — ask for one while collecting `damage`, but it is \
OPTIONAL; never block the claim on a photo. If the system tells you a photo was \
received and assessed, incorporate that assessment into the `damage` slot and thank them.

The customer can also send OTHER attachments over RCS. The system will describe any \
attachment to you in a note like "(customer sent a voice note; transcript: ...)" or \
"(customer sent a PDF document...)". Handle them naturally:
- Voice note: use the transcript as if the customer typed it (extract slot info from it).
- Video: thank them and, if you still need damage detail, ask for a clear still photo.
- PDF/document: acknowledge it (e.g., a police report or repair estimate) and note it's \
  attached to the claim; keep collecting any missing slots.
- Contact card: acknowledge it (e.g., the other driver or a witness) and continue.
Never ignore an attachment — always acknowledge what they sent before your next question.

SAFETY FIRST: On the very first substantive turn, make sure everyone is safe / no \
injuries. If the customer mentions injuries or danger, tell them to call 911 first, \
then continue gently.

When all four slots (what, when, where, damage) are filled, set "ready_to_file": true \
and write a `reply` that says you're filing the claim now (do NOT invent a claim \
number — the system generates it).

SLOT-FILLING RULES (important):
- Be GENEROUS when extracting slots. "someone hit my car" / "another car backed into \
  me" IS a valid `what` (a collision) — fill it, don't keep re-asking for clarification.
- NEVER ask again about a slot that is already listed in "slots so far" in the system note. \
  Only ask about slots that are still null.
- The photo is OPTIONAL. Ask for it at most ONCE. If the customer already gave a damage \
  description, do NOT block filing on a photo — proceed to file.
- Ask about at most one MISSING slot per turn. If none are missing, file the claim.

OUTPUT FORMAT: Respond with ONLY a valid JSON object, no markdown, no prose around it:
{
  "reply": "<the next message to send the customer>",
  "slots": {"what": <string or null>, "when": <string or null>, "where": <string or null>, "damage": <string or null>},
  "photo_received": <true|false>,
  "ready_to_file": <true|false>
}
- Carry forward previously known slot values; only add/refine. Never null out a value you \
  were told is already known.
- `reply` must never be empty.
- Set ready_to_file true as soon as what, when, where, and damage are all non-null (a photo \
  is NOT required). When ready_to_file is true, the reply should say you're filing the claim now.
"""


def _converse(history: list[dict[str, str]], user_text: str, system_note: str | None) -> str:
    messages = []
    for turn in history:
        messages.append({"role": turn["role"], "content": [{"text": turn["text"]}]})
    user_block = user_text
    if system_note:
        user_block = f"{user_text}\n\n[system note: {system_note}]"
    messages.append({"role": "user", "content": [{"text": user_block}]})

    resp = _bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=messages,
        inferenceConfig={"maxTokens": 500, "temperature": 0.3},
        **_guardrail_kwargs(),
    )
    parts = resp["output"]["message"]["content"]
    return "".join(p.get("text", "") for p in parts).strip()


def _parse_json(raw: str) -> dict[str, Any]:
    """Best-effort extraction of the JSON object from the model output."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1:
        s = s[start : end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {
            "reply": raw[:600] or "Sorry, could you say that again?",
            "slots": {},
            "photo_received": False,
            "ready_to_file": False,
        }


def assess_photo(image_bytes: bytes, fmt: str = "jpeg") -> str:
    """Run Bedrock vision on a damage photo; return a one-paragraph assessment."""
    prompt = (
        "You are ClaimPilot's auto-damage assessor. In 2-3 short sentences describe "
        "the vehicle damage visible, an overall severity (minor/moderate/severe), and "
        "flag if the image does not look like an original photo of a damaged vehicle."
    )
    resp = _bedrock.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {"image": {"format": fmt, "source": {"bytes": image_bytes}}},
                    {"text": prompt},
                ],
            }
        ],
        inferenceConfig={"maxTokens": 250, "temperature": 0.2},
        **_guardrail_kwargs(),
    )
    parts = resp["output"]["message"]["content"]
    return "".join(p.get("text", "") for p in parts).strip()


def generate_claim_number() -> str:
    suffix = "".join(random.choices(string.digits, k=6))
    return f"CLM-{suffix}"


def step(
    state: dict[str, Any],
    user_text: str,
    photo_assessment: str | None = None,
) -> dict[str, Any]:
    """Advance the conversation one turn.

    state: {"history": [...], "slots": {...}, "photo_received": bool,
            "claim_number": str|None, "status": "collecting"|"filed"}
    Returns updated state plus a "reply" and optional "just_filed" flag.
    """
    history = state.get("history", [])
    slots = state.get("slots", {}) or {}

    note_bits = []
    known = {k: v for k, v in slots.items() if v}
    if known:
        note_bits.append(f"slots so far: {json.dumps(known)}")
    if photo_assessment:
        note_bits.append(f"a damage photo was received and assessed: {photo_assessment}")
    system_note = " | ".join(note_bits) if note_bits else None

    raw = _converse(history, user_text, system_note)
    parsed = _parse_json(raw)

    # merge slots (carry forward, let model refine)
    new_slots = dict(slots)
    for k in SLOTS:
        v = (parsed.get("slots") or {}).get(k)
        if v:
            new_slots[k] = v
    if photo_assessment and not new_slots.get("damage"):
        new_slots["damage"] = photo_assessment

    reply = parsed.get("reply") or "Could you tell me a bit more?"
    photo_received = bool(parsed.get("photo_received") or photo_assessment or state.get("photo_received"))
    slots_complete = bool(parsed.get("ready_to_file")) or all(new_slots.get(s) for s in SLOTS)

    history = history + [
        {"role": "user", "text": user_text},
        {"role": "assistant", "text": reply},
    ]

    # NOTE: filing is NOT done here anymore. The handler drives the staged
    # workflow (email consent gate -> code verify -> file). step() only advances
    # the slot-collecting conversation and signals when all slots are collected.
    return {
        "reply": reply,
        "slots": new_slots,
        "photo_received": photo_received,
        "slots_complete": slots_complete,
        "claim_number": state.get("claim_number"),
        "status": state.get("status", "collecting"),
        "history": history[-24:],
    }


# ---------- workflow helpers (used by the handler's staged orchestrator) ----------

import re as _re

_EMAIL_RE = _re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def extract_email(text: str) -> str | None:
    m = _EMAIL_RE.search(text or "")
    return m.group(0).strip().rstrip(".") if m else None


def extract_code(text: str, expected_len: int = 6) -> str | None:
    """Pull a numeric confirmation code out of a user reply."""
    digits = _re.findall(r"\b(\d{%d})\b" % expected_len, text or "")
    if digits:
        return digits[0]
    # fall back: any run of exactly expected_len digits ignoring spaces
    compact = _re.sub(r"\D", "", text or "")
    return compact if len(compact) == expected_len else None


def generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))
