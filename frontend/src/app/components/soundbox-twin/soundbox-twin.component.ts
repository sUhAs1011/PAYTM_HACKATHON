import { Component, OnDestroy, computed, effect, inject, input, output, signal } from '@angular/core';

import { AuditCompleteData, PayoutApprovedData } from '@contracts/contracts';

import { ApiService } from '../../services/api.service';
import { formatINR } from '../../shared/format';

type TwinView = 'IDLE' | 'PROCESSING' | 'ALERT' | 'APPROVED';

/**
 * Paytm AI Soundbox Digital Twin (PRD F4) — the right panel of `/counter`.
 *
 * Renders the device chassis: speaker grille (animated while speaking), the
 * front touchscreen Red/Green audit card, and the clickable physical Paytm
 * Button. Voice alert playback follows the contract `audio_alert_url`; when
 * autoplay is blocked or the audio asset is unavailable (demo mode), the twin
 * falls back to `speechSynthesis` speaking the contract `voice_transcript`.
 */
@Component({
  selector: 'app-soundbox-twin',
  standalone: true,
  template: `
    <div class="twin-shell" [class.speaking]="speaking()">
      <div class="grille" aria-hidden="true">
        <span></span><span></span><span></span><span></span><span></span>
      </div>

      <div class="screen">
        @switch (view()) {
          @case ('IDLE') {
            <div class="screen-idle">
              <p class="brand">Paytm AI Soundbox</p>
              <p class="sub">Ready for the next parcha</p>
            </div>
          }
          @case ('PROCESSING') {
            <div class="screen-processing">
              <div class="sweep" aria-hidden="true"></div>
              <p class="brand">Auditing Parcha&hellip;</p>
              <p class="sub">Gemini 2.5 Flash &middot; Decimal audit &middot; Mandi-Pulse</p>
            </div>
          }
          @case ('ALERT') {
            @if (audit(); as a) {
              <div
                class="screen-alert"
                [class.over]="a.overcharge_amount > 0"
                [class.clean]="a.overcharge_amount === 0"
              >
                @if (a.overcharge_amount > 0) {
                  <p class="alert-title">&#9888; Overcharge {{ inr(a.overcharge_amount) }}</p>
                } @else {
                  <p class="alert-title ok">&#10003; Bill verified</p>
                }
                <p class="pay">Pay {{ inr(a.approved_total) }}</p>
                <p class="billed">Billed {{ inr(a.billed_total) }} &middot; {{ a.items.length }} items</p>
                @if (flagged(a) > 0) {
                  <p class="flag">{{ flagged(a) }} item{{ flagged(a) === 1 ? '' : 's' }} flagged</p>
                }
              </div>
            }
          }
          @case ('APPROVED') {
            @if (payout(); as p) {
              <div class="screen-approved">
                <p class="alert-title ok">&#10003; Payout approved</p>
                <p class="pay">{{ inr(p.loan_schedule.principal) }}</p>
                <p class="billed">
                  {{
                    p.settlement_method === 'SOUNDBOX_7_DAY_SPLIT'
                      ? '7-Day Soundbox Split active'
                      : p.settlement_method
                  }}
                </p>
                <p class="flag">WhatsApp reconciliation sent &middot; GST IMS shield active</p>
              </div>
            }
          }
        }
      </div>

      @if (needsTapToPlay()) {
        <button class="tap-to-hear" (click)="retryAudio()">
          &#128266; Tap to hear the audit
        </button>
      }

      <div class="button-deck">
        @switch (view()) {
          @case ('ALERT') {
            <button
              class="paytm-button"
              (click)="approve.emit()"
              [disabled]="busy()"
              aria-label="Paytm Button: approve the audited payout"
            >
              <span class="ring"></span>
              <span class="label">Paytm<br />Button</span>
            </button>
          }
          @case ('APPROVED') {
            <button class="split-btn" (click)="openSplit.emit()">
              Pay via 7-Day Soundbox Split
            </button>
          }
          @default {
            <div class="paytm-button idle" aria-hidden="true">
              <span class="ring"></span>
              <span class="label">Paytm<br />Button</span>
            </div>
          }
        }
      </div>
    </div>
  `,
  styles: `
    .twin-shell {
      display: flex;
      flex-direction: column;
      gap: 14px;
      padding: 22px 20px 26px;
      border-radius: 26px;
      background: linear-gradient(180deg, #16223c, #0d1526);
      border: 1px solid var(--pp-line);
      box-shadow: var(--pp-shadow), inset 0 1px 0 rgba(255, 255, 255, 0.05);
    }

    .grille {
      display: flex;
      justify-content: center;
      gap: 7px;
      padding: 10px 0 4px;
    }
    .grille span {
      width: 6px;
      height: 14px;
      border-radius: 4px;
      background: #22304e;
      transition: background 0.25s ease, height 0.25s ease;
    }
    .twin-shell.speaking .grille span {
      background: var(--pp-blue);
      animation: pp-eq 0.7s ease-in-out infinite;
    }
    .twin-shell.speaking .grille span:nth-child(2) { animation-delay: 0.1s; }
    .twin-shell.speaking .grille span:nth-child(3) { animation-delay: 0.2s; }
    .twin-shell.speaking .grille span:nth-child(4) { animation-delay: 0.3s; }
    .twin-shell.speaking .grille span:nth-child(5) { animation-delay: 0.4s; }
    @keyframes pp-eq {
      0%, 100% { height: 14px; }
      50% { height: 26px; }
    }

    .screen {
      position: relative;
      min-height: 190px;
      border-radius: 18px;
      padding: 20px 18px;
      background: radial-gradient(140% 120% at 50% 0%, #1d2c4e, #101a30);
      border: 1px solid #2c3d63;
      box-shadow: inset 0 0 24px rgba(0, 0, 0, 0.45);
      text-align: center;
      display: grid;
      place-items: center;
      overflow: hidden;
    }

    .screen .brand {
      margin: 0;
      font-size: 20px;
      font-weight: 800;
      letter-spacing: 0.02em;
    }
    .screen .sub {
      margin: 6px 0 0;
      font-size: 12px;
      color: var(--pp-text-dim);
    }

    .sweep {
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, transparent 30%, rgba(0, 186, 242, 0.28) 50%, transparent 70%);
      animation: pp-sweep-y 1.4s ease-in-out infinite;
    }
    @keyframes pp-sweep-y {
      0%, 100% { transform: translateY(-70%); }
      50% { transform: translateY(70%); }
    }

    .alert-title {
      margin: 0;
      font-size: 15px;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--pp-red);
    }
    .alert-title.ok {
      color: var(--pp-green);
    }
    .screen-alert.over {
      background: radial-gradient(140% 120% at 50% 0%, #3a1526, #170b18);
      border-color: #6b2438;
    }
    .screen-alert.clean,
    .screen-approved {
      background: radial-gradient(140% 120% at 50% 0%, #0f2f24, #0b1a18);
      border-color: #1d5c44;
    }
    .pay {
      margin: 10px 0 2px;
      font-size: 40px;
      font-weight: 800;
      color: var(--pp-text);
      line-height: 1.05;
    }
    .billed {
      margin: 2px 0 0;
      font-size: 13px;
      color: var(--pp-text-dim);
    }
    .flag {
      margin: 10px 0 0;
      font-size: 11px;
      color: var(--pp-yellow);
      font-weight: 700;
    }

    .tap-to-hear {
      align-self: center;
      padding: 10px 18px;
      border-radius: 999px;
      border: 1px solid rgba(0, 186, 242, 0.5);
      background: rgba(0, 186, 242, 0.12);
      color: var(--pp-blue-soft);
      font-size: 13px;
      font-weight: 700;
      animation: pp-pulse 1.6s ease-in-out infinite;
    }
    @keyframes pp-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(0, 186, 242, 0.35); }
      50% { box-shadow: 0 0 0 10px rgba(0, 186, 242, 0); }
    }

    .button-deck {
      display: grid;
      place-items: center;
      min-height: 116px;
    }

    .paytm-button {
      position: relative;
      width: 96px;
      height: 96px;
      border-radius: 50%;
      border: none;
      background: radial-gradient(circle at 35% 30%, #2ea8ff, #0068c8 70%);
      box-shadow:
        0 10px 24px rgba(0, 116, 200, 0.45),
        inset 0 -6px 12px rgba(0, 0, 0, 0.35),
        inset 0 4px 8px rgba(255, 255, 255, 0.35);
      color: #fff;
      transition: transform 0.1s ease, box-shadow 0.2s ease;
      animation: pp-pulse 2.2s ease-in-out infinite;
    }
    .paytm-button:active {
      transform: scale(0.94);
      box-shadow: 0 4px 10px rgba(0, 116, 200, 0.4);
    }
    .paytm-button.idle {
      animation: none;
      filter: grayscale(0.7) brightness(0.7);
      box-shadow: inset 0 -6px 12px rgba(0, 0, 0, 0.35);
    }
    .paytm-button .ring {
      position: absolute;
      inset: -9px;
      border-radius: 50%;
      border: 2px solid rgba(0, 186, 242, 0.4);
    }
    .paytm-button .label {
      font-size: 13px;
      font-weight: 800;
      line-height: 1.15;
      letter-spacing: 0.02em;
      text-align: center;
    }

    .split-btn {
      padding: 16px 22px;
      border-radius: 14px;
      border: 1px solid rgba(47, 208, 122, 0.55);
      background: linear-gradient(135deg, rgba(47, 208, 122, 0.22), rgba(13, 84, 52, 0.35));
      color: var(--pp-green);
      font-size: 15px;
      font-weight: 800;
    }
    .split-btn:hover {
      filter: brightness(1.12);
    }
  `,
})
export class SoundboxTwinComponent implements OnDestroy {
  private readonly api = inject(ApiService);

