import { Component, OnDestroy, computed, effect, inject, input, output, signal } from '@angular/core';

import { LoanSchedule, SplitCreditPreApproval } from '@contracts/contracts';

import { formatINR } from '../../shared/format';
import { ApiService, SweepDayPreview, SweepPreviewResponse } from '../../services/api.service';

const DEMO_FIXTURE_INVOICE_ID = 'demo-golden-fixture-001';

/**
 * 7-Day Split-Credit drawer (PRD F6) — reveals the loan schedule created by
 * APPROVE_SPLIT. Renders the pre-approval caps from the audit payload and
 * animates the Day 1 QR-sweep deduction from the PAYOUT_APPROVED
 * `loan_schedule`. All numbers are contract values rendered as-is; the
 * underwriting math behind them belongs to Module 4's Decimal engine.
 */
@Component({
  selector: 'app-split-credit',
  standalone: true,
  template: `
    <div class="backdrop" (click)="closed.emit()"></div>
    <section class="sheet" role="dialog" aria-label="7-day Soundbox split credit schedule">
      <header>
        <div class="title">
          <span class="pp-label">QR split simulation</span>
          <h2>7-Day Soundbox Split</h2>
        </div>
        @if (preApproval().autopay_mandate_registered) {
          <span class="badge autopay">&#128737;&#65039; Backup mandate simulation available</span>
        }
        <button class="close" (click)="closed.emit()" aria-label="Close split credit drawer">
          &times;
        </button>
      </header>

      <div class="days">
        @for (d of days(); track d) {
          <div
            class="day"
            [class.paid]="dayPaid(d)"
            [class.bank]="dayUsesBank(d)"
            [class.missed]="dayMissed(d)"
          >
            <span class="dnum">D{{ d }}</span>
            <span class="dbar">
              <i></i>
            </span>
            <span class="damt">{{ inr(dueAmount(d)) }}</span>
            <span class="rail">{{ railLabel(d) }}</span>
          </div>
        }
      </div>

      <div class="preview-controls">
        @if (isFixtureSample()) {
          <span>Fixture schedule only: no QR history is attached; future deductions are not simulated.</span>
        } @else {
          <button class="play" type="button" (click)="togglePlayback()" [disabled]="previewLoading() || !preview()?.days?.length || !day1Paid()">
            {{ playing() ? 'Pause simulation' : playbackComplete() ? 'Replay 7-day simulation' : 'Play repayment simulation' }}
          </button>
          @if (previewLoading()) {
            <span>Loading read-only QR balance preview…</span>
          } @else if (previewError()) {
            <span class="preview-error">{{ previewError() }} Day 1 remains recorded; later days are not simulated.</span>
          } @else {
            <span>Days 2–7 are a projection from recent QR history. Bank fallback is a what-if only; no payment is sent.</span>
          }
        }
      </div>

      <p class="progress-note">
        {{ statusNote() }}
      </p>

      <div class="stats">
        <div class="stat remaining">
          <span class="pp-label">{{ isFixtureSample() ? 'Fixture balance after Day 1' : playbackStarted() ? 'Projected loan balance' : 'Recorded balance after Day 1' }}</span>
          <strong>{{ inr(displayRemaining()) }}</strong>
        </div>
        <div class="stat">
          <span class="pp-label">Principal</span>
          <strong>{{ inr(schedule().principal) }}</strong>
        </div>
        <div class="stat">
          <span class="pp-label">Daily deduction</span>
          <strong>{{ inr(schedule().daily_deduction) }}</strong>
        </div>
        <div class="stat">
          <span class="pp-label">Max credit limit</span>
          <strong>{{ inr(preApproval().max_credit_limit) }}</strong>
        </div>
        <div class="stat">
          <span class="pp-label">Daily velocity cap</span>
          <strong>{{ inr(preApproval().daily_velocity_cap) }}</strong>
        </div>
      </div>

      <p class="fineprint">
        @if (isFixtureSample()) {
          The golden sample is a UI fixture only; no QR balance is read and no real deduction or bank debit is made.
        } @else {
          Day 1 is the recorded resolve state. Days 2–7 are a read-only projection. The bank amount is
          shown as an assumed UPI Autopay fallback for the demo only; no mandate or bank debit is issued.
        }
      </p>
    </section>
  `,
  styles: `
    .backdrop {
      position: fixed;
      inset: 0;
      background: rgba(4, 8, 18, 0.55);
      backdrop-filter: blur(2px);
      z-index: 50;
      animation: pp-fade 0.25s ease;
    }
    @keyframes pp-fade {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    .sheet {
      position: fixed;
      left: 50%;
      bottom: 0;
      transform: translateX(-50%);
      width: min(880px, 95vw);
      max-height: 88vh;
      overflow-y: auto;
      z-index: 51;
      padding: 22px 24px 26px;
      border-radius: 22px 22px 0 0;
      background: linear-gradient(180deg, #14203a, #0d1526);
      border: 1px solid var(--pp-line);
      border-bottom: none;
      box-shadow: 0 -18px 44px rgba(0, 0, 0, 0.5);
      animation: pp-slide-up 0.36s cubic-bezier(0.2, 0.9, 0.25, 1);
    }
    @keyframes pp-slide-up {
      from { transform: translate(-50%, 100%); }
      to { transform: translate(-50%, 0); }
    }

    header {
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
      margin-bottom: 20px;
    }
    .title h2 {
      margin: 2px 0 0;
      font-size: 22px;
    }
    .badge.autopay {
      margin-left: auto;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 12px;
      border-radius: 999px;
      font-size: 11.5px;
      font-weight: 800;
      color: var(--pp-green);
      background: var(--pp-green-bg);
      border: 1px solid rgba(47, 208, 122, 0.35);
    }
    .close {
      border: none;
      background: transparent;
      color: var(--pp-text-dim);
      font-size: 26px;
      line-height: 1;
      padding: 2px 8px;
      border-radius: 8px;
    }
    .close:hover {
      color: var(--pp-text);
      background: rgba(255, 255, 255, 0.08);
    }

    .days {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 10px;
    }
    .day {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 7px;
      padding: 12px 6px 10px;
      border-radius: 12px;
      border: 1px solid var(--pp-line);
      background: rgba(255, 255, 255, 0.02);
    }
    .dnum {
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.08em;
      color: var(--pp-text-dim);
    }
    .dbar {
      width: 100%;
      height: 8px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.06);
      overflow: hidden;
    }
    .dbar i {
      display: block;
      height: 100%;
      width: 0;
      border-radius: 6px;
      background: linear-gradient(90deg, var(--pp-green), #7ef0b0);
      transition: width 0.7s cubic-bezier(0.2, 0.9, 0.25, 1);
    }
    .day.paid .dbar i {
      width: 100%;
    }
    .day.paid {
      border-color: rgba(47, 208, 122, 0.5);
      background: var(--pp-green-bg);
    }
    .day.paid .dnum {
      color: var(--pp-green);
    }
    .day.bank {
      border-color: rgba(244, 183, 64, 0.72);
      background: rgba(244, 183, 64, 0.1);
    }
    .day.bank .dbar i {
      width: 100%;
      background: linear-gradient(90deg, #e6a52e, #ffd36b);
    }
    .day.missed {
      border-color: rgba(255, 98, 98, 0.7);
      background: rgba(255, 98, 98, 0.09);
    }
    .day.missed .dbar i {
      width: 100%;
      background: linear-gradient(90deg, #d94f5a, #ff8b8b);
    }
    .damt {
      font-size: 11px;
      color: var(--pp-text-dim);
    }
    .rail {
      min-height: 27px;
      font-size: 9px;
      line-height: 1.3;
      text-align: center;
      color: var(--pp-text-faint);
    }
    .day.bank .rail { color: #ffd36b; }
    .day.missed .rail { color: #ff9b9b; }

    .preview-controls {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 14px;
      font-size: 11px;
      line-height: 1.45;
      color: var(--pp-text-faint);
    }
    .play {
      flex: 0 0 auto;
      border: 1px solid rgba(47, 208, 122, 0.5);
      border-radius: 9px;
      padding: 9px 13px;
      background: var(--pp-green-bg);
      color: var(--pp-text);
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    .play:disabled { opacity: 0.5; cursor: not-allowed; }
    .preview-error { color: #ffadad; }

    .progress-note {
      margin: 14px 2px 18px;
      font-size: 13px;
      color: var(--pp-text);
      font-weight: 600;
    }

    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
    }
    .stat {
      border: 1px solid var(--pp-line);
      border-radius: 12px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 5px;
      background: rgba(255, 255, 255, 0.02);
    }
    .stat strong {
      font-size: 19px;
    }
    .stat.remaining strong {
      color: var(--pp-green);
      font-size: 24px;
    }

    .fineprint {
      margin: 18px 2px 0;
      font-size: 11.5px;
      line-height: 1.6;
      color: var(--pp-text-faint);
    }

    @media (max-width: 640px) {
      .days {
        grid-template-columns: repeat(4, 1fr);
      }
    }
  `,
})
export class SplitCreditComponent implements OnDestroy {
  readonly preApproval = input.required<SplitCreditPreApproval>();
  readonly schedule = input.required<LoanSchedule>();
  readonly invoiceId = input.required<string>();
  readonly closed = output<void>();

