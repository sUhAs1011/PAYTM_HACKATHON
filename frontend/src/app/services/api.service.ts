import { Injectable, inject, signal } from '@angular/core';

import {
  AuditedInvoiceResponse,
  AuditCompleteData,
  ExportFormat,
  LoadSampleRequest,
  PayoutApprovedData,
  ResolveRequest,
  ResolveActionResponse,
} from '@contracts/contracts';
import demoFixtureJson from '@contracts/demo-bill-fixture';

import { WebsocketService } from './websocket.service';
import { formatINR } from '../shared/format';

/**
 * Seeded demo merchant (CIS 002 seed: 'Sharma General Store', Bellandur
 * 560103). ASSUMPTION: a single demo merchant constant is used until an
 * auth/merchant-context surface exists in the spec.
 */
export const DEMO_MERCHANT_ID = 'a0000000-0000-0000-0000-000000000001';

const DEMO_SAMPLE_ID = 'sample_pen_edit_01';

/** Theatrical processing delay in demo mode so /counter shows the PROCESSING state. */
const MOCK_SCAN_DELAY_MS = 900;

/**
 * Mock asset substitution for demo mode (Module 1 mock-first isolation).
 * Contract URLs are never rewritten in the payload — this mapping is applied
 * only at render time when no backend is serving /static.
 * The audio URL has no bundled stand-in on purpose: the Soundbox twin falls
 * back to speechSynthesis using the contract `voice_transcript`.
 */
const MOCK_ASSET_MAP: Record<string, string> = {
  '/static/crops/demo_pen_edit.jpg': '/assets/mock/demo_pen_edit.svg',
};

/** Distributor phone from the CIS PAYOUT_APPROVED example payload. */
const DEMO_DISTRIBUTOR_PHONE = '+919876543210';

const JSON_HEADERS: Record<string, string> = { 'Content-Type': 'application/json' };

