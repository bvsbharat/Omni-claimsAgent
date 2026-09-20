"""Render a branded ClaimPilot claim-confirmation card image and upload to S3.

Produces a 1440x1440-ish summary card (claim number, slots, timestamp) and
uploads it to the media bucket under confirmations/, returning an HTTPS URL that
RCS can use as rich-card media.

Rendering uses Pillow if available; if not, it falls back to a simple solid card
so the flow never breaks in the Lambda runtime.
"""
from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from typing import Any

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "claimpilot-rcs-media-203918842720")
PUBLIC_MEDIA_BASE = os.environ.get("PUBLIC_MEDIA_BASE", "")  # optional CDN/base override

_s3 = boto3.client("s3", region_name=REGION)

BRAND = (26, 86, 219)
BRAND_DARK = (17, 58, 150)
WHITE = (255, 255, 255)
INK = (24, 24, 27)
MUTED = (113, 113, 122)


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = (
        "/var/task/fonts/DejaVuSans-Bold.ttf" if bold else "/var/task/fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    )
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:3]


def render_card(claim_number: str, slots: dict[str, Any]) -> bytes:
    """Render a compact 2:1 landscape thumbnail sized for an RCS rich-card header.

    RCS shows card media at the card's width with a fixed aspect band, so a small
    2:1 image (800x400) renders as a tidy mobile thumbnail rather than a huge tile.
    Detailed slot text lives in the card's Description, not baked into the image.
    """
    from PIL import Image, ImageDraw

    W, H = 800, 400  # 2:1 landscape — the RCS card thumbnail ratio
    img = Image.new("RGB", (W, H), BRAND)
    d = ImageDraw.Draw(img)

    # subtle diagonal depth
    d.polygon([(0, H), (W, int(H * 0.35)), (W, H)], fill=BRAND_DARK)

    # brand + status
    d.text((44, 40), "ClaimPilot", font=_font(46, True), fill=WHITE)
    d.text((46, 96), "Claim filed", font=_font(26), fill=(210, 224, 255))

    # claim-number chip
    chip_w = min(520, 60 + int(d.textlength(claim_number, font=_font(40, True))) + 220)
    d.rounded_rectangle([44, 168, 44 + chip_w, 260], radius=16, fill=WHITE)
    d.text((66, 182), "CLAIM NUMBER", font=_font(18, True), fill=MUTED)
    d.text((66, 206), claim_number, font=_font(40, True), fill=BRAND)

    # one-line "what" summary + footer
    what = str(slots.get("what") or "").strip()
    if what:
        line = _wrap(d, what, _font(24), W - 88)[:1]
        if line:
            d.text((46, 292), line[0], font=_font(24), fill=(226, 234, 255))
    d.text((46, H - 46), "A human adjuster will follow up shortly.",
           font=_font(20), fill=(198, 214, 255))

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def build_and_upload(claim_number: str, slots: dict[str, Any]) -> str:
    """Render + upload the confirmation card; return a public HTTPS URL."""
    try:
        png = render_card(claim_number, slots)
    except Exception as exc:  # pragma: no cover - never break the claim on rendering
        print(f"confirmation image render failed: {exc}")
        return ""

    key = f"confirmations/{claim_number}.png"
    _s3.put_object(
        Bucket=MEDIA_BUCKET,
        Key=key,
        Body=png,
        ContentType="image/png",
    )
    if PUBLIC_MEDIA_BASE:
        return f"{PUBLIC_MEDIA_BASE.rstrip('/')}/{key}"
    # presigned URL so RCS can fetch the private object
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": MEDIA_BUCKET, "Key": key},
        ExpiresIn=7 * 24 * 3600,
    )
