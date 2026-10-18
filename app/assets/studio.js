() => {
  if (window.__studioReady) return;
  window.__studioReady = true;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let preference = null;
  try { preference = localStorage.getItem('studio-motion'); } catch (_) {}
  function renderMotion() {
    const off = reduced.matches || preference === 'off';
    document.documentElement.dataset.motion = off ? 'off' : 'on';
    const button = document.querySelector('#motion-toggle');
    if (button) {
      button.setAttribute('aria-pressed', String(!off));
      const label = off ? '动效已关闭' : '动效已开启';
      if (button.textContent !== label) button.textContent = label;
    }
  }
  document.addEventListener('click', event => {
    if (!event.target.closest('#motion-toggle')) return;
    preference = document.documentElement.dataset.motion === 'off' ? 'on' : 'off';
    try { localStorage.setItem('studio-motion', preference); } catch (_) {}
    renderMotion();
  });
  reduced.addEventListener('change', renderMotion);
  // A shared underline follows the real Gradio-selected tab or radio option.
  let frame = 0;
  function updateIndicators() {
    frame = 0;
    document.querySelectorAll('#story-tabs [role="tablist"], #channel-choice .wrap').forEach(group => {
      const chosen = group.querySelector('[role="tab"][aria-selected="true"], label:has(input:checked)');
      if (!chosen) return;
      const parent = group.getBoundingClientRect(), box = chosen.getBoundingClientRect();
      group.style.setProperty('--indicator-x', `${box.left-parent.left+group.scrollLeft}px`);
      group.style.setProperty('--indicator-width', `${box.width}px`);
      group.style.setProperty('--indicator-y', `${box.top-parent.top}px`);
      group.style.setProperty('--indicator-height', `${box.height}px`);
    });
    renderMotion();
  }
  function schedule() { if (!frame) frame = requestAnimationFrame(updateIndicators); }
  new MutationObserver(schedule).observe(document.querySelector('.gradio-container') || document.body,
    {subtree:true, childList:true, attributes:true, attributeFilter:['aria-selected','checked']});
  document.addEventListener('change', schedule);
  window.addEventListener('resize', schedule, {passive:true});
  schedule();
}
