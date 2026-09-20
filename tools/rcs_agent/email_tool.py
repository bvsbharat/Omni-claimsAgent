"""SES email tool for ClaimPilot.

Two emails in the FNOL workflow:
  1. confirmation-code email  (Stage 1 consent gate: user must confirm before filing)
  2. claim-filed email        (Stage 2: formal record with claim number + settlement)

Sender is a verified SES identity (uibharat@gmail.com). SES account is in
production (can send to any recipient). All sends are best-effort: a failure is
logged and returned, never raised, so the claim flow is never broken by email.
"""
from __future__ import annotations

import os
from typing import Any

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
SENDER = os.environ.get("SES_SENDER", "ClaimPilot Claims <uibharat@gmail.com>")

_ses = boto3.client("sesv2", region_name=REGION)


def _send(to: str, subject: str, html: str, text: str) -> dict:
    try:
        resp = _ses.send_email(
            FromEmailAddress=SENDER,
            Destination={"ToAddresses": [to]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject},
                    "Body": {
                        "Html": {"Data": html},
                        "Text": {"Data": text},
                    },
                }
            },
        )
        return {"ok": True, "messageId": resp.get("MessageId", "")}
    except Exception as exc:  # noqa: BLE001 - email must never break the flow
        print({"sesError": str(exc), "to": to, "subject": subject})
        return {"ok": False, "error": str(exc)}


def _shell(title: str, body_html: str) -> str:
    return f"""\
<!doctype html><html><body style="margin:0;background:#f4f5f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<div style="max-width:560px;margin:0 auto;padding:24px">
  <div style="background:#1A56DB;border-radius:14px 14px 0 0;padding:22px 28px">
    <div style="color:#fff;font-size:22px;font-weight:700">ClaimPilot</div>
    <div style="color:#d6e2ff;font-size:13px;margin-top:2px">{title}</div>
  </div>
  <div style="background:#fff;border-radius:0 0 14px 14px;padding:28px;color:#18181b;font-size:15px;line-height:1.6">
    {body_html}
    <p style="color:#71717a;font-size:12px;margin-top:28px">This is an automated message from ClaimPilot. A human adjuster will follow up.</p>
  </div>
</div></body></html>"""


def send_confirmation_code(to: str, code: str, slots: dict[str, Any]) -> dict:
    summary = _slots_html(slots)
    subject = "Confirm your ClaimPilot claim"
    html = _shell("Confirm your claim", f"""
      <p>We're ready to file your auto claim. To authorize it, reply in your chat with this code:</p>
      <div style="font-size:34px;font-weight:800;letter-spacing:6px;color:#1A56DB;
                  background:#f0f5ff;border-radius:12px;padding:18px 0;text-align:center;margin:18px 0">{code}</div>
      <p style="color:#71717a;font-size:13px">Code expires in 15 minutes. If you didn't request this, ignore this email.</p>
      <h3 style="margin:24px 0 8px">Claim details</h3>{summary}""")
    text = (f"Confirm your ClaimPilot claim.\nReply in chat with this code: {code}\n"
            f"(expires in 15 minutes)\n\nDetails:\n{_slots_text(slots)}")
    return _send(to, subject, html, text)


def send_claim_filed(to: str, claim_number: str, slots: dict[str, Any], settlement: dict) -> dict:
    summary = _slots_html(slots)
    subject = f"Your claim {claim_number} is filed"
    html = _shell(f"Claim {claim_number} filed", f"""
      <p>Your claim has been filed. Keep this email for your records.</p>
      <div style="background:#f0f5ff;border-radius:12px;padding:16px 20px;margin:14px 0">
        <div style="color:#71717a;font-size:12px;font-weight:700">CLAIM NUMBER</div>
        <div style="color:#1A56DB;font-size:26px;font-weight:800">{claim_number}</div>
      </div>
      <h3 style="margin:22px 0 8px">Estimated settlement</h3>
      <table style="width:100%;font-size:15px;border-collapse:collapse">
        <tr><td style="color:#71717a;padding:4px 0">Estimated repair</td><td style="text-align:right">${settlement['estimate']:,}</td></tr>
        <tr><td style="color:#71717a;padding:4px 0">Deductible</td><td style="text-align:right">-${settlement['deductible']:,}</td></tr>
        <tr><td style="font-weight:700;padding:8px 0;border-top:1px solid #e4e4e7">Estimated payout</td>
            <td style="text-align:right;font-weight:700;border-top:1px solid #e4e4e7">${settlement['payout']:,}</td></tr>
      </table>
      <p style="color:#71717a;font-size:13px">Estimate only, pending adjuster review.</p>
      <h3 style="margin:22px 0 8px">Claim details</h3>{summary}
      <p style="margin-top:20px">Next, we'll help you schedule an adjuster and choose a repair shop — reply in chat to continue.</p>""")
    text = (f"Claim {claim_number} filed.\n\nEstimated payout: ${settlement['payout']:,} "
            f"(repair ${settlement['estimate']:,} - deductible ${settlement['deductible']:,})\n\n"
            f"Details:\n{_slots_text(slots)}\n\nReply in chat to schedule an adjuster and repair shop.")
    return _send(to, subject, html, text)


def _slots_html(slots: dict) -> str:
    rows = [
        ("What happened", slots.get("what")),
        ("When", slots.get("when")),
        ("Where", slots.get("where")),
        ("Damage", slots.get("damage")),
    ]
    cells = "".join(
        f'<tr><td style="color:#71717a;padding:4px 12px 4px 0;vertical-align:top;white-space:nowrap">{k}</td>'
        f'<td style="padding:4px 0">{v or "-"}</td></tr>'
        for k, v in rows
    )
    return f'<table style="width:100%;font-size:14px;border-collapse:collapse">{cells}</table>'


def _slots_text(slots: dict) -> str:
    return "\n".join(
        f"- {k}: {slots.get(v) or '-'}"
        for k, v in [("What", "what"), ("When", "when"), ("Where", "where"), ("Damage", "damage")]
    )
