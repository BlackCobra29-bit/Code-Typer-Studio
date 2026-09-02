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

  initTypingCardAnimation(surface);
}

document.addEventListener('htmx:load', initHomePage);
initHomePage();
