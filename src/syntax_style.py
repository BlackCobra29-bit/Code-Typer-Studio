from __future__ import annotations

from pygments.token import Comment, Generic, Keyword, Literal, Name, Number, Operator, Punctuation, String, Token


DEFAULT_THEME = "VS Code Dark+"

SYNTAX_PALETTES = {
    "VS Code Dark+": {
        "base": "#d4d4d4",
        "comment": "#6a9955",
        "keyword": "#569cd6",
        "control": "#c586c0",
        "function": "#dcdcaa",
        "string": "#ce9178",
        "number": "#b5cea8",
        "type": "#4ec9b0",
        "variable": "#9cdcfe",
        "constant": "#4fc1ff",
        "operator": "#d4d4d4",
        "invalid": "#f44747",
    },
    "Monokai Pro": {
        "base": "#fcfcfa",
        "comment": "#727072",
        "keyword": "#ff6188",
        "control": "#ff6188",
        "function": "#a9dc76",
        "string": "#ffd866",
        "number": "#ab9df2",
        "type": "#78dce8",
        "variable": "#fcfcfa",
        "constant": "#ab9df2",
        "operator": "#ff6188",
        "invalid": "#ff6188",
    },
    "Material Ocean": {
        "base": "#eeffff",
        "comment": "#546e7a",
        "keyword": "#c792ea",
        "control": "#c792ea",
        "function": "#82aaff",
        "string": "#c3e88d",
        "number": "#f78c6c",
        "type": "#ffcb6b",
        "variable": "#eeffff",
        "constant": "#89ddff",
        "operator": "#89ddff",
        "invalid": "#ff5370",
    },
    "Palenight": {
        "base": "#a6accd",
        "comment": "#676e95",
        "keyword": "#c792ea",
        "control": "#c792ea",
        "function": "#82aaff",
        "string": "#c3e88d",
        "number": "#f78c6c",
        "type": "#ffcb6b",
        "variable": "#eeffff",
        "constant": "#89ddff",
        "operator": "#89ddff",
        "invalid": "#ff5370",
    },
    "Shades of Purple": {
        "base": "#ffffff",
        "comment": "#b362ff",
        "keyword": "#ff9d00",
        "control": "#ff9d00",
        "function": "#fad000",
        "string": "#a5ff90",
        "number": "#ff628c",
        "type": "#9effff",
        "variable": "#9effff",
        "constant": "#fb94ff",
        "operator": "#ff9d00",
        "invalid": "#ff628c",
    },
    "One Dark Pro": {
        "base": "#abb2bf",
        "comment": "#5c6370",
        "keyword": "#c678dd",
        "control": "#c678dd",
        "function": "#61afef",
        "string": "#98c379",
        "number": "#d19a66",
        "type": "#e5c07b",
        "variable": "#e06c75",
        "constant": "#56b6c2",
        "operator": "#56b6c2",
        "invalid": "#f44747",
    },
    "Tokyo Night": {
        "base": "#c0caf5",
        "comment": "#565f89",
        "keyword": "#bb9af7",
        "control": "#bb9af7",
        "function": "#7aa2f7",
        "string": "#9ece6a",
        "number": "#ff9e64",
        "type": "#2ac3de",
        "variable": "#c0caf5",
        "constant": "#f7768e",
        "operator": "#89ddff",
        "invalid": "#db4b4b",
    },
    "Night Owl": {
        "base": "#d6deeb",
        "comment": "#637777",
        "keyword": "#c792ea",
        "control": "#c792ea",
        "function": "#82aaff",
        "string": "#ecc48d",
        "number": "#f78c6c",
        "type": "#ffcb8b",
        "variable": "#addb67",
        "constant": "#82aaff",
        "operator": "#7fdbca",
        "invalid": "#ef5350",
    },
    "Nord": {
        "base": "#d8dee9",
        "comment": "#616e88",
        "keyword": "#81a1c1",
        "control": "#81a1c1",
        "function": "#88c0d0",
        "string": "#a3be8c",
        "number": "#b48ead",
        "type": "#8fbcbb",
        "variable": "#d8dee9",
        "constant": "#5e81ac",
        "operator": "#81a1c1",
        "invalid": "#bf616a",
    },
    "Catppuccin Mocha": {
        "base": "#cdd6f4",
        "comment": "#6c7086",
        "keyword": "#cba6f7",
        "control": "#f5c2e7",
        "function": "#89b4fa",
        "string": "#a6e3a1",
        "number": "#fab387",
        "type": "#94e2d5",
        "variable": "#cdd6f4",
        "constant": "#f38ba8",
        "operator": "#89dceb",
        "invalid": "#f38ba8",
    },
    "Ayu Mirage": {
        "base": "#cccac2",
        "comment": "#5c6773",
        "keyword": "#ffae57",
        "control": "#ffae57",
        "function": "#ffd580",
        "string": "#bbe67e",
        "number": "#d4bfff",
        "type": "#73d0ff",
        "variable": "#cccac2",
        "constant": "#ffdfb3",
        "operator": "#f29e74",
        "invalid": "#ff3333",
    },
    "Gruvbox Dark": {
        "base": "#ebdbb2",
        "comment": "#928374",
        "keyword": "#fb4934",
        "control": "#fb4934",
        "function": "#b8bb26",
        "string": "#b8bb26",
        "number": "#d3869b",
        "type": "#fabd2f",
        "variable": "#ebdbb2",
        "constant": "#83a598",
        "operator": "#fe8019",
        "invalid": "#fb4934",
    },
    "Solarized Dark": {
        "base": "#839496",
        "comment": "#586e75",
        "keyword": "#859900",
        "control": "#d33682",
        "function": "#268bd2",
        "string": "#2aa198",
        "number": "#d33682",
        "type": "#b58900",
        "variable": "#839496",
        "constant": "#cb4b16",
        "operator": "#93a1a1",
        "invalid": "#dc322f",
    },
    "Solarized Light": {
        "base": "#657b83",
        "comment": "#93a1a1",
        "keyword": "#859900",
        "control": "#d33682",
        "function": "#268bd2",
        "string": "#2aa198",
        "number": "#d33682",
        "type": "#b58900",
        "variable": "#657b83",
        "constant": "#cb4b16",
        "operator": "#586e75",
        "invalid": "#dc322f",
    },
    "Cobalt2": {
        "base": "#ffffff",
        "comment": "#0088ff",
        "keyword": "#ff9d00",
        "control": "#ff9d00",
        "function": "#ffc600",
        "string": "#a5ff90",
        "number": "#ff628c",
        "type": "#9effff",
        "variable": "#ffffff",
        "constant": "#fb94ff",
        "operator": "#ff9d00",
        "invalid": "#ff628c",
    },
    "GitHub Dark": {
        "base": "#c9d1d9",
        "comment": "#8b949e",
        "keyword": "#ff7b72",
        "control": "#ff7b72",
        "function": "#d2a8ff",
        "string": "#a5d6ff",
        "number": "#79c0ff",
        "type": "#ffa657",
        "variable": "#ffa657",
        "constant": "#79c0ff",
        "operator": "#ff7b72",
        "invalid": "#f85149",
    },
    "Dracula Glow": {
        "base": "#f8f8f2",
        "comment": "#6272a4",
        "keyword": "#ff79c6",
        "control": "#ff79c6",
        "function": "#50fa7b",
        "string": "#f1fa8c",
        "number": "#bd93f9",
        "type": "#8be9fd",
        "variable": "#f8f8f2",
        "constant": "#bd93f9",
        "operator": "#ff79c6",
        "invalid": "#ff5555",
    },
    "Midnight Pro": {
        "base": "#e5e7eb",
        "comment": "#64748b",
        "keyword": "#60a5fa",
        "control": "#c084fc",
        "function": "#facc15",
        "string": "#86efac",
        "number": "#fdba74",
        "type": "#67e8f9",
        "variable": "#bfdbfe",
        "constant": "#f0abfc",
        "operator": "#93c5fd",
        "invalid": "#f87171",
    },
    "Synthwave": {
        "base": "#fdf4ff",
        "comment": "#a78bfa",
        "keyword": "#f472b6",
        "control": "#f472b6",
        "function": "#facc15",
        "string": "#86efac",
        "number": "#fb7185",
        "type": "#67e8f9",
        "variable": "#fdf4ff",
        "constant": "#c084fc",
        "operator": "#f472b6",
        "invalid": "#fb7185",
    },
    "Light Studio": {
        "base": "#24292f",
        "comment": "#6e7781",
        "keyword": "#cf222e",
        "control": "#cf222e",
        "function": "#8250df",
        "string": "#0a3069",
        "number": "#0550ae",
        "type": "#953800",
        "variable": "#24292f",
        "constant": "#0550ae",
        "operator": "#cf222e",
        "invalid": "#cf222e",
    },
}


