# WhatsApp Templates — ClaimPilot

WABA: `FNOL-Claim` (`waba-26964a65f70442b2aa63f83f8a4404b1`)
Sender: `+1 408-462-1873` (`phone-number-id-c6422678213d4226becc4aa290a85dca`)

## Why templates matter
WhatsApp lets a business send **free-form** messages only inside a 24-hour window that opens
when the customer messages the business first. To *initiate* a conversation (the real ClaimPilot
demo — reaching out to the policyholder), you must use a **Meta-approved message template**.

## Approval strategy (what gets approved fast)
Meta reviews templates by **category**:
- **UTILITY** — transactional, tied to an existing relationship/action (order updates, appointments,
  account/claim status). Approves quickly and reliably. ← we use this.
- **MARKETING** — promotional. More scrutiny, slower, easier to reject.

Our earlier `welcome` / `fnol_test_hello` were MARKETING and stayed stuck PENDING, so they were deleted.

### Rules we followed to maximize approval odds
1. **Category = UTILITY** and the copy reads as transactional (a claim the customer initiated).
2. **No promotional language** (no discounts, offers, marketing hooks).
3. **Named variables with examples** so Meta's reviewer can render the template.
4. **Clear opt-out** in the footer ("Reply STOP to opt out").
5. **Quick-reply buttons** that map to the flow ("Start claim", "Talk to an agent").
6. Concise body, no ALL-CAPS, no excessive punctuation/emojis.

## Current template: `claim_started`
- Category: UTILITY · Language: en_US · metaTemplateId: `1093493396397797`
- Definition: `claim_ack_template.json`
- Body: `Hi {{1}}, this is ClaimPilot from {{2}}. We've received your request to start an insurance
  claim. Reply START to continue and I'll guide you through it in a few quick steps.`
- Variables: `{{1}}` = customer first name, `{{2}}` = insurer/brand name.

## Commands

Check status:
```bash
./scripts/awscds.sh socialmessaging list-whatsapp-message-templates \
  --id waba-26964a65f70442b2aa63f83f8a4404b1 \
  --query 'templates[].{name:templateName,status:templateStatus,cat:templateCategory}' --output table
```

Send once APPROVED (business-initiated):
```bash
MSG='{"messaging_product":"whatsapp","recipient_type":"individual","to":"+1XXXXXXXXXX","type":"template","template":{"name":"claim_started","language":{"code":"en_US"},"components":[{"type":"body","parameters":[{"type":"text","text":"Alex"},{"type":"text","text":"Acme Insurance"}]}]}}'
B64=$(printf '%s' "$MSG" | base64)
./scripts/awscds.sh socialmessaging send-whatsapp-message \
  --origination-phone-number-id "phone-number-id-c6422678213d4226becc4aa290a85dca" \
  --meta-api-version "v20.0" --message "$B64"
```

Recreate the template if needed:
```bash
B64=$(base64 < infra/whatsapp/claim_ack_template.json)
./scripts/awscds.sh socialmessaging create-whatsapp-message-template \
  --id waba-26964a65f70442b2aa63f83f8a4404b1 --template-definition "$B64"
```

## If Meta rejects it
- Read the rejection reason: `get-whatsapp-message-template`.
- Common fixes: remove anything promotional, ensure variables have examples, keep it clearly
  transactional. Then delete + recreate, or `update-whatsapp-message-template`.
