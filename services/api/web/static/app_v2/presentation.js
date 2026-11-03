// app_v2 presentation only. All requests, clinical state and actions remain in /static/app.js,
// the same application script the original interface runs.
// This module adds decorative initials, a read-only progress indicator and display controls.
const root = document.getElementById('root');
const display = document.getElementById('v2-display');
const initials = text => text.trim().split(/\s+/).map(word => word[0]).slice(0, 2).join('').toUpperCase();

function avatar(host, text) {
  if (!text || host.querySelector(':scope > .v2-avatar')) return;
  const node = document.createElement('span');
  node.className = 'avatar v2-avatar';
  node.setAttribute('aria-hidden', 'true');
  node.textContent = initials(text);
  host.prepend(node);
}

function decorate() {
  root.querySelectorAll('.pitem').forEach(row => avatar(row, row.querySelector('.name')?.textContent));
  root.querySelectorAll('.phead').forEach(head => avatar(head, head.querySelector('h2')?.textContent));
  const header = root.querySelector('.me');
  if (header && display.parentElement !== header) header.insertBefore(display, header.lastElementChild);
  if (!header && display.parentElement !== document.body) document.body.append(display);

  const main = document.getElementById('main');
  const surface = main?.querySelector('.review, .record');
  if (!surface || main.querySelector('.v2-stepper')) return;
  const approved = Boolean(surface.querySelector('.approved'));
  const review = surface.classList.contains('review');
  const processing = Boolean(surface.querySelector('.proc'));
  const current = approved ? 2 : review || processing ? 1 : 0;
  const steps = document.createElement('ol');
  steps.className = 'v2-stepper';
  steps.setAttribute('aria-label', 'Visit progress');
  ['Record', 'Check', 'Approve'].forEach((label, index) => {
    const step = document.createElement('li');
    step.textContent = label;
    step.dataset.state = approved || index < current ? 'done' : index === current ? 'now' : 'todo';
    if (index === current) step.setAttribute('aria-current', 'step');
    steps.append(step);
  });
  surface.before(steps);
}

let scheduled = false;
new MutationObserver(() => {
  if (scheduled) return;
  scheduled = true;
  requestAnimationFrame(() => { scheduled = false; decorate(); });
}).observe(root, { childList: true, subtree: true, characterData: true });
decorate();

display.addEventListener('click', event => {
  const button = event.target.closest('button[data-pref]');
  if (!button) return;
  document.documentElement.dataset[button.dataset.pref] = button.dataset.value;
  display.querySelectorAll(`button[data-pref="${button.dataset.pref}"]`).forEach(option => {
    option.setAttribute('aria-pressed', String(option === button));
  });
});
document.addEventListener('click', event => { if (!display.contains(event.target)) display.open = false; });
document.addEventListener('keydown', event => { if (event.key === 'Escape') display.open = false; });
document.addEventListener('visibilitychange', () => document.documentElement.classList.toggle('v2-background-paused', document.hidden));
document.getElementById('v2-skip').addEventListener('click', () => {
  const target = document.getElementById('main') || root;
  target.setAttribute('tabindex', '-1');
  target.focus();
  target.scrollIntoView({ block: 'start' });
});