  readonly isFixtureSample = computed(() => this.invoiceId() === DEMO_FIXTURE_INVOICE_ID);

  private readonly api = inject(ApiService);
  protected readonly inr = formatINR;

  readonly day1Paid = signal(false);
  readonly displayRemaining = signal(0);
  readonly preview = signal<SweepPreviewResponse | null>(null);
  readonly previewLoading = signal(true);
  readonly previewError = signal('');
  readonly playbackDay = signal(1);
  readonly playbackStarted = signal(false);
  readonly playing = signal(false);

  readonly days = computed(() =>
    Array.from({ length: this.preApproval().tenure_days }, (_, i) => i + 1),
  );

  private animated = false;
  private timer: ReturnType<typeof setInterval> | null = null;
  private playbackTimer: ReturnType<typeof setInterval> | null = null;
  private destroyed = false;

  constructor() {
    effect(() => {
      const invoiceId = this.invoiceId();
      if (this.isFixtureSample()) {
        this.preview.set(null);
        this.previewError.set('');
        this.previewLoading.set(false);
        return;
      }
      void this.loadPreview(invoiceId);
    });
    effect(() => {
      const s = this.schedule();
      if (!s || this.animated) {
        return;
      }
      this.animated = true;
      this.displayRemaining.set(s.principal);
      if (!s.day_1_deducted) {
        return;
      }
      setTimeout(() => this.day1Paid.set(true), 450);
      const start = s.principal;
      const end = s.remaining_balance;
      if (start <= end) {
        this.displayRemaining.set(end);
        return;
      }
      const steps = 22;
      let i = 0;
      this.timer = setInterval(() => {
        i += 1;
        this.displayRemaining.set(Math.max(end, Math.round(start - ((start - end) * i) / steps)));
        if (i >= steps && this.timer) {
          clearInterval(this.timer);
          this.timer = null;
        }
      }, 40);
    });
  }