  /** True while the counter dashboard is in its PROCESSING stage. */
  readonly processing = input(false);
  readonly audit = input<AuditCompleteData | null>(null);
  readonly payout = input<PayoutApprovedData | null>(null);
  readonly busy = input(false);

  readonly approve = output<void>();
  readonly openSplit = output<void>();

  protected readonly inr = formatINR;

  readonly speaking = signal(false);
  readonly needsTapToPlay = signal(false);

  private audioEl: HTMLAudioElement | null = null;
  private spokenForInvoice = '';

  readonly view = computed<TwinView>(() => {
    if (this.payout()) {
      return 'APPROVED';
    }
    if (this.audit()) {
      return 'ALERT';
    }
    if (this.processing()) {
      return 'PROCESSING';
    }
    return 'IDLE';
  });

  constructor() {
    effect(() => {
      const audit = this.audit();
      const payout = this.payout();
      if (payout) {
        this.stopAudio();
        return;
      }
      if (audit) {
        this.speakAudit(audit);
      }
    });
  }

  flagged(a: AuditCompleteData): number {
    return a.items.filter(
      (i) => i.rate_status !== 'OK' || i.ocr_confidence < 0.8 || i.has_pen_markup,
    ).length;
  }

  retryAudio(): void {
    const audit = this.audit();
    if (!audit) {
      return;
    }
    if (this.audioEl) {
      this.audioEl
        .play()
        .then(() => {
          this.speaking.set(true);
          this.needsTapToPlay.set(false);
        })
        .catch(() => this.fallbackTts(audit));
    } else {
      this.fallbackTts(audit);
    }
  }

