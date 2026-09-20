# ClaimPilot Agent — Staged Omnichannel FNOL Workflow

The ClaimPilot agent runs a **secure, staged First Notice of Loss (FNOL) claim
workflow** over AWS Communication Developer Services. One agent brain serves
**RCS, SMS, and WhatsApp**, with **SES email** as an authorization + record channel.

## The workflow (5 phases)

```
 collecting ──▶ awaiting_email ──▶ awaiting_code ──▶ filed ──▶ followup
     │                │                  │              │           │
 gather what/     ask for the       SES emails a     verify code  adjuster +
 when/where/      customer's        6-digit code;    -> file      repair-shop
 damage (text,    email to          user replies     claim +      scheduling
 photo, voice)    authorize         it in chat       settlement   (WhatsApp)
```

1. **collecting** — The agent (Amazon Bedrock, Claude Sonnet 4.6) conversationally
   collects the four claim slots: `what`, `when`, `where`, `damage`. It understands
   **text, photos** (Bedrock vision damage assessment), **voice notes**
   (Amazon Transcribe), and **uploaded documents** — PDFs or images of a police
   report / repair estimate / license are OCR'd with **Amazon Textract** and the
   claim-relevant fields are extracted and folded into the claim.
2. **awaiting_email** — Once all slots are filled, the agent does NOT file yet. It
   asks for the customer's email address to authorize the claim.
3. **awaiting_code** — A **6-digit code is emailed via SES**. The customer replies
   with the code in chat. Wrong codes are re-prompted; after 4 misses a new code is
   sent. This is the secure consent gate — nothing is filed without confirmation.
4. **filed** — On a correct code, the claim is filed:
   - a **claim number** (`CLM-XXXXXX`) is generated,
   - a **simulated settlement** is computed (estimate − deductible = payout),
   - the customer receives the claim number + settlement on their **messaging
     channel** (text + compact rich confirmation card) **and** a formal **SES
     confirmation email**.
5. **followup** — Post-filing, the agent helps schedule an adjuster and choose a
   repair shop / rental / tow by location preference (omnichannel; WhatsApp-friendly).

State is persisted in DynamoDB per `channel:phone`, so a conversation can pause and
resume, and RCS vs WhatsApp sessions are tracked separately.

## Architecture (files)

| File | Role |
|---|---|
| `lambda_function.py` | Phase orchestrator + SQS handler (channel-agnostic) |
| `channels.py` | RCS + WhatsApp adapters (`parse`, `send_text`, `send_confirmation`) |
| `claim_agent.py` | Bedrock FNOL slot-filling brain, photo vision, email/code helpers |
| `media.py` | Routes attachments: image vision / audio transcription / document OCR |
| `ocr.py` | Amazon Textract OCR (sync for images, async for multi-page PDFs) → text + form fields |
| `email_tool.py` | SES emails: confirmation code + filed confirmation (sender `uibharat@gmail.com`) |
| `settlement.py` | Simulated settlement estimator (severity → payout) |
| `confirmation_image.py` | Branded 2:1 confirmation thumbnail → S3 |
| `deploy.sh` | Idempotent deploy (table, role, Lambda, RCS + WhatsApp SQS sources) |

## AWS resources

| Resource | Name |
|---|---|
| Lambda | `claimpilot-rcs-agent` (python3.12, arm64, bundled Pillow + current boto3) |
| DynamoDB | `claimpilot-claims` (key `phone` = `channel:number`) |
| S3 | `claimpilot-rcs-media-<account>` (`inbound/`, `confirmations/`) |
| RCS agent | `rcs-f9a76b2b8448418fb9ae6747622beaa6` (TESTING) |
| WhatsApp | WABA `FNOL-Claim`, sender `+1 408-462-1873` |
| SES sender | `uibharat@gmail.com` (verified; account has production access) |
| Bedrock | `us.anthropic.claude-sonnet-4-6` + Guardrail `claimpilot-guardrail` v1 |
| Transcribe / Textract | on-demand (voice → text, document OCR) |

## Deploy

```bash
./tools/rcs_agent/deploy.sh
```

Idempotent: creates/updates the table, IAM role (Bedrock, sms-voice,
social-messaging, transcribe, ses, s3, dynamodb, sqs, logs), the Lambda, and wires
both the RCS and WhatsApp SQS event sources.

## Test the end-to-end flow

### Option A — from a real device (the real demo)
RCS: message the ClaimPilot agent from a **registered test device**. WhatsApp:
message the FNOL-Claim business number (`+1 408-462-1873`) to open the 24-hour window.

