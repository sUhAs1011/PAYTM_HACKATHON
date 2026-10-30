import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';

import { AuditCompleteData, PayoutApprovedData } from '@contracts/contracts';

import { AuditTableComponent } from '../../components/audit-table/audit-table.component';
import { SoundboxTwinComponent } from '../../components/soundbox-twin/soundbox-twin.component';
import { SplitCreditComponent } from '../../components/split-credit/split-credit.component';
import { WhatsappDrawerComponent } from '../../components/whatsapp-drawer/whatsapp-drawer.component';
import { ApiService } from '../../services/api.service';
import { WebsocketService } from '../../services/websocket.service';
import { formatINR } from '../../shared/format';

export type CounterStage = 'IDLE' | 'PROCESSING' | 'AUDIT_ALERT' | 'RESOLVED';

/**
 * Countertop projector dashboard (`/counter`) — PRD F4/F5/F6 orchestration.
 *
 * The four PRD journey states are driven exclusively by the three CIS
 * WebSocket events (or their demo-mode injections, which flow through the
 * same observables):
 *   IDLE → (SCAN_STARTED) → PROCESSING → (AUDIT_COMPLETE) → AUDIT_ALERT
 *        → Paytm Button = APPROVE_SPLIT → (PAYOUT_APPROVED) → RESOLVED
 */
