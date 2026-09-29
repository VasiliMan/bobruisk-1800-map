/* feedback.js — public feedback via Web3Forms (no account needed for visitors).
 *
 * ── ONE-TIME SETUP ────────────────────────────────────────────────────────
 * 1. Go to https://web3forms.com , enter YOUR email — an access key is emailed
 *    to you instantly (this is the only signup; visitors never register).
 * 2. Paste that key into WEB3FORMS_KEY below and commit.
 * Until a key is set, the form shows a polite "not configured yet" notice.
 * Submissions are emailed to the address tied to the key.
 * ─────────────────────────────────────────────────────────────────────────── */
const WEB3FORMS_KEY = "a6762f84-fd1d-422b-94bf-1481e419ac9d"; // public Web3Forms key (safe client-side)

// POST a set of fields to Web3Forms. Returns {ok:true} or {ok:false,error}.
async function sendFeedback(fields) {
  if (!WEB3FORMS_KEY) return { ok: false, error: 'no-key' };
  const payload = Object.assign({
    access_key: WEB3FORMS_KEY,
    from_name: 'Карта землеўладальнікаў 1800',
  }, fields);
  try {
    const r = await fetch('https://api.web3forms.com/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(payload),
    });
    const res = await r.json();
    return res.success ? { ok: true } : { ok: false, error: res.message || 'error' };
  } catch (e) { return { ok: false, error: String(e) }; }
}

// ---- inline modal (used by the map popups) ----------------------------------
(function injectFeedbackCSS() {
  if (document.getElementById('fb-css')) return;
  const css = `
  #fb-overlay { position: fixed; inset: 0; background: rgba(20,16,8,.45); z-index: 4000;
    display: none; align-items: center; justify-content: center; padding: 16px; }
  #fb-overlay.open { display: flex; }
  #fb-card { background: #f6f3ea; color: #2c2415; width: 420px; max-width: 100%; max-height: 90vh;
    overflow: auto; border-radius: 10px; border: 1px solid #cdc6b0; box-shadow: 0 12px 40px rgba(0,0,0,.3);
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }
  #fb-card h3 { margin: 0; padding: 12px 16px; font-size: 15px; color: #4a3f2a; background: #efe9d6;
    border-bottom: 1px solid #d8d2c0; border-radius: 10px 10px 0 0; }
  #fb-body { padding: 14px 16px; }
  #fb-ctx { font-size: 13px; color: #7a6f50; background: #efe9d6; border: 1px solid #e2dcc9;
    border-radius: 6px; padding: 7px 9px; margin-bottom: 12px; }
  #fb-body label { display: block; font-size: 12px; color: #5b5135; margin: 10px 0 3px; font-weight: 600; }
  #fb-body select, #fb-body input[type=text], #fb-body textarea { width: 100%; padding: 7px 8px;
    border: 1px solid #cdc6b0; border-radius: 6px; font-size: 14px; font-family: inherit; background: #fff; }
  #fb-body textarea { min-height: 70px; resize: vertical; }
  #fb-actions { display: flex; gap: 8px; margin-top: 16px; }
  #fb-actions button { flex: 1; padding: 9px; border-radius: 7px; font-size: 14px; cursor: pointer; }
  #fb-send { background: #c9a14a; color: #fff; border: 1px solid #c9a14a; font-weight: 600; }
  #fb-send:disabled { opacity: .55; cursor: default; }
  #fb-cancel { background: #fff; border: 1px solid #cdc6b0; color: #5b5135; }
  #fb-status { font-size: 13px; margin-top: 10px; min-height: 18px; }
  #fb-status.err { color: #b5651d; }
  #fb-status.ok { color: #3c7a2a; }
  .fb-hp { position: absolute; left: -9999px; }`;
  const s = document.createElement('style'); s.id = 'fb-css'; s.textContent = css;
  document.head.appendChild(s);
})();

