# AWS CDS Agentic AI Hackathon — Research-Backed Idea Board

**Deadline:** Oct 28, 2026 · **Prizes:** $40K total + separate $10K Meta WhatsApp prize
**Registered as:** bvsbharat · **Workspace:** AWS-FNOL-SMS

---

## 1. What actually wins this hackathon (research-backed)

**Judging weights and what each really rewards:**

| Criterion | Weight | Design implication |
|---|---|---|
| Technical Execution | **40%** | Use **multiple** CDS channels (RCS + SMS + WhatsApp + SES) + AgentCore doing *real* multi-step work, integrated with broader AWS. Ship it as **IaC** (reproducible). |
| Potential Value / Impact | 20% | Real, expensive, high-volume problem with **measurable** ROI. |
| Demo Presentation | 20% | Show the **end-to-end agentic workflow** in ~3 min with a clear before/after. |
| Creativity | 10% | Novel problem OR novel approach. Avoid AWS's own example verticals. |
| Functionality | 10% | Reliable, scalable, AI genuinely improves the process. |

**Evidence from recent AWS agentic-AI hackathon winners:**
- The top project at AWS's "Accelerating the V-Cycle with Agentic AI" hackathon won on **"purchase readiness"** — judges reward things that look like a *real, buyable product*, not a tech demo. ([EE Journal](https://www.eejournal.com/industry_news/with-aws-hackathon-win-tasking-led-team-demonstrates-the-future-of-automotive-safety-critical-software-development/), [Business Wire](https://www.businesswire.com/news/home/20260818770734/en/)) This maps 1:1 to this hackathon's AWS Marketplace / ACE-opportunity emphasis.
- Devpost judge guidance: present it like a startup — real name, crisp narrative. ([Amazon Nova Hackathon](https://amazon-nova.devpost.com/updates/42214-level-up-your-build-how-to-wow-the-judges))

*Content rephrased for compliance with licensing restrictions.*

**The pattern the brief is begging for:** a conversation that **starts in one channel and completes an action in another**, orchestrated by an agent, with CDS as the backbone.

**Three under-exploited technical levers that differentiate a winner:**
1. **AgentCore Memory** — managed long-term memory so the agent literally "picks up where the last conversation left off" (the brief's exact phrase). ([AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/amazon-bedrock-agent-core.html))
2. **AgentCore Payments (x402 / stablecoin microtransactions)** — agents can *autonomously pay* for services with policy-based spend guardrails; GA with Coinbase. Almost nobody will use this → big creativity + technical points. McKinsey projects agentic commerce at **$3–5T by 2030**. ([AWS blog](https://aws.amazon.com/blogs/machine-learning/technical-deep-dive-agentcore-payments-and-innovation-in-agentic-commerce/), [Coinbase](https://www.coinbase.com/developer-platform/discover/launches/agentcore-ga))
3. **RCS verified sender = built-in anti-fraud** — every RCS message is tied to a vetted brand with a verification badge, which kills SMS spoofing/phishing; iOS 18 made RCS universal, and RCS business volume surged ~500% into 2025–26. ([Sinch](https://sinch.com/blog/rcs-in-banking-financial-services/), [Zembula](https://www.zembula.com/blog/rcs-business-messaging-for-retail-where-smart-banners-rich/)) *Content rephrased for compliance.*

**RCS capabilities we can build on:** rich cards, carousels, media (image/video), suggested replies, and suggested actions (open URL, dial, **share location**) — all via the `SendRcsMessage` API. ([AWS docs](https://docs.aws.amazon.com/sms-voice/latest/userguide/rcs-rich-messaging.html))

---

## 2. Top recommendations (ranked)

### 🥇 Tier 1 — Best win probability

---

### ⭐ Idea A — "ClaimPilot": Agentic FNOL Insurance Claims (primary)

**One-liner:** Turn insurance First Notice of Loss from a multi-day phone/portal ordeal into a claim filed, triaged, and serviced in 3 minutes — from the customer's default messaging app.

- **Problem/impact:** FNOL is slow, manual, fraud-prone, expensive. Measurable: intake time (days→minutes), claim leakage, adjuster hours saved, CSAT.
- **Flow:** SMS "I had an accident" → agent verifies policy, escalates to **RCS** for structured evidence (photo upload, tap-to-share GPS, damage carousel) → **Bedrock vision** scores damage + fraud signals → agent books tow/rental via RCS tap-actions → formal claim summary via **SES** → **WhatsApp** for international drivers. **AgentCore Memory** keeps claim state across days/channels.
- **CDS:** SMS + RCS + SES + WhatsApp. **AWS:** AgentCore (Memory, Gateway, tools), Bedrock vision, DynamoDB, S3, EventBridge, Step Functions, Lambda. IaC via CDK.
- **Why it wins:** full CDS breadth, dramatic demo, obvious carrier ROI, clean Marketplace story; aligns with existing workspace.

---

### ⭐ Idea B — "TrustLine": RCS Anti-Fraud Verification & Dispute Agent (highest differentiation)

**One-liner:** Kill smishing. Every sensitive interaction happens over **verified-sender RCS** so customers can *trust the brand badge*, and an agent handles verification, freezes, and disputes conversationally — in minutes, not a 40-min call queue.

- **Problem/impact:** SMS phishing (smishing) costs billions and erodes trust in every OTP/alert. RCS's verified-sender model structurally defeats spoofing. Measurable: fraud-confirmation latency, dispute-resolution time, call deflection, phishing-loss reduction.
- **Flow:** Suspicious transaction → **RCS** verified-sender alert "Did you make this $X charge?" with tap-verify (the badge is the anti-fraud proof) → if disputed, agent walks through recent activity via RCS cards, files dispute, issues provisional credit → **SES** case summary; **SMS** fallback where RCS unavailable. **AgentCore Memory** + **Identity** for secure step-up.
- **CDS:** RCS + SMS + SES (+ WhatsApp). **AWS:** AgentCore (Identity, Memory), Bedrock, Amazon Fraud Detector, DynamoDB, KMS.
- **Why it wins:** *novel approach* (uses RCS's unique security property as the core value prop, not just rich UI), strong architecture/security scoring, universal FSI relevance. Keep it demo-able with a mock bank (no real PCI scope).

---

### 🥈 Tier 2 — Strong, differentiated

---

### Idea C — "PayFlow": Autonomous Agentic Commerce over Messaging (most novel tech)

**One-liner:** A shopping/services agent that not only recommends inside RCS/WhatsApp but **autonomously pays** for micro-services on the customer's behalf using AgentCore Payments (x402), within guardrailed budgets.

- **Problem/impact:** Rides the agentic-commerce wave ($3–5T by 2030). Concretely: an agent that books + pays for a bundle (e.g., parking + EV charge + toll, or a travel micro-itinerary) in one conversation, settling many tiny provider payments the customer would never do manually.
- **Flow:** Customer states intent in **WhatsApp/RCS** → agent assembles options as an RCS carousel → on tap-approve, agent **autonomously pays** each micro-provider via x402 with spend guardrails → receipts via **SES**; status two-way over SMS.
- **CDS:** WhatsApp + RCS + SMS + SES (all four → Meta prize + max technical breadth). **AWS:** AgentCore Payments (x402/Coinbase), Memory, Gateway, Bedrock, DynamoDB.
- **Why it wins:** almost no competitor will touch AgentCore Payments → outsized creativity + technical-execution differentiation. Watch: keep on x402 **test network**; scope the provider set tightly.

---

### Idea D — "CareBridge": Accessibility-First Benefits & Care Agent (highest social impact)

**One-liner:** A no-app, plain-messaging agent that helps under-served populations (elderly, low digital-literacy, non-English speakers) enroll in benefits, manage medications, and stay connected — meeting them on SMS/RCS/WhatsApp in their language.

- **Problem/impact:** Peer-reviewed studies show conversational agents on familiar channels measurably reduce depressive symptoms and improve adherence for older adults, and lower barriers for low-digital-literacy users. ([Springer meta-analysis](https://link.springer.com/article/10.1186/s12877-026-07418-6)) Benefits under-enrollment leaves billions unclaimed. Measurable: enrollment completion, adherence, no-show reduction, reach in low-connectivity areas.
- **Flow:** Reminder via **SMS** (works on any phone) → richer guidance via **RCS** (map to nearest office/pharmacy, tap-to-schedule, forms as cards) → multilingual conversational Q&A grounded via **Bedrock Knowledge Bases + Guardrails** → confirmations/instructions via **SES**; **WhatsApp** for immigrant communities. **AgentCore Memory** for continuity across visits.
- **CDS:** SMS + RCS + SES + WhatsApp. **AWS:** AgentCore (Memory), Bedrock Guardrails + KB, Amazon Translate, DynamoDB.
- **Why it wins:** maxes the 20% impact criterion and creativity; powerful demo narrative; strong public-sector/healthcare GTM. Graceful SMS-only fallback is itself a differentiator.

---

### 🥉 Tier 3 — Solid alternates

- **Idea E — "ReRoute": Travel Disruption Recovery Agent.** Flight cancelled → agent proactively rebooks via RCS cards, pushes boarding pass to WhatsApp, emails receipt via SES. Most demo-friendly; medium creativity.
- **Idea F — "Storefront": SMB Conversational Commerce Agent.** AI sales associate in WhatsApp + RCS carousel + SMS cart-recovery + SES receipts. Lowest build risk, strongest WhatsApp-prize position, clean Marketplace product.
- **Idea G — "GridTalk": Proactive Utility Outage Agent.** Outage event → proactive RCS notify with map/ETA + two-way "is your power back?" triage → crew prioritization → SES restoration report. Strong B2B/enterprise ACE story.

---

## 3. Comparison matrix

| Idea | CDS breadth | Impact | Demo wow | Creativity | Novel AWS tech | WhatsApp/$10K | Build risk |
|---|---|---|---|---|---|---|---|
| A. ClaimPilot (FNOL) | High | Very high | Very high | Med-High | Memory + vision | Yes | Med |
| B. TrustLine (anti-fraud RCS) | High | Very high | High | **High** | Identity + verified RCS | Optional | Med |
| C. PayFlow (agentic payments) | Very high | High | High | **Very high** | **Payments/x402** | Strong | Med-High |
| D. CareBridge (accessibility) | High | **Very high** | High | High | Guardrails + Translate | Yes | Med |
| E. ReRoute (travel) | High | High | Very high | Med | Memory | Yes | Med |
| F. Storefront (SMB) | Very high | Med-High | High | Med | Payments optional | Strong | Low-Med |
| G. GridTalk (utility) | High | High | High | High | IoT + fan-out | Yes | Med |

---

## 4. Recommendation

- **Safest high-ceiling pick:** **Idea A (ClaimPilot / FNOL)** — full CDS breadth, dramatic demo, obvious ROI, aligns with the workspace, strong Marketplace story.
- **Highest-differentiation pick:** **Idea B (TrustLine)** or **Idea C (PayFlow)** — both use a *unique* property of the stack (RCS verified-sender security; AgentCore Payments) that most teams won't touch, which is exactly where the 10% creativity + parts of the 40% technical score are won.
- **Highest social-impact pick:** **Idea D (CareBridge).**

**A strong hybrid:** Build **ClaimPilot** as the core (safe, complete, demo-ready) and fold in **TrustLine's verified-sender trust angle** (claims fraud detection + verified-brand RCS) so we get differentiation *and* completeness in one submission.

### Decisions needed to lock scope for Oct 28
1. Vertical: lock **A (FNOL)**, or go differentiation-first with **B/C**, or impact-first with **D**?
2. AWS access: do we have credits + **End User Messaging / RCS sender** provisioned? (RCS brand verification takes ~1–3 business days — start early.)
3. Chase the **$10K WhatsApp** prize (build WhatsApp in)? Recommended if effort allows.
4. Team + skills (frontend / backend / ML)?

Once you pick, I'll produce a full build plan: architecture diagram, service-by-service breakdown, CDK scaffold, a 3-minute demo script, and a repo skeleton.