@Component({
  selector: 'app-counter',
  standalone: true,
  imports: [AuditTableComponent, SoundboxTwinComponent, SplitCreditComponent, WhatsappDrawerComponent],
  template: `
    <div class="counter-shell">
      <input
        #laptopFileInput
        type="file"
        accept="image/*"
        hidden
        (change)="onLaptopFileSelected($event)"
      />
      <header class="topbar">
        <div class="brand">
          <div class="mark">&#8377;</div>
          <div>
            <h1>ParchaPay AI</h1>
            <p>Paytm AI Soundbox &middot; Counter Dashboard</p>
          </div>
        </div>
        <div class="actions">
          @switch (ws.connectionState()) {
            @case ('OPEN') {
              <span class="chip live">&#9679; WebSocket live</span>
            }
            @case ('CONNECTING') {
              <span class="chip dim">&#9679; Connecting&hellip;</span>
            }
            @case ('RECONNECTING') {
              <span class="chip warn">&#9679; Reconnecting&hellip;</span>
            }
          }
          @if (stage() !== 'IDLE') {
            <button class="btn-ghost" (click)="reset()">Reset</button>
          }
          <button class="btn-primary" (click)="laptopFileInput.click()" [disabled]="busy()">
            &#128247; Upload Bill
          </button>
          <button class="btn-ghost" (click)="loadDemoBill()" [disabled]="busy()">
            Load Sample
          </button>
        </div>
      </header>

      @switch (stage()) {
        @case ('IDLE') {
          <section class="idle-wrap">
            <div class="pp-card idle-card">
              <div class="idle-icon">&#128247;</div>
              <h2>Awaiting supplier parcha&hellip;</h2>
              <p>
                Snap a photo on the shopkeeper&rsquo;s phone at <code>/scan</code>, or select an
                invoice photo directly from your laptop.
              </p>
              <div style="display: flex; gap: 12px; justify-content: center; margin-top: 20px; flex-wrap: wrap;">
                <button class="btn-primary big" (click)="laptopFileInput.click()" [disabled]="busy()">
                  &#128247; Upload Bill Photo
                </button>
                <button class="btn-ghost" (click)="loadDemoBill()" [disabled]="busy()">
                  Load Sample Fixture
                </button>
              </div>
            </div>
          </section>
        }
        @case ('PROCESSING') {
          <section class="processing-wrap">
            <div class="pp-card processing-card">
              <div class="receipt" aria-hidden="true">
                <div class="paper">
                  <span></span><span></span><span></span><span></span><span></span><span></span>
                </div>
                <div class="laser"></div>
              </div>
              <h2>Auditing Parcha&hellip;</h2>
              <p class="pmsg">{{ processingMessage() }}</p>
            </div>
          </section>
        }
        @default {
          @if (audit(); as a) {
            <section class="audit-grid">
              <div class="left-col">
                <div class="pp-card banner">
                  <div class="who">
                    <h2>{{ a.supplier_name }}</h2>
                    <p>{{ a.invoice_number }}</p>
                  </div>
                  <div class="money">
                    <div>
                      <span class="pp-label">Billed</span>
                      <strong>{{ inr(a.billed_total) }}</strong>
                    </div>
                    <div class="good">
                      <span class="pp-label">Approved</span>
                      <strong>{{ inr(a.approved_total) }}</strong>
                    </div>
                    <div>
                      <span class="pp-label">Overcharge</span>
                      @if (a.overcharge_amount > 0) {
                        <strong class="bad">{{ inr(a.overcharge_amount) }}</strong>
                      } @else {
                        <strong>None</strong>
                      }
                    </div>
                  </div>
                </div>

                <div class="pp-card ims" [class.active]="stage() === 'RESOLVED'">
                  <div class="ims-head">
                    <span class="pp-label">GST IMS Shield</span>
                    @if (stage() === 'RESOLVED') {
                      <span class="chip on">Shield Active &middot; {{ payout()?.gst_ims_state }}</span>
                    } @else {
                      <span class="chip">{{ a.gst_ims_shield.status }}</span>
                    }
                  </div>
                  @if (stage() === 'RESOLVED') {
                    <p>
                      Invoice staged as disputed in the IMS queue &mdash; blocks deemed acceptance on
                      unreceived stock before the 14th.
                    </p>
                  } @else {
                    <p>{{ a.gst_ims_shield.flag_reason }}</p>
                    <p class="deadline">Auto-lock deadline: {{ a.gst_ims_shield.deadline }}</p>
                  }
                </div>

                <app-audit-table [items]="a.items" />

                @if (hasPenEdit()) {
                  <div class="pp-card crop">
                    <div class="crop-head">
                      <span class="pp-label">Pen edit &middot; dispute crop</span>
                      <span class="chip">{{ a.items.length }} line items audited</span>
                    </div>
                    <img [src]="cropSrc()" alt="Cropped pen-marked region of the supplier bill" />
                  </div>
                }
              </div>

              <div class="right-col">
                <app-soundbox-twin
                  [processing]="stage() === 'PROCESSING'"
                  [audit]="audit()"
                  [payout]="payout()"
                  [busy]="busy()"
                  (approve)="approve()"
                  (openSplit)="openSplitDrawer()"
                />
                @if (payout(); as p) {
                  <div class="pp-card payout-note">
                    <span class="pp-label">Payout</span>
                    <p>
                      {{ inr(p.loan_schedule.principal) }} to {{ a.supplier_name }} via
                      {{
                        p.settlement_method === 'SOUNDBOX_7_DAY_SPLIT'
                          ? '7-Day Soundbox Split'
                          : p.settlement_method
                      }}
                      &middot; WhatsApp claim {{ p.whatsapp_claim.status }}
                    </p>
                  </div>
                }
              </div>
            </section>
          }
        }
      }

      @if (payout(); as p) {
        @if (whatsappOpen()) {
          <app-whatsapp-drawer
            [claim]="p.whatsapp_claim"
            [cropUrl]="cropSrc()"
            [approvedTotal]="p.loan_schedule.principal"
            (closed)="whatsappOpen.set(false)"
          />
        }
      }

      @if (splitDrawerOpen()) {
        @if (splitPreApproval(); as pre) {
          @if (payout(); as p) {
            <app-split-credit
              [preApproval]="pre"
              [schedule]="p.loan_schedule"
              (closed)="splitDrawerOpen.set(false)"
            />
          }
        }
      }
    </div>
  `,
  styles: `
    .counter-shell {
      max-width: 1720px;
      margin: 0 auto;
      padding: 20px 28px 60px;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 22px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .mark {
      width: 48px;
      height: 48px;
      border-radius: 13px;
      display: grid;
      place-items: center;
      font-size: 24px;
      font-weight: 800;
      color: #fff;
      background: linear-gradient(135deg, var(--pp-blue), var(--pp-navy));
      box-shadow: 0 8px 22px rgba(0, 186, 242, 0.35);
    }
    .brand h1 {
      margin: 0;
      font-size: 22px;
    }
    .brand p {
      margin: 2px 0 0;
      font-size: 12px;
      color: var(--pp-text-dim);
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .chip {
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 11.5px;
      font-weight: 800;
      letter-spacing: 0.03em;
      border: 1px solid var(--pp-line);
      color: var(--pp-text-dim);
      background: rgba(255, 255, 255, 0.03);
      white-space: nowrap;
    }
    .chip.live {
      color: var(--pp-green);
      border-color: rgba(47, 208, 122, 0.4);
      background: var(--pp-green-bg);
    }
    .chip.warn {
      color: var(--pp-yellow);
      border-color: rgba(255, 204, 71, 0.4);
      background: var(--pp-yellow-bg);
    }
    .chip.dim {
      color: var(--pp-text-faint);
    }
    .chip.on {
      color: var(--pp-green);
      background: var(--pp-green-bg);
      border-color: rgba(47, 208, 122, 0.4);
    }

    .btn-ghost,
    .btn-primary {
      padding: 11px 18px;
      border-radius: 12px;
      font-size: 14px;
      font-weight: 800;
      border: 1px solid var(--pp-line);
      background: transparent;
      color: var(--pp-text-dim);
    }
    .btn-ghost:hover {
      color: var(--pp-text);
      border-color: var(--pp-blue);
    }
    .btn-primary {
      border: none;
      background: linear-gradient(135deg, var(--pp-blue), #0074c8);
      color: #00121f;
    }
    .btn-primary:hover {
      filter: brightness(1.08);
    }
    .btn-primary.big {
      padding: 15px 26px;
      font-size: 15px;
    }

    .idle-wrap,
    .processing-wrap {
      display: grid;
      place-items: center;
      min-height: 68vh;
    }
    .idle-card {
      max-width: 680px;
      padding: 44px 42px;
      text-align: center;
    }
    .idle-icon {
      font-size: 40px;
      margin-bottom: 10px;
    }
    .idle-card h2 {
      margin: 0 0 12px;
      font-size: 24px;
    }
    .idle-card p {
      margin: 0 0 10px;
      color: var(--pp-text-dim);
      font-size: 14px;
      line-height: 1.65;
    }
    .idle-card code {
      color: var(--pp-blue-soft);
      background: rgba(0, 186, 242, 0.1);
      padding: 2px 6px;
      border-radius: 6px;
    }
    .fail-safe {
      font-size: 12.5px !important;
      color: var(--pp-text-faint) !important;
    }
    .idle-card .btn-primary {
      margin-top: 14px;
    }

    .processing-card {
      width: min(520px, 92vw);
      padding: 40px 36px;
      text-align: center;
    }
    .receipt {
      position: relative;
      width: 150px;
      height: 190px;
      margin: 0 auto 22px;
      border-radius: 8px 8px 14px 14px;
      background: #f4f1e8;
      overflow: hidden;
      box-shadow: 0 14px 30px rgba(0, 0, 0, 0.45);
    }
    .paper {
      display: flex;
      flex-direction: column;
      gap: 13px;
      padding: 20px 16px;
    }
    .paper span {
      height: 7px;
      border-radius: 4px;
      background: #c9c4b4;
    }
    .paper span:nth-child(2) {
      width: 70%;
    }
    .paper span:nth-child(4) {
      width: 80%;
    }
    .paper span:nth-child(5) {
      width: 55%;
    }
    .laser {
      position: absolute;
      left: 0;
      right: 0;
      height: 26px;
      background: linear-gradient(180deg, transparent, rgba(0, 186, 242, 0.75), transparent);
      animation: pp-laser 1.3s ease-in-out infinite;
    }
    @keyframes pp-laser {
      0%, 100% { top: 4%; }
      50% { top: 84%; }
    }
    .processing-card h2 {
      margin: 0 0 6px;
      font-size: 24px;
    }
    .pmsg {
      margin: 0;
      color: var(--pp-text-dim);
      font-size: 13.5px;
    }

    .audit-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 400px;
      gap: 22px;
      align-items: start;
    }
    .left-col,
    .right-col {
      display: flex;
      flex-direction: column;
      gap: 18px;
      min-width: 0;
    }
    .right-col {
      position: sticky;
      top: 20px;
    }

    .banner {
      padding: 20px 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
    }
    .who h2 {
      margin: 0 0 4px;
      font-size: 21px;
    }
    .who p {
      margin: 0;
      color: var(--pp-text-dim);
      font-size: 13px;
    }
    .money {
      display: flex;
      gap: 26px;
      flex-wrap: wrap;
    }
    .money > div {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .money strong {
      font-size: 24px;
    }
    .money .good strong {
      color: var(--pp-green);
    }
    .money .bad {
      color: var(--pp-red);
    }

    .ims {
      padding: 16px 20px;
    }
    .ims-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .ims p {
      margin: 0 0 4px;
      font-size: 13.5px;
      color: var(--pp-text-dim);
      line-height: 1.55;
    }
    .ims .deadline {
      margin: 0;
      font-size: 12px;
      color: var(--pp-text-faint);
    }
    .ims.active {
      border-color: rgba(47, 208, 122, 0.45);
      box-shadow: var(--pp-shadow), 0 0 0 1px rgba(47, 208, 122, 0.25);
    }

    .crop {
      padding: 16px 18px;
    }
    .crop-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }
    .crop img {
      width: 100%;
      max-height: 320px;
      object-fit: contain;
      border-radius: 10px;
      border: 1px solid var(--pp-line);
      display: block;
      background: #0b1322;
    }

    .payout-note {
      padding: 14px 18px;
    }
    .payout-note p {
      margin: 6px 0 0;
      font-size: 13px;
      color: var(--pp-text-dim);
      line-height: 1.55;
    }

    @media (max-width: 1080px) {
      .audit-grid {
        grid-template-columns: 1fr;
      }
      .right-col {
        position: static;
      }
    }
  `,
})
export class CounterComponent implements OnDestroy {
  private readonly api = inject(ApiService);
  readonly ws = inject(WebsocketService);

