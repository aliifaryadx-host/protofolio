/* ===== APP: render data, navigasi + transisi, keyboard, jam ===== */
(function () {
  const D = window.P5_DATA, A = window.P5Audio, FX = window.P5FX;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const body = document.body, wipe = $('#wipe'), intro = $('#intro');
  let current = 'hero', busy = false, started = false;

  /* ---------- Render konten dari data.js ---------- */
  function renderProjects() {
    $('#projects-grid').innerHTML = D.projects.map(p => `
      <article class="card tilt" data-reveal>
        <div class="card-in">
          <figure class="frame" data-slot="assets/images/${p.img}">
            <img src="assets/images/${p.img}" alt="Cuplikan ${p.title}" loading="lazy" onerror="this.parentNode.classList.add('no-img')">
            <span class="chip">${p.tag}</span>
          </figure>
          <h3>${p.title}</h3>
          <p>${p.desc}</p>
          <div class="card-foot">
            <span class="status">${p.status}</span><span class="year">${p.year}</span>
            <a class="btn-sm press" href="${p.link}" ${p.link !== '#' ? 'target="_blank" rel="noopener"' : ''}>${p.cta}</a>
          </div>
        </div>
      </article>`).join('');
  }

  function renderSkills() {
    $('#skills-grid').innerHTML = D.skills.map(g => `
      <div class="skill-box" data-reveal>
        <h3>${g.title}</h3>
        <div class="skill-list">${g.items.map(([n, v]) => `
          <div><div class="skill-row"><span>${n}</span><em>${v}%</em></div>
          <div class="bar"><i style="--w:${v}%"></i></div></div>`).join('')}
        </div>
      </div>`).join('');
  }

  /* ---------- Navigasi ---------- */
  function activate(name) {
    $$('.view').forEach(v => { v.classList.remove('active', 'enter'); });
    const v = $('#view-' + name);
    if (!v) return;
    v.classList.add('active');
    $$('[data-reveal]', v).forEach((el, i) => el.style.setProperty('--i', i));
    void v.offsetWidth;
    v.classList.add('enter');
    // lepas kelas "enter" setelah animasi selesai supaya efek tekan tombol bisa jalan lagi
    setTimeout(() => { if (current === name) v.classList.remove('enter'); }, 2200);
    window.scrollTo(0, 0);
    current = name;
  }

  // Jalankan transisi wipe; fn dipanggil saat layar tertutup penuh
  function transition(fn, after) {
    if (busy) return;
    busy = true;
    A.whoosh();
    wipe.classList.remove('run'); void wipe.offsetWidth; wipe.classList.add('run');
    setTimeout(fn, 560);
    setTimeout(() => { wipe.classList.remove('run'); busy = false; if (after) after(); }, 1020);
  }

  function go(name) {
    if (busy || name === current) return;
    A.select(); FX.shake(); FX.flash();
    transition(() => activate(name));
  }

  function start() {
    if (started || busy) return;
    started = true;
    A.start(); FX.shake(); FX.flash();
    intro.classList.add('leave');
    transition(() => {
      intro.hidden = true;
      body.classList.remove('is-intro');
      body.classList.add('booted');
      activate('hero');
      current = 'hero';
    });
  }

  /* ---------- Event ---------- */
  document.addEventListener('pointerdown', e => {
    A.unlock();
    const btn = e.target.closest('.press');
    if (!btn) return;
    FX.burst(e.clientX, e.clientY);
    FX.pop(btn);
  });

  document.addEventListener('click', e => {
    const a = e.target.closest('a[href="#"]');
    if (a) { e.preventDefault(); A.select(); return; }
    if (e.target.closest('#start-btn')) return start();
    const nav = e.target.closest('[data-go]');
    if (nav) return go(nav.dataset.go);
    const snd = e.target.closest('#sound-btn');
    if (snd) {
      const on = A.toggle();
      snd.setAttribute('aria-pressed', on);
      snd.textContent = on ? 'SFX ON' : 'SFX OFF';
      if (on) A.select();
    } else if (e.target.closest('a.press, .btn-sm')) A.select();
  });

  document.addEventListener('mouseover', e => {
    const t = e.target.closest('button, a.channel, .btn-sm');
    if (t && !t.contains(e.relatedTarget) && !t.matches('#start-btn')) A.hover();
  });

  /* Keyboard: ↑↓ pindah menu, ENTER pilih (native), ESC kembali */
  const menu = $$('#main-menu .menu-item');
  let idx = -1;
  menu.forEach((b, i) => b.addEventListener('focus', () => { idx = i; }));

  document.addEventListener('keydown', e => {
    if (!started) return;
    if (e.key === 'Escape') return go('hero');
    if (current !== 'hero' || busy) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const d = e.key === 'ArrowDown' ? 1 : -1;
      idx = (idx + d + menu.length) % menu.length;
      menu[idx].focus();
      A.hover();
    }
  });

  /* Jam real-time */
  function clock() {
    const n = new Date();
    $('#clock').textContent = String(n.getHours()).padStart(2, '0') + ':' + String(n.getMinutes()).padStart(2, '0');
  }

  /* ---------- Init ---------- */
  FX.buildRansom();
  FX.buildStars(16);
  FX.buildTickers(D.ticker);
  FX.typewriter($('#typer'), D.roles);
  FX.initTilt();
  renderProjects();
  renderSkills();
  clock(); setInterval(clock, 1000);
  $('#start-btn').focus({ preventScroll: true });
})();