  ngOnDestroy(): void {
    this.stopAudio();
  }

  private speakAudit(audit: AuditCompleteData): void {
    if (this.spokenForInvoice === audit.invoice_id) {
      return;
    }
    this.spokenForInvoice = audit.invoice_id;
    this.stopAudio();
    const audio = new Audio(this.api.assetUrl(audit.audio_alert_url));
    this.audioEl = audio;
    audio.onended = () => this.speaking.set(false);
    this.speaking.set(true);
    audio
      .play()
      .then(() => this.needsTapToPlay.set(false))
      .catch(() => {
        // Autoplay blocked, or the alert file is absent (demo mode) — offer
        // tap-to-play; the tap retries the file, then TTS as final fallback.
        this.speaking.set(false);
        this.needsTapToPlay.set(true);
      });
  }

  private fallbackTts(audit: AuditCompleteData): void {
    this.needsTapToPlay.set(false);
    if (!('speechSynthesis' in window)) {
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(audit.voice_transcript);
    const voices = window.speechSynthesis.getVoices();
    const voice =
      voices.find((v) => v.lang === 'en-IN') ??
      voices.find((v) => v.lang === 'hi-IN') ??
      voices.find((v) => v.lang?.startsWith('en'));
    if (voice) {
      utterance.voice = voice;
    }
    utterance.rate = 1.02;
    utterance.onend = () => this.speaking.set(false);
    this.speaking.set(true);
    window.speechSynthesis.speak(utterance);
  }

  private stopAudio(): void {
    this.speaking.set(false);
    this.needsTapToPlay.set(false);
    if (this.audioEl) {
      this.audioEl.onended = null;
      this.audioEl.pause();
      this.audioEl = null;
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }
}
