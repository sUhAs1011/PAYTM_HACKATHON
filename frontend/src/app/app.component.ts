import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { DemoAuthService } from './services/demo-auth.service';

/**
 * Root shell. Deliberately bare: `/scan` must render chrome-free on a phone
 * and `/counter` fills the projector — no shared header between surfaces.
 */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  template: `
    <router-outlet />
    @if (demoAuth.dialogOpen()) {
      <div class="auth-backdrop">
        <section
          class="auth-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="demo-auth-title"
        >
          <h2 id="demo-auth-title">Demo access</h2>
          <p>{{ demoAuth.promptMessage() }}</p>
          <form (submit)="submitCredentials($event)">
            <label>
              Username
              <input #username name="username" autocomplete="username" required />
            </label>
            <label>
              Password
              <input
                #password
                name="password"
                type="password"
                autocomplete="current-password"
                required
              />
            </label>
            <div class="auth-actions">
              <button type="button" class="auth-cancel" (click)="demoAuth.cancel()">Cancel</button>
              <button type="submit" class="auth-submit">Continue</button>
            </div>
          </form>
        </section>
      </div>
    }
  `,
  styles: `
    .auth-backdrop {
      position: fixed;
      inset: 0;
      z-index: 10000;
      display: grid;
      place-items: center;
      padding: 20px;
      background: rgba(3, 13, 25, 0.72);
      backdrop-filter: blur(5px);
    }
    .auth-dialog {
      width: min(100%, 420px);
      padding: 24px;
      border: 1px solid rgba(0, 186, 242, 0.35);
      border-radius: 18px;
      background: #0b1b2b;
      color: #f4f8fc;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.4);
      font-family: Inter, system-ui, sans-serif;
    }
    .auth-dialog h2 { margin: 0 0 8px; font-size: 21px; }
    .auth-dialog p { margin: 0 0 18px; color: #a9bacb; line-height: 1.5; }
    .auth-dialog label { display: grid; gap: 7px; margin-top: 14px; font-size: 13px; font-weight: 700; }
    .auth-dialog input {
      box-sizing: border-box;
      width: 100%;
      padding: 11px 12px;
      border: 1px solid #34485a;
      border-radius: 9px;
      background: #071321;
      color: #f4f8fc;
      font: inherit;
    }
    .auth-dialog input:focus { outline: 2px solid #00baf2; outline-offset: 1px; }
    .auth-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 22px; }
    .auth-actions button { padding: 10px 16px; border-radius: 9px; font: inherit; font-weight: 700; cursor: pointer; }
    .auth-cancel { border: 1px solid #34485a; background: transparent; color: #d0dce8; }
    .auth-submit { border: 0; background: #00baf2; color: #00121f; }
  `,
})
export class AppComponent {
  readonly demoAuth = inject(DemoAuthService);

  submitCredentials(event: Event): void {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const values = new FormData(form);
    this.demoAuth.submit(
      String(values.get('username') ?? ''),
      String(values.get('password') ?? ''),
    );
  }
}
