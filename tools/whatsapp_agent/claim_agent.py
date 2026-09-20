"""ClaimPilot FNOL conversation engine.

Runs the multi-turn First Notice of Loss conversation using Amazon Bedrock
(Claude Sonnet 4.6 via the us. cross-region inference profile). State is kept
per-conversation in DynamoDB so the agent can pick up where it left off.

This module is channel-agnostic: it takes the inbound text + prior state and
returns the reply text + updated state. The Lambda handler wires it to the
WhatsApp channel.
"""
from __future__ import annotations

import json
import os
from typing import Any

import boto3

MODEL_ID = os.environ.get("CLAIM_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
REGION = os.environ.get("AWS_REGION", "us-east-1")

_bedrock = boto3.client("bedrock-runtime", region_name=REGION)

SYSTEM_PROMPT = """\
You are ClaimPilot, an AI assistant for filing an auto insurance First Notice of \
Loss (FNOL) claim over a messaging app. You are warm, calm, and concise \
(messages must fit comfortably in a chat bubble — 1 to 3 short sentences).

Your job is to guide the policyholder through starting a claim by collecting, \
one step at a time, in this order:
1. SAFETY: confirm everyone is safe / whether anyone is injured. If injuries or \
   danger, tell them to call 911 first.
2. POLICY: ask for their policy number or the name on the policy.
3. WHAT HAPPENED: a short description of the incident (collision, theft, weather, etc.).
4. WHEN & WHERE: date/time and location of the incident.
5. DAMAGE: ask them to describe the damage, and to send photos if they can.
6. NEXT STEP: offer to arrange a tow or rental if the vehicle is not drivable, \
   then confirm you've started the claim and give them a claim reference.

Rules:
- Ask for only ONE thing per message. Acknowledge what they just told you before \
  asking the next question.
- Never invent policy details, prices, or coverage decisions. If asked something \
  you don't know, say a human adjuster will confirm.
- Keep a friendly, reassuring tone — they may be shaken up.
- When you have collected items 1-5, generate a short claim reference like \
  CLM-XXXXXX (6 digits) and confirm the claim has been started.

You will be given the conversation so far. Reply with ONLY the next message to \
send the customer — no labels, no quotes, no explanations.
"""


def next_reply(history: list[dict[str, str]], user_text: str) -> str:
    """Given prior turns and the new user message, return ClaimPilot's reply.

    history: list of {"role": "user"|"assistant", "text": str}
    """
    messages = []
    for turn in history:
        messages.append(
            {"role": turn["role"], "content": [{"text": turn["text"]}]}
        )
    messages.append({"role": "user", "content": [{"text": user_text}]})

    resp = _bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=messages,
        inferenceConfig={"maxTokens": 300, "temperature": 0.3},
    )
    parts = resp["output"]["message"]["content"]
    text = "".join(p.get("text", "") for p in parts).strip()
    return text or "Sorry, I didn't catch that — could you say it again?"
