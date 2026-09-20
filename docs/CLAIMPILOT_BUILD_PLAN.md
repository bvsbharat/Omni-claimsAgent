# ClaimPilot — Agentic FNOL Insurance Claims Agent

**Full build plan for the AWS CDS Agentic AI Hackathon**
Deadline: Oct 28, 2026 · Target prizes: Grand ($18K) + Best of WhatsApp ($10K)

---

## 1. The pitch (30 seconds)

**ClaimPilot** turns insurance First Notice of Loss (FNOL) from a multi-day phone/portal ordeal into a claim that is filed, triaged, and serviced in **under 3 minutes** — entirely inside the customer's default messaging app, on the channel they prefer.

A policyholder texts *"I had an accident."* An AI agent (Amazon Bedrock AgentCore) verifies their policy, switches them to **verified-sender RCS** to collect photos, GPS location, and structured damage details through rich cards, uses Bedrock vision to assess severity and flag fraud, books a tow and rental with a tap, and emails a formal claim record via SES — while remembering the entire conversation across channels and days.

**Why insurers care:** FNOL is the single most expensive, slowest, most fraud-prone moment in the claims lifecycle. ClaimPilot compresses intake from days to minutes, cuts adjuster workload, and catches fraud earlier — a repeatable AWS Marketplace offering for any carrier.

---

## 2. How this maps to the judging criteria

| Criterion | Weight | How ClaimPilot scores |
|---|---|---|
| Technical Execution | 40% | 4 CDS channels (RCS + SMS + SES + WhatsApp), AgentCore doing real multi-step work (Memory, Gateway tools, vision), full IaC via CDK → reproducible. |
| Potential Value / Impact | 20% | Measurable: intake time (days→min), adjuster hours saved, fraud caught, CSAT. Every P&C carrier is a customer. |
| Demo Presentation | 20% | One continuous take: accident → filed claim + booked tow + email confirmation. Visual, clear before/after. |
| Creativity | 10% | Verified-sender RCS as an anti-fraud trust layer; cross-channel memory handoff. |
| Functionality | 10% | Reliable, scalable serverless; AI genuinely replaces manual intake. |

---

## 3. Architecture

### 3.1 High-level flow

```
                        ┌─────────────────────────────────────────────┐
   Customer phone       │              AWS Cloud (IaC / CDK)           │
   (any device)         │                                             │
      │                 │   ┌──────────────────────────────────────┐  │
      │  1. SMS          │   │  AWS End User Messaging (CDS)         │  │
      │  "I had an       │   │   • SMS  • RCS  • WhatsApp (Social)   │  │
      │   accident"      │   │   • SES (email)                      │  │
      ├─────────────────────▶│                                      │  │
      │                 │   └───────────────┬──────────────────────┘  │
      │                 │        inbound event (SNS / EventBridge)     │
      │                 │                    ▼                         │
      │                 │        ┌───────────────────────┐            │
      │                 │        │ Lambda: channel-router │            │
      │                 │        │ (normalize inbound msg)│            │
      │                 │        └───────────┬───────────┘            │
      │                 │                    ▼                         │
      │                 │   ┌──────────────────────────────────────┐  │
      │  2. RCS rich     │   │  Amazon Bedrock AgentCore (the brain)│  │
      │  cards / photos  │   │  • Runtime (Strands agent)           │  │
      │◀────────────────────│  • Memory (claim state across        │  │
      │  tap-to-share    │   │    channels + days)                  │  │
      │  location        │   │  • Gateway → tools (Lambdas below)   │  │
      │                 │   └───────┬──────────────┬───────────────┘  │
      │                 │           │              │                  │
      │                 │   ┌───────▼─────┐ ┌──────▼──────────────┐   │
      │  3. tap: book    │   │ Tool: policy│ │ Tool: damage assess │   │
      │     tow/rental   │   │ lookup      │ │ (Bedrock vision on  │   │
      │◀────────────────────│ (DynamoDB)  │ │  S3 photos)         │   │
      │                 │   └─────────────┘ └─────────────────────┘   │
      │                 │   ┌─────────────┐ ┌─────────────────────┐   │
      │  4. SES email    │   │ Tool: book  │ │ Tool: fraud signals │   │
      │     claim summary│   │ tow/rental  │ │ (rules + Bedrock)   │   │
      │◀────────────────────│ (mock API)  │ │                     │   │
      │                 │   └─────────────┘ └─────────────────────┘   │
      │                 │                                             │
      │                 │   Data: DynamoDB (claims/policies)          │
      │                 │         S3 (accident photos)                │
      │                 └─────────────────────────────────────────────┘
```

