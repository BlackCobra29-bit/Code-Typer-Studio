function initHeroCodeField(surface) {
  const canvas = surface.querySelector('[data-code-field]');
  const hero = canvas?.closest('.home-hero');
  if (!canvas || !hero || canvas.dataset.codeFieldInitialized === 'true') return;
  canvas.dataset.codeFieldInitialized = 'true';

  const context = canvas.getContext('2d');
  if (!context) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(pointer: fine)').matches;
  const snippets = [
    {
      language: 'JAVASCRIPT',
      code: 'const scene = await Coduxum.render({\n  language: "javascript",\n  motion: "typing",\n});',
    },
    {
      language: 'PYTHON',
      code: 'scene = Coduxum(\n    language="python",\n    motion="typing",\n)\nawait scene.render()',
    },
    {
      language: 'RUST',
      code: 'let scene = Coduxum::new("rust")\n    .motion(Motion::Typing);\nscene.render().await?;',
    },
    {
      language: 'GO',
      code: 'scene := coduxum.New("go")\nscene.Motion = "typing"\nif err := scene.Render(); err != nil {\n    log.Fatal(err)\n}',
    },
  ];
  const syntaxColors = {
    plain: '#c9d1d9',
    punctuation: '#c9d1d9',
    keyword: '#ff7b72',
    function: '#d2a8ff',
    string: '#a5d6ff',
    number: '#79c0ff',
    type: '#ffa657',
    comment: '#8b949e',
    lineNumber: '#484f58',
    language: '#7ee787',
    cursor: '#ff6a43',
  };
  const languageKeywords = {
    JAVASCRIPT: new Set(['const', 'let', 'async', 'await', 'return', 'function', 'new', 'if', 'else', 'import', 'from']),
    PYTHON: new Set(['async', 'await', 'def', 'return', 'if', 'else', 'from', 'import', 'class', 'with', 'as']),
    RUST: new Set(['let', 'mut', 'fn', 'async', 'await', 'impl', 'struct', 'enum', 'use', 'pub', 'match']),
    GO: new Set(['package', 'import', 'func', 'var', 'const', 'go', 'defer', 'if', 'else', 'return', 'nil']),
  };

  const characterDuration = 38;
  const snippetDurations = snippets.map((snippet) => snippet.code.length * characterDuration);
  const snippetOffsets = snippetDurations.map((_, index) => (
    snippetDurations.slice(0, index).reduce((total, duration) => total + duration, 0)
  ));
  const sequenceDuration = snippetDurations.reduce((total, duration) => total + duration, 0);
  let width = 0;
  let height = 0;
  let pixelRatio = 1;
  let animationFrame = 0;
  const startedAt = performance.now();
  let parallaxX = 0;
  let parallaxY = 0;
  let targetParallaxX = 0;
  let targetParallaxY = 0;
  let disposed = false;

  function tokenizeLine(line, language) {
    const segments = [];
    const keywords = languageKeywords[language];
    const commentMarker = language === 'PYTHON' ? '#' : '//';
    let index = 0;

    while (index < line.length) {
      if (line.startsWith(commentMarker, index)) {
        segments.push({ text: line.slice(index), type: 'comment' });
        break;
      }

      const character = line[index];
      if (character === '"' || character === "'" || character === '`') {
        let end = index + 1;
        while (end < line.length) {
          if (line[end] === character && line[end - 1] !== '\\') {
            end += 1;
            break;
          }
          end += 1;
        }
        segments.push({ text: line.slice(index, end), type: 'string' });
        index = end;
        continue;
      }

      if (/\d/u.test(character)) {
        let end = index + 1;
        while (end < line.length && /[\d._]/u.test(line[end])) end += 1;
        segments.push({ text: line.slice(index, end), type: 'number' });
        index = end;
        continue;
      }

      if (/[A-Za-z_]/u.test(character)) {
        let end = index + 1;
        while (end < line.length && /[A-Za-z0-9_]/u.test(line[end])) end += 1;
        const word = line.slice(index, end);
        const remaining = line.slice(end);
        let type = 'plain';
        if (keywords.has(word)) type = 'keyword';
        else if (/^[A-Z]/u.test(word)) type = 'type';
        else if (/^\s*\(/u.test(remaining)) type = 'function';
        segments.push({ text: word, type });
        index = end;
        continue;
      }

      let end = index + 1;
      while (end < line.length && !/[A-Za-z0-9_'"`]/u.test(line[end]) && !line.startsWith(commentMarker, end)) end += 1;
      segments.push({ text: line.slice(index, end), type: 'punctuation' });
      index = end;
    }

    return segments;
  }

  function resizeCanvas() {
    const bounds = hero.getBoundingClientRect();
    width = Math.max(1, bounds.width);
    height = Math.max(1, bounds.height);
    pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * pixelRatio);
    canvas.height = Math.round(height * pixelRatio);
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  }

  function streamLayouts() {
    if (width < 700) {
      return [
        { x: -.08, y: .08, scale: .76, rotation: -.035, opacity: .68, phase: .08, depth: .72, languageOffset: 0 },
        { x: .23, y: .65, scale: .58, rotation: .045, opacity: .38, phase: .58, depth: .38, languageOffset: 2 },
      ];
    }
    return [
      { x: .025, y: .08, scale: 1, rotation: -.052, opacity: .78, phase: .08, depth: .9, languageOffset: 0 },
      { x: .67, y: .56, scale: .76, rotation: .055, opacity: .56, phase: .48, depth: .58, languageOffset: 1 },
      { x: .64, y: .07, scale: .56, rotation: .022, opacity: .3, phase: .76, depth: .28, languageOffset: 2 },
    ];
  }

  function drawCodeLine(line, x, y, alpha, language) {
    let cursorX = x;
    tokenizeLine(line, language).forEach((segment) => {
      context.fillStyle = syntaxColors[segment.type];
      context.globalAlpha = alpha;
      context.fillText(segment.text, cursorX, y);
      cursorX += context.measureText(segment.text).width;
    });
    return cursorX;
  }

  function drawCodeStream(layout, elapsed, staticFrame = false) {
    let snippetIndex = layout.languageOffset;
    let localTime = 0;

    if (!staticFrame) {
      localTime = (elapsed + snippetOffsets[layout.languageOffset]) % sequenceDuration;
      snippetIndex = 0;
      while (localTime >= snippetDurations[snippetIndex]) {
        localTime -= snippetDurations[snippetIndex];
        snippetIndex = (snippetIndex + 1) % snippets.length;
      }
    }

    const snippet = snippets[snippetIndex];
    const visibleCharacters = staticFrame
      ? snippet.code.length
      : Math.min(snippet.code.length, Math.floor(localTime / characterDuration) + 1);
    const visibleCode = snippet.code.slice(0, visibleCharacters);
    const streamAlpha = layout.opacity;

    const floatX = staticFrame ? 0 : Math.sin(elapsed * .00022 + layout.phase * 9) * 10 * layout.depth;
    const floatY = staticFrame ? 0 : Math.cos(elapsed * .00018 + layout.phase * 7) * 8 * layout.depth;
    const breathe = staticFrame ? 1 : 1 + Math.sin(elapsed * .00016 + layout.phase * 11) * .018;
    const scale = layout.scale * breathe;
    const originX = width * layout.x + floatX + parallaxX * layout.depth;
    const originY = height * layout.y + floatY + parallaxY * layout.depth;
    const fontSize = width < 700 ? 12 : 13;
    const lineHeight = fontSize * 1.72;
    const lines = visibleCode.split('\n');

    context.save();
    context.translate(originX, originY);
    context.rotate(layout.rotation);
    context.scale(scale, scale * .94);
    context.textBaseline = 'alphabetic';
    context.font = `700 9px "JetBrains Mono", "Cascadia Code", monospace`;
    context.letterSpacing = '1.4px';
    context.fillStyle = syntaxColors.language;
    context.globalAlpha = streamAlpha * .72;
    context.shadowColor = syntaxColors.language;
    context.shadowBlur = 12;
    context.fillText(`// ${snippet.language}  ·  LIVE`, 0, 0);
    context.shadowBlur = 0;
    context.letterSpacing = '0px';
    context.font = `500 ${fontSize}px "JetBrains Mono", "Cascadia Code", monospace`;

    let caretX = 0;
    let caretY = 0;
    lines.forEach((line, lineIndex) => {
      const y = 27 + lineIndex * lineHeight;
      context.fillStyle = syntaxColors.lineNumber;
      context.globalAlpha = streamAlpha * .52;
      context.textAlign = 'right';
      context.fillText(String(lineIndex + 1).padStart(2, '0'), -14, y);
      context.textAlign = 'left';
      caretX = drawCodeLine(line, 0, y, streamAlpha * .72, snippet.language);
      caretY = y;
    });

    const showCaret = staticFrame || Math.floor(elapsed / 480) % 2 === 0;
    if (showCaret) {
      context.globalAlpha = streamAlpha;
      context.fillStyle = syntaxColors.cursor;
      context.shadowColor = syntaxColors.cursor;
      context.shadowBlur = 10;
      context.fillRect(caretX + 2, caretY - fontSize + 1, 1.5, fontSize + 3);
    }
    context.restore();
  }

  function drawFrame(now, staticFrame = false) {
    if (disposed || !canvas.isConnected) {
      cleanup();
      return;
    }

    const elapsed = Math.max(0, now - startedAt);
    parallaxX += (targetParallaxX - parallaxX) * .045;
    parallaxY += (targetParallaxY - parallaxY) * .045;
    context.clearRect(0, 0, width, height);
    streamLayouts().forEach((layout) => drawCodeStream(layout, elapsed, staticFrame));
    context.globalAlpha = 1;

    if (!staticFrame) animationFrame = window.requestAnimationFrame(drawFrame);
  }

  function onPointerMove(event) {
    const bounds = hero.getBoundingClientRect();
    targetParallaxX = ((event.clientX - bounds.left) / bounds.width - .5) * -24;
    targetParallaxY = ((event.clientY - bounds.top) / bounds.height - .5) * -16;
  }

  function resetParallax() {
    targetParallaxX = 0;
    targetParallaxY = 0;
  }

  const resizeObserver = new ResizeObserver(() => {
    resizeCanvas();
    if (reducedMotion) drawFrame(performance.now(), true);
  });
  resizeObserver.observe(hero);
  if (finePointer && !reducedMotion) {
    hero.addEventListener('pointermove', onPointerMove, { passive: true });
    hero.addEventListener('pointerleave', resetParallax, { passive: true });
  }

  function cleanup() {
    if (disposed) return;
    disposed = true;
    window.cancelAnimationFrame(animationFrame);
    resizeObserver.disconnect();
    hero.removeEventListener('pointermove', onPointerMove);
    hero.removeEventListener('pointerleave', resetParallax);
  }

  resizeCanvas();
  if (reducedMotion) {
    drawFrame(performance.now(), true);
    document.fonts?.ready.then(() => drawFrame(performance.now(), true));
  } else {
    animationFrame = window.requestAnimationFrame(drawFrame);
  }
}

function initTypingCardAnimation(surface) {
  const demo = surface.querySelector('.scene-demo--typing');
  if (!demo || demo.dataset.characterTyping === 'true') return;
  demo.dataset.characterTyping = 'true';

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const codeBlocks = [...demo.querySelectorAll('.scene-code-line code')];
  codeBlocks.forEach((code) => {
    const walker = document.createTreeWalker(code, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    textNodes.forEach((textNode) => {
      const fragment = document.createDocumentFragment();
      Array.from(textNode.textContent || '').forEach((character) => {
        if (/\s/u.test(character)) {
          fragment.appendChild(document.createTextNode(character));
          return;
        }
        const span = document.createElement('span');
        span.className = 'scene-typing-char';
        span.textContent = character;
        fragment.appendChild(span);
      });
      textNode.replaceWith(fragment);
    });
  });

  const characters = [...demo.querySelectorAll('.scene-typing-char')];
  const firstCode = codeBlocks[0];
  if (!characters.length || !firstCode) return;

  const caret = document.createElement('span');
  caret.className = 'scene-demo__typing-caret';
  firstCode.prepend(caret);

  const characterMs = 40;
  const typingDuration = characters.length * characterMs;
  const completedHold = 850;
  const resetDuration = 260;
  const cycleDuration = typingDuration + completedHold + resetDuration;
  const startedAt = performance.now();
  let previousCount = -1;
  let previousResetting = false;

  function drawTypingFrame(now) {
    if (!surface.isConnected) return;

    const elapsed = (now - startedAt) % cycleDuration;
    const resetting = elapsed >= typingDuration + completedHold;
    const visibleCount = elapsed < typingDuration
      ? Math.min(characters.length, Math.floor(elapsed / characterMs))
      : characters.length;

    if (visibleCount !== previousCount) {
      characters.forEach((character, index) => {
        character.classList.toggle('is-visible', index < visibleCount);
      });

      if (visibleCount > 0) {
        characters[visibleCount - 1].after(caret);
      } else {
        firstCode.prepend(caret);
      }
      previousCount = visibleCount;
    }

    if (resetting !== previousResetting) {
      demo.classList.toggle('is-resetting', resetting);
      previousResetting = resetting;
    }

    window.requestAnimationFrame(drawTypingFrame);
  }

  window.requestAnimationFrame(drawTypingFrame);
}

function initHomePage() {
  const surface = document.querySelector('.home-surface');
  if (!surface || surface.dataset.homeInitialized === 'true') return;
  surface.dataset.homeInitialized = 'true';

  initHeroCodeField(surface);
  initTypingCardAnimation(surface);
}

document.addEventListener('htmx:load', initHomePage);
initHomePage();