// ctx: { num, chast, owners (string), owner_ids (string), type } — all optional
function openFeedbackModal(ctx) {
  ctx = ctx || {};
  let ov = document.getElementById('fb-overlay');
  if (!ov) {
    ov = document.createElement('div'); ov.id = 'fb-overlay';
    ov.innerHTML = `<div id="fb-card">
      <h3>Паведаміць пра памылку / прапанаваць праўку</h3>
      <div id="fb-body">
        <div id="fb-ctx"></div>
        <label>Тып</label>
        <select id="fb-type">
          <option value="транскрыпцыя">Транскрыпцыя (імя / чытанне)</option>
          <option value="нумар участка">Нумар участка / частка (не той уладальнік)</option>
          <option value="спасылка/крыніца">Спасылка / крыніца пра ўладальніка</option>
          <option value="герб">Герб (выява / назва)</option>
          <option value="іншае">Іншае</option>
        </select>
        <label>Ваша выпраўленне / каментар *</label>
        <textarea id="fb-text" placeholder="Апішыце, што не так і як павінна быць…"></textarea>
        <label>Крыніца / спасылка (неабавязкова)</label>
        <input id="fb-src" type="text" placeholder="URL, архіўны шыфр, выданне…">
        <label>Ваша імя (неабавязкова)</label>
        <input id="fb-name" type="text" placeholder="як вас згадаць у падзяках">
        <label>E-mail для адказу (неабавязкова)</label>
        <input id="fb-email" type="text" placeholder="калі хочаце атрымаць адказ">
        <input type="checkbox" name="botcheck" class="fb-hp" tabindex="-1" autocomplete="off">
        <div id="fb-status"></div>
        <div id="fb-actions">
          <button id="fb-cancel" type="button">Адмена</button>
          <button id="fb-send" type="button">Адправіць</button>
        </div>
      </div></div>`;
    document.body.appendChild(ov);
    ov.addEventListener('click', e => { if (e.target === ov) ov.classList.remove('open'); });
    ov.querySelector('#fb-cancel').onclick = () => ov.classList.remove('open');
    ov.querySelector('#fb-send').onclick = submitModal;
  }
  // reset + prefill
  const ctxBox = ov.querySelector('#fb-ctx');
  if (ctx.num != null) {
    ctxBox.style.display = '';
    ctxBox.textContent = `Участак № ${ctx.num}` + (ctx.chast ? `, частка ${ctx.chast}` : '') +
      (ctx.owners ? ` — ${ctx.owners}` : '');
  } else { ctxBox.style.display = 'none'; ctxBox.textContent = ''; }
  ov.querySelector('#fb-type').value = ctx.type || 'транскрыпцыя';
  ov.querySelector('#fb-text').value = '';
  ov.querySelector('#fb-src').value = '';
  const st = ov.querySelector('#fb-status'); st.textContent = ''; st.className = '';
  const send = ov.querySelector('#fb-send'); send.disabled = false; send.textContent = 'Адправіць';
  ov._ctx = ctx;
  ov.classList.add('open');
  ov.querySelector('#fb-text').focus();

  async function submitModal() {
    const text = ov.querySelector('#fb-text').value.trim();
    const st = ov.querySelector('#fb-status');
    if (!text) { st.className = 'err'; st.textContent = 'Калі ласка, апішыце праўку.'; return; }
    if (ov.querySelector('[name=botcheck]').checked) { ov.classList.remove('open'); return; }
    const c = ov._ctx || {};
    const type = ov.querySelector('#fb-type').value;
    send.disabled = true; send.textContent = 'Адпраўка…';
    st.className = ''; st.textContent = '';
    const res = await sendFeedback({
      subject: `Карта 1800: ${type}` + (c.num != null ? ` — участак ${c.num}${c.chast ? '/' + c.chast : ''}` : ''),
      Тып: type,
      Участак: c.num != null ? String(c.num) : '—',
      Частка: c.chast != null ? String(c.chast) : '—',
      Уладальнікі: c.owners || '—',
      owner_ids: c.owner_ids || '',
      Праўка: text,
      Крыніца: ov.querySelector('#fb-src').value.trim() || '—',
      Імя: ov.querySelector('#fb-name').value.trim() || '—',
      Email_для_адказу: ov.querySelector('#fb-email').value.trim() || '—',
    });
    if (res.ok) {
      st.className = 'ok'; st.textContent = 'Дзякуй! Водгук адпраўлены.';
      send.textContent = 'Адпраўлена ✓';
      setTimeout(() => ov.classList.remove('open'), 1400);
    } else if (res.error === 'no-key') {
      st.className = 'err';
      st.textContent = 'Форма яшчэ не наладжана (няма ключа Web3Forms). Паведаміце адміністратару.';
      send.disabled = false; send.textContent = 'Адправіць';
    } else {
      st.className = 'err'; st.textContent = 'Не ўдалося адправіць: ' + res.error;
      send.disabled = false; send.textContent = 'Адправіць';
    }
  }
}
