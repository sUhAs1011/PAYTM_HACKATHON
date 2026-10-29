# ParchaPay AI: Project Blueprint & Strategic Brief

**Track:** Track 1 — Merchant Growth AI (Paytm Build for India AI Hackathon 2026\)  
**Target Device & Rails:** Paytm AI Soundbox, Paytm for Business App, Paytm Split Settlements & Merchant Lending Rails

---

## 1\. Executive Summary

**ParchaPay AI** is a multimodal procurement, margin-protection, and settlement-backed credit copilot for small merchants.

While Paytm and previous hackathon winners (such as *Munim AI*) digitized customer-facing payments via QR codes and digital ledgers, the **supplier procurement side** remains entirely manual. Small retailers receive inventory accompanied by thermal printouts, handwritten delivery slips (*parchas*), or static WhatsApp PDFs. This creates silent margin loss from unannounced price creep, billing math errors, and cash-flow crunches when distributors demand cash on delivery.

ParchaPay AI bridges this gap without requiring expensive barcode computers:

1. **Snap or Forward:** The merchant photographs a paper bill (complete with delivery pen markups) or forwards a supplier WhatsApp PDF.  
2. **Audit in Seconds:** A vision-language model parses line items, checks math, and verifies prices against both historical bills and local pin-code averages.  
3. **Soundbox Voice & Screen Alert:** The Paytm AI Soundbox speaks out overcharges in the merchant's local language and displays a red/green price card on its front screen.  
4. **Automated Dispute & Working Capital:** One press of the physical **Paytm Button** dispatches a visual dispute note to the distributor on WhatsApp and unlocks a **7-Day Split-Credit**—paying the distributor upfront while automatically deducting small daily micro-installments from incoming customer QR scans.

---

## 2\. Problem Statement & Ground Truth

### The Context

India’s 12+ million neighborhood retail stores (*kiranas*, medical stores, bakeries, small hardware shops) generate over 85% of retail FMCG sales. Over 1.5 crore (15 million) of these counters use a Paytm Soundbox to receive customer payments. However, their wholesale purchasing process remains unintegrated with their digital payment tools.

### The "Data Air-Gap"

A common misconception is that suppliers write everything on scraps of paper, or conversely, that everything is already digital via APIs. The actual reality is a **data air-gap**:

* **Marg/Tally Printouts with Pen Markups:** Distributors generate invoices on desktop ERPs. But when the delivery arrives at the shop, if two items are missing or damaged, the delivery salesman crosses out the printed numbers with a ballpoint pen and scribbles the adjusted total on the paper sheet.  
* **WhatsApp "Digital Paper":** Modern distributors frequently message invoices as PDFs or photos over WhatsApp. To a busy shopkeeper with a line of customers, a PDF on a 6-inch phone screen is still static paper—they must manually read it, calculate landed costs, and type figures into a payment app.  
* **Handwritten Mandi Slips (*Kaccha Parchas*):** Unbranded staples (rice, pulses, vegetables, local dairy) continue to arrive on traditional handwritten chits.

```
┌─────────────────────────────────┐                ┌──────────────────────────────────┐
│   SUPPLIER / DISTRIBUTOR SIDE   │                │     RETAILER COUNTER SIDE        │
│ • Desktop ERPs (Tally, Marg)    │  DATA AIR-GAP  │ • Paytm Soundbox (1.51 Cr units) │
│ • Printed Challans + Pen Edits  │ ─────────────► │ • Customer UPI QR Scans          │
│ • WhatsApp PDF/Image Invoices   │  (No Direct    │ • Fast-Paced Customer Queues     │
│ • Handwritten Mandi Slips       │   Integration) │ • No Barcode Scanners / POS PCs  │
└─────────────────────────────────┘                └──────────────────────────────────┘
```

### The Three Critical Consequences

1. **Silent Margin Leakage (3% to 8% Gross Profit Loss):** Wholesale distributors adjust item prices, alter volume schemes (e.g., dropping a "Buy 10 Get 1 Free" deal), or make calculation errors. Because shopkeepers lack the time to manually check every line against previous bills, they absorb wholesale price hikes without adjusting their retail counter prices.  
2. **The GST 2.0 IMS Hard-Locking Trap:** Under India’s **Invoice Management System (IMS)**, GST-registered buyers must actively accept or reject supplier-uploaded invoices. If a supplier's accountant uploads the original pre-edited invoice and the merchant fails to flag the delivery deduction before the 14th of the month, the invoice is **"Deemed Accepted."** The merchant gets stuck paying tax on stock they never received.  
3. **Restocking Cash Crunches:** Distributors demand payment on delivery. If a store’s morning customer collections are low, the merchant must either turn away stock or borrow from informal lenders at high interest—even though their Paytm QR will reliably collect twice that invoice amount over the coming week.

