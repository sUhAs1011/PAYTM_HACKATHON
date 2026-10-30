import { Component, input, output } from '@angular/core';

import { WhatsappClaim } from '@contracts/contracts';

import { formatINR } from '../../shared/format';

/**
 * Supplier WhatsApp Simulator Drawer (PRD F5) — slides out after the Paytm
 * Button resolves APPROVE_SPLIT. Renders the polite B2B reconciliation slip
 * from the CIS `PAYOUT_APPROVED.whatsapp_claim` payload: the message preview,
 * the cropped pen-edit proof, and the Paytm Payment Link for the corrected
 * amount. P0 is an in-app preview; live dispatch is a backend concern.
 */
@Component({
  selector: 'app-whatsapp-drawer',
  standalone: true,
  template: `
    <div class="backdrop" (click)="closed.emit()"></div>
    <aside class="drawer" role="dialog" aria-label="Supplier WhatsApp reconciliation preview">
      <header>
        <div class="wa-mark">&#128172;</div>
        <div class="who">
          <strong>Supplier WhatsApp</strong>
          <span>{{ claim().distributor_phone }} &middot; delivery reconciliation</span>
        </div>
        <button class="close" (click)="closed.emit()" aria-label="Close WhatsApp drawer">
          &times;
        </button>
      </header>

      <div class="chat">
        <div class="bubble">
          @if (cropUrl()) {
            <img [src]="cropUrl()" alt="Annotated crop of the pen-corrected challan line" />
          }
          <p class="msg">{{ claim().message_preview }}</p>
          <button class="pay-link" type="button">
            Accept &amp; Collect {{ inr(approvedTotal()) }} &middot; Paytm Link
          </button>
          <div class="meta">
            <span class="ticks">{{ statusTicks() }}</span>
            <span>{{ sentAt }}</span>
          </div>
        </div>
      </div>

      <footer>
        P0 preview &mdash; the live pipeline dispatches this slip via the WhatsApp Business API
        when APPROVE_SPLIT resolves.
      </footer>
    </aside>
  `,
  styles: `
    .backdrop {
      position: fixed;
      inset: 0;
      background: rgba(4, 8, 18, 0.55);
      backdrop-filter: blur(2px);
      z-index: 40;
      animation: pp-fade 0.25s ease;
    }
    @keyframes pp-fade {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    .drawer {
      position: fixed;
      top: 0;
      right: 0;
      height: 100%;
      width: min(430px, 94vw);
      z-index: 41;
      display: flex;
      flex-direction: column;
      background: #0e1f18;
      border-left: 1px solid rgba(47, 208, 122, 0.25);
      box-shadow: -18px 0 44px rgba(0, 0, 0, 0.5);
      animation: pp-slide-in 0.32s cubic-bezier(0.2, 0.9, 0.25, 1);
    }
    @keyframes pp-slide-in {
      from { transform: translateX(100%); }
      to { transform: translateX(0); }
    }

    header {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      background: #075e54;
      color: #fff;
    }
    .wa-mark {
      width: 38px;
      height: 38px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: #128c7e;
      font-size: 18px;
    }
    .who {
      display: flex;
      flex-direction: column;
      line-height: 1.3;
      flex: 1;
      min-width: 0;
    }
    .who strong {
      font-size: 14px;
    }
    .who span {
      font-size: 12px;
      opacity: 0.85;
    }
    .close {
      border: none;
      background: transparent;
      color: #fff;
      font-size: 24px;
      line-height: 1;
      padding: 4px 8px;
      border-radius: 8px;
    }
    .close:hover {
      background: rgba(255, 255, 255, 0.15);
    }

    .chat {
      flex: 1;
      overflow-y: auto;
      padding: 18px 14px;
      background:
        radial-gradient(rgba(255, 255, 255, 0.05) 1.5px, transparent 1.5px) 0 0 / 22px 22px,
        #0b1a14;
    }

    .bubble {
      max-width: 92%;
      margin-left: auto;
      background: #d9fdd3;
      color: #0b1a14;
      border-radius: 14px 4px 14px 14px;
      padding: 10px 12px 8px;
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35);
    }
    .bubble img {
      width: 100%;
      border-radius: 10px;
      border: 1px solid rgba(0, 0, 0, 0.12);
      margin-bottom: 8px;
      display: block;
    }
    .msg {
      margin: 0 0 10px;
      font-size: 13.5px;
      line-height: 1.55;
      color: #10231a;
    }
    .pay-link {
      width: 100%;
      border: none;
      border-radius: 10px;
      padding: 12px;
      background: linear-gradient(135deg, #25d366, #128c7e);
      color: #04120b;
      font-size: 13px;
      font-weight: 800;
    }
    .pay-link:hover {
      filter: brightness(1.06);
    }
    .meta {
      display: flex;
      justify-content: flex-end;
      gap: 6px;
      margin-top: 6px;
      font-size: 10.5px;
      color: #4c6357;
    }
    .ticks {
      color: #34b7f1;
      font-weight: 800;
    }

    footer {
      padding: 10px 14px;
      font-size: 11px;
      color: #7fa793;
      background: #0a1712;
      border-top: 1px solid rgba(47, 208, 122, 0.15);
      text-align: center;
    }
  `,
})
export class WhatsappDrawerComponent {
  readonly claim = input.required<WhatsappClaim>();
  readonly cropUrl = input('');
  readonly approvedTotal = input(0);
  readonly closed = output<void>();

  protected readonly inr = formatINR;
  protected readonly sentAt = new Date().toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });

  /** WhatsApp-style double tick when the claim is SENT. */
  protected statusTicks(): string {
    return this.claim().status === 'SENT' ? '\u2713\u2713' : this.claim().status;
  }
}
