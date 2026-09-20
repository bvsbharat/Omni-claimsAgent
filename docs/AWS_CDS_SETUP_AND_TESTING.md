# AWS CDS — Environment, Inventory & Testing Guide

Verified working on: Sep 19, 2026. Account **203918842720**, region **us-east-1**.

---

## 1. Environment fixes applied (important)

Two problems were found and fixed on this machine:

### 1a. The Homebrew AWS CLI is broken
`/opt/homebrew/bin/aws` crashes on every command:
```
Symbol not found: _XML_SetAllocTrackerActivationThreshold ... /usr/lib/libexpat.1.dylib
```
Cause: brew's Python 3.14 `pyexpat` is built expecting brew's newer libexpat, but is hardcoded to load the older macOS system `libexpat`. `brew reinstall python@3.14 / awscli` did **not** fix it (the link path is baked into the bottle).

**Fix:** installed the official standalone **AWS CLI v2** (no sudo) to the home dir:
- Binary: `/Users/bharatbvs/aws-cli/aws-cli/aws` (v2.36.49)

### 1b. Stale credential env vars
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` are set in the shell but invalid → `InvalidClientTokenId`. They override the good `aws login` session credentials (`~/.aws/login/`). Stripping them makes auth succeed.

### The wrapper — always use this
`scripts/awscds.sh` uses the working binary AND strips the bad env vars:
```bash
./scripts/awscds.sh sts get-caller-identity
./scripts/awscds.sh pinpoint-sms-voice-v2 describe-phone-numbers
```
Default region: us-east-1.

> Note: current identity is the account **root user** with `aws login` session creds. Root access keys are discouraged for real work — create an IAM user/role before going to production. Fine for hackathon testing.

---

## 2. CDS resource inventory (already provisioned 🎉)

The account is further along than expected. Account tier: **SANDBOX**.

### Phone numbers (`pinpoint-sms-voice-v2`)
| Number | Type | Status | Capabilities | Notes |
|---|---|---|---|---|
| `+12065558412` | SIMULATOR | **ACTIVE** | SMS | ✅ Use for SMS testing now |
| `+12065557997` | SIMULATOR | **ACTIVE** | SMS | ✅ Second simulator |
| `+18556966263` | TOLL_FREE | PENDING | SMS, VOICE | Two-way → SNS `cds-eum-events`; needs TF registration to send to real phones |
| `+18443724817` | TOLL_FREE | PENDING | MMS, SMS, VOICE | Needs TF registration |

### Registrations
| Type | Status |
|---|---|
| `US_TOLL_FREE_REGISTRATION` | CREATED (in progress — not yet approved) |
| `TEST_RCS_LAUNCH_REGISTRATION` | CREATED (RCS test-launch path started) |

### RCS
- A `TEST_RCS_LAUNCH_REGISTRATION` exists (status CREATED) but no RCS sender/agent is fully provisioned yet, and no number reports `RCS` capability. RCS test sending is **not ready yet** — the test-launch registration must complete first.

### WhatsApp (AWS End User Messaging Social)
- Linked WABA **`FNOL-Claim`** (`waba-26964a65f70442b2aa63f83f8a4404b1`), registration **COMPLETE**.
- Phone: **+1 408-462-1873** (`phone-number-id-c6422678213d4226becc4aa290a85dca`).
- Events → SNS `cds-whatsapp-events`. `marketingMessagesOnboardingStatus: PENDING_INTERNAL_SETUP`.
- ✅ WhatsApp is essentially ready for template/test sends to opted-in numbers.

### Config sets & events
- Configuration set: **`cds-hackathon`**
- SNS topics: `cds-eum-events` (SMS/RCS inbound + delivery), `cds-whatsapp-events` (WhatsApp inbound + status)

### Spend limits (SANDBOX — very low)
All monthly limits (TEXT/VOICE/MEDIA/NOTIFY/RCS) are **$1**. Fine for simulator testing; request increases + production access before demo volume.

---

## 3. How to test each channel

### 3a. SMS — works right now (simulator) ✅
Send from a simulator number to an AWS simulator destination (exercises the full send path, no registration, no real carrier delivery):
```bash
./scripts/awscds.sh pinpoint-sms-voice-v2 send-text-message \
  --destination-phone-number "+14254147755" \
  --origination-identity "+12065558412" \
  --message-body "ClaimPilot: I had an accident and need to file a claim." \
  --message-type TRANSACTIONAL
```
Simulator destination magic numbers:
- `+14254147755` → simulates **successful** delivery
- `+14254147167` → simulates a **failure/blocked** delivery
Returns a `MessageId` on success. ✅ Verified working.

**To test against your real phone:** the toll-free number must finish `US_TOLL_FREE_REGISTRATION`, OR add your own phone to the sandbox verified-destinations list, then send from the toll-free number.

### 3b. Receiving inbound SMS (two-way)
The toll-free number is two-way enabled → inbound texts publish to SNS `cds-eum-events`. To see them, subscribe a Lambda (or temporarily an email/SQS) to that topic. This is how ClaimPilot's `channel-router` will receive "I had an accident."

### 3c. RCS — not ready yet ⏳
The `TEST_RCS_LAUNCH_REGISTRATION` is CREATED but not complete; no RCS-capable sender exists yet. Once the RCS test launch completes and an RCS sender/phone is provisioned, send rich content with:
```bash
# (once an RCS sender id / origination is available)
./scripts/awscds.sh pinpoint-sms-voice-v2 send-rcs-message ...
```
Action item: finish the RCS test-launch registration in the console (End User Messaging → RCS).

### 3d. WhatsApp — ready ✅ (needs opted-in recipient + template)
Send via Social Messaging from the linked WABA number (+1 408-462-1873). WhatsApp requires an approved message template for business-initiated messages and an opted-in recipient. Example (template send):
```bash
./scripts/awscds.sh socialmessaging send-whatsapp-message \
  --origination-phone-number-id "phone-number-id-c6422678213d4226becc4aa290a85dca" \
  --meta-api-version "v20.0" \
  --message '{"messaging_product":"whatsapp","to":"<E164_RECIPIENT>","type":"template","template":{"name":"<approved_template>","language":{"code":"en_US"}}}'
