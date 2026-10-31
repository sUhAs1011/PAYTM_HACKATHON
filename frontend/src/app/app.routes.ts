import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'counter' },
  {
    path: 'scan',
    title: 'ParchaPay AI — Scan Parcha',
    loadComponent: () => import('./routes/scan/scan.component').then((m) => m.ScanComponent),
  },
  {
    path: 'counter',
    title: 'ParchaPay AI — Soundbox Counter',
    loadComponent: () => import('./routes/counter/counter.component').then((m) => m.CounterComponent),
  },
  { path: '**', redirectTo: 'scan' },
];