### 3.2 Component responsibilities

| Component | Service | Role |
|---|---|---|
| Inbound ingress | AWS End User Messaging (SMS/RCS/WhatsApp) + SNS/EventBridge | Receives two-way messages, emits events. |
| Channel router | Lambda | Normalizes inbound payloads from any channel into a common schema; invokes the agent; picks the best outbound channel (RCS if capable, else SMS; WhatsApp per preference). |
| Agent brain | Bedrock AgentCore Runtime (Strands) | Multi-turn reasoning, decides next action, calls tools. |
| Conversation state | AgentCore Memory (long + short term) | Remembers claim progress across channels and days — the brief's "pick up where the last conversation left off." |
| Tool access | AgentCore Gateway | Secure, governed access to the tool Lambdas. |
| Policy lookup | Lambda + DynamoDB | Verify policyholder, coverage, deductible. |
| Damage assessment | Lambda + Bedrock vision | Score severity + estimate from S3 photos. |
| Fraud signals | Lambda (rules + Bedrock) | Inconsistency/duplicate/anomaly flags. |
| Booking | Lambda (mock tow/rental API) | Tap-to-book actions from RCS suggestions. |
| Outbound formal record | Amazon SES | Emails claim summary + next steps. |
| Storage | DynamoDB + S3 | Claims/policies; accident photos. |

### 3.3 Channel selection logic
1. Check recipient RCS capability → if capable, use **RCS** (rich cards, photo upload, tap-to-share-location, suggested actions).
2. Else fall back to **SMS** (plain prompts, link to a hosted upload page).
3. Honor explicit customer preference for **WhatsApp** (international / preference).
4. Always send the **SES** formal record at claim completion.

---

## 4. The agentic conversation (demo script backbone)

| Turn | Channel | Customer | ClaimPilot (agent) |
|---|---|---|---|
| 1 | SMS | "I was just in a car accident" | Confirms identity, reassures, asks if everyone is safe. Verifies policy via tool. |
| 2 | RCS | (taps "Start claim") | Sends rich card: "Share your location" (tap-to-share GPS) + "Add photos of the damage." |
| 3 | RCS | Shares location + uploads 3 photos | Vision tool scores damage = moderate; estimates repair band; runs fraud signals (clean). |
| 4 | RCS | (reviews) | Carousel: "Book a tow" / "Reserve a rental" / "Talk to a human." Customer taps Book tow. |
| 5 | RCS | (taps "Book tow") | Booking tool confirms tow ETA + rental; agent summarizes claim number + next steps. |
| 6 | SES | — | Formal email: claim #, damage summary, tow/rental confirmations, adjuster contact, timeline. |
| 7 | WhatsApp | (international variant) | Same flow, demonstrating channel flexibility + Meta prize eligibility. |

**Memory beat for the demo:** close the app, reopen next day, text "any update?" — agent recalls the exact claim state. This visibly demonstrates AgentCore Memory.

---

## 5. Tech stack decisions

- **Agent framework:** Strands (AWS-native, tightest AgentCore integration, most samples). Scaffolded via the AgentCore CLI.
- **Model:** Claude Sonnet 4.5 for reasoning; a vision-capable Bedrock model for photo assessment. (Model set in `app/<AgentName>/model/load.py`.)
- **Memory:** `longAndShortTerm` — required for cross-session claim continuity (only works after deploy, not in `agentcore dev`).
- **IaC:** AgentCore CLI manages its own CDK; add a separate CDK app (or SAM) for the CDS wiring (messaging event sources, Lambdas, DynamoDB, S3, SES). Everything reproducible for judging + Marketplace.
- **Language:** Python for agent + tool Lambdas.

---

## 6. Repository layout (proposed)