  protected readonly inr = formatINR;

  readonly stage = signal<CounterStage>('IDLE');
  readonly processingMessage = signal('Auditing supplier parcha via Gemini 2.5 Flash…');
  readonly audit = signal<AuditCompleteData | null>(null);
  readonly payout = signal<PayoutApprovedData | null>(null);
  readonly whatsappOpen = signal(false);
  readonly splitDrawerOpen = signal(false);
  readonly busy = signal(false);

  readonly hasPenEdit = computed(() => !!this.audit()?.items.some((i) => i.has_pen_markup));
  readonly cropSrc = computed(() => {
    const a = this.audit();
    return a ? this.api.assetUrl(a.dispute_crop_url) : '';
  });
  readonly splitPreApproval = computed(() => this.audit()?.split_credit_pre_approval ?? null);

  private readonly subs: Subscription[] = [];

  constructor() {
    this.subs.push(
      // CIS Event 1 — within <0.5s of the phone starting an upload.
      this.ws.scanStarted$.subscribe((d) => {
        this.stage.set('PROCESSING');
        this.processingMessage.set(d.message || 'Auditing parcha…');
      }),
      // CIS Event 2 — full audited payload.
      this.ws.auditComplete$.subscribe((d) => this.applyAudit(d)),
      // CIS Event 3 — Paytm Button resolution outcome.
      this.ws.payoutApproved$.subscribe((d) => this.applyPayout(d)),
    );
  }

