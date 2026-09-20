"""ClaimPilot agent loop (Lambda) — channel-agnostic.

Triggered by SQS queues subscribed to the AWS End User Messaging event topics:
  - cds-eum-events        (RCS / SMS)
  - cds-whatsapp-events   (WhatsApp, via EUM Social)

The SAME agent brain serves every channel. For each inbound customer message:
  1. detect the channel and parse the event (text OR media stored in S3),
  2. turn any attachment (image/audio/video/pdf/...) into a text observation
     (Bedrock vision for images, Amazon Transcribe for audio),
  3. load conversation/claim state from DynamoDB,
  4. advance the FNOL agent one turn (Bedrock),
  5. send the reply back on the SAME channel (rich confirmation when filed),
  6. persist updated state.

Env:
  CONV_TABLE                DynamoDB table (default claimpilot-claims)
  RCS_AGENT_ARN             RCS agent origination ARN
  WA_ORIGINATION_PHONE_ID   WhatsApp origination phone-number-id
  META_API_VERSION          WhatsApp Graph API version (default v20.0)
  MEDIA_BUCKET              S3 bucket for inbound media + confirmation images
  CLAIM_MODEL_ID            Bedrock model id
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3

import channels
import claim_agent
import confirmation_image
import email_tool
import media as media_mod
import settlement as settlement_mod

REGION = os.environ.get("AWS_REGION", "us-east-1")
CONV_TABLE = os.environ.get("CONV_TABLE", "claimpilot-claims")

_ddb = boto3.resource("dynamodb", region_name=REGION).Table(CONV_TABLE)


# ---------- inbound envelope ----------

def _unwrap(record: dict) -> dict:
    body = json.loads(record["body"])
    if "Message" in body and "TopicArn" in body:  # SNS envelope
        return json.loads(body["Message"])
    return body


# ---------- state (per phone, shared across channels) ----------

def _state_key(channel: str, phone: str) -> str:
    return f"{channel}:{phone}"


def _load(key: str) -> dict:
    item = _ddb.get_item(Key={"phone": key}).get("Item")
    if not item:
        return {"history": [], "slots": {}, "photo_received": False,
                "claim_number": None, "status": "collecting",
                "phase": "collecting", "email": None, "code": None,
                "code_attempts": 0, "settlement": None}
    return {
        "history": item.get("history", []),
        "slots": item.get("slots", {}),
        "photo_received": bool(item.get("photo_received")),
        "claim_number": item.get("claim_number"),
        "status": item.get("status", "collecting"),
        "phase": item.get("phase", "collecting"),
        "email": item.get("email"),
        "code": item.get("code"),
        "code_attempts": int(item.get("code_attempts", 0)),
        "settlement": item.get("settlement"),
    }


def _save(key: str, state: dict) -> None:
    _ddb.put_item(Item={
        "phone": key,
        "history": state.get("history", []),
        "slots": state.get("slots", {}),
        "photo_received": state.get("photo_received", False),
        "claim_number": state.get("claim_number"),
        "status": state.get("status", "collecting"),
        "phase": state.get("phase", "collecting"),
        "email": state.get("email"),
        "code": state.get("code"),
        "code_attempts": int(state.get("code_attempts", 0)),
        "settlement": state.get("settlement"),
        "updated_at": int(time.time()),
        # DynamoDB TTL: auto-expire an inactive session after 7 days (privacy + cost).
        "ttl": int(time.time()) + 7 * 24 * 3600,
    })


# ---------- media (image vision, audio transcription, docs, etc.) ----------

def _observe_media(media: dict | None) -> dict:
    return media_mod.observe(media, claim_agent.assess_photo)


# ---------- staged workflow orchestrator ----------
#
# Phases:
#   collecting     -> gather what/when/where/damage via the agent
#   awaiting_email -> all slots collected; ask for email to authorize
#   awaiting_code  -> email sent with a 6-digit code; user must reply the code
#   filed          -> code verified; claim filed, settlement + confirmation sent
#   followup       -> post-filing omnichannel follow-up (adjuster / repair shop)

def _handle(channel_name: str, ch, phone: str, key: str, state: dict,
            user_text: str, photo_assessment: str | None) -> None:
    phase = state.get("phase", "collecting")

    # ---- awaiting_code: verify the emailed code before filing ----
    if phase == "awaiting_code":
        code = claim_agent.extract_code(user_text)
        # allow "resend" / new email mid-flow
        new_email = claim_agent.extract_email(user_text)
        if new_email and not code:
            state["email"] = new_email
            _issue_code(ch, phone, state)
            _save(key, state)
            return
        if code and code == state.get("code"):
            _file_and_confirm(channel_name, ch, phone, key, state)
            return
        state["code_attempts"] = int(state.get("code_attempts", 0)) + 1
        if state["code_attempts"] >= 4:
            # regenerate + resend after too many misses
            _issue_code(ch, phone, state, resend=True)
            state["code_attempts"] = 0
        else:
            ch.send_text(phone, "That code didn't match. Please reply with the 6-digit "
                                "code from the email we sent (or reply with a new email address).")
        _save(key, state)
        return

    # ---- awaiting_email: capture email, send code ----
    if phase == "awaiting_email":
        email = claim_agent.extract_email(user_text)
        if not email:
            ch.send_text(phone, "To authorize and file your claim, what's the best email "
                                "address to send your confirmation to?")
            _save(key, state)
            return
        state["email"] = email
        _issue_code(ch, phone, state)
        _save(key, state)
        return

    # ---- filed / followup: continue the post-claim conversation ----
    if phase in ("filed", "followup"):
        state["phase"] = "followup"
        reply = _followup_reply(state, user_text)
        ch.send_text(phone, reply)
        state.setdefault("history", []).extend(
            [{"role": "user", "text": user_text}, {"role": "assistant", "text": reply}]
        )
        state["history"] = state["history"][-24:]
        _save(key, state)
        return

    # ---- collecting: run the FNOL agent ----
    result = claim_agent.step(state, user_text, photo_assessment=photo_assessment)
    state.update({
        "history": result["history"],
        "slots": result["slots"],
        "photo_received": result["photo_received"],
    })
    if result.get("slots_complete"):
        # move to the email consent gate
        state["phase"] = "awaiting_email"
        ch.send_text(phone, result["reply"])
        ch.send_text(phone, "Almost done! Before I file this, I'll email you a confirmation "
                            "to authorize it. What's the best email address for you?")
    else:
        ch.send_text(phone, result["reply"])
    _save(key, state)


def _issue_code(ch, phone: str, state: dict, resend: bool = False) -> None:
    code = claim_agent.generate_code()
    state["code"] = code
    state["phase"] = "awaiting_code"
    email_tool.send_confirmation_code(state["email"], code, state.get("slots", {}))
    verb = "re-sent" if resend else "sent"
    ch.send_text(phone, f"I've {verb} a confirmation email to {state['email']} with a 6-digit "
                        f"code. Reply here with that code and I'll file your claim.")


def _file_and_confirm(channel_name: str, ch, phone: str, key: str, state: dict) -> None:
    claim_number = claim_agent.generate_claim_number()
    slots = state.get("slots", {})
    sett = settlement_mod.estimate(claim_number, slots)
    state.update({"claim_number": claim_number, "status": "filed",
                  "phase": "filed", "settlement": sett, "code": None})

    # 1) confirmation image + rich card / image on the messaging channel
    media_url = confirmation_image.build_and_upload(claim_number, slots)
    try:
        ch.send_text(phone, f"You're confirmed — filing your claim now. Your claim number is "
                            f"{claim_number}. {settlement_mod.summary_line(sett)}")
        ch.send_confirmation(phone, claim_number, slots, media_url)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"channel": channel_name, "phone": phone, "confirmSendError": str(exc)}))

    # 2) formal email with claim number + settlement
    if state.get("email"):
        email_tool.send_claim_filed(state["email"], claim_number, slots, sett)

    # 3) invite to omnichannel follow-up
    ch.send_text(phone, "Next, I can help schedule an adjuster and pick a repair shop. "
                        "Would you like to continue here or on WhatsApp?")
    state["phase"] = "followup"
    _save(key, state)
    print(json.dumps({"channel": channel_name, "phone": phone, "filed": claim_number,
                      "payout": sett["payout"]}))


def _followup_reply(state: dict, user_text: str) -> str:
    """Post-filing follow-up: adjuster scheduling + repair-shop/vendor preference."""
    claim = state.get("claim_number", "your claim")
    sys = (f"You are ClaimPilot, continuing AFTER claim {claim} has been filed. Help the "
           f"customer with next steps only: scheduling an adjuster inspection and choosing a "
           f"repair shop / rental / tow by location preference. Be concise (1-2 sentences). "
           f"If they mention a city or area, acknowledge and suggest you'll find nearby "
           f"options. Do not re-collect claim details. Reply with plain text only.")
    resp = claim_agent._bedrock.converse(
        modelId=claim_agent.MODEL_ID,
        system=[{"text": sys}],
        messages=[{"role": t["role"], "content": [{"text": t["text"]}]}
                  for t in state.get("history", [])[-8:]] + [
            {"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig={"maxTokens": 200, "temperature": 0.3},
    )
    parts = resp["output"]["message"]["content"]
    return "".join(p.get("text", "") for p in parts).strip() or \
        "I can help schedule an adjuster or find a nearby repair shop — which would you like?"


# ---------- handler ----------

def lambda_handler(event: dict, _ctx: Any = None) -> dict:
    processed = 0
    for record in event.get("Records", []):
        try:
            eum = _unwrap(record)
        except (KeyError, json.JSONDecodeError):
            continue

        inbound = channels.detect_and_parse(eum)
        if not inbound:
            continue

        channel_name = inbound["channel"]
        ch = channels.for_channel(channel_name)
        phone = inbound["from"]
        key = _state_key(channel_name, phone)
        state = _load(key)

        obs = _observe_media(inbound.get("media"))
        photo_assessment = obs.get("damage_text")

        user_text = inbound["text"]
        if not user_text:
            user_text = obs.get("observation") or "(no content)"
        elif obs.get("observation"):
            user_text = f"{user_text}\n{obs['observation']}"

        try:
            _handle(channel_name, ch, phone, key, state, user_text, photo_assessment)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"channel": channel_name, "phone": phone, "handleError": str(exc)}))
        processed += 1
    return {"processed": processed}
