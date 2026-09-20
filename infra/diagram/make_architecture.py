"""Compose an AWS-style architecture diagram for ClaimPilot using the official
AWS Architecture Icons (PNGs in ./icons) and Pillow.

Layout (left -> right), AWS reference-architecture style with generous spacing:
  Customer -> Channels (EUM: RCS/SMS/WhatsApp + SES) -> SNS -> SQS -> Lambda
  Lambda <-> Bedrock (+Guardrail) + Transcribe (AI)   Lambda <-> DynamoDB + S3 (data)
  Security controls shown inline on the edges they protect.

Outputs: claimpilot-architecture.png
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, "icons")

W, H = 2100, 1360
BG = (247, 248, 250)
INK = (35, 47, 62)
MUTED = (120, 128, 138)
AWS_ORANGE = (236, 145, 21)
CLOUD_STROKE = (150, 158, 166)
SEC = (200, 55, 55)
GROUP_FILLS = {
    "channels": (234, 242, 253),
    "ai": (243, 236, 255),
    "data": (233, 247, 239),
}
GROUP_STROKE = {
    "channels": (26, 86, 219),
    "ai": (122, 63, 242),
    "data": (30, 142, 78),
}
ARROW = (90, 99, 110)
ICON = 82
_fonts: dict = {}


def font(sz, bold=False):
    key = (sz, bold)
    if key in _fonts:
        return _fonts[key]
    for p in (
        f"/System/Library/Fonts/Supplemental/Arial{' Bold' if bold else ''}.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if os.path.exists(p):
            try:
                _fonts[key] = ImageFont.truetype(p, sz)
                return _fonts[key]
            except OSError:
                pass
    _fonts[key] = ImageFont.load_default()
    return _fonts[key]


def load_icon(name, size=ICON):
    img = Image.open(os.path.join(ICONS, f"{name}.png")).convert("RGBA")
    return img.resize((size, size), Image.LANCZOS)


def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    nodes = {}  # name -> (cx, cy)

    def text_w(s, f):
        return d.textlength(s, font=f)

    # ---------- title ----------
    d.text((52, 36), "ClaimPilot — Agentic Omnichannel FNOL on AWS CDS",
           font=font(40, True), fill=INK)
    d.text((54, 90), "One Amazon Bedrock agent over RCS · SMS · WhatsApp · SES — staged, secure claim workflow",
           font=font(22), fill=MUTED)

    # ---------- AWS Cloud boundary ----------
    cloud = (40, 150, W - 40, H - 150)
    d.rounded_rectangle(cloud, radius=20, outline=CLOUD_STROKE, width=2)
    d.text((cloud[0] + 22, cloud[1] + 14), "AWS Cloud   ·   us-east-1", font=font(20, True), fill=MUTED)

    # ---------- helpers ----------
    def group_box(key, label, box):
        d.rounded_rectangle(box, radius=16, fill=GROUP_FILLS[key], outline=GROUP_STROKE[key], width=2)
        d.text((box[0] + 22, box[1] + 16), label, font=font(20, True), fill=GROUP_STROKE[key])

    def place(name, icon, cx, cy, label, sublabel=""):
        ic = load_icon(icon)
        img.paste(ic, (int(cx - ICON / 2), int(cy - ICON / 2)), ic)
        d.text((cx, cy + ICON / 2 + 12), label, font=font(18, True), fill=INK, anchor="ma")
        if sublabel:
            d.text((cx, cy + ICON / 2 + 36), sublabel, font=font(14), fill=MUTED, anchor="ma")
        nodes[name] = (cx, cy)

    def h_arrow(a, b, label="", label_dy=-16):
        (x1, y1), (x2, y2) = nodes[a], nodes[b]
        fwd = x2 > x1
        sx = x1 + ICON / 2 + 6 if fwd else x1 - ICON / 2 - 6
        ex = x2 - ICON / 2 - 6 if fwd else x2 + ICON / 2 + 6
        midx = (sx + ex) / 2
        # orthogonal: out horizontally, vertical jog, into target
        d.line([(sx, y1), (midx, y1), (midx, y2), (ex, y2)], fill=ARROW, width=3, joint="curve")
        head = 11
        d.polygon([(ex, y2), (ex - head if fwd else ex + head, y2 - 6),
                   (ex - head if fwd else ex + head, y2 + 6)], fill=ARROW)
        if label:
            d.ellipse([midx - 15, (y1 + y2) / 2 - 15, midx + 15, (y1 + y2) / 2 + 15],
                      fill=(255, 255, 255), outline=ARROW, width=2)
            d.text((midx, (y1 + y2) / 2), label, font=font(15, True), fill=INK, anchor="mm")

    # ---------- column X centers (well separated) ----------
    XCUST, XCH, XSNS, XSQS, XLAMBDA, XRIGHT = 130, 400, 700, 950, 1230, 1720

    # ---------- Customer (outside the flow, left) ----------
    d.rounded_rectangle((XCUST - 62, 470, XCUST + 62, 640), radius=16, fill=(255, 246, 229),
                        outline=AWS_ORANGE, width=2)
    d.text((XCUST, 486), "Customer", font=font(19, True), fill=INK, anchor="ma")
    ic = load_icon("eum")
    img.paste(ic, (int(XCUST - ICON / 2), 520), ic)
    d.text((XCUST, 616), "any phone", font=font(14), fill=MUTED, anchor="ma")
    nodes["cust"] = (XCUST, 561)

    # ---------- 1) Channels ----------
    group_box("channels", "1)  Channels — AWS End User Messaging (CDS)", (XCH - 150, 300, XCH + 210, 930))
    place("rcs", "eum", XCH, 400, "RCS / SMS", "End User Messaging")
    place("wa", "eum", XCH, 600, "WhatsApp", "EUM Social")
    place("ses", "ses", XCH, 790, "Amazon SES", "email consent + record")

    # ---------- 2) Ingestion (SNS, SQS) ----------
    place("sns", "sns", XSNS, 430, "Amazon SNS", "channel events")
    place("sqs", "sqs", XSQS, 430, "Amazon SQS", "queue")
    # DLQ hanging under SQS
    place("dlq", "sqs", XSQS, 640, "SQS DLQ", "poison-msg isolation")
    d.line([(XSQS, 430 + ICON / 2 + 44), (XSQS, 640 - ICON / 2 - 6)], fill=SEC, width=2)
    d.polygon([(XSQS, 640 - ICON / 2 - 6), (XSQS - 5, 640 - ICON / 2 - 16),
               (XSQS + 5, 640 - ICON / 2 - 16)], fill=SEC)

    # ---------- 3) Orchestrator (Lambda) ----------
    d.rounded_rectangle((XLAMBDA - 140, 470, XLAMBDA + 140, 690), radius=16,
                        fill=(255, 255, 255), outline=INK, width=2)
    place("lambda", "lambda", XLAMBDA, 545, "ClaimPilot Agent", "AWS Lambda")
    d.text((XLAMBDA, 636), "collect → email → code → file → follow-up",
           font=font(14), fill=MUTED, anchor="ma")
    d.text((XLAMBDA, 660), "TTL-backed session state", font=font(13), fill=SEC, anchor="ma")

    # ---------- 4) AI & processing ----------
    group_box("ai", "4)  AI & processing", (XRIGHT - 210, 288, XRIGHT + 210, 748))
    place("bedrock", "bedrock", XRIGHT, 378, "Amazon Bedrock", "reason + photo vision")
    place("transcribe", "transcribe", XRIGHT, 510, "Amazon Transcribe", "voice notes → text")
    place("textract", "textract", XRIGHT, 642, "Amazon Textract", "PDF/doc OCR → fields")

    # ---------- 5) State & media ----------
    group_box("data", "5)  State & media", (XRIGHT - 210, 792, XRIGHT + 210, 1110))
    place("ddb", "dynamodb", XRIGHT, 882, "Amazon DynamoDB", "claims + phase (TTL)")
    place("s3", "s3", XRIGHT, 1010, "Amazon S3", "media + confirmation cards")

    # ---------- flow arrows ----------
    h_arrow("cust", "rcs", "1")
    h_arrow("rcs", "sns", "2")
    h_arrow("sns", "sqs", "3")
    h_arrow("sqs", "lambda", "4")
    h_arrow("lambda", "bedrock", "5")
    h_arrow("lambda", "transcribe")
    h_arrow("lambda", "textract")
    h_arrow("lambda", "ddb", "6")
    h_arrow("lambda", "s3", "7")
    h_arrow("lambda", "ses", "8")

    # ---------- inline Guardrail badge on the Lambda -> Bedrock edge ----------
    # sits above the arrow row (Bedrock is at y=415), clear of the arrow line at y=545
    bx, by = nodes["bedrock"]
    gx = (XLAMBDA + 140 + (bx - ICON / 2)) / 2   # midpoint of the horizontal run to Bedrock
    gy = 300 - 40                                # tuck just above the AI group top
    gsz = 46
    gi = load_icon("guardrails", gsz)
    d.rounded_rectangle((gx - 150, gy - 6, gx + 160, gy + gsz + 6), radius=12,
                        fill=(253, 240, 240), outline=SEC, width=2)
    img.paste(gi, (int(gx - 140), int(gy)), gi)
    d.text((gx - 84, gy + 4), "Bedrock Guardrail", font=font(14, True), fill=SEC)
    d.text((gx - 84, gy + 26), "prompt-injection + PII filter", font=font(12), fill=MUTED)

    # ---------- legend ----------
    ly = H - 120
    d.text((52, ly), "Flow", font=font(16, True), fill=INK)
    d.text((52, ly + 26),
           "1 inbound msg / photo / voice / document     2 SNS event     3 SQS (→ DLQ after 3 fails)     "
           "4 invoke agent     5 reason · photo vision · voice transcribe · document OCR",
           font=font(15), fill=MUTED)
    d.text((52, ly + 50),
           "6 read/write claim state (TTL)     7 render + store confirmation card     "
           "8 SES email: 6-digit consent code, then filed record     →  reply on same channel",
           font=font(15), fill=MUTED)
    d.text((52, ly + 82),
           "Security: Bedrock Guardrails · SQS DLQ · DynamoDB TTL · email consent gate · least-privilege IAM",
           font=font(15, True), fill=SEC)

    out = os.path.join(HERE, "claimpilot-architecture.png")
    img.save(out, "PNG")
    print("wrote", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
