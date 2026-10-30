import { Component, input } from '@angular/core';

import { AuditedItem } from '@contracts/contracts';

import { formatINR2, formatPct } from '../../shared/format';

/**
 * Line-item audit table (PRD F3/F4 left panel) — renders the CIS
 * `AUDIT_COMPLETE.items[]` array with the three audit semantics:
 * red row = overcharge (rate hike / math / pen error), yellow row =
 * OCR confidence below 0.80 pending 1-tap review, green row = OK.
 * Mandi-Pulse band and personal history rate are shown per CIS fields.
 */
@Component({
  selector: 'app-audit-table',
  standalone: true,
  template: `
    <div class="pp-card table-card">
      <div class="head">
        <span class="pp-label">Line-item audit</span>
        <div class="legend">
          <span><i class="dot red"></i>overcharge</span>
          <span><i class="dot yellow"></i>review &lt; 80%</span>
          <span><i class="dot green"></i>ok</span>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Qty</th>
              <th>Free</th>
              <th>Rate</th>
              <th>GST</th>
              <th>Landed</th>
              <th>History</th>
              <th>Mandi-Pulse</th>
              <th>OCR</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            @for (item of items(); track item.item_name) {
              <tr [class]="rowClass(item)">
                <td class="name">
                  {{ item.item_name }}
                  @if (item.has_pen_markup) {
                    <span class="pen" title="Pen-corrected on delivery">&#9999;&#65039;</span>
                  }
                  @if (item.discrepancy_type) {
                    <span class="dtype">{{ item.discrepancy_type }}</span>
                  }
                </td>
                <td>
                  @if (item.has_pen_markup && item.printed_qty !== item.billed_qty) {
                    <span class="qty-edit">
                      {{ item.printed_qty }} &rarr; {{ item.billed_qty }}
                    </span>
                  } @else {
                    {{ item.billed_qty }}
                  }
                </td>
                <td>{{ item.free_qty }}</td>
                <td>{{ inr2(item.billed_rate) }}</td>
                <td>{{ pct(item.tax_percent) }}</td>
                <td>{{ inr2(item.true_landed_cost) }}</td>
                <td>{{ inr2(item.personal_history_rate) }}</td>
                <td>
                  <span class="band">{{ item.mandi_pulse_band }}</span>
                  <span class="median">{{ inr2(item.mandi_pulse_median) }}</span>
                </td>
                <td [class.low]="item.ocr_confidence < 0.8">{{ pct(item.ocr_confidence, true) }}</td>
                <td>
                  <span class="status" [class.bad]="item.rate_status !== 'OK'">
                    {{ item.rate_status }}
                  </span>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </div>
  `,
  styles: `
    .table-card {
      padding: 16px 18px 18px;
    }

    .head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }
    .legend {
      display: flex;
      gap: 14px;
      font-size: 11px;
      color: var(--pp-text-dim);
    }
    .legend span {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
    }
    .dot.red { background: var(--pp-red); }
    .dot.yellow { background: var(--pp-yellow); }
    .dot.green { background: var(--pp-green); }

    .table-wrap {
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 780px;
    }
    th {
      text-align: left;
      padding: 8px 10px;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--pp-text-faint);
      border-bottom: 1px solid var(--pp-line);
      white-space: nowrap;
    }
    td {
      padding: 12px 10px;
      border-bottom: 1px solid rgba(42, 56, 84, 0.5);
      vertical-align: top;
      color: var(--pp-text-dim);
      white-space: nowrap;
    }
    td.name {
      white-space: normal;
      min-width: 200px;
      color: var(--pp-text);
      font-weight: 600;
    }

    tr.row-red td {
      background: var(--pp-red-bg);
    }
    tr.row-red td:first-child {
      box-shadow: inset 3px 0 0 var(--pp-red);
    }
    tr.row-yellow td {
      background: var(--pp-yellow-bg);
    }
    tr.row-yellow td:first-child {
      box-shadow: inset 3px 0 0 var(--pp-yellow);
    }
    tr.row-green td:first-child {
      box-shadow: inset 3px 0 0 var(--pp-green);
    }

    .pen {
      margin-left: 6px;
    }
    .dtype {
      display: block;
      margin-top: 4px;
      font-size: 10px;
      letter-spacing: 0.06em;
      font-weight: 800;
      color: var(--pp-text-faint);
    }
    tr.row-red .dtype { color: var(--pp-red); }
    tr.row-yellow .dtype { color: var(--pp-yellow); }

    .qty-edit {
      font-weight: 800;
      color: var(--pp-yellow);
      background: rgba(255, 204, 71, 0.15);
      border-radius: 6px;
      padding: 2px 6px;
    }

    .band {
      display: inline-block;
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      color: var(--pp-blue-soft);
      background: rgba(0, 186, 242, 0.12);
      border: 1px solid rgba(0, 186, 242, 0.3);
    }
    .median {
      display: block;
      margin-top: 4px;
      font-size: 11px;
      color: var(--pp-text-faint);
    }

    td.low {
      color: var(--pp-yellow);
      font-weight: 800;
    }

    .status {
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.05em;
      padding: 3px 8px;
      border-radius: 999px;
      background: var(--pp-green-bg);
      color: var(--pp-green);
    }
    .status.bad {
      background: var(--pp-red-bg);
      color: var(--pp-red);
    }
  `,
})
export class AuditTableComponent {
  readonly items = input.required<AuditedItem[]>();

  protected readonly inr2 = formatINR2;
  protected readonly pct = formatPct;

  rowClass(item: AuditedItem): 'row-red' | 'row-yellow' | 'row-green' {
    if (item.rate_status === 'FLAGGED_HIGH' || /RATE_HIKE|MATH|PEN/i.test(item.discrepancy_type)) {
      return 'row-red';
    }
    if (item.ocr_confidence < 0.8 || /LOW_CONFIDENCE/i.test(item.discrepancy_type)) {
      return 'row-yellow';
    }
    return 'row-green';
  }
}
