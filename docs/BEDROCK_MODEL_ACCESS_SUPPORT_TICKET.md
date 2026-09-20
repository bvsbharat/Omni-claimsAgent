# AWS Support Ticket — Bedrock Claude 5 / frontier model access

Ready to submit. Because this account is on **Basic Support**, the AWS Support API
(`aws support ...`) cannot open the case — file it through the **AWS Console**:

**Console → Support → Create case → "Looking for service limit increases?" / "Account and billing"**
(For model access specifically: **Amazon Bedrock console → Model access → Request model access**;
if the models show as unavailable/greyed there, open the support case below.)

---

## Case type
Service: **Amazon Bedrock**
Category: **Models / Model access**
Severity: General guidance (or highest your plan allows)

## Subject
Request access to Anthropic Claude 5 (Opus 5, Sonnet 5, Fable 5) foundation models — denied account-wide across all US regions

## Description (paste this)

Account ID: **203918842720**
Primary region: **us-east-1** (also tested us-east-2, us-west-2)

We are building an agentic application for the **AWS Communication Developer Services (CDS)
Agentic AI Partner Hackathon** (AWS End User Messaging + Amazon Bedrock AgentCore). We would
like access to the latest Anthropic Claude 5 generation models on Amazon Bedrock.

**Problem:** Invoking the Claude 5 models returns `AccessDeniedException` — "is not available
for this account ... contact AWS Sales" — in **every US region we tested**, using both the raw
model IDs and the `us.` cross-region inference profiles.

**Diagnostics we have already performed:**

1. `bedrock get-foundation-model-availability` reports these models as
   `authorizationStatus: AUTHORIZED`, `agreementAvailability: AVAILABLE`,
   `entitlementAvailability: AVAILABLE`, `regionAvailability: AVAILABLE` — yet invocation is denied.
2. `bedrock create-foundation-model-agreement` for each model returns
   **"Agreement already exists"** — so the model-access agreement is already accepted;
   the block is not at the agreement level.
3. Invocation denied across **us-east-1, us-east-2, and us-west-2** (so it is not a
   region-mismatch / inference-profile-region issue).
4. The **Claude 4 generation works fine** in all three regions (Opus 4.6/4.7/4.8,
   Sonnet 4.6/4.5, Haiku 4.5) — so general Bedrock access and IAM are healthy.
5. Caller identity is the account root user (no restrictive IAM policy in play).

**Exact error:**
```
AccessDeniedException when calling the Converse operation:
anthropic.claude-opus-5 is not available for this account.
... For additional access options, contact AWS Sales ...
```

**Request:** Please enable account-level entitlement for the following models (us-east-1,
and us-west-2 if applicable):
- `anthropic.claude-opus-5`
- `anthropic.claude-sonnet-5`
- `anthropic.claude-fable-5`
(and, if available to us, `openai.gpt-5.6-terra`)

Use case: AI claims-intake agent (insurance FNOL) over AWS End User Messaging (SMS/RCS/WhatsApp)
orchestrated with Amazon Bedrock AgentCore, for the AWS CDS hackathon. Expected volume is low
(prototype/demo). Standard usage-based pricing is acceptable.

Please advise whether this requires an AWS Sales/enterprise entitlement, an account-tier change,
or a specific allow-list action on your side.

---

## Evidence appendix (commands to reproduce)

```bash
# 1. Availability API says AUTHORIZED (misleading):
aws bedrock get-foundation-model-availability --region us-east-1 --model-id anthropic.claude-opus-5

# 2. Agreement already exists:
aws bedrock create-foundation-model-agreement --region us-east-1 \
  --model-id anthropic.claude-opus-5 --offer-token <token>
# -> ValidationException: Could not create agreement - Agreement already exists

# 3. Invoke denied in every US region:
for r in us-east-1 us-east-2 us-west-2; do
  aws bedrock-runtime converse --region $r --model-id us.anthropic.claude-opus-5 \
    --messages '[{"role":"user","content":[{"text":"hi"}]}]'
done
# -> AccessDeniedException: anthropic.claude-opus-5 is not available for this account

# 4. Claude 4.x works everywhere (control):
aws bedrock-runtime converse --region us-east-1 --model-id us.anthropic.claude-opus-4-6-v1 \
  --messages '[{"role":"user","content":[{"text":"hi"}]}]'   # -> 200 OK
```

---

## Findings summary (why the ticket, not a self-serve fix)

| Check | Result |
|---|---|
| Region mismatch? | ❌ No — denied in us-east-1, us-east-2, us-west-2 alike |
| Inference profile needed? | ❌ No — denied with both bare ID and `us.` profile |
| Agreement not accepted? | ❌ No — "Agreement already exists" |
| IAM restriction? | ❌ No — root user; Claude 4.x works |
| Conclusion | **Account-level entitlement gate — requires AWS Sales/Support to lift** |

## Meanwhile (unblocked path for the build)
Use the Claude 4 generation via `us.` inference profiles — full access confirmed:
- `us.anthropic.claude-opus-4-6-v1` (top reasoning)
- `us.anthropic.claude-sonnet-4-6` / `us.anthropic.claude-sonnet-4-5-20250929-v1:0` (agent default)
- `us.anthropic.claude-haiku-4-5-20251001-v1:0` (cheap/fast)
