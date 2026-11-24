"""Terminal text colors: shell hints for plain text, faithful SGR for ANSI text."""
import re

OUTPUT_BASE_COLOR = '#e0e0e5'
PALETTE = ['#242428','#ff5f57','#87d79b','#e5c07b','#82aaff','#c6a0f6','#7dcfff','#d8d8df',
           '#777782','#ff8a80','#a6e3a1','#f9e2af','#a6c8ff','#dfb6ff','#a5e8ff','#ffffff']
ANSI_COLORS = {**dict(zip(range(30,38),PALETTE[:8])), **dict(zip(range(90,98),PALETTE[8:]))}
ANSI_PATTERN = re.compile(r'\x1b\[([0-9;]*)m')
CONTROL_PATTERN = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f]')
SEMANTIC_PATTERN = re.compile(
    r'(?P<error>\b(?:error(?:\[[A-Z0-9]+\])?|fatal|failed|failure|panic)\b:?)'
    r'|(?P<warning>\b(?:warn(?:ing)?|deprecated)\b:?)'
    r'|(?P<success>✓|✔|\b(?:success(?:ful(?:ly)?)?|finished|compiled?|compiling|created|installed|done|passed|ok|built)\b)'
    r'|(?P<path>(?:\.{0,2}/)?(?:[\w.-]+/)+[\w.-]+(?::\d+(?::\d+)?)?)'
    r'|(?P<string>`[^`]*`|\x27[^\x27]*\x27|"[^"]*")'
    r'|(?P<marker>-->|==>|\^+|~{3,})'
    r'|(?P<number>\b\d+(?:\.\d+)?\s*(?:ms|s|kB|MB|GB)\b)', re.I)
SEMANTIC_COLORS = dict(error=PALETTE[1],warning=PALETTE[3],success=PALETTE[2],
                       path=PALETTE[4],string=PALETTE[3],marker=PALETTE[6],number=PALETTE[8])


def token(text, color=OUTPUT_BASE_COLOR, **style):
    return {**dict(text=text,color=color,bold=False,italic=False,underline=False,background=None), **style}


def _indexed_color(index):
    index=max(0,min(255,index))
    if index<16:return PALETTE[index]
    if index>=232:
        value=8+(index-232)*10
        return f'#{value:02x}{value:02x}{value:02x}'
    n=index-16; levels=(0,95,135,175,215,255)
    return '#%02x%02x%02x' % (levels[n//36],levels[n//6%6],levels[n%6])


def _ansi_output_tokens(text):
    result=[]; foreground=OUTPUT_BASE_COLOR; background=None
    bold=italic=underline=dim=inverse=False; position=0
    def emit(value):
        value=CONTROL_PATTERN.sub('',value)
        if not value:return
        fg,bg=(background or '#1e1e22',foreground) if inverse else (foreground,background)
        if dim:
            fg='#' + ''.join(f'{round(int(fg[i:i+2],16)*.60):02x}' for i in (1,3,5))
        result.append(token(value,fg,bold=bold,italic=italic,underline=underline,background=bg))
    for match in ANSI_PATTERN.finditer(text):
        emit(text[position:match.start()])
        codes=[int(v or 0) for v in match[1].split(';')]; i=0
        while i<len(codes):
            code=codes[i]
            if code==0:foreground=OUTPUT_BASE_COLOR; background=None; bold=italic=underline=dim=inverse=False
            elif code==1:bold=True
            elif code==2:dim=True
            elif code==3:italic=True
            elif code==4:underline=True
            elif code==7:inverse=True
            elif code==22:bold=dim=False
            elif code==23:italic=False
            elif code==24:underline=False
            elif code==27:inverse=False
            elif code==39:foreground=OUTPUT_BASE_COLOR
            elif code==49:background=None
            elif code in ANSI_COLORS:foreground=ANSI_COLORS[code]
            elif 40<=code<=47:background=PALETTE[code-40]
            elif 100<=code<=107:background=PALETTE[code-100+8]
            elif code in (38,48) and i+1<len(codes):
                color=None
                if codes[i+1]==5 and i+2<len(codes):color=_indexed_color(codes[i+2]);i+=2
                elif codes[i+1]==2 and i+4<len(codes):
                    color='#' + ''.join(f'{max(0,min(255,v)):02x}' for v in codes[i+2:i+5]);i+=4
                else:
                    # Incomplete extended-color payloads must not become SGR flags.
                    break
                if color:
                    if code==38:foreground=color
                    else:background=color
            i+=1
        position=match.end()
    emit(text[position:])
    return result


def terminal_output_tokens(output):
    text=(output or '').replace('\r\n','\n').replace('\r','\n')
    if ANSI_PATTERN.search(text):return _ansi_output_tokens(text)
    text=CONTROL_PATTERN.sub('',text); result=[]; position=0
    for match in SEMANTIC_PATTERN.finditer(text):
        if match.start()>position:result.append(token(text[position:match.start()]))
        kind=match.lastgroup
        result.append(token(match[0],SEMANTIC_COLORS[kind],bold=kind in ('error','warning','success')))
        position=match.end()
    if position<len(text):result.append(token(text[position:]))
    return result


def command_tokens(command):
    parts=re.findall(r'\s+|"[^"]*"|\x27[^\x27]*\x27|[^\s]+',CONTROL_PATTERN.sub('',command or ''))
    result=[]; executable=True
    for part in parts:
        color=OUTPUT_BASE_COLOR
        if part.strip():
            if part in ('|','||','&&',';','>','>>','<'):color=PALETTE[5];executable=True
            elif part.startswith(('"',"'")):color=PALETTE[3];executable=False
            elif executable:color=PALETTE[2];executable=False
            elif part.startswith('-'):color=PALETTE[6]
            elif part.startswith('$'):color=PALETTE[5]
        result.append(token(part,color))
    return result


def prompt_tokens(prompt):
    text=CONTROL_PATTERN.sub('',prompt or '%')
    match=re.match(r'(\S+@\S+)(\s+.*?)(\s*[%$#❯])$',text)
    if match:return [token(match[1],PALETTE[2]),token(match[2],PALETTE[4]),token(match[3]+' ',PALETTE[8])]
    return [token(text+' ',PALETTE[4])]


def wrap_tokens(tokens,columns):
    """Soft-wrap terminal cells, preserving styles and blank lines."""
    rows=[[]]; column=0
    for item in tokens:
        for char in item['text']:
            if char=='\n':rows.append([]);column=0;continue
            chars=' '*(8-column%8) if char=='\t' else char
            for char in chars:
                if column>=columns:rows.append([]);column=0
                style={key:value for key,value in item.items() if key!='text'}
                if rows[-1] and all(rows[-1][-1].get(key)==value for key,value in style.items()):
                    rows[-1][-1]['text']+=char
                else:rows[-1].append(dict(style,text=char))
                column+=1
    return rows


def prefix_tokens(tokens,count):
    result=[]
    for item in tokens:
        if count<=0:break
        result.append(dict(item,text=item['text'][:count]));count-=len(item['text'])
    return result
