import { Component, OnDestroy, computed, effect, input, output, signal } from '@angular/core';

import { LoanSchedule, SplitCreditPreApproval } from '@contracts/contracts';

import { formatINR } from '../../shared/format';

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
          <span class="pp-label">Settlement-backed credit</span>
          <h2>7-Day Soundbox Split</h2>
        </div>
        @if (preApproval().autopay_mandate_registered) {
          <span class="badge autopay">&#128737;&#65039; UPI Autopay backup mandate active</span>
        }
        <button class="close" (click)="closed.emit()" aria-label="Close split credit drawer">
          &times;
        </button>
      </header>

      <div class="days">
        @for (d of days(); track d) {
          <div class="day" [class.paid]="d === 1 && schedule().day_1_deducted && day1Paid()">
            <span class="dnum">D{{ d }}</span>
            <span class="dbar">
              <i></i>
            </span>
            <span class="damt">{{ inr(schedule().daily_deduction) }}</span>
          </div>
        }
      </div>

      <p class="progress-note">
        @if (schedule().day_1_deducted && day1Paid()) {
          Day 1 of {{ days().length }} &middot; {{ inr(schedule().daily_deduction) }} reserved from
          today&rsquo;s customer QR sweep
        } @else {
          Waiting for today&rsquo;s QR sweep&hellip;
        }
      </p>

      <div class="stats">
        <div class="stat remaining">
          <span class="pp-label">Remaining balance</span>
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
        Daily deductions are reserved from incoming customer QR settlements before the remaining
        balance is paid out. If QR collections stall, the UPI Autopay mandate sweeps the installment
        from the registered bank account.
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
    .damt {
      font-size: 11px;
      color: var(--pp-text-dim);
    }

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
  readonly closed = output<void>();

  protected readonly inr = formatINR;

  readonly day1Paid = signal(false);
  readonly displayRemaining = signal(0);

  readonly days = computed(() =>
    Array.from({ length: this.preApproval().tenure_days }, (_, i) => i + 1),
  );

  private animated = false;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor() {
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

  ngOnDestroy(): void {
    if (this.timer) {
      clearInterval(this.timer);
    }
  }
}
