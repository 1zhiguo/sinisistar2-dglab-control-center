(() => {
  const selector = document.querySelector('#language');
  const labels = document.querySelectorAll('[data-i18n]');
  const alternateLabels = document.querySelectorAll('[data-i18n-alt]');
  let translations;
  let preference = 'zh';
  try { preference = localStorage.getItem('sinisistar2-language') || 'zh'; } catch {}
  const apply = (language) => {
    const lang = ['zh', 'en', 'ja'].includes(language) ? language : 'zh';
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : lang;
    selector.value = lang;
    if (translations) labels.forEach(el => { el.textContent = translations[el.dataset.i18n][lang]; });
    if (translations) alternateLabels.forEach(el => { el.alt = translations[el.dataset.i18nAlt][lang]; });
    try { localStorage.setItem('sinisistar2-language', lang); } catch {}
  };
  fetch('translations.json').then(r => { if (!r.ok) throw Error('translations'); return r.json(); })
    .then(data => { translations = data; apply(preference); }).catch(() => { selector.disabled = true; });
  selector.addEventListener('change', () => apply(selector.value));
  const hudDemo = document.querySelector('#hud-demo-image');
  const hudToggle = document.querySelector('#hud-demo-toggle');
  if (hudDemo && hudToggle) {
    let paused = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const syncDemo = () => {
      hudDemo.src = paused ? hudDemo.dataset.poster : hudDemo.dataset.animation;
      hudToggle.dataset.i18n = paused ? 'hudplay' : 'hudpause';
      hudToggle.setAttribute('aria-pressed', String(paused));
      const lang = ['zh', 'en', 'ja'].includes(selector.value) ? selector.value : 'zh';
      hudToggle.textContent = translations ? translations[hudToggle.dataset.i18n][lang] : paused ? '播放动图' : '暂停动图';
    };
    syncDemo();
    hudToggle.addEventListener('click', () => { paused = !paused; syncDemo(); });
  }
  const dialog = document.querySelector('#lightbox');
  document.querySelectorAll('[data-image]').forEach(button => {
    button.addEventListener('click', () => {
      dialog.querySelector('img').src = button.dataset.image;
      dialog.querySelector('img').alt = button.querySelector('img').alt;
      dialog.showModal();
    });
  });
  document.querySelector('#close-image').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
})();
