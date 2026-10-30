import { Injectable, OnDestroy, signal } from '@angular/core';
import { Subject, Observable } from 'rxjs';

import {
  AuditCompleteData,
  PayoutApprovedData,
  ScanStartedData,
  WsEnvelope,
  WsEventName,
} from '@contracts/contracts';

export type WsConnectionState = 'CONNECTING' | 'OPEN' | 'RECONNECTING';

/**
 * Manages the persistent `/ws/counter` connection (CIS §4).
 *
 * Connects through the Angular dev-server proxy on port 4200 (never directly
 * to the API origin — CIS §6.2) and fans CIS events out to typed observables.
 */
@Injectable({ providedIn: 'root' })
export class WebsocketService implements OnDestroy {
  private socket: WebSocket | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly maxReconnectDelayMs = 15000;

  readonly connectionState = signal<WsConnectionState>('CONNECTING');

  private readonly scanStartedSubject = new Subject<ScanStartedData>();
  private readonly auditCompleteSubject = new Subject<AuditCompleteData>();
  private readonly payoutApprovedSubject = new Subject<PayoutApprovedData>();

  /** CIS Event 1 — fired within <0.5s of an upload starting. */
  readonly scanStarted$: Observable<ScanStartedData> = this.scanStartedSubject.asObservable();
  /** CIS Event 2 — full audited payload within <3.5s. */
  readonly auditComplete$: Observable<AuditCompleteData> = this.auditCompleteSubject.asObservable();
  /** CIS Event 3 — fired when the Paytm Button resolution completes. */
  readonly payoutApproved$: Observable<PayoutApprovedData> = this.payoutApprovedSubject.asObservable();

  constructor() {
    this.connect();
  }

  /** Relative URL through the 4200 proxy (CIS §6.2) — works on localhost and LAN alike. */
  private wsUrl(): string {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}/ws/counter`;
  }

  private connect(): void {
    this.connectionState.set(this.reconnectAttempts === 0 ? 'CONNECTING' : 'RECONNECTING');
    try {
      this.socket = new WebSocket(this.wsUrl());
    } catch (err) {
      console.warn('[ws] construction failed', err);
      this.scheduleReconnect();
      return;
    }
    this.socket.onopen = () => {
      this.reconnectAttempts = 0;
      this.connectionState.set('OPEN');
    };
    this.socket.onmessage = (ev: MessageEvent) => this.handleMessage(ev.data);
    this.socket.onerror = () => {
      /* onclose always follows an error; reconnection handled there */
    };
    this.socket.onclose = () => {
      this.socket = null;
      this.scheduleReconnect();
    };
  }

  private handleMessage(raw: unknown): void {
    let envelope: WsEnvelope;
    try {
      envelope = JSON.parse(String(raw)) as WsEnvelope;
    } catch {
      console.warn('[ws] ignored non-JSON message');
      return;
    }
    if (!envelope || typeof envelope.event !== 'string') {
      console.warn('[ws] message without event name ignored', envelope);
      return;
    }
    const event = envelope.event as WsEventName;
    switch (event) {
      case 'SCAN_STARTED':
        this.scanStartedSubject.next(envelope.data as ScanStartedData);
        break;
      case 'AUDIT_COMPLETE':
        this.auditCompleteSubject.next(envelope.data as AuditCompleteData);
        break;
      case 'PAYOUT_APPROVED':
        this.payoutApprovedSubject.next(envelope.data as PayoutApprovedData);
        break;
      default:
        console.warn('[ws] unknown event ignored', (envelope as { event: string }).event);
    }
  }

  private scheduleReconnect(): void {
    this.reconnectAttempts += 1;
    this.connectionState.set('RECONNECTING');
    const delay = Math.min(1000 * 2 ** (this.reconnectAttempts - 1), this.maxReconnectDelayMs);
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
    }
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  ngOnDestroy(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
    }
    if (this.socket) {
      this.socket.onclose = null;
      this.socket.close(1000, 'destroyed');
      this.socket = null;
    }
  }
}