  async loadPreview(invoiceId: string): Promise<void> {
    if (invoiceId === DEMO_FIXTURE_INVOICE_ID) {
      this.preview.set(null);
      this.previewError.set('');
      this.previewLoading.set(false);
      return;
    }
    this.previewLoading.set(true);
    this.previewError.set('');
    try {
      const response = await this.api.getSweepPreview(invoiceId);
      if (!this.destroyed) this.preview.set(response);
    } catch {
      if (!this.destroyed) this.previewError.set('Could not load the repayment preview.');
    } finally {
      if (!this.destroyed) this.previewLoading.set(false);
    }
  }

  togglePlayback(): void {
    if (this.playing()) {
      this.stopPlayback();
      return;
    }
    const days = this.preview()?.days ?? [];
    if (!days.length) return;
    if (this.playbackDay() >= days[days.length - 1].day) {
      this.playbackDay.set(1);
      this.displayRemaining.set(this.schedule().remaining_balance);
    }
    this.playbackStarted.set(true);
    this.playing.set(true);
    this.playbackTimer = setInterval(() => this.advancePlayback(), 850);
  }

  dayPaid(day: number): boolean {
    if (day === 1) return this.schedule().day_1_deducted && this.day1Paid();
    if (this.isFixtureSample()) return false;
    const previewDay = this.previewFor(day);
    return day <= this.playbackDay() && !!previewDay && previewDay.missed === 0;
  }

