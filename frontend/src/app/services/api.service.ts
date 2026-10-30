import { Injectable, inject, signal } from '@angular/core';

import {
  AuditedInvoiceResponse,
  ExportFormat,
  LoadSampleRequest,
  PayoutApprovedData,
  ResolveRequest,
  ResolveActionResponse,
} from '@contracts/contracts';

import { WebsocketService } from './websocket.service';

export const DEMO_MERCHANT_ID = 'a0000000-0000-0000-0000-000000000001';
const JSON_HEADERS: Record<string, string> = { 'Content-Type': 'application/json' };

/**
 * REST client for CIS §4 endpoints.
 * Directly communicates with the FastAPI backend through the /api proxy.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly ws = inject(WebsocketService);

  // -- POST /api/parcha/scan (multipart: file, merchant_id) ------------------

  async scan(file: File, merchantId: string = DEMO_MERCHANT_ID): Promise<AuditedInvoiceResponse> {
    const form = new FormData();
    form.append('file', file, file.name || 'parcha.jpg');
    form.append('merchant_id', merchantId);

    const res = await fetch('/api/parcha/scan', { method: 'POST', body: form });
    if (!res.ok) {
      let errorDetail = `HTTP ${res.status}`;
      try {
        const errorJson = await res.json();
        if (errorJson && errorJson.detail) {
          errorDetail = errorJson.detail;
        }
      } catch {
        // use default HTTP status
      }
      throw new Error(`Bill scan failed: ${errorDetail}`);
    }

    const data = (await res.json()) as AuditedInvoiceResponse;
    this.assertAudited(data, 'scan');
    return data;
  }

  // -- POST /api/demo/load-sample ---------------------------------------------

  async loadSample(sampleId: string = 'sample_pen_edit_01'): Promise<AuditedInvoiceResponse> {
    const body: LoadSampleRequest = { sample_id: sampleId };
    const res = await fetch('/api/demo/load-sample', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      let errorDetail = `HTTP ${res.status}`;
      try {
        const errorJson = await res.json();
        if (errorJson && errorJson.detail) {
          errorDetail = errorJson.detail;
        }
      } catch {
        // use default HTTP status
      }
      throw new Error(`Load sample failed: ${errorDetail}`);
    }

    const data = (await res.json()) as AuditedInvoiceResponse;
    this.assertAudited(data, 'load-sample');
    return data;
  }

  // -- POST /api/parcha/{id}/resolve ------------------------------------------

  async resolve(invoiceId: string, tenureDays = 7): Promise<ResolveActionResponse> {
    const body: ResolveRequest = { action: 'APPROVE_SPLIT', tenure_days: tenureDays };
    const res = await fetch(`/api/parcha/${encodeURIComponent(invoiceId)}/resolve`, {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      let errorDetail = `HTTP ${res.status}`;
      try {
        const errorJson = await res.json();
        if (errorJson && errorJson.detail) {
          errorDetail = errorJson.detail;
        }
      } catch {
        // use default HTTP status
      }
      throw new Error(`Resolve failed: ${errorDetail}`);
    }

    const data = (await res.json()) as ResolveActionResponse;
    return data;
  }

  // -- GET /api/parcha/{id}/export?format=tally|marg -------------------------

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

  /** Returns the static crop or asset URL directly from the server. */
  assetUrl(contractUrl: string): string {
    return contractUrl;
  }

  private assertAudited(data: unknown, source: string): asserts data is AuditedInvoiceResponse {
    if (!data || typeof data !== 'object') {
      throw new Error(`[api] ${source} returned non-object response`);
    }
    const d = data as Partial<AuditedInvoiceResponse>;
    if (!d.invoice_id || !Array.isArray(d.items) || typeof d.billed_total !== 'number') {
      throw new Error(`[api] ${source} missing required AuditedInvoiceResponse fields`);
    }
  }
}