---

## 3\. Market Research & Feasibility Validation

* **Distribution Channels:** According to industry studies (Dataintelo FMCG B2B Report), less than 20% of FMCG procurement happens via organized B2B apps; over 80% remains routed through local distributor salesmen who drop physical bills at the counter.  
* **Proven Demand for Purchase Digitization:** Leading SMB billing apps (Vyapar and myBillBook) publicly report over **1 crore (10 million) purchase bills scanned** via camera OCR, confirming that small merchants actively look for ways to eliminate manual purchase entry.  
* **Existential Pressure from Quick-Commerce:** Retail federation reports indicate over 200,000 neighborhood stores have faced severe viability challenges due to quick-commerce delivery apps. Protecting procurement margins and maintaining working capital is now critical for merchant survival.

---

## 4\. The Proposed Solution (ParchaPay AI)

ParchaPay AI connects **wholesale intake** directly to the **Paytm AI Soundbox** and **Paytm Settlement Rails**.

```
  [Paper Bill / WhatsApp PDF]
               │
               ▼
   [Vision-Language Engine]  ──► Extracts items, tax, and pen strikethroughs
               │
               ▼
   [Margin-Guard & IMS Engine] ──► Checks history, pin-code rates & GST
               │
               ▼
  [Paytm AI Soundbox Output] ──► 11-Language Audio Alert + Front Screen Card
               │
               ▼
   [Merchant Presses Button]
         ┌─────┴────────────────────────┐
         ▼                              ▼
 [WhatsApp Dispute Crop Note]   [7-Day QR Split-Settlement]
 (Auto-sent to distributor)     (Daily deduction from customer QR)
```

### Workflow Stages

#### 1\. Zero-Friction Intake (Phone or WhatsApp)

* **Paper Bills:** The merchant snaps a single photo using the Paytm for Business app.  
* **Digital Invoices:** The merchant forwards incoming distributor WhatsApp PDFs or images directly to the Paytm Business WhatsApp Bot.

#### 2\. Multimodal Vision & Layout Parsing

* The system extracts supplier details, line items, quantities, HSN codes, GST tiers, and free/scheme units.  
* **Visual Pen-Correction Detection:** If a delivery salesman modified printed numbers by hand (e.g., crossing out `12` and writing `10`), the vision model identifies both values, isolates the pen markup as an annotated crop, and checks if the subtotal was calculated correctly.

#### 3\. Deterministic Price Audit & Pin-Code Benchmarking

* An isolated code engine (avoiding LLM math hallucinations) calculates the **True Landed Cost per Unit**: $$\text{True Landed Unit Cost} = \frac{\text{Net Line Amount} + \text{GST}}{\text{Billed Quantity} + \text{Free Units}}$$  
* Compares landed costs against the merchant’s previous invoices from that supplier.  
* Compares rates against the **Hyperlocal Mandi-Pulse** (anonymized average wholesale prices paid for that same SKU across Paytm stores in that pin code).

#### 4\. Dual-Surface Soundbox Interaction

* **Voice Alert:** The Paytm AI Soundbox speaks in the merchant's chosen language (e.g., Kannada, Hindi, Tamil):  
  > *"Sharmaji Wholesale bill checked. Fortune Oil unit price increased by ₹6, and there is a ₹140 math overcharge. Recommended payout is ₹13,860."*  
* **Display Card:** The front touchscreen shows an itemized breakdown with color-coded discrepancies.

#### 5\. One-Touch Resolution: Dispute Claim & GST IMS Flag

* Pressing the physical **Paytm Button** on the Soundbox (or tapping the phone screen) triggers two actions:  
  1. **Supplier WhatsApp Notice:** Sends the distributor a structured breakdown with a cropped image of the pen-marked bill, detailing the math difference alongside a revised Paytm Payment Link.  
  2. **GST IMS Shield:** Automatically flags the invoice as `Pending/Disputed` in the merchant's GST queue to block "Deemed Acceptance" on unreceived stock.

#### 6\. Settlement-Backed B2B Split-Credit