```

### 3e. Email — SES (verify identities separately)
Not yet audited here. Next step: `./scripts/awscds.sh ses list-identities` / `sesv2 list-email-identities`, verify a domain/sender, and exit the SES sandbox for the demo.

---

## 4. Readiness summary for ClaimPilot

| Channel | State | Can test now? |
|---|---|---|
| SMS (send) | Simulator ACTIVE | ✅ Yes (simulator) |
| SMS (real phone) | Toll-free PENDING registration | ⏳ After TF registration / sandbox verify |
| SMS (inbound/two-way) | Wired to SNS `cds-eum-events` | ✅ Subscribe a consumer |
| RCS | Test-launch registration CREATED (incomplete) | ⏳ Finish RCS launch first |
| WhatsApp | WABA COMPLETE, number live | ✅ With template + opted-in recipient |
| SES email | Not audited | ⏳ Verify identity next |

---

## 5. Next actions
1. **Finish RCS test-launch registration** (console: End User Messaging → RCS) — this is the critical path for the rich-card FNOL flow.
2. **Complete US toll-free registration** so we can text real phones (or add verified sandbox destinations for the demo).
3. **Audit + verify SES identity**; request production access.
4. **Raise sandbox spend limits** ahead of the demo.
5. Wire a Lambda subscriber to `cds-eum-events` to receive inbound SMS (start of the ClaimPilot channel-router).

---

## 6. Live test results (Sep 19–20, 2026)

### WhatsApp — ✅ WORKING end-to-end to a real phone
Proven two-way conversation with `+1-224-659-8896` via WABA number `+1 408-462-1873`:
- **Inbound:** user's "File a claim" message received via SNS `cds-whatsapp-events` → SQS `cds-whatsapp-events-debug`.
- **Outbound (free-form):** replies delivered successfully once the user opened the 24-hour customer-service window by messaging the business first. `messageId`s returned, no failure callbacks.
- **Delivery diagnostics** come back on the events queue. Two error codes we hit and what they mean:
  - `132001` — template not usable (was PENDING / not approved).
  - `131047` — free-form text sent outside the 24-hour window (before the user messaged first).

**How to reproduce a WhatsApp reply (inside 24h window):**
```bash
MSG='{"messaging_product":"whatsapp","recipient_type":"individual","to":"+1XXXXXXXXXX","type":"text","text":{"body":"..."}}'
B64=$(printf '%s' "$MSG" | base64)
./scripts/awscds.sh socialmessaging send-whatsapp-message \
  --origination-phone-number-id "phone-number-id-c6422678213d4226becc4aa290a85dca" \
  --meta-api-version "v20.0" --message "$B64"
```
Note: `--message` is a base64 blob of Meta's message JSON. Use E.164 with `+` for `to`.

### WhatsApp templates — cleaned up + new UTILITY template submitted
- Deleted the two bad `MARKETING` templates (`welcome`, `fnol_test_hello`) that were stuck PENDING and rejected by Meta.
- Created **`claim_started`** (category **UTILITY**, `en_US`, metaTemplateId `1093493396397797`) — definition in `infra/whatsapp/claim_ack_template.json`. UTILITY transactional templates approve fast. Poll status:
```bash
./scripts/awscds.sh socialmessaging list-whatsapp-message-templates \
  --id waba-26964a65f70442b2aa63f83f8a4404b1 \
  --query 'templates[].{name:templateName,status:templateStatus,cat:templateCategory}' --output table
```
Once `APPROVED`, ClaimPilot can *initiate* WhatsApp conversations (outside the 24h window).

### SMS — still blocked for real phones (both paths have lead time)
- Outbound to a real phone in SANDBOX requires the destination to be OTP-verified first. `+12246598896` is registered but PENDING; its daily verification-code quota (`VERIFICATION_ATTEMPTS_PER_DAY`, shared across TEXT+VOICE) is exhausted — resets ~24h.
- The toll-free number `+18556966263` registration is in **DRAFT** (never submitted). Toll-free carrier approval typically takes 1–3 weeks.
- ✅ Simulator send path works (to AWS magic numbers only, not real phones).

**To unblock SMS to your phone, pick one:**
1. Wait for the daily OTP quota reset, then re-run verification (I'll send the code, you enter it).
2. Submit the toll-free registration (company + use-case fields) and wait for carrier approval.
3. Request SANDBOX → production access for End User Messaging SMS (removes verified-destination requirement).

### RCS — not ready
`TEST_RCS_LAUNCH_REGISTRATION` still CREATED/incomplete; no RCS-capable sender. Finish in console.

### Updated readiness

| Channel | To a real phone now? | Blocker / next step |
|---|---|---|
| **WhatsApp (reply in 24h window)** | ✅ Yes | None — works today |
| WhatsApp (business-initiated) | ⏳ | `claim_started` template awaiting Meta approval |
| SMS | ❌ | OTP quota reset, OR toll-free registration, OR production access |
| RCS | ❌ | Finish RCS test-launch registration |
| SES email | ⏳ | Not audited yet |
