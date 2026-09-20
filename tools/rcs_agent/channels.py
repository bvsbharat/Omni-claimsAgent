"""Channel adapters for ClaimPilot.

The FNOL agent brain (claim_agent), media handling (media), and state
(DynamoDB) are channel-agnostic. This module isolates the two things that
differ per channel:

  1. parse_inbound(eum_event) -> normalized {channel, from, text, media} | None
  2. send_text / send_confirmation  -> deliver a reply on that channel

Two adapters implement the same interface:
  - RcsChannel       : AWS End User Messaging SMS/RCS (SendTextMessage / SendRcsMessage)
  - WhatsAppChannel  : AWS End User Messaging Social (SendWhatsAppMessage)

Both receive inbound media the same way: AWS stores the file in S3 and the
event carries the S3 location, so `media.observe()` works identically for both.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")

_sms = boto3.client("pinpoint-sms-voice-v2", region_name=REGION)
_social = boto3.client("socialmessaging", region_name=REGION)

# ---- config (from env) ----
RCS_AGENT_ARN = os.environ.get("RCS_AGENT_ARN", "")
WA_PHONE_ID = os.environ.get("WA_ORIGINATION_PHONE_ID", "")
WA_API_VERSION = os.environ.get("META_API_VERSION", "v20.0")


# ---- shared confirmation summary (same wording on every channel) ----

def _confirmation_caption(claim_number: str, slots: dict) -> str:
    parts = [p for p in (
        slots.get("what"), slots.get("when"), slots.get("where"), slots.get("damage"),
    ) if p]
    summary = " · ".join(str(p) for p in parts)
    text = f"Claim {claim_number} filed."
    if summary:
        text += f" {summary}."
    text += " A human adjuster will follow up shortly."
    return text[:2000]


# =========================================================================
# RCS / SMS (AWS End User Messaging)
# =========================================================================

class RcsChannel:
    name = "rcs"

    @staticmethod
    def parse(event_msg: dict) -> dict | None:
        frm = event_msg.get("originationNumber")
        if not frm:
            return None
        body = event_msg.get("messageBody", "")
        media, text = None, body
        if isinstance(body, str) and body.lstrip().startswith("{"):
            try:
                inner = json.loads(body)
            except json.JSONDecodeError:
                inner = None
            if isinstance(inner, dict) and inner.get("type") == "FILE":
                text = ""
                if inner.get("mediaStatus") == "SUCCESS":
                    media = {
                        "bucket": inner.get("s3Bucket"),
                        "key": inner.get("s3Key"),
                        "mime": inner.get("mimeType", "image/jpeg"),
                    }
                else:
                    media = {"error": inner.get("mediaStatus")}
        return {"channel": "rcs", "from": frm, "text": text or "", "media": media}

    @staticmethod
    def send_text(to: str, body: str) -> str:
        resp = _sms.send_text_message(
            DestinationPhoneNumber=to,
            OriginationIdentity=RCS_AGENT_ARN,
            MessageBody=body,
            MessageType="TRANSACTIONAL",
        )
        return resp.get("MessageId", "")

    @staticmethod
    def send_confirmation(to: str, claim_number: str, slots: dict, media_url: str) -> str:
        card = {
            "CardOrientation": "VERTICAL",
            "CardContent": {
                "Title": f"Claim {claim_number} filed",
                "Description": _confirmation_caption(claim_number, slots),
                "Suggestions": [
                    {"Reply": {"Text": "Add a photo", "PostbackData": "add_photo"}},
                    {"Reply": {"Text": "Talk to an adjuster", "PostbackData": "human"}},
                ],
            },
        }
        if media_url:
            card["CardContent"]["Media"] = {"Height": "SHORT", "FileUrl": media_url}
        resp = _sms.send_rcs_message(
            DestinationPhoneNumber=to,
            OriginationIdentity=RCS_AGENT_ARN,
            RcsMessageContent={"Content": {"RichCard": card}},
            MessageTrafficType="TRANSACTIONAL",
        )
        return resp.get("MessageId", "")


# =========================================================================
# WhatsApp (AWS End User Messaging Social)
# =========================================================================

class WhatsAppChannel:
    name = "whatsapp"

    @staticmethod
    def parse(eum_event: dict) -> dict | None:
        """Parse the WhatsApp webhook entry nested in the EUM Social event."""
        entry_raw = eum_event.get("whatsAppWebhookEntry")
        if not entry_raw:
            return None
        entry = json.loads(entry_raw) if isinstance(entry_raw, str) else entry_raw
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []) or []:
                frm = msg.get("from")
                mtype = msg.get("type")
                if mtype == "text":
                    return {"channel": "whatsapp", "from": frm,
                            "text": msg.get("text", {}).get("body", ""), "media": None}
                if mtype == "button":
                    return {"channel": "whatsapp", "from": frm,
                            "text": msg.get("button", {}).get("text", ""), "media": None}
                if mtype in ("image", "audio", "video", "document"):
                    node = msg.get(mtype, {})
                    # WhatsApp media in EUM Social is delivered to S3 like RCS.
                    media = {
                        "bucket": node.get("s3Bucket"),
                        "key": node.get("s3Key"),
                        "mime": node.get("mime_type") or node.get("mimeType") or f"{mtype}/*",
                    }
                    if not media["key"]:
                        media = {"error": "NO_S3"}
                    return {"channel": "whatsapp", "from": frm,
                            "text": node.get("caption", ""), "media": media}
        return None

    @staticmethod
    def _send(to: str, message: dict) -> str:
        to_e164 = to if str(to).startswith("+") else f"+{to}"
        message["to"] = to_e164
        blob = base64.b64encode(json.dumps(message).encode()).decode()
        resp = _social.send_whatsapp_message(
            originationPhoneNumberId=WA_PHONE_ID,
            metaApiVersion=WA_API_VERSION,
            message=blob,
        )
        return resp.get("messageId", "")

    @staticmethod
    def send_text(to: str, body: str) -> str:
        return WhatsAppChannel._send(to, {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "type": "text",
            "text": {"body": body},
        })

    @staticmethod
    def send_confirmation(to: str, claim_number: str, slots: dict, media_url: str) -> str:
        # WhatsApp free-form (inside 24h window): compact confirmation image + caption
        # if we have a URL, otherwise a text summary. (Business-initiated would require
        # an approved template.)
        caption = _confirmation_caption(claim_number, slots)
        if media_url:
            return WhatsAppChannel._send(to, {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "type": "image",
                "image": {"link": media_url, "caption": caption},
            })
        return WhatsAppChannel.send_text(to, caption)


# =========================================================================
# Dispatch
# =========================================================================

def detect_and_parse(eum_event: dict) -> dict | None:
    """Figure out which channel an inbound EUM event belongs to, and parse it."""
    if eum_event.get("whatsAppWebhookEntry"):
        return WhatsAppChannel.parse(eum_event)
    if eum_event.get("originationNumber"):
        return RcsChannel.parse(eum_event)
    return None


def for_channel(name: str):
    return WhatsAppChannel if name == "whatsapp" else RcsChannel
