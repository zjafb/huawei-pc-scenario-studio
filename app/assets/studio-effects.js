() => {
  if (window.__studioDepthReady) return;
  window.__studioDepthReady = true;
  document.documentElement.dataset.studioDesign = 'paper-depth-03';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
  const enabled = () => !reduced.matches && document.documentElement.dataset.motion !== 'off';
  let previousProgress = 0;
  let lastPipeline = null;
  let frame = 0;
  let pointerFrame = 0;
  let surface = null;
  let point = null;

  function clearSurface() {
    if (!surface) return;
    surface.classList.remove('studio-pointer');
    ['--rx', '--ry', '--spot-x', '--spot-y'].forEach(property => surface.style.removeProperty(property));
    surface = null;
  }

  function decorate() {
    frame = 0;
    const pipeline = document.querySelector('#workflow .pipeline');
    if (pipeline && pipeline !== lastPipeline) {
      const target = Math.max(0, Math.min(1, parseFloat(pipeline.style.getPropertyValue('--progress')) / 100 || 0));
      pipeline.style.setProperty('--display-progress', String(enabled() ? Math.min(previousProgress, target) : target));
      // The target is read from a real backend milestone, never from a timer.
      requestAnimationFrame(() => {
        if (pipeline.isConnected) pipeline.style.setProperty('--display-progress', String(target));
      });
      previousProgress = target;
      lastPipeline = pipeline;
    }
    const article = document.querySelector('#article-preview .story-card');
    if (article && !article.dataset.studioArrival) {
      article.dataset.studioArrival = 'true';
      if (enabled()) article.classList.add('studio-arrival');
    }
    const preview = document.querySelector('#article-preview .article-empty');
    if (preview && /正在组织|正在生成/.test(preview.textContent) && !preview.classList.contains('article-waiting')) {
      preview.classList.add('article-waiting');
      if (!preview.querySelector('.empty-mark')) {
        const mark = document.createElement('div');
        mark.className = 'empty-mark';
        mark.textContent = '✳';
        mark.setAttribute('aria-hidden', 'true');
        preview.prepend(mark);
      }
      if (!preview.querySelector('.empty-lines')) {
        const lines = document.createElement('div');
        lines.className = 'empty-lines';
        lines.setAttribute('aria-hidden', 'true');
        for (let i = 0; i < 3; i++) lines.append(document.createElement('i'));
        preview.append(lines);
      }
    }
  }
  const schedule = () => { if (!frame) frame = requestAnimationFrame(decorate); };
  new MutationObserver(schedule).observe(document.querySelector('.gradio-container') || document.body,
    { subtree: true, childList: true });

  new MutationObserver(() => {
    if (enabled()) return;
    clearSurface();
    cancelAnimationFrame(pointerFrame);
    pointerFrame = 0;
    document.querySelectorAll('.studio-click-ripple').forEach(element => element.remove());
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-motion'] });
  reduced.addEventListener('change', clearSurface);
  finePointer.addEventListener('change', clearSurface);

  document.addEventListener('pointermove', event => {
    if (!enabled() || !finePointer.matches) return;
    const next = event.target.closest('#brief-column, #story-tabs .story-card img');
    if (next !== surface) { clearSurface(); surface = next; }
    if (!surface) return;
    point = { x: event.clientX, y: event.clientY };
    if (pointerFrame) return;
    pointerFrame = requestAnimationFrame(() => {
      pointerFrame = 0;
      if (!surface?.isConnected || !point || !enabled()) return;
      const rect = surface.getBoundingClientRect();
      const x = Math.max(0, Math.min(1, (point.x - rect.left) / rect.width));
      const y = Math.max(0, Math.min(1, (point.y - rect.top) / rect.height));
      surface.classList.add('studio-pointer');
      surface.style.setProperty('--spot-x', `${x * 100}%`);
      surface.style.setProperty('--spot-y', `${y * 100}%`);
      if (surface.tagName === 'IMG') {
        surface.style.setProperty('--rx', `${(.5 - y) * 3}deg`);
        surface.style.setProperty('--ry', `${(x - .5) * 4}deg`);
      }
    });
  }, { passive: true });
  document.addEventListener('pointerout', event => { if (!event.relatedTarget) clearSurface(); }, { passive: true });
  document.addEventListener('visibilitychange', () => { if (document.hidden) clearSurface(); });
  document.addEventListener('click', event => {
    if (!enabled() || event.detail === 0) return;
    const button = event.target.closest('#generate');
    if (!button || button.disabled) return;
    const rect = button.getBoundingClientRect();
    const ripple = document.createElement('span');
    ripple.className = 'studio-click-ripple';
    ripple.setAttribute('aria-hidden', 'true');
    ripple.style.left = `${event.clientX - rect.left - 6}px`;
    ripple.style.top = `${event.clientY - rect.top - 6}px`;
    button.append(ripple);
    ripple.addEventListener('animationend', () => ripple.remove(), { once: true });
  });
  schedule();
}
