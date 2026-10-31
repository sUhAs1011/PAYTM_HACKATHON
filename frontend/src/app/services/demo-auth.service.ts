import { Injectable, signal } from '@angular/core';

const SESSION_KEY = 'parchapay-demo-basic-auth';

/** Holds the short-lived demo Basic credential and coordinates its prompt. */
@Injectable({ providedIn: 'root' })
export class DemoAuthService {
  readonly dialogOpen = signal(false);
  readonly promptMessage = signal('Enter the demo credentials to continue.');

  private credential = this.readCredential();
  private pending: ((credential: string | null) => void) | null = null;
  private readonly waiters: Array<(credential: string | null) => void> = [];

  currentCredential(): string | null {
    return this.credential;
  }

  requestCredential(message?: string): Promise<string | null> {
    if (this.credential) return Promise.resolve(this.credential);
    if (message) this.promptMessage.set(message);
    if (this.pending) {
      return new Promise((resolve) => this.waiters.push(resolve));
    }

    this.dialogOpen.set(true);
    return new Promise((resolve) => {
      this.pending = resolve;
    });
  }

  submit(username: string, password: string): boolean {
    if (!username || !password || /[^\x00-\x7f]/.test(`${username}:${password}`)) {
      this.promptMessage.set('Enter the ASCII username and password supplied for the demo.');
      return false;
    }

    try {
      this.credential = btoa(`${username}:${password}`);
    } catch {
      this.promptMessage.set('Could not save the demo credential in this browser tab.');
      return false;
    }
    try {
      sessionStorage.setItem(SESSION_KEY, this.credential);
    } catch {
      // Keep the credential in memory for this page if storage is unavailable.
    }

    this.promptMessage.set('Enter the demo credentials to continue.');
    this.finish(this.credential);
    return true;
  }

  reject(message = 'Those credentials were not accepted. Try again.'): void {
    this.credential = null;
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      // The in-memory value is still cleared if browser storage is unavailable.
    }
    this.promptMessage.set(message);
  }

  cancel(): void {
    this.promptMessage.set('Enter the demo credentials to continue.');
    this.finish(null);
  }

  private finish(credential: string | null): void {
    const resolvePending = this.pending;
    this.pending = null;
    this.dialogOpen.set(false);
    resolvePending?.(credential);
    for (const resolve of this.waiters.splice(0)) resolve(credential);
  }

  private readCredential(): string | null {
    try {
      return sessionStorage.getItem(SESSION_KEY);
    } catch {
      return null;
    }
  }
}