def syntax_css(theme_name: str) -> str:
    palette = syntax_palette(theme_name)
    return f"""
.code-content,
.code-content .w {{
  color: {palette["base"]};
}}

.code-content .c,
.code-content .ch,
.code-content .cm,
.code-content .cp,
.code-content .cpf,
.code-content .c1,
.code-content .cs {{
  color: {palette["comment"]};
  font-style: italic;
}}

.code-content .k,
.code-content .kd,
.code-content .kn,
.code-content .kr {{
  color: {palette["keyword"]};
}}

.code-content .kp,
.code-content .kc {{
  color: {palette["control"]};
}}

.code-content .kt,
.code-content .nc,
.code-content .nn {{
  color: {palette["type"]};
}}

.code-content .ow,
.code-content .o {{
  color: {palette["operator"]};
}}

.code-content .p {{
  color: {palette["base"]};
}}

.code-content .s,
.code-content .sa,
.code-content .sb,
.code-content .sc,
.code-content .dl,
.code-content .sd,
.code-content .s2,
.code-content .se,
.code-content .sh,
.code-content .si,
.code-content .sx,
.code-content .sr,
.code-content .s1,
.code-content .ss {{
  color: {palette["string"]};
}}

.code-content .m,
.code-content .mb,
.code-content .mf,
.code-content .mh,
.code-content .mi,
.code-content .mo,
.code-content .il {{
  color: {palette["number"]};
}}

.code-content .nf,
.code-content .fm {{
  color: {palette["function"]};
}}

.code-content .n,
.code-content .na,
.code-content .nb,
.code-content .bp,
.code-content .nv,
.code-content .vc,
.code-content .vg,
.code-content .vi,
.code-content .vm {{
  color: {palette["variable"]};
}}

.code-content .no,
.code-content .nl,
.code-content .ne,
.code-content .nd,
.code-content .ni {{
  color: {palette["constant"]};
}}

.code-content .nt {{
  color: {palette["keyword"]};
}}

.code-content .ge {{
  font-style: italic;
}}

.code-content .gs {{
  font-weight: 700;
}}

.code-content .gd {{
  color: {palette["invalid"]};
}}

.code-content .gi {{
  color: {palette["comment"]};
}}
"""


