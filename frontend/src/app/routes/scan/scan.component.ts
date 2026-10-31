import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AuditedInvoiceResponse, DraftLineItem, LineItemCorrection, ScanDraftResponse } from '@contracts/contracts';

import { ApiService } from '../../services/api.service';
import { formatINR } from '../../shared/format';

type ScanStage = 'IDLE' | 'UPLOADING' | 'REVIEW' | 'AUDIT_READY' | 'ERROR';

/**
 * Mobile scanner route (`/scan`) — PRD F1.
 *
 * Camera constraint (CIS §6.1): zero WebRTC streams. A hidden file input with
 * `capture="environment"` launches the phone's native rear-camera app — which
 * also works over plain http:// LAN origins where getUserMedia would be
 * blocked. Uploads multipart/form-data (file + merchant_id) to
 * POST /api/parcha/scan; if the backend is unreachable, the fail-safe demo
 * fixture takes over so the flow is always demonstrable.
 */
@Component({
  selector: 'app-scan',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <div class="scan-shell">
      <header class="scan-header">
        <div class="brand-mark">&#8377;</div>
        <div>
          <h1>ParchaPay AI</h1>
          <p>Wholesale parcha scanner</p>
        </div>
      </header>

      <input
        #cameraInput
        id="cameraInput"
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        (change)="onFileSelected($event)"
      />

      @switch (stage()) {
        @case ('IDLE') {
          <section class="pp-card capture-card">
            <p class="pp-label">Step 1</p>
            <h2>Snap the supplier parcha</h2>
            <p class="hint">
              Point at the delivery bill — thermal printouts, pen markups and mandi slips all work.
            </p>
            <label for="cameraInput" class="capture-btn">
              <span class="cam-icon">&#128247;</span>
              <span>Open camera &amp; capture bill</span>
            </label>
            <div class="divider"><span>no camera handy?</span></div>
            <button class="btn-ghost" (click)="loadDemo()" [disabled]="busy()">
              Load Demo Bill (fail-safe)
            </button>
            <label class="review-toggle">
              <input type="checkbox" [(ngModel)]="reviewMode" [disabled]="busy()" />
              Review OCR before audit
            </label>
            <p class="desktop-hint">
              This is the shopkeeper&rsquo;s phone view. On a laptop, open the
              <a routerLink="/counter">Soundbox counter dashboard &rarr;</a>
            </p>
          </section>
        }
        @case ('UPLOADING') {
          <section class="pp-card upload-card">
            @if (previewUrl(); as p) {
              <img [src]="p" class="preview" alt="Captured bill preview" />
            }
            <h2>Auditing parcha&hellip;</h2>
            <ul class="pipeline">
              <li>Gemini 3.6 Flash extraction</li>
              <li>Decimal math &amp; checksum verification</li>
              <li>Mandi-Pulse pin-code comparison</li>
            </ul>
            <div class="shimmer" aria-hidden="true"></div>
          </section>
        }
        @case ('REVIEW') {
          @if (draft(); as d) {
            <section class="pp-card capture-card">
              <p class="pp-label">Step 2</p>
              <h2>Review parsed bill</h2>
              <p class="hint">{{ d.supplier_name }} &middot; {{ d.invoice_number }}</p>
              <table class="review-table">
                <thead>
                  <tr>
                    <th>Item</th><th>Printed</th><th>Qty</th><th>Free</th><th>Rate</th><th>GST%</th>
                  </tr>
                </thead>
                <tbody>
                  @for (item of editableItems(); track $index) {
                    <tr [class.low-confidence]="item.ocr_confidence < 0.8" [class.pen-markup]="item.has_pen_markup">
                      <td><input type="text" [(ngModel)]="item.raw_item_name" /></td>
                      <td><input type="number" [(ngModel)]="item.printed_qty" /></td>
                      <td><input type="number" [(ngModel)]="item.billed_qty" /></td>
                      <td><input type="number" [(ngModel)]="item.free_qty" /></td>
                      <td><input type="number" step="0.01" [(ngModel)]="item.billed_rate" /></td>
                      <td><input type="number" step="0.01" [(ngModel)]="item.tax_percent" /></td>
                    </tr>
                  }
                </tbody>
              </table>
              <button class="capture-btn" (click)="confirmDraft()" [disabled]="busy()">
                Confirm &amp; audit
              </button>
              <button class="btn-ghost" (click)="reset()" [disabled]="busy()">
                Discard draft
              </button>
            </section>
          }
        }
        @case ('AUDIT_READY') {
          @if (audit(); as a) {
            <section class="pp-card result-card">
              <span
                class="chip"
                [class.red]="a.overcharge_amount > 0"
                [class.green]="a.overcharge_amount === 0"
              >
                {{
                  a.overcharge_amount > 0
                    ? 'Overcharge ' + inr(a.overcharge_amount)
                    : 'Bill verified'
                }}
              </span>
              <h2>{{ a.supplier_name }}</h2>
              <p class="inv">{{ a.invoice_number }} &middot; {{ a.invoice_date }}</p>
              <div class="totals">
                <div>
                  <span class="pp-label">Billed</span>
                  <strong>{{ inr(a.billed_total) }}</strong>
                </div>
                <div class="approved">
                  <span class="pp-label">Pay</span>
                  <strong>{{ inr(a.approved_total) }}</strong>
                </div>
              </div>
              <ul class="mini-items">
                @for (item of a.items; track item.item_name) {
                  <li
                    [class.bad]="item.rate_status !== 'OK'"
                    [class.warn]="item.ocr_confidence < 0.8"
                  >
                    <span class="dot"></span>{{ item.item_name }}
                  </li>
                }
              </ul>
              @if (flaggedCount() > 0) {
                <p class="flag-count">{{ flaggedCount() }} of {{ a.items.length }} items need attention</p>
              }
              <blockquote class="transcript">&#128266; &ldquo;{{ a.voice_transcript }}&rdquo;</blockquote>
              <p class="counter-hint">The Soundbox twin on the counter screen is speaking this audit.</p>
              <div class="actions">
                <a routerLink="/counter" class="btn-ghost">Open counter view</a>
                <button class="btn-primary" (click)="reset()">Scan another parcha</button>
              </div>
            </section>
          }
        }
        @case ('ERROR') {
          <section class="pp-card error-card">
            <h2>Couldn&rsquo;t process that photo</h2>
            <p>{{ errorMessage() }}</p>
            <div class="actions">
              <label for="cameraInput" class="btn-primary">Try again</label>
              <button class="btn-ghost" (click)="reset()">Start over</button>
            </div>
          </section>
        }
      }
    </div>
  `,
  styles: `
    .scan-shell {
      max-width: 480px;
      margin: 0 auto;
      padding: 20px 16px 48px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    .scan-header {
      display: flex;
      align-items: center;
      gap: 12px;
      color: var(--pp-text);
    }
    .brand-mark {
      width: 44px;
      height: 44px;
      border-radius: 12px;
      display: grid;
      place-items: center;
      font-size: 22px;
      font-weight: 800;
      color: #fff;
      background: linear-gradient(135deg, var(--pp-blue), var(--pp-navy));
      box-shadow: 0 6px 18px rgba(0, 186, 242, 0.35);
    }
    .scan-header h1 {
      margin: 0;
      font-size: 20px;
      letter-spacing: 0.01em;
    }
    .scan-header p {
      margin: 2px 0 0;
      font-size: 12px;
      color: var(--pp-text-dim);
    }

    .pp-card {
      padding: 22px 20px;
    }

    .capture-card h2,
    .upload-card h2,
    .result-card h2,
    .error-card h2 {
      margin: 6px 0 8px;
      font-size: 20px;
    }
    .hint {
      margin: 0 0 18px;
      color: var(--pp-text-dim);
      font-size: 14px;
      line-height: 1.5;
    }

    .capture-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      width: 100%;
      padding: 18px;
      border-radius: 16px;
      border: 1px solid rgba(0, 186, 242, 0.45);
      background: linear-gradient(135deg, rgba(0, 186, 242, 0.18), rgba(0, 41, 112, 0.35));
      color: var(--pp-text);
      font-size: 16px;
      font-weight: 700;
      transition: transform 0.12s ease, box-shadow 0.12s ease;
    }
    .capture-btn:active {
      transform: scale(0.98);
      box-shadow: 0 0 0 3px rgba(0, 186, 242, 0.25);
    }
    .cam-icon {
      font-size: 20px;
    }

    .divider {
      display: flex;
      align-items: center;
      gap: 12px;
      margin: 18px 0 10px;
      color: var(--pp-text-faint);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .divider::before,
    .divider::after {
      content: '';
      flex: 1;
      height: 1px;
      background: var(--pp-line);
    }

    .review-toggle {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-top: 10px;
      font-size: 0.85rem;
      color: var(--muted, #5f6470);
      cursor: pointer;
    }
    .review-table {
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0;
      font-size: 0.8rem;
    }
    .review-table th { text-align: left; padding: 4px 6px; color: var(--muted, #5f6470); }
    .review-table td { padding: 2px 4px; }
    .review-table input {
      width: 100%;
      padding: 4px 6px;
      border: 1px solid var(--border, #d8dbe3);
      border-radius: 6px;
      font: inherit;
    }
    .review-table tr.low-confidence { background: rgba(255, 193, 7, 0.12); }
    .review-table tr.pen-markup { background: rgba(244, 67, 54, 0.08); }
    .desktop-hint {
      margin: 18px 0 0;
      font-size: 12px;
      color: var(--pp-text-faint);
      line-height: 1.6;
      text-align: center;
    }
    .desktop-hint a {
      color: var(--pp-blue-soft);
      font-weight: 700;
      text-decoration: none;
    }
    .desktop-hint a:hover {
      text-decoration: underline;
    }

    .btn-ghost,
    .btn-primary {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 12px 18px;
      border-radius: 12px;
      font-size: 14px;
      font-weight: 700;
      border: 1px solid var(--pp-line);
      background: transparent;
      color: var(--pp-text-dim);
      text-decoration: none;
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

    .preview {
      width: 100%;
      max-height: 220px;
      object-fit: contain;
      border-radius: 12px;
      border: 1px solid var(--pp-line);
      margin-bottom: 14px;
    }

    .pipeline {
      margin: 0 0 14px;
      padding-left: 20px;
      color: var(--pp-text-dim);
      font-size: 13px;
      line-height: 1.9;
    }

    .shimmer {
      height: 10px;
      border-radius: 6px;
      background: linear-gradient(90deg, var(--pp-line) 25%, rgba(0, 186, 242, 0.55) 50%, var(--pp-line) 75%);
      background-size: 200% 100%;
      animation: pp-sweep 1.1s linear infinite;
    }
    @keyframes pp-sweep {
      from { background-position: 200% 0; }
      to { background-position: -200% 0; }
    }

    .chip {
      display: inline-block;
      padding: 5px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.03em;
      background: var(--pp-yellow-bg);
      color: var(--pp-yellow);
    }
    .chip.red {
      background: var(--pp-red-bg);
      color: var(--pp-red);
    }
    .chip.green {
      background: var(--pp-green-bg);
      color: var(--pp-green);
    }

    .inv {
      margin: 2px 0 14px;
      color: var(--pp-text-dim);
      font-size: 13px;
    }

    .totals {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 16px;
    }
    .totals > div {
      border: 1px solid var(--pp-line);
      border-radius: 12px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .totals strong {
      font-size: 22px;
    }
    .approved strong {
      color: var(--pp-green);
    }

    .mini-items {
      list-style: none;
      margin: 0 0 14px;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 13px;
    }
    .mini-items li {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--pp-text-dim);
    }
    .mini-items .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--pp-green);
      flex: none;
    }
    .mini-items li.bad .dot {
      background: var(--pp-red);
    }
    .mini-items li.bad {
      color: var(--pp-red);
      font-weight: 600;
    }
    .mini-items li.warn .dot {
      background: var(--pp-yellow);
    }

    .transcript {
      margin: 0 0 12px;
      padding: 12px 14px;
      border-left: 3px solid var(--pp-blue);
      background: rgba(0, 186, 242, 0.08);
      border-radius: 0 10px 10px 0;
      font-size: 13px;
      color: var(--pp-text);
      line-height: 1.55;
    }

    .counter-hint {
      margin: 0 0 16px;
      font-size: 12px;
      color: var(--pp-text-faint);
    }

    .flag-count {
      margin: -6px 0 14px;
      font-size: 12px;
      font-weight: 700;
      color: var(--pp-yellow);
    }

    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .actions .btn-primary {
      flex: 1;
    }

    .error-card p {
      color: var(--pp-red);
      font-size: 14px;
    }
  `,
})
export class ScanComponent {
  private readonly api = inject(ApiService);

  protected readonly inr = formatINR;

  readonly stage = signal<ScanStage>('IDLE');
  readonly busy = signal(false);
  readonly previewUrl = signal<string | null>(null);
  readonly audit = signal<AuditedInvoiceResponse | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly reviewMode = signal(false);
  readonly draft = signal<ScanDraftResponse | null>(null);
  readonly editableItems = signal<DraftLineItem[]>([]);

  readonly flaggedCount = computed(() => {
    const a = this.audit();
    if (!a) {
      return 0;
    }
    return a.items.filter(
      (i) => i.rate_status !== 'OK' || i.ocr_confidence < 0.8 || i.has_pen_markup,
    ).length;
  });

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    if (!file) {
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      this.fail('Photo is larger than 20 MB. Retake at a lower resolution.');
      return;
    }
    const previous = this.previewUrl();
    if (previous) {
      URL.revokeObjectURL(previous);
    }
    this.previewUrl.set(URL.createObjectURL(file));
    void this.upload(file);
  }

  async loadDemo(): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.busy.set(true);
    this.stage.set('UPLOADING');
    this.errorMessage.set(null);
    try {
      const audit = await this.api.loadSample();
      this.audit.set(audit);
      this.stage.set('AUDIT_READY');
    } catch (err) {
      this.fail(err instanceof Error ? err.message : 'Could not load the demo bill.');
    } finally {
      this.busy.set(false);
    }
  }

  async confirmDraft(): Promise<void> {
    const draft = this.draft();
    if (!draft || this.busy()) {
      return;
    }
    this.busy.set(true);
    try {
      const corrections: LineItemCorrection[] = this.editableItems()
        .map((item, idx) => {
          const orig = draft.items[idx];
          const patch: LineItemCorrection = { id: item.id };
          if (item.raw_item_name !== orig.raw_item_name) patch.raw_item_name = item.raw_item_name;
          if (item.printed_qty !== orig.printed_qty) patch.printed_qty = item.printed_qty;
          if (item.billed_qty !== orig.billed_qty) patch.billed_qty = item.billed_qty;
          if (item.free_qty !== orig.free_qty) patch.free_qty = item.free_qty;
          if (item.billed_rate !== orig.billed_rate) patch.billed_rate = item.billed_rate;
          if (item.tax_percent !== orig.tax_percent) patch.tax_percent = item.tax_percent;
          return patch;
        })
        .filter((c) => Object.keys(c).length > 1);
      const audit = await this.api.confirmReview(draft.invoice_id, {
        merchant_id: draft.merchant_id,
        corrections,
      });
      this.draft.set(null);
      this.editableItems.set([]);
      this.audit.set(audit);
      this.stage.set('AUDIT_READY');
    } catch (err) {
      this.fail(err instanceof Error ? err.message : 'Confirm failed');
    } finally {
      this.busy.set(false);
    }
  }

  reset(): void {
    const previous = this.previewUrl();
    if (previous) {
      URL.revokeObjectURL(previous);
    }
    this.previewUrl.set(null);
    this.audit.set(null);
    this.draft.set(null);
    this.editableItems.set([]);
    this.errorMessage.set(null);
    this.stage.set('IDLE');
  }

  private async upload(file: File): Promise<void> {
    this.busy.set(true);
    this.stage.set('UPLOADING');
    this.errorMessage.set(null);
    try {
      if (this.reviewMode()) {
        const draft = await this.api.scanDraft(file);
        this.draft.set(draft);
        this.editableItems.set(draft.items.map((i) => ({ ...i })));
        this.stage.set('REVIEW');
        this.busy.set(false);
        return;
      }
      const audit = await this.api.scan(file);
      this.audit.set(audit);
      this.stage.set('AUDIT_READY');
    } catch (err) {
      // scan() falls back to the fixture on network failure; reaching here
      // means a local error (bad file, etc.).
      this.fail(err instanceof Error ? err.message : 'Upload failed. Please try again.');
    } finally {
      this.busy.set(false);
    }
  }

  private fail(message: string): void {
    this.stage.set('ERROR');
    this.errorMessage.set(message);
  }
}