  async onLaptopFileSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    if (!file) {
      return;
    }
    this.busy.set(true);
    this.stage.set('PROCESSING');
    this.processingMessage.set('Auditing supplier parcha via Gemini 2.5 Flash…');
    try {
      const audit = await this.api.scan(file);
      this.applyAudit(audit);
    } catch (err) {
      console.error('[counter] Bill scan failed', err);
      alert(err instanceof Error ? err.message : 'Bill scan failed');
      this.stage.set('IDLE');
    } finally {
      this.busy.set(false);
    }
  }

  async loadDemoBill(): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.busy.set(true);
    this.stage.set('PROCESSING');
    this.processingMessage.set('Auditing supplier parcha via Gemini 2.5 Flash…');
    try {
      const audit = await this.api.loadSample();
      // Demo mode: the mock WS injection already drove the state machine; in
      // real mode /api/demo/load-sample may not broadcast, so apply directly.
      this.applyAudit(audit);
    } catch (err) {
      console.error('[counter] load-sample failed', err);
      this.stage.set('IDLE');
    } finally {
      this.busy.set(false);
    }
  }

  async approve(): Promise<void> {
    const audit = this.audit();
    if (!audit || this.busy() || this.stage() === 'RESOLVED') {
      return;
    }
    this.busy.set(true);
    try {
      const payout = await this.api.resolve(audit.invoice_id);
      // Demo mode: the mock PAYOUT_APPROVED injection already applied this;
      // real mode may deliver it via WS — applying directly is idempotent.
      this.applyPayout(payout);
    } catch (err) {
      console.error('[counter] APPROVE_SPLIT failed', err);
    } finally {
      this.busy.set(false);
    }
  }

  openSplitDrawer(): void {
    this.splitDrawerOpen.set(true);
  }

  reset(): void {
    this.stage.set('IDLE');
    this.audit.set(null);
    this.payout.set(null);
    this.whatsappOpen.set(false);
    this.splitDrawerOpen.set(false);
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  private applyAudit(audit: AuditCompleteData): void {
    // Laptop uploads receive both a REST response and AUDIT_COMPLETE over WS.
    // Treat the invoice ID as the transition key so the Soundbox speaks and
    // drawer state changes only once for that scan.
    if (this.audit()?.invoice_id === audit.invoice_id && this.stage() === 'AUDIT_ALERT') {
      return;
    }
    this.audit.set(audit);
    this.payout.set(null);
    this.whatsappOpen.set(false);
    this.splitDrawerOpen.set(false);
    this.stage.set('AUDIT_ALERT');
  }

  private applyPayout(payout: PayoutApprovedData): void {
    if (this.payout()?.invoice_id === payout.invoice_id && this.stage() === 'RESOLVED') {
      return;
    }
    this.payout.set(payout);
    this.whatsappOpen.set(true);
    this.stage.set('RESOLVED');
  }
}