* If cash is tight, the merchant selects **"Pay via Soundbox Split."**  
* Paytm settles the distributor’s bill immediately via payout rails.  
* Repayment is handled via **Paytm Split Settlements**: the system automatically reserves a set amount (e.g., ₹2,000/day) from incoming customer QR transactions over the next 7 days before transferring the daily balance to the merchant's bank account.

---

## 5\. Scope Boundaries: Avoiding the "Inventory Trap"

A major failure point for retail tech products is trying to force small stores to maintain full inventory systems.

| Target Merchant Segment | Core Problem | ParchaPay AI Approach | Out-of-Scope (Intentionally Excluded) |
| :---- | :---- | :---- | :---- |
| **90% Unorganized Kiranas** *(No billing software, no barcode scanners)* | Cannot maintain real-time stock ledgers; itemized sales entry causes product abandonment within a week. | **Inward Restock & Expiry Watcher:** Tracks inbound stock prices and flags expiry dates 30 days prior. Voice query supported (e.g., *"When did I last buy Fortune Oil?"*). | **No Real-Time Counter Stock Ledger:** Will NOT attempt counter-sales deduction for small retail sales (e.g., single biscuit packets). |
| **10% Semi-Organized Stores** *(Running Marg ERP, Tally, or Vyapar)* | Manual, error-prone line-by-line entry of paper purchase vouchers into desktop ERP systems. | **Automated Ingestion Bridge:** 1-click export to Tally XML / Marg CSV. Adds wholesale price-creep auditing and split-settlement credit. | **No Full Inventory Management System:** Does not attempt to replace established desktop ERP accounting modules. |

---

## 6\. Competitive Analysis & Unique Selling Propositions (USPs)

### Competitive Landscape

| Solution Category | Key Players | How They Work | Where They Stop |
| :---- | :---- | :---- | :---- |
| **SMB Accounting Apps** | Vyapar, myBillBook (*Mira AI*) | Ingest purchase bills via camera/OCR into an accounting ledger. | Act purely as accounting software. They do not sit on the checkout counter, lack hardware integration, do not benchmark rates across stores, and cannot underwrite loans using payment flows. |
| **AI Retail SaaS** | Dukaan AI (`dukaanai.co.in`) | Mobile app scanning wholesale mandi bills with profit margin calculators. | Software-only mobile utility without payment rail integration. Cannot automate supplier payouts or collect loan repayments via daily QR settlements. |
| **Vertical ERPs** | PharmIQ, Madhushala Pro | Cloud POS for pharmacies and liquor stores with supplier price variance tracking. | Desktop-bound, complex, and expensive (₹500–₹2,000/month). Unusable for standard, unorganized kirana counters. |
| **Fintech Lenders** | BharatPe, Progcap, Paytm Loans | Underwrite merchant loans and deduct loan installments from daily card/QR settlement sweeps. | Offer only generic lump-sum loans. They do not scan line-item paper bills to verify exact invoice legitimacy at the moment of delivery. |

### The 4 Core USPs of ParchaPay AI

1. **Hardware-Native Countertop Workflow (The Soundbox Advantage):** Unlike mobile-only apps that require scrolling through tables on a phone while customers wait, ParchaPay AI utilizes the **Paytm AI Soundbox** (dual screen \+ 11-language voice \+ physical button). The merchant hears the audit aloud and approves payouts with a single button press.  
2. **"Mandi-Pulse" Hyperlocal Wholesale Benchmarking:** While existing tools only compare a merchant’s bill against their own past receipts, ParchaPay AI leverages Paytm’s dense merchant network. It cross-references landed wholesale costs against anonymized purchase data from nearby stores in the same pin code, instantly exposing localized supplier overcharges.  
3. **GST IMS Shield \+ Pen-Markup Visual Verification:** Solves the specific compliance challenge of GST 2.0. By isolating pen-corrected delivery adjustments and queuing dispute proofs before the 14th of the month, it prevents merchants from being locked into tax overpayments.  
4. **Settlement-Backed B2B Micro-Credit:** Closes the loop between invoice verification and working capital. Paytm funds the distributor invoice upfront and uses its **Split Settlement engine** to recover funds directly from daily customer QR transactions. This creates a low-risk, self-liquidating loan product.

---

## 7\. Architecture & Technology Stack