/**
 * REST client for the four CIS §4 endpoints, with a fixture-driven fallback
 * so the entire dual-surface UI runs with zero backend (mock-first).
 *
 * In demo mode the service synthesizes the documented CIS payloads from the
 * golden fixture — including a PAYOUT_APPROVED-shaped resolve response — so
 * `/counter` exercises the exact same rendering path as the live pipeline.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly ws = inject(WebsocketService);

  /** True once a CIS endpoint was unreachable and the fixture took over. */
  readonly demoMode = signal(false);

  private lastAudit: AuditedInvoiceResponse = demoFixtureJson as AuditedInvoiceResponse;

  // -- POST /api/parcha/scan (multipart: file, merchant_id) ------------------

  async scan(file: File, merchantId: string = DEMO_MERCHANT_ID): Promise<AuditedInvoiceResponse> {
    if (this.demoMode()) {
      return this.fallbackToDemo();
    }
    const form = new FormData();
    form.append('file', file, file.name || 'parcha.jpg');
    form.append('merchant_id', merchantId);
    try {
      const res = await fetch('/api/parcha/scan', { method: 'POST', body: form });
      if (!res.ok) {
        throw new Error(`scan failed: HTTP ${res.status}`);
      }
      const data = (await res.json()) as AuditedInvoiceResponse;
      this.assertAudited(data, 'scan');
      this.lastAudit = data;
      return data;
    } catch (err) {
      console.warn('[api] /api/parcha/scan unavailable — switching to demo fixture', err);
      return this.fallbackToDemo();
    }
  }

  // -- POST /api/demo/load-sample ---------------------------------------------

  async loadSample(sampleId: string = DEMO_SAMPLE_ID): Promise<AuditedInvoiceResponse> {
    if (this.demoMode()) {
      return this.fallbackToDemo();
    }
    const body: LoadSampleRequest = { sample_id: sampleId };
    try {
      const res = await fetch('/api/demo/load-sample', {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        throw new Error(`load-sample failed: HTTP ${res.status}`);
      }
      const data = (await res.json()) as AuditedInvoiceResponse;
      this.assertAudited(data, 'load-sample');
      this.lastAudit = data;
      return data;
    } catch (err) {
      console.warn('[api] /api/demo/load-sample unavailable — switching to demo fixture', err);
      return this.fallbackToDemo();
    }
  }

  // -- POST /api/parcha/{id}/resolve (APPROVE_SPLIT is the only CIS action) ---

  async resolve(invoiceId: string, tenureDays = 7): Promise<ResolveActionResponse> {
    const body: ResolveRequest = { action: 'APPROVE_SPLIT', tenure_days: tenureDays };
    if (this.demoMode()) {
      return this.resolveViaMock(invoiceId);
    }
    try {
      const res = await fetch(`/api/parcha/${encodeURIComponent(invoiceId)}/resolve`, {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        throw new Error(`resolve failed: HTTP ${res.status}`);
      }
      const data = (await res.json()) as ResolveActionResponse;
      // Real mode: the backend broadcasts PAYOUT_APPROVED on /ws/counter
      // itself — this response is returned to the caller only.
      return data;
    } catch (err) {
      console.warn('[api] resolve unavailable — completing via demo mode', err);
      return this.resolveViaMock(invoiceId);
    }
  }

  // -- GET /api/parcha/{id}/export?format=tally|marg (P1 F8 — method only) ----

  async downloadExport(invoiceId: string, format: ExportFormat): Promise<void> {
    const res = await fetch(`/api/parcha/${encodeURIComponent(invoiceId)}/export?format=${format}`);
    if (!res.ok) {
      throw new Error(`export failed: HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `parchapay-${invoiceId}.${format === 'tally' ? 'xml' : 'csv'}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  // -- Demo-mode helpers --------------------------------------------------------

  /**
   * Maps a contract static URL for rendering. In demo mode the bundled mock
   * asset is substituted; in real mode the contract URL passes through
   * unchanged (served by the API's /static mount via the proxy).
   */
  assetUrl(contractUrl: string): string {
    const mapped = this.demoMode() ? MOCK_ASSET_MAP[contractUrl] : undefined;
    return mapped ?? contractUrl;
  }

  /** True when the fixture is driving the UI (drives the demo-mode chip). */
  isDemoMode(): boolean {
    return this.demoMode();
  }

  private fallbackToDemo(): Promise<AuditedInvoiceResponse> {
    const firstFallback = !this.demoMode();
    this.demoMode.set(true);
    this.ws.enableDemoMode();
    const audit = this.lastAudit;
    if (firstFallback) {
      // CIS Event 1 shape, fired immediately (<0.5s) so /counter animates.
      this.ws.mockScanStarted({
        session_id: `sess_${Math.random().toString(16).slice(2, 10)}`,
        timestamp: new Date().toISOString(),
        status: 'PROCESSING_IMAGE',
        message: 'Auditing supplier parcha via Gemini 2.5 Flash...',
      });
    }
    return new Promise<AuditedInvoiceResponse>((resolve) => {
      setTimeout(() => {
        this.ws.mockAuditComplete(audit as AuditCompleteData);
        resolve(audit);
      }, MOCK_SCAN_DELAY_MS);
    });
  }

  /**
   * Demo-mode APPROVE_SPLIT. Builds the documented PAYOUT_APPROVED payload
   * from the current audit. Display theater only — the loan numbers shown
   * derive from contract fields (daily_deduction_amount, approved_total);
   * real underwriting is Module 4's Decimal credit engine.
   */
  private resolveViaMock(invoiceId: string): ResolveActionResponse {
    const audit = this.lastAudit;
    const principal = audit.approved_total;
    const daily = audit.split_credit_pre_approval.daily_deduction_amount;
    const payout: PayoutApprovedData = {
      invoice_id: invoiceId || audit.invoice_id,
      settlement_method: 'SOUNDBOX_7_DAY_SPLIT',
      whatsapp_claim: {
        distributor_phone: DEMO_DISTRIBUTOR_PHONE,
        message_preview:
          `Namaste ${audit.supplier_name}. Delivery received for Inv #${audit.invoice_number}. ` +
          `Note: quantity pen-corrected on challan. Amount approved: ${formatINR(audit.approved_total)}. ` +
          `[View Verified Challan Crop & Collect via Paytm Link]`,
        status: 'SENT',
      },
      gst_ims_state: 'DISPUTED_PENDING_IMS',
      loan_schedule: {
        principal,
        daily_deduction: daily,
        day_1_deducted: true,
        remaining_balance: principal - daily,
      },
    };
    this.ws.mockPayoutApproved(payout);
    return payout;
  }

  /** Minimal runtime sanity check so a malformed backend reply falls back loudly. */
  private assertAudited(data: unknown, source: string): asserts data is AuditedInvoiceResponse {
    const d = data as Partial<AuditedInvoiceResponse> | null;
    if (!d || typeof d.invoice_id !== 'string' || !Array.isArray(d.items) || !d.gst_ims_shield || !d.split_credit_pre_approval) {
      throw new Error(`${source}: response does not match AuditedInvoiceResponse`);
    }
  }
}
