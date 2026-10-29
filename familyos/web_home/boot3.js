/* how it works: every beat hangs off one 18-second timeline; reduced motion keeps the resting frame the CSS draws */
(function () {
  var stage = document.getElementById('how-stage'), frame = document.getElementById('how-frame');
  var playBtn = document.getElementById('how-play'), replayBtn = document.getElementById('how-replay');
  if (!stage || !frame) return;
  var T = 18, END = 17.3, EASE = 'cubic-bezier(.3,.7,.2,1)', anims = [], userPaused = false, inView = false, port = null;
  var still = !stage.animate || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function q(s, r) { return (r || stage).querySelector(s); }
  function qa(s, r) { return Array.prototype.slice.call((r || stage).querySelectorAll(s)); }
  function pos(el) { var x = 0, y = 0, e = el; while (e && e !== stage) { x += e.offsetLeft; y += e.offsetTop; e = e.offsetParent; } return { x: x, y: y, w: el.offsetWidth, h: el.offsetHeight, cx: x + el.offsetWidth / 2, cy: y + el.offsetHeight / 2 }; }
  function tf(x, y, r, s) { return 'translate(' + x + 'px,' + y + 'px) rotate(' + r + 'deg) scale(' + s + ')'; }
  function mv(x, y, s) { return 'translate(' + x + 'px,' + y + 'px) scale(' + s + ')'; }
  function fade(o, y) { return { opacity: o, transform: 'translateY(' + y + 'px)' }; }
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
  var srcs = 'abcde'.split('').map(function (c) { return q('.s-' + c); });
  var pairs = [[0, '.r1'], [2, '.r2'], [3, '.r3'], [4, '.r4'], [1, '.need']];
  function threads() {
    qa('.th').forEach(function (s) { s.remove(); });
    var W = stage.offsetWidth, H = stage.offsetHeight, NS = 'http://www.w3.org/2000/svg';
    return pairs.map(function (p, j) {
      var m = pos(q('mark', srcs[p[0]])), t = pos(q(p[1])), d, x1, y1, x2, y2;
      if (port) { x1 = m.cx; y1 = m.y + m.h; x2 = t.cx; y2 = t.y; d = 'M' + x1 + ' ' + y1 + 'C' + x1 + ' ' + (y1 + 90) + ' ' + x2 + ' ' + (y2 - 160) + ' ' + x2 + ' ' + y2; }
      else { x1 = m.x + m.w + 3; y1 = m.cy; x2 = t.x; y2 = t.cy; d = 'M' + x1 + ' ' + y1 + 'C' + (x1 + 90) + ' ' + y1 + ' ' + (x2 - 140) + ' ' + y2 + ' ' + x2 + ' ' + y2; }
      var svg = document.createElementNS(NS, 'svg');
      svg.setAttribute('class', 'th' + (j ? (j === 4 ? ' t-n' : '') : ' t-a')); svg.setAttribute('width', W); svg.setAttribute('height', H); svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
      svg.innerHTML = '<path class="gl" d="' + d + '"/><path d="' + d + '"/><circle r="2.5" cx="' + x1 + '" cy="' + y1 + '"/>';
      stage.insertBefore(svg, q('.how-board'));
      svg.clip0 = port ? 'inset(0px 0px ' + (H - y1 + 4) + 'px 0px)' : 'inset(0px ' + (W - x1 + 4) + 'px 0px 0px)';
      return svg;
    });
  }
  function build() {
    var t = anims.length ? anims[0].currentTime : 0;
    anims.forEach(function (a) { a.cancel(); }); anims = [];
    port = frame.clientWidth < 700; stage.classList.toggle('port', port); fit();
    var th = threads();
    if (still) return;
    var chaos = port ? [[136, 12, 6], [-174, 64, -5], [210, 112, 7], [-212, 154, -6], [166, 234, 5]] : [[40, 10, -7], [430, 268, 6], [352, -150, 8], [520, -212, -6], [250, 62, 5]];
    var rest = [-3, 2.5, -2.5, 3, -1.5], range = port ? stage.offsetWidth : 480;
    /* 0 to 4s, the problem: notices drift in from five places; where each one lives, and what it cost */
    srcs.forEach(function (el, i) {
      var c = chaos[i], a = .15 + i * .3, k = [[0, { opacity: 0, transform: tf(c[0] - 30, c[1] + 24, c[2] * 1.6, .96) }], [a, {}], [a + .9, { opacity: 1, transform: tf(c[0], c[1], c[2], 1) }, 'ease-in-out'],
        [4, { transform: tf(c[0] + 8, c[1] - 6, c[2] + 1, 1) }], [4.8, { transform: tf(0, 0, rest[i], 1) }], [5 + i * .12, {}], [5.5 + i * .12, { transform: tf(0, 0, 0, 1) }], [8.4, {}], [8.9, { opacity: .72 }]];
      if (!i) k.push([12.9, {}], [13.2, { opacity: 1 }]);
      track(el, k, true);
      var tags = qa('.tag', el);
      track(tags[0], tags[1] ? [[0, { opacity: 1 }], [2.3, {}], [2.6, { opacity: 0 }]] : [[0, { opacity: 1 }], [3.9, {}], [4.3, { opacity: 0 }]]);
      if (tags[1]) track(tags[1], [[0, { opacity: 0 }], [2.4, {}], [2.8, { opacity: 1 }], [3.9, {}], [4.3, { opacity: 0 }]]);
      var m = pos(q('mark', el)), tm = 4.6 + 1.3 * m.x / (range + 140);
      track(q('mark i', el), [[0, { transform: 'scaleX(0)', opacity: 1 }], [tm, {}], [tm + .35, { transform: 'scaleX(1)' }]], true);
    });
    track(q('.cap'), [[0, fade(0, 8)], [.6, {}], [1.2, fade(1, 0)], [3.8, {}], [4.2, fade(0, -6)]]);
    track(q('.ppl'), [[0, fade(0, 10)], [1.6, {}], [2.2, fade(1, 0)], [3.9, {}], [4.3, fade(0, -8)]]);
    /* 4 to 6s, the board arrives and a soft light reads each notice */
    track(q('.how-board'), [[0, { opacity: 0, transform: 'translateY(14px) scale(.97)' }], [4.2, {}], [5, { opacity: 1, transform: 'translateY(0px) scale(1)' }]], true);
    track(q('.scan'), [[4.6, { transform: 'translateX(-140px)' }, 'linear'], [5.9, { transform: 'translateX(' + range + 'px)' }]]);
    track(q('.scan'), [[4.5, { opacity: 0 }], [4.75, { opacity: 1 }], [5.6, {}], [5.95, { opacity: 0 }]]);
    /* 6 to 8.3s, each finding lifts off its page and lands on the board, with a thread back to the source */
    pairs.forEach(function (p, j) {
      var m = pos(q('mark', srcs[p[0]])), el = q(p[1]), r = pos(el), f = j < 4 ? 6 + j * .45 : 8.3, from = mv(m.cx - r.cx, m.cy - r.cy, .5);
      var k = [[0, { opacity: 0, transform: from }], [f, {}], [f + .15, { opacity: 1 }], [f + .9, { transform: mv(0, 0, 1) }]];
      if (j < 4) track(el, k, true); else track(el, k.concat([[10.95, {}], [11.25, { opacity: 0, transform: mv(0, -10, .97) }]]));
      var tk = [[0, { opacity: 0, clipPath: th[j].clip0 }], [f + .35, {}], [f + .4, { opacity: 1 }], [f + 1.1, { clipPath: 'inset(0px 0px 0px 0px)' }], [j < 4 ? 8.6 : 10.4, {}], [j < 4 ? 9.1 : 11, { opacity: j < 4 ? .45 : 0 }]];
      if (!j) tk.push([12.9, {}], [13.2, { opacity: 1 }]);
      track(th[j], tk, j < 4);
    });
    /* 8.3 to 11s, the one that needs a person: a tap on Accept, and Friday lights up */
    var y = pos(q('.yes')), sx = y.cx + 110, sy = y.cy + 70;
    track(q('.l-need'), [[0, { opacity: 0 }], [8.3, {}], [8.6, { opacity: 1 }], [10.9, {}], [11.2, { opacity: 0 }]]);
    track(q('.touch'), [[0, { opacity: 0, transform: mv(sx, sy, 1) }], [9.15, {}], [9.4, { opacity: 1 }], [9.95, { transform: mv(y.cx, y.cy, 1) }], [10.1, { transform: mv(y.cx, y.cy, .8) }], [10.3, { transform: mv(y.cx, y.cy, 1) }], [10.6, {}], [10.9, { opacity: 0 }]]);
    track(q('.tap'), [[0, { opacity: 0, transform: mv(y.cx, y.cy, .5) }], [10.05, {}], [10.12, { opacity: .9 }], [10.6, { opacity: 0, transform: mv(y.cx, y.cy, 2.4) }]]);
    track(q('.yes i'), [[0, { opacity: 0 }], [10.1, {}], [10.3, { opacity: 1 }]]);
    track(q('.wk i'), [[0, { opacity: 0, transform: 'scale(1)' }], [10.3, {}], [10.5, { opacity: 1, transform: 'scale(1.18)' }], [10.85, { transform: 'scale(1)' }]], true);
    /* 11 to 14s, ask: the answer carries a number, and its source lights up */
    track(q('.l-ask'), [[0, { opacity: 0 }], [11.1, {}], [11.4, { opacity: 1 }]], true);
    track(q('.ask .q'), [[0, fade(0, 10)], [11.3, {}], [11.65, fade(1, 0)]], true);
    track(q('.ask .ty'), [[0, { opacity: 0 }], [11.8, {}], [11.95, { opacity: 1 }], [12.5, {}], [12.6, { opacity: 0 }]]);
    track(q('.ask .a'), [[0, fade(0, 8)], [12.55, {}], [12.9, fade(1, 0)]], true);
    [q('.ask sup'), q('.r1 sup')].forEach(function (s) { track(s, [[0, { transform: 'scale(1)' }], [13, {}], [13.25, { transform: 'scale(1.7)' }], [13.6, { transform: 'scale(1)' }]]); });
    track(q('.ring'), [[0, { opacity: 0 }], [13, {}], [13.3, { opacity: 1 }]], true);
    /* 14s on, the promise; then everything lets go and the week starts again */
    track(q('.promise'), [[0, fade(0, 6)], [13.9, {}], [14.4, fade(1, 0)]], true);
    var steps = [[0, 4], [4, 5.9], [5.9, 8.3], [8.3, 11.1], [11.1, 13.9]];
    qa('#how-steps li', document).forEach(function (li, i) {
      var s = steps[i][0] || .001, e = steps[i][1];
      track(q('em', li), [[0, { transform: 'scaleX(0)', opacity: 1 }], [s, {}, 'linear'], [e, { transform: 'scaleX(1)' }]], true);
      track(q('.n i', li), [[0, { opacity: 0 }], [s, {}], [s + .2, { opacity: 1 }], [e, {}], [e + .2, { opacity: 0 }]]);
    });
    anims.forEach(function (a) { a.currentTime = t; });
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