  dayUsesBank(day: number): boolean {
    if (this.isFixtureSample()) return false;
    const previewDay = this.previewFor(day);
    return day <= this.playbackDay() && !!previewDay && previewDay.bank_mandate_deduction > 0;
  }

  dayMissed(day: number): boolean {
    if (this.isFixtureSample()) return false;
    const previewDay = this.previewFor(day);
    return day <= this.playbackDay() && !!previewDay && previewDay.missed > 0;
  }

  railLabel(day: number): string {
    if (day === 1) return this.day1Paid() ? 'Recorded QR debit' : 'Day 1';
    if (this.isFixtureSample()) return 'Fixture schedule only';
    const item = this.previewFor(day);
    if (!item) return 'Preview unavailable';
    if (day > this.playbackDay()) return `QR ${this.inr(item.qr_deduction)} · Bank ${this.inr(item.bank_mandate_deduction)}`;
    if (item.missed > 0) return `Unpaid ${this.inr(item.missed)}`;
    if (item.bank_mandate_deduction > 0) return `QR + Bank ${this.inr(item.bank_mandate_deduction)}`;
    return `QR ${this.inr(item.qr_deduction)}`;
  }

  dueAmount(day: number): number {
    return this.previewFor(day)?.due ?? this.schedule().daily_deduction;
  }

  statusNote(): string {
    if (this.isFixtureSample()) {
      return 'Golden fixture schedule; no QR transaction history is attached to this sample.';
    }
    if (this.previewLoading()) return 'Loading a read-only projection from recent QR activity…';
    if (this.previewError()) return `${this.previewError()} Later days remain a preview only.`;
    if (!this.playbackStarted()) {
      return 'Day 1 is recorded in the loan. Play to preview QR coverage and any simulated bank shortfall for Days 2–7.';
    }
    const current = this.previewFor(this.playbackDay());
    if (!current) return 'Day 1 recorded; no future installments remain in this schedule.';
    const bank = current.bank_mandate_deduction > 0
      ? ` Simulated bank fallback: ${this.inr(current.bank_mandate_deduction)}.`
      : '';
    const missed = current.missed > 0 ? ` Uncovered: ${this.inr(current.missed)}.` : '';
    return `Day ${current.day} projection: QR ${this.inr(current.qr_deduction)} of ${this.inr(current.due)}.${bank}${missed}`;
  }

  playbackComplete(): boolean {
    const days = this.preview()?.days ?? [];
    return !!days.length && !this.playing() && this.playbackDay() >= days[days.length - 1].day;
  }

  private previewFor(day: number): SweepDayPreview | undefined {
    return this.preview()?.days.find((item) => item.day === day);
  }

  private advancePlayback(): void {
    const next = (this.preview()?.days ?? []).find((item) => item.day > this.playbackDay());
    if (!next) {
      this.stopPlayback();
      return;
    }
    this.playbackDay.set(next.day);
    this.displayRemaining.set(next.projected_loan_balance);
    const days = this.preview()?.days ?? [];
    if (next.day >= (days.length ? days[days.length - 1].day : 1)) this.stopPlayback();
  }

  private stopPlayback(): void {
    if (this.playbackTimer) clearInterval(this.playbackTimer);
    this.playbackTimer = null;
    this.playing.set(false);
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    if (this.timer) {
      clearInterval(this.timer);
    }
    this.stopPlayback();
  }
}