```
AWS-FNOL-SMS/
├── docs/
│   ├── HACKATHON_IDEAS.md
│   ├── CLAIMPILOT_BUILD_PLAN.md      ← this file
│   ├── ARCHITECTURE.md               ← diagram + text description (submission artifact)
│   └── DEMO_SCRIPT.md                ← 3-min video script
├── agentcore/                        ← created by `agentcore create`
│   └── ...                           ← agent config + its CDK (auto-managed)
├── app/
│   └── ClaimPilot/
│       ├── main.py                   ← Strands agent: system prompt, tool wiring
│       └── model/load.py             ← model selection
├── infra/                            ← CDK app for CDS + data plane
│   ├── messaging_stack.py            ← EUM event sources, SNS/EventBridge, SES
│   ├── data_stack.py                 ← DynamoDB (claims/policies), S3 (photos)
│   └── tools_stack.py                ← tool Lambdas + Gateway targets
├── tools/                            ← tool Lambda source
│   ├── policy_lookup/
│   ├── damage_assess/
│   ├── fraud_signals/
│   ├── booking/
│   └── channel_router/
├── LICENSE                           ← open-source license (required if repo public)
└── README.md                         ← setup + how to run (required for judging)
```

---

## 7. Build phases (fits the timeline to Oct 28)

**Phase 0 — Access & prerequisites (start immediately; has lead time)**
- Request AWS credits + Kiro codes (per hackathon to-dos).
- Provision AWS End User Messaging: SMS number, **RCS sender + brand verification** (~1–3 business days — critical path), WhatsApp business number (for Meta prize), SES verified domain/identity (move out of sandbox if needed).
- Install AgentCore CLI (`npm i -g @aws/agentcore`, Node 20+), verify `agentcore --version` ≥ 0.9.0.
- Enable Bedrock model access (reasoning + vision) in your region.

**Phase 1 — Agent skeleton (Day 1–2)**
- `agentcore create --name ClaimPilot --framework Strands --model-provider Bedrock --build CodeZip --memory longAndShortTerm`
- Write the FNOL system prompt + conversation policy in `main.py`.
- `agentcore dev` to iterate on the dialog locally (note: memory + gateway need deploy).

**Phase 2 — Tools (Day 2–4)**
- Implement tool Lambdas: policy_lookup, damage_assess (Bedrock vision), fraud_signals, booking.
- Wire them as AgentCore Gateway targets.
- Seed DynamoDB with sample policies; seed S3 with sample accident photos.

**Phase 3 — CDS channel integration (Day 4–7)**
- `channel_router` Lambda: normalize inbound from SMS/RCS/WhatsApp; capability detection; outbound channel selection.
- Build RCS rich cards, carousel, and suggestions (`SendRcsMessage`).
- SMS fallback + hosted photo-upload page for non-RCS devices.
- WhatsApp path (Social messaging) for the Meta prize.
- SES templated claim-summary email.

**Phase 4 — End-to-end + polish (Day 7–10)**
- Full deploy (`agentcore deploy` + `cdk deploy` for infra).
- Live test the whole conversation on a real phone across channels.
- Add the memory "next day update" beat.
- Harden: guardrails on the agent, IAM least-privilege, error handling.

**Phase 5 — Submission artifacts (Day 10–12)**
- Architecture diagram + text description.
- ~3-minute demo video (one continuous take of the flow + memory beat).
- README with setup/run instructions; add open-source LICENSE (or share private repo with testing@devpost.com + aws-cds-partner@amazon.com).
- Register the ACE opportunity with campaign code "AWS CDS Agentic AI Hackathon -Sept. 2026."
- WhatsApp prize writeup: how AWS End User Messaging Social was used.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| RCS brand verification lead time | Start Phase 0 today; build SMS path first so demo works even if RCS approval is late. |
| SES sandbox limits | Verify identities early; request production access; demo to verified addresses if still sandboxed. |
| WhatsApp onboarding complexity | Treat WhatsApp as additive (Meta prize); don't block core demo on it. |
| Memory only works after deploy | Develop dialog locally, but test memory beats against a deployed agent. |
| Scope creep | Core = SMS+RCS+SES happy path. WhatsApp, fraud depth, rental are stretch. |
| PII / real data | Use synthetic policyholders + sample photos; no real PII in the demo. |

---

## 9. Immediate next actions

1. Confirm the pick (ClaimPilot) and whether we chase the WhatsApp prize.
2. Tell me your AWS access state: do you have EUM SMS/RCS sender + SES set up, or should I write the exact setup steps/commands?
3. Then I'll scaffold: run `agentcore create`, write the `main.py` system prompt + agent, and stub the tool Lambdas + CDK infra.

> Open questions that change the plan: (a) team size/skills, (b) do you already have an AWS account with Bedrock + EUM enabled in a supported region, (c) preferred region (RCS/WhatsApp availability varies).
