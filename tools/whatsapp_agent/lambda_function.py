"""ClaimPilot WhatsApp agent loop (Lambda).

Triggered by the SQS queue subscribed to the WhatsApp events SNS topic
(cds-whatsapp-events). For each inbound customer WhatsApp message it:
  1. parses the (heavily nested) Meta webhook payload,
  2. loads conversation state from DynamoDB,
  3. asks the ClaimPilot engine for the next reply (Bedrock),
  4. sends that reply back over WhatsApp (free-form, within the 24h window),
  5. persists the updated conversation.

Env vars:
  CONV_TABLE            DynamoDB table for conversation state (default claimpilot-conversations)
  ORIGINATION_PHONE_ID  WhatsApp origination phone-number-id
  META_API_VERSION      e.g. v20.0
  CLAIM_MODEL_ID        Bedrock model id (default us.anthropic.claude-sonnet-4-6)
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

import boto3

import claim_agent

CONV_TABLE = os.environ.get("CONV_TABLE", "claimpilot-conversations")
ORIGINATION_PHONE_ID = os.environ["ORIGINATION_PHONE_ID"]
META_API_VERSION = os.environ.get("META_API_VERSION", "v20.0")
REGION = os.environ.get("AWS_REGION", "us-east-1")
MAX_HISTORY = 20  # turns kept for context

_ddb = boto3.resource("dynamodb", region_name=REGION).Table(CONV_TABLE)
_social = boto3.client("socialmessaging", region_name=REGION)


# ---------- inbound parsing ----------

def _unwrap_sns_from_sqs(record: dict) -> dict:
    """SQS body wraps an SNS notification whose Message is the EUM event JSON."""
    body = json.loads(record["body"])
    # SNS envelope
    if "Message" in body and "TopicArn" in body:
        return json.loads(body["Message"])
    return body


def _extract_inbound_messages(eum_event: dict) -> list[dict[str, str]]:
    """Return [{'from': e164, 'text': str}] for each inbound text message.

    The WhatsApp webhook entry is a JSON string nested inside the EUM event.
    """
    out: list[dict[str, str]] = []
    entry_raw = eum_event.get("whatsAppWebhookEntry")
    if not entry_raw:
        return out
    entry = json.loads(entry_raw) if isinstance(entry_raw, str) else entry_raw
    for change in entry.get("changes", []):
        value = change.get("value", {})
        for msg in value.get("messages", []) or []:
            if msg.get("type") == "text":
                out.append(
                    {
                        "from": msg.get("from", ""),
                        "text": msg.get("text", {}).get("body", ""),
                    }
                )
            elif msg.get("type") == "button":
                out.append(
                    {"from": msg.get("from", ""), "text": msg.get("button", {}).get("text", "")}
                )
    return out


# ---------- state ----------

def _load_conv(phone: str) -> list[dict[str, str]]:
    resp = _ddb.get_item(Key={"phone": phone})
    item = resp.get("Item")
    if not item:
        return []
    return item.get("history", [])


def _save_conv(phone: str, history: list[dict[str, str]]) -> None:
    _ddb.put_item(
        Item={
            "phone": phone,
            "history": history[-MAX_HISTORY:],
            "updated_at": int(time.time()),
        }
    )


# ---------- outbound ----------

def _send_whatsapp_text(to_e164: str, body: str) -> str:
    to = to_e164 if to_e164.startswith("+") else f"+{to_e164}"
    message = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    blob = base64.b64encode(json.dumps(message).encode()).decode()
    resp = _social.send_whatsapp_message(
        originationPhoneNumberId=ORIGINATION_PHONE_ID,
        metaApiVersion=META_API_VERSION,
        message=blob,
    )
    return resp.get("messageId", "")


# ---------- handler ----------

def lambda_handler(event: dict, _context: Any = None) -> dict:
    processed = 0
    for record in event.get("Records", []):
        try:
            eum_event = _unwrap_sns_from_sqs(record)
        except (KeyError, json.JSONDecodeError):
            continue
        for msg in _extract_inbound_messages(eum_event):
            phone, text = msg["from"], msg["text"]
            if not phone or not text:
                continue
            history = _load_conv(phone)
            reply = claim_agent.next_reply(history, text)
            history.append({"role": "user", "text": text})
            history.append({"role": "assistant", "text": reply})
            _save_conv(phone, history)
            try:
                mid = _send_whatsapp_text(phone, reply)
                print(json.dumps({"phone": phone, "messageId": mid, "reply": reply}))
            except Exception as exc:  # noqa: BLE001 - log and continue
                print(json.dumps({"phone": phone, "sendError": str(exc)}))
            processed += 1
    return {"processed": processed}
