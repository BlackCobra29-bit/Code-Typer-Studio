(() => {
  'use strict';
  const options = JSON.parse(document.getElementById('typingOptions').textContent);
  const { timeline } = options;
  const stage = document.getElementById('stage');
  const editor = document.getElementById('editorWindow');
  const root = document.getElementById('codeContent');
  const viewport = document.getElementById('viewport');
  const cursor = document.getElementById('cursor');
  const playButton = document.getElementById('playPause');
  const scrubber = document.getElementById('scrubber');
  const lines = [...root.querySelectorAll('.code-line')];
  const glyphs = [...root.querySelectorAll('.glyph')];
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let positions = [], scrollKeys = [], playing = false, elapsed = 0, lastStamp = null, raf = 0;
  let fontSize = options.fontSize || 26;
  let lastCount = -1, lastLine = -1, lastReported = -1;
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const ease = t => 1 - Math.pow(1 - clamp(t), 4);
  const smoothstep = t => { t = clamp(t); return t*t*t*(t*(t*6-15)+10); };
  function upperBound(items, time) {
    let lo = 0, hi = items.length;
    while (lo < hi) { const mid = (lo + hi) >>> 1; if (items[mid].at <= time) lo = mid + 1; else hi = mid; }
    return lo;
  }
  function fit() {
    const controls = document.body.classList.contains('embedded') || document.body.classList.contains('flush-frame') ? 0 : 46;
    const scale = Math.min(innerWidth / options.width, (innerHeight - controls) / options.height);
    stage.style.transform = `translate(${(innerWidth-options.width*scale)/2}px,${(innerHeight-controls-options.height*scale)/2}px) scale(${scale})`;
  }
  function measure() {
    // Measure once, in untransformed stage coordinates; playback never reflows code.
    const saved = stage.style.transform;
    stage.style.transform = 'none';
    editor.style.transform = 'none';
    viewport.scrollTop = viewport.scrollLeft = 0;
    const bounds = viewport.getBoundingClientRect();
    const lineHeight = parseFloat(getComputedStyle(root).lineHeight);
    fontSize = parseFloat(getComputedStyle(root).fontSize);
    const lineStart = lines.map(line => {
      const box = line.querySelector('.line-content').getBoundingClientRect();
      return { x: box.left - bounds.left + 16, y: box.top - bounds.top + (lineHeight - fontSize)/2, line: Number(line.dataset.line) };
    });
    positions = [lineStart[0]];
    const map = new Map(glyphs.map(glyph => [Number(glyph.dataset.index), glyph]));
    timeline.chars.forEach((char, index) => {
      if (char.text === '\n') positions[index + 1] = lineStart[char.line + 1];
      else {
        const box = map.get(index).getBoundingClientRect();
        positions[index + 1] = { x: box.right - bounds.left, y: lineStart[char.line].y, line: char.line };
      }
    });
    scrollKeys = [];
    let targetX = 0, targetY = 0;
    for (const event of timeline.events) {
      const p = positions[event.count];
      const y = clamp(p.y - viewport.clientHeight + lineHeight * 2.5, 0, Math.max(0, root.scrollHeight-viewport.clientHeight));
      const x = clamp(p.x - viewport.clientWidth + 60, 0, Math.max(0, root.scrollWidth-viewport.clientWidth));
      if (y !== targetY || x !== targetX) {
        const previous = scrollAt(event.at);
        scrollKeys.push({ at: event.at, fromX: previous.x, fromY: previous.y, x, y });
        targetX = x; targetY = y;
      }
    }
    stage.style.transform = saved;
    draw(elapsed);
  }
  function scrollAt(time) {
    const key = scrollKeys[upperBound(scrollKeys, time)-1];
    if (!key) return { x: 0, y: 0 };
    const t = reducedMotion ? 1 : smoothstep((time-key.at)/260);
    return { x: key.fromX + (key.x-key.fromX)*t, y: key.fromY + (key.y-key.fromY)*t };
  }
  function draw(time) {
    elapsed = clamp(time, 0, timeline.duration);
    const eventIndex = upperBound(timeline.events, elapsed)-1;
    const event = timeline.events[eventIndex];
    const count = event?.count || 0;
    for (const glyph of glyphs) {
      const char = timeline.chars[Number(glyph.dataset.index)];
      const progress = elapsed < char.at ? 0 : reducedMotion ? 1 : ease((elapsed-char.at)/timeline.fadeMs);
      const opacity = progress.toFixed(4);
      const transform = `translate3d(0,${((1-progress)*3.5).toFixed(3)}px,0) scale(${(.985+progress*.015).toFixed(4)})`;
      if (glyph.style.opacity !== opacity) glyph.style.opacity = opacity;
      if (glyph.style.transform !== transform) glyph.style.transform = transform;
    }
    const p = positions[count] || positions[0];
    if (p) {
      if (lastLine !== p.line) {
        lines[lastLine]?.classList.remove('active'); lines[p.line]?.classList.add('active'); lastLine = p.line;
      }
      const before = positions[eventIndex > 0 ? timeline.events[eventIndex-1].count : 0] || p;
      const age = elapsed - (event?.at || 0);
      const next = timeline.events[eventIndex+1];
      const available = event && next ? Math.max(16, next.at-event.at) : (timeline.cursorEaseMs || 70);
      const travel = Math.min(timeline.cursorEaseMs || 70, available);
      // Finish each move before the following key so rapid typing stays continuous.
      const t = !reducedMotion && before.line === p.line ? smoothstep(age / travel) : 1;
      const x = before.x + (p.x-before.x)*t;
      const y = p.y + (editor.classList.contains('cursor-underline') ? fontSize : 0);
      cursor.style.transform = `translate3d(${x}px,${y}px,0)`;
      const blink = age < 350 || Math.floor((age-350)/500)%2 === 0;
      const lineReveal = !reducedMotion && before.line !== p.line ? ease(age/90) : 1;
      const cursorOpacity = options.cursor === 'block' ? .55 : 1;
      cursor.style.opacity = elapsed >= timeline.typingEnd + 1100 || !blink ? '0' : String(cursorOpacity*lineReveal);
    }
    const scroll = scrollAt(elapsed);
    viewport.scrollLeft = scroll.x; viewport.scrollTop = scroll.y;
    const entrance = reducedMotion ? 1 : smoothstep(elapsed / Math.max(1, Math.min(650, options.startDelayMs || 1)));
    editor.style.transform = `translate3d(0,${(1-entrance)*14}px,0) scale(${.992+entrance*.008})`;
    editor.style.opacity = String(.76 + entrance*.24);
    scrubber.value = String(elapsed/timeline.duration*1000);
    document.getElementById('timecode').textContent = `${(elapsed/1000).toFixed(1)} / ${(timeline.duration/1000).toFixed(1)}s`;
    root.dataset.visibleCount = count; root.dataset.time = elapsed.toFixed(1);
    if (count !== lastCount || Math.abs(elapsed-lastReported)>80) { report(); lastReported = elapsed; }
    lastCount = count;
  }
  function report() {
    playButton.textContent = playing ? 'Pause' : 'Play';
    if (parent !== window) parent.postMessage({ type: 'typing:state', playing, time: elapsed, duration: timeline.duration, language: options.language, theme: options.theme }, '*');
  }
  function tick(stamp) {
    if (!playing) return;
    if (lastStamp !== null) elapsed += stamp-lastStamp;
    lastStamp = stamp;
    if (elapsed >= timeline.duration) {
      if (options.loop) elapsed %= timeline.duration;
      else { draw(timeline.duration); pause(); return; }
    }
    draw(elapsed); raf = requestAnimationFrame(tick);
  }
  function play() {
    if (playing) return;
    if (elapsed >= timeline.duration) elapsed = 0;
    playing = true; lastStamp = null; raf = requestAnimationFrame(tick); report();
  }
  function pause() { playing = false; cancelAnimationFrame(raf); lastStamp = null; report(); }
  function seek(time) { pause(); draw(time); report(); }
  function restart() { pause(); draw(0); play(); }
  playButton.addEventListener('click', () => playing ? pause() : play());
  document.getElementById('restart').addEventListener('click', restart);
  scrubber.addEventListener('input', () => seek(Number(scrubber.value)/1000*timeline.duration));
  window.addEventListener('message', event => {
    if (event.source !== parent || event.data?.type !== 'typing:command') return;
    if (event.data.action === 'toggle') playing ? pause() : play();
    if (event.data.action === 'restart') restart();
    if (event.data.action === 'seek' && Number.isFinite(Number(event.data.progress))) seek(Number(event.data.progress)*timeline.duration);
  });
  document.addEventListener('visibilitychange', () => { lastStamp = null; });
  window.addEventListener('resize', fit);
  // A public seek interface also makes exported HTML usable by capture pipelines.
  window.codeTyping = Object.freeze({ play, pause, restart, seek, duration: timeline.duration });
  document.fonts.ready.then(() => {
    fit(); measure();
    if (options.autoplay && !reducedMotion) play(); else { draw(reducedMotion ? timeline.duration : 0); report(); }
  });
})();
