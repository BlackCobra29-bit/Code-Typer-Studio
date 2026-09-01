// Source is JSON data, never executable code. All grammars/themes are local.
import { createHighlighter, bundledLanguages, bundledThemes } from 'shiki';
import { createInterface } from 'node:readline';
const highlighter = await createHighlighter({ themes: [], langs: [] });
const aliases = { shell: 'shellscript', bash: 'shellscript', vbnet: 'vb', objectivec: 'objective-c' };
for await (const line of createInterface({ input: process.stdin })) {
  try {
    const input = JSON.parse(line);
    const requested = aliases[input.language] || input.language;
    const language = bundledLanguages[requested] ? requested : 'text';
    const theme = bundledThemes[input.theme] ? input.theme : 'dark-plus';
    await highlighter.loadTheme(theme);
    if (language !== 'text') await highlighter.loadLanguage(language);
    const result = highlighter.codeToTokens(input.code, { lang: language, theme });
    process.stdout.write(JSON.stringify({ language, theme,
      foreground: result.fg, background: result.bg,
      colors: highlighter.getTheme(theme).colors || {},
      lines: result.tokens.map(tokens => tokens.map(({ content, color, fontStyle }) =>
        ({ content, color: color || result.fg, fontStyle: fontStyle || 0 }))),
    }) + '\n');
  } catch (error) {
    process.stdout.write(JSON.stringify({ error: String(error.message) }) + '\n');
  }
}
