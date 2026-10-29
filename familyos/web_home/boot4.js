/* your family holds the key: one 18-second timeline in the shape of how it works; the sealed box beat is marked coming next; reduced motion keeps the resting frame the CSS draws */
(function () {
  var stage = document.getElementById('key-stage'), frame = document.getElementById('key-frame');
  var playBtn = document.getElementById('key-play'), replayBtn = document.getElementById('key-replay');
  if (!stage || !frame) return;
  var T = 18, END = 17.3, EASE = 'cubic-bezier(.3,.7,.2,1)', anims = [], userPaused = false, inView = false, port = null;
  var still = !stage.animate || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function q(s, r) { return (r || stage).querySelector(s); }
  function qa(s, r) { return Array.prototype.slice.call((r || stage).querySelectorAll(s)); }
  function pos(el) { var x = 0, y = 0, e = el; while (e && e !== stage) { x += e.offsetLeft; y += e.offsetTop; e = e.offsetParent; } return { x: x, y: y, w: el.offsetWidth, h: el.offsetHeight, cx: x + el.offsetWidth / 2, cy: y + el.offsetHeight / 2 }; }
  function mv(x, y, s, r) { return 'translate(' + x + 'px,' + y + 'px) rotate(' + (r || 0) + 'deg) scale(' + s + ')'; }
  function fade(o, y) { return { opacity: o, transform: 'translateY(' + y + 'px)' }; }
  function on(a, b) { return [[0, { opacity: 0 }], [a, {}], [a + .2, { opacity: 1 }], [b, {}], [b + .2, { opacity: 0 }]]; }
  /* keys: [seconds, props, easing]; props carry forward, so each key names only what changes */
  function track(el, keys, tail) {
    if (!el) return;
    if (tail) keys = keys.concat([[END, {}], [T, { opacity: 0 }]]);
    var first = {}, cur;
    keys.forEach(function (k) { for (var p in k[1]) if (!(p in first)) first[p] = k[1][p]; });
    cur = first;
    var fr = keys.map(function (k) { cur = Object.assign({}, cur, k[1]); return Object.assign({ offset: k[0] / T, easing: k[2] || EASE }, cur); });
    if (fr[0].offset > 0) fr.unshift(Object.assign({}, fr[0], { offset: 0 }));
    if (fr[fr.length - 1].offset < 1) fr.push(Object.assign({}, fr[fr.length - 1], { offset: 1 }));
    anims.push(el.animate(fr, { duration: T * 1000, iterations: Infinity, fill: 'both' }));
  }
  function fit() {
    var w = frame.clientWidth, k = Math.min(1, w / stage.offsetWidth);
    stage.style.transform = 'scale(' + k + ')'; stage.style.left = ((w - stage.offsetWidth * k) / 2) + 'px';
    frame.style.height = (stage.offsetHeight * k) + 'px';
  }
  function build() {
    var t = anims.length ? anims[0].currentTime : 0;
    anims.forEach(function (a) { a.cancel(); }); anims = [];
    port = frame.clientWidth < 700; stage.classList.toggle('kp', port); fit();
    qa('.k-fly').forEach(function (f) { f.remove(); });
    if (still) return;
    var key = q('.k-key'), kc = pos(key), srv = pos(q('.k-srv')), lk = pos(q('.k-lock')), docs = qa('.k-doc'), w = qa('.k-w'), dots = qa('.k-badge s');
    var seal = [.9, 1.3, 1.7, 2.1], rot = [-4, 3, -2.5, 3.5], cl = qa('.k-cl span'), pl = qa('.k-pl span'), shk = q('.k-shk');
    /* 0 to 3.2s, live: the family's papers, sealed one by one under the glowing key, then put away on the server */
    track(q('.k-srv'), [[0, fade(0, 10)], [.1, {}], [.6, fade(1, 0)]], true);
    qa('.k-p').forEach(function (p, i) { track(p, [[0, fade(0, 10)], [.3 + i * .15, {}], [.8 + i * .15, fade(1, 0)]], true); });
    var kk = [[0, { opacity: 0, transform: mv(0, 10, .6) }], [.2, {}], [.6, { opacity: 1, transform: mv(0, 0, 1) }]];
    docs.forEach(function (d, i) {
      var p = pos(d), s = seal[i];
      kk.push([s - .3, { transform: mv(p.x + p.w - 34 - kc.cx, p.cy - kc.cy, .6) }], [s + .05, {}]);
      track(d, [[0, { opacity: 0, transform: mv(-20, 18, .96, rot[i] * 1.5) }], [.1 + i * .15, {}], [.6 + i * .15, { opacity: 1, transform: mv(0, 0, 1, rot[i]) }],
        [2.4 + i * .1, {}], [3 + i * .1, { opacity: 0, transform: mv(srv.cx - p.cx, srv.cy - p.cy, .3) }]]);
      track(q('.k-ct', d), [[0, { opacity: 0 }], [s - .05, {}], [s + .2, { opacity: 1 }]]);
    });
    kk.push([2.8, { transform: mv(0, 0, 1) }], [3.5, {}], [3.9, { opacity: 0, transform: mv(0, 0, 1.3) }]);
    track(key, kk);
    var hk = [[0, { opacity: .35 }]];
    seal.forEach(function (s) { hk.push([s - .05, {}], [s + .1, { opacity: 1 }], [s + .35, { opacity: .35 }]); });
    track(q('.k-halo'), hk);
    cl.forEach(function (c, j) { track(c, [[0, { opacity: 0 }], [2.9 + j * .08, {}], [3.1 + j * .08, { opacity: 1 }], [7.95, {}], [8.25, { opacity: 0 }], [9.95, {}], [10.25, { opacity: 1 }], [14.3, {}], [14.6, { opacity: 0 }], [15.3, {}], [15.6, { opacity: 1 }]], true); });
    track(q('.k-lock'), [[0, { opacity: 0, transform: 'scale(.8)' }], [3, {}], [3.3, { opacity: 1, transform: 'scale(1)' }], [5.1, {}], [5.4, { transform: 'scale(1.14)' }], [5.8, { transform: 'scale(1)' }]], true);
    track(shk, [[0, { transform: 'translateY(-7px)' }], [3.3, {}], [3.5, { transform: 'translateY(0px)' }], [7.9, {}], [8.15, { transform: 'translateY(-7px)' }], [9.95, {}], [10.2, { transform: 'translateY(0px)' }], [14.3, {}], [14.55, { transform: 'translateY(-7px)' }], [15.3, {}], [15.55, { transform: 'translateY(0px)' }]]);
    track(q('.s-l'), [[0, { opacity: 0 }], [3.4, {}], [3.6, { opacity: 1 }], [7.85, {}], [8, { opacity: 0 }], [10.1, {}], [10.3, { opacity: 1 }], [14.25, {}], [14.4, { opacity: 0 }], [15.4, {}], [15.6, { opacity: 1 }]], true);
    /* 3.2 to 4.8s, live: the key becomes three word shares, one for each adult */
    w.forEach(function (s, i) { var p = pos(s); track(s, [[0, { opacity: 0, transform: mv(kc.cx - p.cx, kc.cy - p.cy, .5) }], [3.7 + i * .12, {}], [3.85 + i * .12, { opacity: 1 }], [4.4 + i * .12, { transform: mv(0, 0, 1) }]], true); });
    /* 4.8 to 6s, live: without two shares, FamilyOS can't open it */
    track(q('.c1'), [[0, fade(0, 8)], [4.8, {}], [5.2, fade(1, 0)], [7.6, {}], [7.9, fade(0, -6)]]);
    /* 6 to 10.4s, live: two people tap their words, the shares meet at the lock, and it opens for a few hours */
    var a = pos(w[0]), b = pos(w[2]);
    track(q('.touch'), [[0, { opacity: 0, transform: mv(a.cx + 90, a.cy + 70, 1) }], [6, {}], [6.2, { opacity: 1 }], [6.5, { transform: mv(a.cx, a.cy, 1) }], [6.6, { transform: mv(a.cx, a.cy, .8) }], [6.75, { transform: mv(a.cx, a.cy, 1) }],
      [7.1, { transform: mv(b.cx, b.cy, 1) }], [7.2, { transform: mv(b.cx, b.cy, .8) }], [7.35, { transform: mv(b.cx, b.cy, 1) }], [7.5, {}], [7.7, { opacity: 0 }]]);
    qa('.tap').forEach(function (el, i) { var p = i ? b : a, s = i ? 7.18 : 6.58; track(el, [[0, { opacity: 0, transform: mv(p.cx, p.cy, .5) }], [s, {}], [s + .07, { opacity: .9 }], [s + .5, { opacity: 0, transform: mv(p.cx, p.cy, 2.4) }]]); });
    /* the ghosts carry a share to the lock: twice now, and twice again in the coming-next act */
    [[0, 6.65], [2, 7.25], [0, 13.4], [2, 13.65]].forEach(function (g) {
      var src = w[g[0]], p = pos(src), c = src.cloneNode(true);
      c.className = 'k-w k-fly'; c.style.left = p.x + 'px'; c.style.top = p.y + 'px'; c.style.width = p.w + 'px'; stage.appendChild(c);
      track(c, [[0, { opacity: 0, transform: mv(0, 0, 1) }], [g[1], {}], [g[1] + .1, { opacity: 1 }], [g[1] + .55, { transform: mv(lk.cx - p.cx, lk.cy - p.cy, .3) }], [g[1] + .65, { opacity: 0 }]]);
    });
    dots.forEach(function (d, i) { var s = i ? 7.85 : 7.25, s2 = i ? 14.25 : 14; track(d, [[0, { opacity: 0, transform: 'scale(.4)' }], [s, {}], [s + .15, { opacity: 1, transform: 'scale(1)' }], [9.95, {}], [10.25, { opacity: 0, transform: 'scale(.4)' }], [s2, {}], [s2 + .15, { opacity: 1, transform: 'scale(1)' }], [15.3, {}], [15.6, { opacity: 0, transform: 'scale(.4)' }]]); });
    track(q('.s-o'), on(8, 9.85));
    track(q('.k-clock i'), [[0, { transform: 'rotate(0deg)' }], [8.15, {}, 'linear'], [9.85, { transform: 'rotate(360deg)' }]]);
    pl.forEach(function (p, j) { track(p, [[0, fade(0, 4)], [8.05 + j * .1, {}], [8.35 + j * .1, fade(1, 0)], [9.9, {}], [10.15, fade(0, 0)], [14.4 + j * .1, {}], [14.7 + j * .1, fade(1, 0)], [15.3, {}], [15.55, fade(0, 0)]]); });
    track(q('.how-board'), [[0, { opacity: 0, transform: 'translateY(14px) scale(.97)' }], [8, {}], [8.5, { opacity: 1, transform: 'translateY(0px) scale(1)' }], [9.95, {}], [10.35, { opacity: 0, transform: 'translateY(-8px) scale(.98)' }]]);
    qa('.rows > div', q('.how-board')).forEach(function (r, j) { track(r, [[0, fade(0, 8)], [8.3 + j * .12, {}], [8.65 + j * .12, fade(1, 0)]]); });
    /* 10.4 to 15.6s, coming next: the server inside a sealed box the phone checks, files sealed on the phone, the key turning only inside */
    track(q('.c2'), [[0, fade(0, 8)], [10.4, {}], [10.8, fade(1, 0)]], true);
    track(q('.k-box'), [[0, { opacity: 0, transform: 'scale(1.05)' }], [10.6, {}], [11.1, { opacity: 1, transform: 'scale(1)' }]], true);
    track(q('.k-phone'), [[0, fade(0, 14)], [11, {}], [11.5, fade(1, 0)]], true);
    qa('.k-chk i').forEach(function (c, i) { track(c, [[0, { opacity: 0, transform: 'scale(.5)' }], [11.8 + i * .4, {}], [12 + i * .4, { opacity: 1, transform: 'scale(1)' }]]); });
    var nw = q('.k-new'), np = pos(nw);
    track(q('.k-ct', nw), [[0, { opacity: 0 }], [12.6, {}], [12.8, { opacity: 1 }]]);
    track(nw, [[0, { opacity: 1, transform: mv(0, 0, 1) }], [12.95, {}], [13.5, { opacity: 0, transform: mv(srv.cx - np.cx, srv.cy - np.cy, .3) }]]);
    track(q('.k-op'), [[0, fade(0, 6)], [13, {}], [13.4, fade(1, 0)]], true);
    track(q('.s-i'), on(14.4, 15.25));
    /* the promise, then everything lets go and the papers come back */
    track(q('.k-prom'), [[0, fade(0, 6)], [15.6, {}], [16, fade(1, 0)]], true);
    var steps = [[0, 3.2], [3.2, 4.8], [4.8, 6], [6, 10.4], [10.4, 12.6], [12.6, 15.6]];
    qa('#key-steps li', document).forEach(function (li, i) {
      var s = steps[i][0] || .001, e = steps[i][1];
      track(q('em', li), [[0, { transform: 'scaleX(0)', opacity: 1 }], [s, {}, 'linear'], [e, { transform: 'scaleX(1)' }]], true);
      track(q('.n i', li), [[0, { opacity: 0 }], [s, {}], [s + .2, { opacity: 1 }], [e, {}], [e + .2, { opacity: 0 }]]);
    });
    anims.forEach(function (x) { x.currentTime = t; });
    sync();
  }
  function sync() {
    var run = !userPaused && inView;
    anims.forEach(function (a) { if (run) a.play(); else a.pause(); });
    playBtn.setAttribute('data-paused', String(userPaused));
    playBtn.setAttribute('aria-label', userPaused ? 'Play the animation' : 'Pause the animation');
  }
  build();
  if (still) return;
  playBtn.addEventListener('click', function () { userPaused = !userPaused; sync(); });
  replayBtn.addEventListener('click', function () { anims.forEach(function (a) { a.currentTime = 0; }); userPaused = false; sync(); });
  if ('IntersectionObserver' in window) new IntersectionObserver(function (es) { inView = es[0].isIntersecting; sync(); }, { threshold: .2 }).observe(frame);
  else { inView = true; sync(); }
  window.addEventListener('resize', function () { if ((frame.clientWidth < 700) !== port) build(); else fit(); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(build);
})();