The solution uses a balanced architecture: an agile **FastAPI** backend for asynchronous AI and data orchestration, paired with a clean **Angular** frontend.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Angular 19)                           │
│  • Mobile Scanner View (PWA / Camera API for Paper Parchas)            │
│  • Soundbox Digital Twin (Audio Player + Dual-Screen Simulation)       │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ HTTP / WebSocket
┌───────────────────────────────────▼────────────────────────────────────┐
│                       BACKEND (Python FastAPI)                         │
│  • Async orchestration pipeline (`asyncio.gather`)                     │
│  • Pydantic schemas for guaranteed invoice JSON structure              │
│  • Deterministic math & True Landed Cost engine                        │
│  • Split settlement amortization calculator                            │
└───────────────▲───────────────────▲────────────────────▲───────────────┘
                │                   │                    │
┌───────────────▼──────────┐ ┌──────▼─────────────┐ ┌────▼───────────────┐
│     AI & VISION LAYER    │ │     VECTOR DB      │ │   RELATIONAL DB     │
│ • Gemini 2.5 Flash /     │ │   (ChromaDB /      │ │  (Postgres/SQLite)  │
│   GPT-4o Vision          │ │    SQLite-vec)     │ │                     │
│ • OpenCV / Pillow        │ │                    │ │ • Merchants & Party │
│   (Pen-markup crop)      │ │ • Canonical SKU    │ │ • Invoices & Items  │
│ • Sarvam AI (Bulbul TTS) │ │   Embeddings       │ │ • GST IMS Records   │
│   11-language voice      │ │ • Pin-Code Match   │ │ • Daily Deductions  │
└──────────────────────────┘ └────────────────────┘ └─────────────────────┘
```

### Stack Overview

* **Frontend (Angular 19):** Mobile Scanner View (PWA / Camera API for Paper Parchas); Soundbox Digital Twin (Audio Player \+ Dual-Screen Simulation).  
* **Backend (Python FastAPI):** Async orchestration pipeline (`asyncio.gather`); Pydantic schemas for guaranteed invoice JSON structure; Deterministic math & True Landed Cost engine; Split settlement amortization calculator.  
* **AI & Vision Layer:** Gemini 2.5 Flash / GPT-4o Vision for structured extraction and pen strikethrough detection; OpenCV / Pillow for automated pen-markup dispute cropping; Sarvam AI (Bulbul TTS) for sub-second 11-language Indian voice synthesis.

### Data Storage Strategy

* **Vector DB (ChromaDB / SQLite-vec) for Unstructured Text & Fuzzy Matching:** Maps noisy invoice abbreviations (e.g., *"HUL BRK BND RDLBL 250G"* vs. *"BROOKE BOND RED LABEL 250GM"*) to a standardized Canonical Product ID in milliseconds. Also powers the Mandi-Pulse pin-code price comparisons.  
* **Relational DB (PostgreSQL / SQLite) for Financial Math & Legal State Tracking:** Enforces exact decimals, foreign key constraints, and transactional consistency for tax calculations, loan amortization schedules, and formal GST IMS statuses (`Pending`, `Accepted`, `Rejected`).

---

## 8\. Business Model & Value for Paytm

ParchaPay AI directly supports Paytm’s post-PIDF profitability strategy:

```
[Merchant Retention]  ──►  [AI Token Consumption]  ──►  [B2B Loan Distribution]
Higher Soundbox stickiness  Monthly subscription add-on   High-margin origination fees
via operational utility     for automated invoice audits  backed by low-risk daily sweeps
```

1. **Monetizing the Paytm AI Soundbox Token Model:** Paytm’s AI Soundbox includes a "Fair Use AI Token Model." ParchaPay AI gives merchants a clear reason to use those tokens daily. Merchants can subscribe to an automated invoice-auditing tier for a monthly fee (e.g., ₹99–₹199/month) or purchase token bundles.  
2. **High-Margin Merchant Loan Origination:** Merchant loan distribution is Paytm’s primary profit engine. By validating invoices at the SKU level, Paytm underwrites low-risk, asset-backed micro-credit. Loans are systematically repaid via automated daily deductions from customer QR payments, keeping default rates low.  
3. **Hardware Retention and Stickiness:** With payment infrastructure subsidies (PIDF) expired, merchants could switch between competing QR soundboxes. Embedding wholesale margin protection and supplier credit into the Paytm Soundbox makes the hardware indispensable to daily shop operations.

---

## 9\. Live Hackathon Demonstration Strategy (The 3-Minute Pitch)

During the in-person finale at the Bellandur office, the team will demonstrate the live system using a **Two-Device Setup**:

* **Device 1 (Phone in Hand):** The Shopkeeper’s Mobile Scanner (Angular mobile web view).  
* **Device 2 (Laptop on Projector \+ Speakers):** The Countertop **Paytm AI Soundbox Digital Twin** connected via real-time WebSockets.

### Pitch Timeline

```
0:00                 0:45                          1:45                       2:30             3:00
┌──────────────────────┬─────────────────────────────┬──────────────────────────┬────────────────┐
│   Hook & Problem     │   Live Scan & Soundbox      │ Mandi-Pulse & Dispute    │ Financial Loop │
│  (Physical Paper)    │     (2.5s Execution)        │    (WhatsApp + GST)      │  & Closing     │
└──────────────────────┴─────────────────────────────┴──────────────────────────┴────────────────┘
```

* **0:00 \- 0:45 (The Hook & Problem Setup):** Hold up a real, crumpled wholesale paper bill with a visible ballpoint pen strikethrough. Explain the data air-gap: *"Distributor delivered 10 units instead of 12, scribbled the total by hand. The shopkeeper has 4 customers waiting and cannot verify the math or check if prices increased."*  
* **0:45 \- 1:45 (The Live Scan & Soundbox Execution):** Take a picture of the bill on the phone. Within 2.5 seconds, the laptop screen on the projector updates: visual bounding boxes highlight the pen strikethrough, the Soundbox screen flashes a Red/Green card, and the room speakers play a Sarvam AI voice alert in Kannada/Hindi detailing the price increase and math error.  
* **1:45 \- 2:30 (Network Intelligence & Resolution):** Point out the Mandi-Pulse card showing that 14 nearby stores bought this item at ₹128, proving an overcharge. Tap the Paytm Button on the Soundbox UI to generate a WhatsApp dispute card with the cropped pen edit and flag the invoice in the GST IMS module.  
* **2:30 \- 3:00 (Financial Loop & Closing):** Demonstrate the "Pay via Soundbox Split" option, showing a 7-day repayment bar deducting ₹2,000/day from incoming customer QR settlements. Conclude with the business and ecosystem impact for Paytm.

---

## 10\. Summary Assessment

* **Is the problem real?** Yes. Verified across retail distribution research, 1 crore+ scanned bills on SMB accounting apps, and recent GST 2.0 IMS compliance rules.  
* **Is it differentiated?** Yes. It avoids the crowded customer-side ledger space (already addressed by *Munim AI*), moves beyond simple data entry (Vyapar/myBillBook), and connects bill verification directly to countertop Soundbox hardware and daily QR loan settlements.  
* **Is it feasible in a 1-day sprint?** Yes. The architecture relies on mature, accessible components: a focused Angular UI, a FastAPI backend, Gemini/GPT-4o multimodal vision for extraction, and fast Indian TTS for local-language voice synthesis.

&nbsp;

&nbsp;

# **11\. Critical Edge Cases & Solution Defenses (Judging Q\&A Defense)**

During live evaluation, fintech judges and Paytm leadership often stress-test lending risk, supplier dynamics, computer vision reliability, and tax compliance. ParchaPay AI addresses each potential failure mode with deterministic guardrails:

## **1\. The Lending Trap: Merchant Default & Soundbox Substitution Risk**

* **The Challenge:** What prevents a merchant from taking the 7-day supplier split-credit and temporarily switching to a competitor's QR code (e.g., PhonePe or Google Pay) on the counter to avoid daily deductions?  
* **Architectural Defense:**  
  * **Dynamic Velocity Cap:** Maximum loan principal is strictly capped at **35% of the merchant’s 30-day rolling daily average QR volume**. For example, a store averaging Rs 10,000/day in customer QR collections can only borrow up to a Rs 2,500/day daily repayment deduction.  
  * **Fallback e-NACH / UPI Autopay Mandate:** When enrolling in Split-Credit, the merchant authenticates a background UPI Autopay / e-NACH bank mandate. If Paytm QR collection drops to Rs 0 for 48 consecutive operational hours, the system triggers an automated backup sweep directly from their primary registered bank account.  
  * **Revolving Credit Lockout:** Neighborhood retail restock happens every 3 to 7 days. Evading repayment on a Rs 10,000 bill freezes access to all future credit lines and alerts field agents, destroying the merchant's most convenient supplier payment tool.

## **2\. The Supplier Relationship Trap: Preserving Distributor Goodwill**

* **The Challenge:** Indian B2B wholesale relies heavily on personal relationships. An aggressive automated bot claiming "You overcharged Rs 140, pay up" could alienate distributor salesmen and disrupt supply.  
* **Architectural Defense:**  
  * **Reconciliation Tone, Not Allegation:** The auto-generated WhatsApp notification is framed as a mutual **B2B Delivery Reconciliation Slip**: "Namaste Sharmaji Wholesale. Delivery received for Invoice \#402. Note: 2 units of Fortune Oil short-supplied (pen-marked on challan). Amount approved: Rs 13,860. \[View Verified Challan Crop & Collect via Paytm Link\]."  
  * **Frictionless Distributor Acceptance:** The salesman does not need to install an app. Tapping the link displays an annotated photo crop of their own handwritten pen strikethrough alongside the corrected subtotal and a single-tap button to "Accept & Collect Rs 13,860," saving their back-office accounting team hours of manual month-end reconciliation.

## **3\. The AI Vision Trap: Faded Thermal Paper & Handwriting Ambiguity**

* **The Challenge:** Oily bills, faded thermal prints, or illegible handwriting could cause vision models to hallucinate numbers or disrupt operations.  
* **Architectural Defense:**  
  * **Deterministic Checksum Guard:** Extracted line items and calculated taxes must strictly reconcile with the written or printed Grand Total. If the calculated sum differs from the printed total, the transaction cannot auto-approve.  
  * **Confidence Scoring & Yellow-Highlight Exception Review:** Every extracted line item is assigned an OCR confidence score (0–100%). Any item below 80% confidence is flagged in yellow on the mobile screen for a 1-tap confirmation (e.g., "Confirm quantity for Parle-G: 24 or 36?"), eliminating silent hallucinations while keeping 95%+ of items zero-typing.

## **4\. The Privacy & Cold-Start Trap: Hyperlocal Rate Benchmarking ("Mandi-Pulse")**

* **The Challenge:** Does sharing local wholesale rates violate supplier pricing secrecy, and how does the system function in areas with low merchant density?  
* **Architectural Defense:**  
  * **k-Anonymity & Price Bands (Never Individual Prices):** ParchaPay AI never reveals individual merchant identities, supplier names, or single transaction prices. It only displays an aggregated median band: "Bellandur (560103) median wholesale band: Rs 126–130/L".  
  * **Minimum Density Threshold:** Mandi-Pulse benchmarking activates only when at least **5 distinct merchant invoice scans for that canonical SKU** exist within that pin code over the preceding 14 days. If the threshold is not met, the system seamlessly falls back to personal historical comparison ("You paid Rs 6 more than your previous invoice on Oct 12").

## **5\. The Compliance Scope Trap: GST IMS Authority vs. Frontline Triage**

* **The Challenge:** Writing directly to the official GST Portal requires GSP integration and merchant credentials. How does ParchaPay AI interact with government tax systems?  
* **Architectural Defense:**  
  * **Frontline Decision Filter & IMS Staging Queue:** ParchaPay AI does not claim unauthorized live writes to the GSTN backend. Instead, it acts as the merchant's **decision staging layer**. When a discrepancy is detected, the system stages a Pending/Disputed action in a local audit queue, attaching the visual crop proof.  
  * **Export to Tax Professionals / GSP Partner Rail:** The merchant’s CA or tax filing partner can review and sync these staged decisions before the 14th of the month via standard GSP partner APIs or a 1-click JSON/Excel export, ensuring the merchant never gets trapped in "Deemed Acceptance" on unreceived stock.

## **Quick-Reference Defense Summary**

* **Merchant defaults on split-credit?:** Capped at 35% of daily QR velocity; backed by an automated UPI Autopay bank sweep after 48h of zero activity.  
* **Distributor relationship friction?:** Formatted as an objective reconciliation slip with the salesman's own pen markup attached for 1-tap approval.  
* **AI hallucinations on bad handwriting?:** Deterministic total checksum verification combined with yellow-highlight exception review for low-confidence items.  
* **Data privacy on Mandi-Pulse?:** Aggregated median price bands across pin codes with a 5-merchant minimum threshold; zero distributor names revealed.  
* **GST portal compliance liability?:** Positioned as an IMS decision staging queue and CA audit ledger, not an unauthenticated direct API write.