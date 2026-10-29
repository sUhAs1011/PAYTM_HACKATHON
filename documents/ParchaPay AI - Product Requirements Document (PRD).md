# **Product Requirements Document: ParchaPay AI**

**Project Name:** ParchaPay AI  
**Track:** Track 1 — Merchant Growth AI (Paytm Build for India AI Hackathon 2026\)  
**Core Stack:** Angulaar 19 (Frontend) \| Python FastAPI (Backend) \| Gemini 2.5 Flash (Vision) \| Sarvam AI (Voice) \| Supabase Postgres \+ pgvector (Shared DB)  
\|---\|---\|---\|

# **1\. Product Goal & Demo Objective**

Build an end-to-end working system where a shopkeeper scans a physical wholesale bill (parcha) on their phone, and within 3 seconds, the Paytm AI Soundbox Digital Twin on the laptop projector speaks a local-language price audit, highlights handwritten pen edits, checks local pin-code rates, and lets the merchant trigger a supplier dispute note \+ a 7-day QR split-credit loan with one button press.

---

# **2\. User Personas (In the Demo)**

1. **The Merchant (Primary User):** A neighborhood kirana or medical store owner using a Paytm Soundbox who receives stock with printed/handwritten bills and has no time for manual math or data entry.  
2. **The Distributor Salesman (Counterparty):** Delivers goods, makes ballpoint-pen adjustments on the paper slip for missing items, and receives an instant reconciliation link \+ payout.

---

# **3\. Feature Scope & Priority (P0 vs. P1)**

## **P0: Must-Have Features (Core Live Demo Flow)**

| ID | Feature Name | User Story | Key Acceptance Criteria |
| :---- | :---- | :---- | :---- |
| **F1** | Mobile Bill Scanner (`/scan`) | Merchant snaps a photo of a paper bill on their phone (or picks a sample bill on laptop). | Opens native phone camera via browser; uploads image to FastAPI and notifies the laptop dashboard via WebSocket in \<0.5s. |
| **F2** | Gemini 2.5 Flash Extraction & Pen-Edit Crop | Extracts supplier info, line items, GST, free units, and detects handwritten pen strikethroughs. | Returns 100% valid JSON via Pydantic schema; returns bounding box coordinates for any pen-edited line; backend crops the pen edit using Pillow and saves the image URL. |
| **F3** | Deterministic Math & Price Audit Engine | Calculates true per-unit cost and checks for overcharges without using AI for math. | Verifies Qty x Rate \+ Tax \= Line Total; calculates True Landed Cost \= (Net Amount \+ GST) / (Billed Qty \+ Free Units); flags items where rate \> merchant's last bill OR \> local pin-code median (Mandi-Pulse); flags items with \<80% OCR confidence in yellow for 1-tap review. |
| **F4** | Paytm AI Soundbox Digital Twin (`/counter`) | Interactive countertop UI on the laptop screen simulating the physical Paytm AI Soundbox. | Front Screen UI displays Red/Green price comparison card and net approved amount; Speaker Audio plays Sarvam AI voice alert in Hindi/Kannada/English within 3 seconds; Paytm Button is a clickable hardware button that approves the audit and triggers downstream actions. |
| **F5** | 1-Tap Resolution (WhatsApp Drawer \+ GST Flag) | Pressing the Paytm Button resolves the discrepancy and protects tax compliance. | Opens an on-screen Supplier WhatsApp Preview Drawer showing the polite reconciliation text, the cropped pen-edit photo, and a Paytm Payment Link for the corrected amount; updates invoice status to Disputed / Pending in the GST IMS Queue table. |
| **F6** | 7-Day Soundbox Split-Credit | Merchant finances the bill payout using incoming daily customer QR collections. | Enforces 35% Daily Velocity Cap (max daily cut \<= 35% of store's average daily QR volume); displays an interactive 7-day repayment progress bar \+ active UPI Autopay backup mandate badge. |

## **P1: Nice-to-Have Features (Quick UI Completeness)**

* **F7: Inward Expiry Radar & Restock Voice Query:** Shows items expiring within 30 days and answers *"When did I last buy Fortune Oil?"* via a simple SQL filter and pre-wired Soundbox button.  
* **F8: 1-Click Tally XML / Marg CSV Export:** Frontend button that downloads the current invoice JSON formatted as a standard .xml or .csv file for semi-organized stores.

---

# **4\. End-to-End User Journey (State Flow)**

1. **State 1 (IDLE):** Phone is on `/scan`. Laptop projector is on `/counter` showing today's QR collections.  
2. **State 2 (PROCESSING \~2.5s):** Merchant snaps photo of crumpled bill on phone. Laptop Soundbox screen switches to "Auditing Parcha..." animation while FastAPI runs Gemini 2.5 Flash \+ pgvector SKU match \+ math audit \+ Sarvam TTS in parallel.  
3. **State 3 (AUDIT ALERT):** Soundbox speaks aloud: *"Sharmaji bill checked. Oil rate up by Rs 6, pen math error of Rs 140\. Pay Rs 13,860."* Dashboard shows extracted table with red highlights, Mandi-Pulse badge, and cropped photo of pen strikethrough.  
4. **State 4 (RESOLVED & FINANCED):** Merchant clicks physical Paytm Button. Slide-out WhatsApp Simulator shows reconciliation card \+ Payment Link. GST IMS status flips to "Shield Active". Merchant clicks "Pay via 7-Day Soundbox Split" \-\> Repayment bar animates Day 1 deduction from QR sweep.

---

# **5\. Core Business Rules & Guardrails**

1. **Zero LLM Arithmetic:** Gemini 2.5 Flash only extracts raw numbers and bounding boxes. Python Decimal logic computes all subtotals, taxes, landed costs, and differences.  
2. **3-Tier Price Benchmark Waterfall:**  
   * **Check 1:** Compare against merchant's own last 3 bills for that SKU.  
   * **Check 2:** Compare against Mandi-Pulse (median price in the same pin code via pgvector canonical SKU match, active only if \>= 5 store records exist).  
   * **Check 3:** Compare printed MRP vs. Landed Cost to warn if retail margin drops below category baseline (\<8%).  
3. **OCR Confidence Check:** Any line item with confidence \<0.80 highlights in yellow for a 1-tap human confirmation before payout.  
4. **Lending Safety Cap:** Max 7-day credit limit \= `(Merchant 30-Day Avg Daily QR Volume x 0.35) x 7`.

---

# **6\. Non-Functional Requirements (Hackathon Targets)**

* **End-to-End Latency:** \< 3.5 seconds from photo upload to Soundbox voice playback.  
* **Fail-Safe Demo Mode:** A 1-click "Load Demo Bill" button on the laptop dashboard in case venue mobile internet or camera lighting fails during the pitch.  
* **Scalability:** Supabase Postgres \+ pgvector schema scales seamlessly from 1 demo merchant to 100,000+ merchants.

