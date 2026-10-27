(() => {
  const selector = document.querySelector('#language');
  const labels = document.querySelectorAll('[data-i18n]');
  let translations;
  let preference = 'zh';
  try { preference = localStorage.getItem('sinisistar2-language') || 'zh'; } catch {}
  const apply = (language) => {
    const lang = ['zh', 'en', 'ja'].includes(language) ? language : 'zh';
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : lang;
    selector.value = lang;
    if (translations) labels.forEach(el => { el.textContent = translations[el.dataset.i18n][lang]; });
    try { localStorage.setItem('sinisistar2-language', lang); } catch {}
  };
  fetch('translations.json').then(r => { if (!r.ok) throw Error('translations'); return r.json(); })
    .then(data => { translations = data; apply(preference); }).catch(() => { selector.disabled = true; });
  selector.addEventListener('change', () => apply(selector.value));
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