Walk the phases:
1. "Another car backed into mine, I need to file a claim" → agent checks safety.
2. "Everyone's safe." → agent asks what happened.
3. Give what/when/where/damage (a sentence like *"today ~3pm at Santana Row garage,
   San Jose; rear bumper dented and cracked, moderate"*). Optionally send a **photo**
   or a **voice note**.
4. Agent asks for your **email** → reply with it.
5. Check your inbox for the **6-digit code** → reply with it in chat.
6. Agent files the claim → you get the **claim number + settlement** in chat (rich
   card) and a **filed confirmation email**.
7. Reply about an adjuster / repair shop location → agent helps schedule.

Watch it live:
```bash
./scripts/awscds.sh logs tail /aws/lambda/claimpilot-rcs-agent --follow --region us-east-1
```

### Option B — simulate inbound events (no device needed)
Inject synthetic RCS inbound events straight into the deployed Lambda. Each call is
one customer turn.

```bash
PHONE="+12246598896"          # a VERIFIED destination / registered test device
ARN="arn:aws:sms-voice:us-east-1:203918842720:rcs-agent/rcs-f9a76b2b8448418fb9ae6747622beaa6"

send() {  # send one customer message through the agent
  python3 - "$1" <<'PY' > /tmp/e.json
import json,sys
m=json.dumps({"originationNumber":"+12246598896","destinationNumber":"rcs-x","messageBody":sys.argv[1]})
s=json.dumps({"Type":"Notification","TopicArn":"arn:aws:sns:us-east-1:203918842720:cds-eum-events","Message":m})
print(json.dumps({"Records":[{"body":s}]}))
PY
  ./scripts/awscds.sh lambda invoke --region us-east-1 \
    --function-name claimpilot-rcs-agent --payload fileb:///tmp/e.json /tmp/o.json >/dev/null
  echo "sent: $1"
}

# reset this caller's state
./scripts/awscds.sh dynamodb delete-item --region us-east-1 \
  --table-name claimpilot-claims --key '{"phone":{"S":"rcs:+12246598896"}}'

# phase 1: collect
send "Another car backed into mine, I need to file a claim"
send "Everyone's safe, no injuries"
send "Today around 3pm at Santana Row garage in San Jose; rear bumper dented and cracked, moderate"

# phase 2: email consent gate
send "My email is uibharat@gmail.com"

# read the emailed code from state (in the real flow, read it from the inbox)
CODE=$(./scripts/awscds.sh dynamodb get-item --region us-east-1 \
  --table-name claimpilot-claims --key '{"phone":{"S":"rcs:+12246598896"}}' \
  --query 'Item.code.S' --output text)
echo "emailed code: $CODE"

# phase 3->4: verify + file
send "$CODE"

# phase 5: follow-up
send "Please schedule an adjuster and a repair shop near downtown San Jose"

# inspect the filed claim
./scripts/awscds.sh dynamodb get-item --region us-east-1 \
  --table-name claimpilot-claims --key '{"phone":{"S":"rcs:+12246598896"}}' \
  --query 'Item.{phase:phase.S,claim:claim_number.S,settlement:settlement.M}'
```

Expected end state: `phase=followup`, a `claim` number, and a settlement
(`estimate`, `deductible`, `payout`). A confirmation image appears at
`s3://claimpilot-rcs-media-<account>/confirmations/<claim>.png`, and the filed
email is sent to the address you provided.

## Security & robustness

Patterns adopted from the AWS reference samples
([Chat Orchestrator](https://github.com/aws-samples/sample-chat-orchestrator-for-generative-ai-conversations),
[GenAI Email Categorization](https://github.com/aws-samples/sample-gen-ai-email-categorization-using-ses-mail-manager)):

| Control | Implementation |
|---|---|
| **Amazon Bedrock Guardrails** | `claimpilot-guardrail` (v1) on every `converse()` call — blocks **prompt injection** (PROMPT_ATTACK), hate/insults/sexual/misconduct, and **PII** (blocks card numbers / SSN / passwords, anonymizes bank accounts). Verified: injection → `guardrail_intervened` + safe deflection. |
| **Consent gate before filing** | Claim is filed only after the customer confirms a **6-digit code emailed via SES** (in-channel authorization). |
| **SQS Dead Letter Queues** | `cds-eum-events-dlq` / `cds-whatsapp-events-dlq` with `maxReceiveCount=3` — poison messages stop retrying (this is what caused an earlier infinite loop). |
| **Non-user event filtering** | `channels.WhatsAppChannel.parse()` drops delivery/status events (returns `None`) — the AWS "channel trigger" pattern; only real inbound messages invoke the agent. |
| **DynamoDB TTL** | Conversation/claim state auto-expires after 7 days (`ttl` attribute) — privacy + cost. |
| **AI disclosure** | The agent discloses it is an AI on first contact (EU AI Act Article 50 style). |
| **Least-privilege IAM** | Bedrock scoped to `foundation-model/*` + `inference-profile/*`; `bedrock:ApplyGuardrail` scoped to `guardrail/*`; S3/DynamoDB/SQS scoped to the specific resources. |

Production next steps (per AWS guidance): enable **Bedrock model-invocation logging**,
**CloudWatch alarms** on the DLQs, **Amazon Macie** on the media bucket, and
**Amazon Comprehend** for deeper PII redaction.

## Notes
- **Consent gate = reply-with-code** (in-channel authorization; no public endpoint).
- **Settlement is simulated** for the demo (not a real actuarial quote).
- SES sender is `uibharat@gmail.com`. To send from `@simkit.ai`, verify that domain
  in SES (DNS/DKIM) and update `SES_SENDER`.
- The same Lambda serves RCS + WhatsApp; the flow is identical on both channels.
