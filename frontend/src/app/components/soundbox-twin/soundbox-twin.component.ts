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
    <div class="pos-device-shell">
      <!-- Top White Thermal Paper Roll Bay -->
      <div class="printer-bay">
        <div class="printer-branding">
          <img
            src="/assets/pictures/Paytm_logo.png"
            alt="Paytm"
            class="printer-paytm-logo"
          />
          <div class="nfc-symbol" title="Contactless NFC Payments">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
              <path d="M6 7a8.5 8.5 0 0 1 0 10" />
              <path d="M9.5 9a4.8 4.8 0 0 1 0 6" />
              <path d="M13 11a1.8 1.8 0 0 1 0 2" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Main Vibrant Paytm Blue POS Chassis -->
      <div class="pos-chassis" [class.speaking]="speaking()">
        <!-- Right-Side Magnetic Card Swipe Reader -->
        <div class="side-card-reader" aria-hidden="true">
          <div class="swipe-groove"></div>
        </div>

        <!-- White Front Faceplate -->
        <div class="pos-faceplate">
          <!-- Top Brand Header: paytm ♥ UPI -->
          <div class="faceplate-header">
            <div class="paytm-upi-brand">
              <span class="paytm-word">paytm</span>
              <span class="heart-mark">&#9829;</span>
              <span class="upi-word">UPI<span class="upi-arrow">&#9654;</span></span>
            </div>
          </div>

          <!-- Android Touchscreen Display -->
          <div class="pos-screen">
            <!-- Android Status Bar -->
            <div class="android-status-bar">
              <span class="carrier-tag">Jio 4G</span>
              <div class="status-icons">
                <span class="bar-icon">&#9646;&#9646;&#9646;&#9646;</span>
                <span class="wifi-icon">&#128246;</span>
                <span class="clock-tag">12:30</span>
                <span class="batt-tag">&#128267; 100%</span>
              </div>
            </div>

            <!-- Subtle Glass Reflection Overlay -->
            <div class="screen-glare" aria-hidden="true"></div>

            <!-- Screen View Content -->
            <div class="screen-body">
              @switch (view()) {
                @case ('IDLE') {
                  <div class="screen-idle">
                    <div class="pos-hero-badge">
                      <span class="paytm-pill">paytm</span>
                      <span class="aio-pill">All-in-One</span>
                    </div>
                    <h2 class="card-machine-title">Card Machine</h2>
                    <p class="twin-subhead">AI Wholesale POS Terminal</p>

                    <!-- Payment Support Cards (matches physical device screen) -->
                    <div class="methods-grid">
                      <div class="method-box">
                        <div class="method-ico">&#128179;</div>
                        <span class="method-lbl">All Debit &amp;<br />Credit Cards</span>
                      </div>
                      <div class="method-box">
                        <div class="method-ico paytm-ico">paytm</div>
                        <span class="method-lbl">Paytm Wallet<br />&amp; UPI</span>
                      </div>
                      <div class="method-box">
                        <div class="method-ico upi-ico">UPI&#9654;</div>
                        <span class="method-lbl">All UPI<br />Apps</span>
                      </div>
                    </div>

                    <div class="idle-footer-cue">
                      <span class="cue-dot"></span>
                      <span>Ready for wholesale parcha</span>
                    </div>
                  </div>
                }
                @case ('PROCESSING') {
                  <div class="screen-processing">
                    <div class="laser-scanner" aria-hidden="true"></div>
                    <div class="audit-spinner"></div>
                    <h3 class="processing-head">Auditing Parcha&hellip;</h3>
                    <p class="processing-sub">Gemini 2.5 Flash &middot; Decimal Engine &middot; Mandi-Pulse</p>
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
                        <div class="status-pill alert-pill">
                          <span class="tag-ico">&#9888;</span>
                          <span>OVERCHARGE {{ inr(a.overcharge_amount) }}</span>
                        </div>
                      } @else {
                        <div class="status-pill verified-pill">
                          <span class="tag-ico">&#10003;</span>
                          <span>BILL VERIFIED &middot; 0 OVERCHARGE</span>
                        </div>
                      }

                      <div class="hero-pay-box">
                        <span class="pay-sub">Approved Payout</span>
                        <div class="pay-amount">Pay {{ inr(a.approved_total) }}</div>
                        <div class="pay-meta">
                          Billed {{ inr(a.billed_total) }} &middot; {{ a.items.length }} items
                        </div>
                      </div>

                      @if (flagged(a) > 0) {
                        <div class="flagged-pill">
                          &#9888; {{ flagged(a) }} item{{ flagged(a) === 1 ? '' : 's' }} flagged for review
                        </div>
                      }

                      @if (needsTapToPlay()) {
                        <button class="voice-tap-pill" (click)="retryAudio()">
                          <span>&#128266;</span>
                          <span>Tap to hear voice audit</span>
                        </button>
                      }

                      <!-- Primary Interactive 1-Tap Split Button -->
                      <button
                        class="pos-pay-button"
                        (click)="approve.emit()"
                        [disabled]="busy()"
                        aria-label="Paytm Button: approve the audited payout"
                      >
                        <div class="btn-text">
                        <div class="btn-top">Paytm 1-Tap Split</div>
                        <div class="btn-action">APPROVE PAYOUT</div>
                        </div>
                      </button>
                    </div>
                  }
                }
                @case ('APPROVED') {
                  @if (payout(); as p) {
                    <div class="screen-approved">
                      <div class="status-pill verified-pill">
                        <span class="tag-ico">&#10003;</span>
                        <span>PAYOUT APPROVED</span>
                      </div>
                      <div class="hero-pay-box">
                        <span class="pay-sub">Loan Principal</span>
                        <div class="pay-amount">{{ inr(p.loan_schedule.principal) }}</div>
                        <div class="pay-meta">
                          {{
                            p.settlement_method === 'SOUNDBOX_7_DAY_SPLIT'
                              ? '7-Day Soundbox Split Active'
                              : p.settlement_method
                          }}
                        </div>
                      </div>
                      <div class="approved-chips-row">
                        <span class="chip-item">WhatsApp Sent</span>
                        <span class="chip-item">IMS Shield Active</span>
                      </div>
                      <button class="pos-split-button" (click)="openSplit.emit()">
                        <span>&#128179; View 7-Day Split Schedule</span>
                      </button>
                    </div>
                  }
                }
              }
            </div>
          </div>

          <!-- Android Bottom Navigation Bar (Capacitive Touch Keys) -->
          <div class="android-nav-bar" aria-hidden="true">
            <span class="nav-key square">&#9634;</span>
            <span class="nav-key home">&#8962;</span>
            <span class="nav-key back">&#8617;</span>
          </div>
        </div>

        <!-- Bottom Chin EMV Chip Card Insertion Slot -->
        <div class="bottom-card-slot" aria-hidden="true">
          <span class="card-slot-lip"></span>
        </div>
      </div>
    </div>
  `,
  styles: `
    :host {
      display: block;
      width: 100%;
    }

    /* Outer Container */
    .pos-device-shell {
      position: relative;
      width: 100%;
      max-width: 385px;
      margin: 0 auto;
      filter: drop-shadow(0 24px 48px rgba(0, 0, 0, 0.7));
    }

    /* Top White Thermal Paper Roll Bay */
    .printer-bay {
      width: 92%;
      margin: 0 auto -8px;
      height: 56px;
      background: #ffffff;
      border-radius: 28px 28px 0 0;
      border: 1.5px solid #d8dde8;
      border-bottom: none;
      box-shadow:
        inset 0 2px 4px rgba(255, 255, 255, 0.95),
        0 4px 10px rgba(0, 0, 0, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      z-index: 1;
    }

    .printer-branding {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      padding: 0 24px;
    }

    .printer-paytm-logo {
      height: 24px;
      width: auto;
      object-fit: contain;
    }

    .nfc-symbol {
      color: #002e6e;
      display: flex;
      align-items: center;
    }

    /* Main Vibrant Paytm Cyan/Blue Chassis */
    .pos-chassis {
      position: relative;
      background: linear-gradient(180deg, #00baf2 0%, #009ce0 40%, #0076bf 100%);
      border-radius: 38px 38px 44px 44px;
      padding: 16px 14px 18px;
      box-shadow:
        0 20px 48px rgba(0, 75, 145, 0.55),
        inset 0 2px 4px rgba(255, 255, 255, 0.6),
        inset 0 -4px 10px rgba(0, 35, 80, 0.55);
      border: 1.5px solid rgba(255, 255, 255, 0.3);
    }

    /* Right-Side Magnetic Stripe Card Swipe Bumper */
    .side-card-reader {
      position: absolute;
      right: -8px;
      top: 195px;
      width: 16px;
      height: 310px;
      background: linear-gradient(90deg, #003e8a, #002b66);
      border-radius: 0 10px 10px 0;
      box-shadow: 2px 4px 12px rgba(0, 0, 0, 0.45);
      z-index: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .swipe-groove {
      width: 3px;
      height: 260px;
      background: #001940;
      border-radius: 2px;
    }

    /* White Front Faceplate */
    .pos-faceplate {
      position: relative;
      z-index: 1;
      background: #ffffff;
      border-radius: 28px 28px 32px 32px;
      padding: 10px 12px 10px;
      box-shadow:
        0 4px 16px rgba(0, 0, 0, 0.22),
        inset 0 1px 3px rgba(255, 255, 255, 0.95);
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    /* Faceplate Brand: paytm ♥ UPI */
    .faceplate-header {
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 2px 0 4px;
    }

    .paytm-upi-brand {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      user-select: none;
    }

    .paytm-word {
      font-size: 20px;
      font-weight: 900;
      color: #002e6e;
      letter-spacing: -0.02em;
    }

    .heart-mark {
      font-size: 16px;
      color: #ef4444;
      animation: pp-heartbeat 1.6s ease-in-out infinite;
    }
    @keyframes pp-heartbeat {
      0%, 100% { transform: scale(1); }
      15% { transform: scale(1.22); }
      30% { transform: scale(1); }
      45% { transform: scale(1.15); }
    }

    .upi-word {
      font-size: 18px;
      font-weight: 900;
      color: #0f172a;
      letter-spacing: -0.01em;
      display: flex;
      align-items: center;
    }
    .upi-arrow {
      color: #ea580c;
      font-size: 12px;
      margin-left: 2px;
    }

    /* Android Touchscreen Display - ELONGATED (TALLER) */
    .pos-screen {
      position: relative;
      border-radius: 16px;
      background: radial-gradient(140% 120% at 50% 0%, #17243e 0%, #0a1120 100%);
      border: 1.5px solid #283a5e;
      box-shadow:
        inset 0 0 24px rgba(0, 0, 0, 0.75),
        0 2px 8px rgba(0, 0, 0, 0.3);
      color: #ffffff;
      min-height: 570px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .screen-glare {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 35%;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.07) 0%, rgba(255, 255, 255, 0) 100%);
      pointer-events: none;
    }

    /* Android Status Bar */
    .android-status-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #000000;
      color: rgba(255, 255, 255, 0.9);
      padding: 4px 12px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.02em;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      z-index: 1;
    }
    .carrier-tag {
      color: #38bdf8;
      font-weight: 800;
    }
    .status-icons {
      display: flex;
      align-items: center;
      gap: 7px;
    }
    .bar-icon {
      font-size: 8px;
      color: #38bdf8;
    }
    .clock-tag {
      font-weight: 800;
    }

    /* Screen Content Body */
    .screen-body {
      flex: 1;
      padding: 18px 14px 16px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      position: relative;
      z-index: 1;
    }

    /* IDLE VIEW */
    .screen-idle {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: 12px;
      padding: 10px 0;
    }

    .pos-hero-badge {
      display: inline-flex;
      border-radius: 6px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.15);
      margin-bottom: 2px;
    }
    .paytm-pill {
      background: #002e6e;
      color: #00baf2;
      font-size: 14px;
      font-weight: 900;
      padding: 4px 10px;
    }
    .aio-pill {
      background: #e11d48;
      color: #ffffff;
      font-size: 12px;
      font-weight: 800;
      padding: 4px 10px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .card-machine-title {
      font-size: 26px;
      font-weight: 900;
      margin: 0;
      letter-spacing: -0.02em;
      color: #ffffff;
      text-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
    }
    .twin-subhead {
      margin: 0 0 12px;
      font-size: 12px;
      font-weight: 700;
      color: #94a3b8;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    /* 3 Payment Method Cards */
    .methods-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      width: 100%;
      margin: 8px 0 16px;
    }
    .method-box {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 10px;
      padding: 10px 4px 8px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 5px;
    }
    .method-ico {
      font-size: 18px;
      height: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .method-ico.paytm-ico {
      font-size: 11px;
      font-weight: 900;
      color: #00baf2;
      background: #002e6e;
      padding: 2px 5px;
      border-radius: 4px;
    }
    .method-ico.upi-ico {
      font-size: 11px;
      font-weight: 900;
      color: #ea580c;
    }
    .method-lbl {
      font-size: 9.5px;
      font-weight: 700;
      color: #cbd5e1;
      line-height: 1.2;
    }

    .idle-footer-cue {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      color: #38bdf8;
      background: rgba(0, 186, 242, 0.12);
      border: 1px solid rgba(0, 186, 242, 0.35);
      padding: 6px 16px;
      border-radius: 999px;
    }
    .cue-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #38bdf8;
      box-shadow: 0 0 10px #38bdf8;
      animation: pp-pulse-dot 1.4s ease-in-out infinite;
    }
    @keyframes pp-pulse-dot {
      0%, 100% { opacity: 0.4; }
      50% { opacity: 1; }
    }

    /* PROCESSING VIEW */
    .screen-processing {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 14px;
      text-align: center;
      position: relative;
    }
    .laser-scanner {
      position: absolute;
      inset: -18px -14px;
      background: linear-gradient(180deg, transparent 20%, rgba(0, 186, 242, 0.22) 50%, transparent 80%);
      animation: pp-laser-sweep 1.4s ease-in-out infinite;
      pointer-events: none;
    }
    @keyframes pp-laser-sweep {
      0%, 100% { transform: translateY(-60%); }
      50% { transform: translateY(60%); }
    }
    .audit-spinner {
      width: 44px;
      height: 44px;
      border: 4px solid rgba(0, 186, 242, 0.2);
      border-top-color: #00baf2;
      border-radius: 50%;
      animation: pp-spin 0.75s linear infinite;
    }
    @keyframes pp-spin { to { transform: rotate(360deg); } }
    .processing-head {
      margin: 0;
      font-size: 22px;
      font-weight: 800;
      color: #ffffff;
    }
    .processing-sub {
      margin: 0;
      font-size: 12px;
      color: #94a3b8;
    }

    /* ALERT VIEW */
    .screen-alert {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      text-align: center;
      padding: 6px 0;
      height: 100%;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 16px;
      border-radius: 999px;
      font-size: 11.5px;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .status-pill.alert-pill {
      background: rgba(239, 68, 68, 0.22);
      border: 1px solid rgba(239, 68, 68, 0.65);
      color: #fca5a5;
    }
    .status-pill.verified-pill {
      background: rgba(34, 197, 94, 0.22);
      border: 1px solid rgba(34, 197, 94, 0.65);
      color: #86efac;
    }

    .hero-pay-box {
      margin: 6px 0 2px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 3px;
    }
    .pay-sub {
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #94a3b8;
    }
    .pay-amount {
      font-size: 40px;
      font-weight: 900;
      color: #ffffff;
      line-height: 1.08;
      letter-spacing: -0.02em;
      text-shadow: 0 3px 12px rgba(0, 0, 0, 0.55);
    }
    .pay-meta {
      font-size: 12.5px;
      font-weight: 600;
      color: #cbd5e1;
      margin-top: 2px;
    }

    .flagged-pill {
      font-size: 11.5px;
      font-weight: 700;
      color: #facc15;
      background: rgba(250, 204, 21, 0.14);
      border: 1px solid rgba(250, 204, 21, 0.4);
      padding: 4px 12px;
      border-radius: 6px;
    }

    .voice-tap-pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 8px 18px;
      border-radius: 999px;
      background: rgba(0, 186, 242, 0.16);
      border: 1px solid rgba(0, 186, 242, 0.5);
      color: #7dd3fc;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      animation: pp-pulse 1.6s ease-in-out infinite;
      transition: all 0.2s ease;
    }
    .voice-tap-pill:hover {
      background: rgba(0, 186, 242, 0.28);
    }
    @keyframes pp-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(0, 186, 242, 0.35); }
      50% { box-shadow: 0 0 0 8px rgba(0, 186, 242, 0); }
    }

    /* POS Screen 1-Tap Action Button - NO TEXT MERGING */
    .pos-pay-button {
      width: 100%;
      margin-top: 8px;
      padding: 13px 16px;
      border-radius: 14px;
      border: none;
      cursor: pointer;
      background: linear-gradient(135deg, #00baf2 0%, #0066cc 100%);
      color: #ffffff;
      box-shadow:
        0 8px 22px rgba(0, 102, 204, 0.5),
        inset 0 1px 2px rgba(255, 255, 255, 0.4);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      transition: all 0.15s ease;
    }
    .pos-pay-button:hover:not(:disabled) {
      transform: translateY(-2px);
      box-shadow: 0 12px 26px rgba(0, 186, 242, 0.6);
    }
    .pos-pay-button:active:not(:disabled) {
      transform: translateY(1px);
      box-shadow: 0 4px 12px rgba(0, 102, 204, 0.4);
    }
    .pos-pay-button:disabled {
      opacity: 0.65;
      cursor: not-allowed;
    }

    .btn-text {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 5px;
      width: 100%;
    }
    .btn-top {
      font-size: 16px;
      font-weight: 900;
      letter-spacing: -0.01em;
      display: block;
      line-height: 1.2;
      color: #ffffff;
      text-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
    }
    .btn-action {
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.1em;
      color: #e0f2fe;
      background: rgba(0, 30, 75, 0.55);
      border: 1px solid rgba(255, 255, 255, 0.25);
      padding: 3px 14px;
      border-radius: 999px;
      display: inline-block;
      text-transform: uppercase;
      box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.3);
    }

    /* APPROVED VIEW */
    .screen-approved {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 14px;
      text-align: center;
      padding: 6px 0;
    }
    .approved-chips-row {
      display: flex;
      gap: 8px;
      margin-top: 2px;
    }
    .chip-item {
      font-size: 11px;
      font-weight: 700;
      color: #86efac;
      background: rgba(34, 197, 94, 0.15);
      border: 1px solid rgba(34, 197, 94, 0.4);
      padding: 3px 10px;
      border-radius: 999px;
    }
    .pos-split-button {
      width: 100%;
      margin-top: 10px;
      padding: 13px 16px;
      border-radius: 14px;
      border: 1px solid rgba(74, 222, 128, 0.55);
      background: linear-gradient(135deg, rgba(34, 197, 94, 0.25) 0%, rgba(13, 84, 52, 0.45) 100%);
      color: #86efac;
      font-size: 13.5px;
      font-weight: 800;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .pos-split-button:hover {
      filter: brightness(1.15);
      transform: translateY(-1px);
    }

    /* Android Bottom Navigation Bar (Capacitive Touch Keys) */
    .android-nav-bar {
      display: flex;
      justify-content: space-around;
      align-items: center;
      padding: 6px 18px 2px;
      color: #94a3b8;
      font-size: 17px;
      user-select: none;
    }
    .nav-key {
      cursor: default;
      transition: color 0.15s ease;
    }
    .nav-key.square { font-size: 15px; }
    .nav-key.home { font-size: 19px; }
    .nav-key.back { font-size: 18px; }

    /* Bottom Chin EMV Chip Card Insertion Slot */
    .bottom-card-slot {
      display: flex;
      justify-content: center;
      padding-top: 10px;
    }
    .card-slot-lip {
      width: 140px;
      height: 5px;
      background: #004f85;
      border-radius: 4px;
      box-shadow: inset 0 2px 3px rgba(0, 0, 0, 0.6), 0 1px 1px rgba(255, 255, 255, 0.3);
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