def syntax_color(theme_name: str, token: Token) -> str:
    palette = syntax_palette(theme_name)
    if token in Comment:
        return palette["comment"]
    if token in String:
        return palette["string"]
    if token in Number:
        return palette["number"]
    if token in Keyword.Type or token in Name.Class or token in Name.Namespace:
        return palette["type"]
    if token in Keyword.Constant or token in Name.Constant:
        return palette["constant"]
    if token in Keyword.Reserved or token in Keyword.Pseudo:
        return palette["control"]
    if token in Keyword or token in Operator.Word:
        return palette["keyword"]
    if token in Name.Function:
        return palette["function"]
    if token in Name.Decorator or token in Name.Exception or token in Name.Label or token in Name.Entity:
        return palette["constant"]
    if token in Name.Tag:
        return palette["keyword"]
    if token in Name:
        return palette["variable"]
    if token in Operator or token in Punctuation:
        return palette["operator"]
    if token in Generic.Deleted or token is Token.Error:
        return palette["invalid"]
    if token in Generic.Inserted:
        return palette["comment"]
    if token in Literal:
        return palette["base"]
    return palette["base"]


def syntax_palette(theme_name: str) -> dict[str, str]:
    return SYNTAX_PALETTES.get(theme_name, SYNTAX_PALETTES[DEFAULT_THEME])

