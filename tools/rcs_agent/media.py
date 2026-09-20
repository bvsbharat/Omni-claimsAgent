"""Multi-modal inbound media handling for ClaimPilot.

RCS (and WhatsApp) let a customer send more than photos: voice notes, video,
PDFs (e.g., a police report), vCards, and location. This module turns any
inbound media object (already stored in S3 by AWS End User Messaging) into a
short text "observation" the FNOL agent can reason over.

Routing by MIME type:
  image/*         -> Bedrock vision (damage assessment)              [handled in claim_agent.assess_photo]
  audio/*         -> Amazon Transcribe (voice note -> text)
  video/*         -> acknowledge; sample not analyzed here
  application/pdf -> acknowledge as a document (e.g., police report)
  text/vcard      -> acknowledge as contact info
  other           -> graceful acknowledgement

Design goals:
  - NEVER drop a message: every media type yields a usable observation.
  - NEVER break the claim flow on a processing error.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
_s3 = boto3.client("s3", region_name=REGION)
_transcribe = boto3.client("transcribe", region_name=REGION)

_AUDIO_EXT = {
    "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/mp4": "mp4", "audio/m4a": "m4a",
    "audio/aac": "mp4", "audio/ogg": "ogg", "audio/opus": "ogg", "audio/amr": "amr",
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/webm": "webm", "audio/3gpp": "amr",
}


def kind_of(mime: str) -> str:
    m = (mime or "").lower()
    if m.startswith("image/"):
        return "image"
    if m.startswith("audio/"):
        return "audio"
    if m.startswith("video/"):
        return "video"
    if m == "application/pdf":
        return "pdf"
    if "vcard" in m or "vcf" in m:
        return "vcard"
    return "other"


def _read_s3(bucket: str, key: str) -> bytes:
    return _s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def transcribe_audio(bucket: str, key: str, mime: str, timeout_s: int = 55) -> str:
    """Transcribe a voice note using Amazon Transcribe (S3-based, synchronous poll)."""
    media_format = _AUDIO_EXT.get((mime or "").lower())
    if not media_format:
        # best-effort from the key extension
        ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
        media_format = ext or "mp4"
    job = f"claimpilot-{uuid.uuid4().hex[:12]}"
    media_uri = f"s3://{bucket}/{key}"
    _transcribe.start_transcription_job(
        TranscriptionJobName=job,
        LanguageCode="en-US",
        MediaFormat=media_format,
        Media={"MediaFileUri": media_uri},
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = _transcribe.get_transcription_job(TranscriptionJobName=job)
        status = resp["TranscriptionJob"]["TranscriptionJobStatus"]
        if status == "COMPLETED":
            uri = resp["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
            import json
            import urllib.request

            with urllib.request.urlopen(uri, timeout=10) as r:  # noqa: S310 (AWS-signed URL)
                data = json.loads(r.read())
            results = data.get("results", {}).get("transcripts", [])
            return results[0]["transcript"].strip() if results else ""
        if status == "FAILED":
            return ""
        time.sleep(3)
    return ""  # timed out; caller falls back to an acknowledgement


def observe(media: dict, assess_image) -> dict:
    """Turn an inbound media object into an observation for the agent.

    media: {"bucket","key","mime"} on success, or {"error": <status>}.
    assess_image: callable(bytes, fmt) -> str  (Bedrock vision, injected to avoid a cycle)

    Returns {"kind": str, "observation": str, "damage_text": str|None}
      - observation: text describing what the customer sent (fed to the agent as user turn)
      - damage_text: set only when this media should populate the `damage` slot (images)
    """
    if not media:
        return {"kind": "none", "observation": "", "damage_text": None}
    if media.get("error"):
        return {
            "kind": "error",
            "observation": "(customer tried to send an attachment but it couldn't be received)",
            "damage_text": None,
        }

    bucket, key, mime = media.get("bucket"), media.get("key"), media.get("mime", "")
    kind = kind_of(mime)

    try:
        if kind == "image":
            data = _read_s3(bucket, key)
            fmt = "png" if "png" in mime else ("gif" if "gif" in mime else "jpeg")
            assessment = assess_image(data, fmt)
            return {
                "kind": "image",
                "observation": f"(customer sent a photo of the damage; assessment: {assessment})",
                "damage_text": assessment,
            }

        if kind == "audio":
            transcript = transcribe_audio(bucket, key, mime)
            if transcript:
                return {
                    "kind": "audio",
                    "observation": f'(customer sent a voice note; transcript: "{transcript}")',
                    "damage_text": None,
                }
            return {
                "kind": "audio",
                "observation": "(customer sent a voice note; it could not be transcribed — ask them to type or resend)",
                "damage_text": None,
            }

        if kind == "video":
            return {
                "kind": "video",
                "observation": "(customer sent a video of the scene/damage; acknowledge it and ask for a clear still photo if possible)",
                "damage_text": None,
            }

        if kind == "pdf":
            return {
                "kind": "pdf",
                "observation": "(customer sent a PDF document, possibly a police report or estimate; acknowledge receipt and note it's attached to the claim)",
                "damage_text": None,
            }

        if kind == "vcard":
            return {
                "kind": "vcard",
                "observation": "(customer shared a contact card; acknowledge it, e.g. the other driver's or a witness's details)",
                "damage_text": None,
            }

        return {
            "kind": "other",
            "observation": f"(customer sent an attachment of type {mime}; acknowledge receipt and continue the claim)",
            "damage_text": None,
        }
    except Exception as exc:  # noqa: BLE001 - never break the flow
        print({"mediaObserveError": str(exc), "kind": kind, "key": key})
        return {
            "kind": kind,
            "observation": "(customer sent an attachment; acknowledge and continue)",
            "damage_text": None,
        }
