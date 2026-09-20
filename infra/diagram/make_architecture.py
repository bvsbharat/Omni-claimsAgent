"""Compose an AWS-style architecture diagram for ClaimPilot using the official
AWS Architecture Icons (PNGs in ./icons) and Pillow.

Layout (left -> right), AWS reference-architecture style:
  Customer -> Channels (EUM: RCS/SMS/WhatsApp + SES) -> SNS -> SQS -> Lambda
  Lambda <-> Bedrock + Transcribe (AI)    Lambda <-> DynamoDB + S3 (data)
  Lambda -> SES (email)  -> reply back to channels

Outputs: claimpilot-architecture.png
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, "icons")

W, H = 1800, 1100
BG = (247, 248, 250)
INK = (35, 47, 62)          # AWS "squid ink"
MUTED = (110, 120, 130)
AWS_ORANGE = (236, 145, 21)
CLOUD_STROKE = (120, 130, 140)
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
ARROW = (70, 80, 92)

ICON = 88  # icon render size


def font(sz, bold=False):
    for p in (
        f"/System/Library/Fonts/Supplemental/Arial{' Bold' if bold else ''}.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except OSError:
                pass
    return ImageFont.load_default()


def load_icon(name):
    img = Image.open(os.path.join(ICONS, f"{name}.png")).convert("RGBA")
    return img.resize((ICON, ICON), Image.LANCZOS)


def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # title
    d.text((48, 34), "ClaimPilot — Agentic Omnichannel FNOL on AWS CDS",
           font=font(38, True), fill=INK)
    d.text((50, 84), "One Bedrock agent over RCS · SMS · WhatsApp · SES — staged, secure claim workflow",
           font=font(22), fill=MUTED)

    # AWS Cloud boundary
    cloud = (36, 150, W - 36, H - 40)
    d.rounded_rectangle(cloud, radius=18, outline=CLOUD_STROKE, width=2)
    d.text((cloud[0] + 18, cloud[1] + 12), "AWS Cloud  ·  us-east-1", font=font(20, True), fill=MUTED)

    nodes = {}  # name -> (cx, cy) center of icon

    def group_box(key, label, box):
        d.rounded_rectangle(box, radius=14, fill=GROUP_FILLS[key], outline=GROUP_STROKE[key], width=2)
        d.text((box[0] + 16, box[1] + 12), label, font=font(19, True), fill=GROUP_STROKE[key])

    def place(name, icon, cx, cy, label, sublabel=""):
        ic = load_icon(icon)
        img.paste(ic, (int(cx - ICON / 2), int(cy - ICON / 2)), ic)
        d.text((cx, cy + ICON / 2 + 8), label, font=font(18, True), fill=INK, anchor="ma")
        if sublabel:
            d.text((cx, cy + ICON / 2 + 32), sublabel, font=font(15), fill=MUTED, anchor="ma")
        nodes[name] = (cx, cy)

    # customer (outside cloud)
    place_cust_x, cust_y = 110, 560
    cust = load_icon("eum")  # stand-in device glyph
    d.rounded_rectangle((60, 500, 170, 640), radius=14, fill=(255, 246, 229), outline=AWS_ORANGE, width=2)
    d.text((115, 470), "Customer", font=font(19, True), fill=INK, anchor="ma")
    d.text((115, 620), "any phone", font=font(15), fill=MUTED, anchor="ma")
    img.paste(cust, (int(115 - ICON / 2), int(560 - ICON / 2)), cust)
    nodes["cust"] = (115, 560)

    # Channels group
    group_box("channels", "1) Channels — AWS End User Messaging (CDS)", (210, 300, 470, 820))
    place("rcs", "eum", 340, 400, "RCS / SMS", "End User Messaging")
    place("wa", "eum", 340, 560, "WhatsApp", "EUM Social")
    place("ses", "ses", 340, 720, "Amazon SES", "email")

    # Ingestion column
    place("sns", "sns", 640, 420, "Amazon SNS", "events")
    place("sqs", "sqs", 640, 620, "Amazon SQS", "queue")

    # Orchestrator (Lambda) center
    d.rounded_rectangle((820, 470, 1060, 660), radius=14, fill=(255, 255, 255), outline=INK, width=2)
    place("lambda", "lambda", 940, 540, "ClaimPilot Agent", "AWS Lambda")
    d.text((940, 628), "collect → email → code → file → follow-up", font=font(14), fill=MUTED, anchor="ma")

    # AI group
    group_box("ai", "4) AI & processing", (1140, 300, 1420, 620))
    place("bedrock", "bedrock", 1280, 400, "Amazon Bedrock", "Claude Sonnet 4.6")
    place("transcribe", "transcribe", 1280, 550, "Transcribe", "voice notes")

    # Data group
    group_box("data", "5) State & media", (1140, 680, 1420, 1000))
    place("ddb", "dynamodb", 1280, 780, "DynamoDB", "claims / phase")
    place("s3", "s3", 1280, 930, "Amazon S3", "media / cards")

    # arrows
    def arrow(a, b, label="", curve=0, color=ARROW):
        (x1, y1), (x2, y2) = nodes[a], nodes[b]
        # start/end at icon edges horizontally
        d.line([(x1 + ICON / 2, y1), (x2 - ICON / 2, y2)] if x2 > x1
               else [(x1 - ICON / 2, y1), (x2 + ICON / 2, y2)], fill=color, width=3)
        # arrowhead
        ex, ey = (x2 - ICON / 2, y2) if x2 > x1 else (x2 + ICON / 2, y2)
        dxs = -12 if x2 > x1 else 12
        d.polygon([(ex, ey), (ex - dxs, ey - 6), (ex - dxs, ey + 6)], fill=color)
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 14
            d.text((mx, my), label, font=font(15, True), fill=color, anchor="ma")

    arrow("cust", "rcs", "1")
    arrow("cust", "wa")
    arrow("rcs", "sns", "2")
    arrow("wa", "sns")
    arrow("sns", "sqs", "3")
    arrow("sqs", "lambda", "4")
    arrow("lambda", "bedrock", "5")
    arrow("lambda", "transcribe")
    arrow("lambda", "ddb", "6")
    arrow("lambda", "s3", "7")
    arrow("lambda", "ses", "8")
    arrow("rcs", "cust")  # reply back

    # legend / step key
    steps = ("1 inbound msg/photo/voice   2 SNS event   3 SQS   4 invoke agent   "
             "5 reason+vision   6 state   7 render card   8 email code+record   → reply")
    d.text((48, H - 30), steps, font=font(15), fill=MUTED)

    out = os.path.join(HERE, "claimpilot-architecture.png")
    img.save(out, "PNG")
    print("wrote", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
