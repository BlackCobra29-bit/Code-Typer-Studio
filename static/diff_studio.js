function initCodeDiffStudio(){
  const form=document.getElementById('diff-form');
  if(!form||form.dataset.initialized==='true')return;
  form.dataset.initialized='true';
  const abort=new AbortController(),signal=abort.signal;
  const originalArea=document.getElementById('original_code'),revisedArea=document.getElementById('revised_code');
  const trigger=document.getElementById('diff-preview-trigger'),status=document.getElementById('diff-preview-status');
  const language=document.getElementById('diff-language'),theme=document.getElementById('diff-theme');
  const styleSheet=document.getElementById('diff-token-styles');
  let timer=0,highlightTimer=0,highlightVersion=0,marks=[];
  const editors=window.CodeMirror?[CodeMirror.fromTextArea(originalArea,{lineNumbers:true,lineWrapping:false,tabSize:2,indentUnit:2}),CodeMirror.fromTextArea(revisedArea,{lineNumbers:true,lineWrapping:false,tabSize:2,indentUnit:2})]:[];
  function sourceValues(){return editors.length?editors.map(editor=>editor.getValue()):[originalArea.value,revisedArea.value]}
  function syncAreas(){if(!editors.length)return;[originalArea,revisedArea].forEach((area,index)=>{const value=editors[index].getValue();if(area.value!==value){area.value=value;area.dispatchEvent(new Event('input',{bubbles:true}))}})}
  function schedule(delay=420){clearTimeout(timer);status.textContent='Editing';scheduleHighlight();timer=setTimeout(()=>{syncAreas();status.textContent='Rendering';window.htmx?.trigger(trigger,'refreshPreview')},delay)}
  function scheduleHighlight(){
    const version=++highlightVersion;clearTimeout(highlightTimer);highlightTimer=setTimeout(async()=>{
      try{
        const values=sourceValues(),responses=await Promise.all(values.map(code=>{const body=new FormData(form);body.set('code',code);return fetch('/highlight',{method:'POST',body,signal})}));
        const data=await Promise.all(responses.map(async response=>{if(!response.ok)throw new Error(await response.text());return response.json()}));
        if(version!==highlightVersion||!editors.length)return;
        marks.flat().forEach(mark=>mark.clear());marks=[];const rules=[];
        data.forEach((highlight,editorIndex)=>{
          const editor=editors[editorIndex],editorMarks=[],prefix=`diff-${editorIndex}`,classes=new Map();
          editor.operation(()=>{
            highlight.lines.forEach((tokens,line)=>{
              let ch=0;
              tokens.forEach(token=>{
                const start=ch;ch+=token.content.length;if(!token.content)return;
                const key=`${token.color}:${token.fontStyle}`;
                if(!classes.has(key)){
                  const name=`${prefix}-token-${classes.size}`;classes.set(key,name);
                  rules.push(`#diff-form .${name}{color:${token.color};font-style:${token.fontStyle&1?'italic':'normal'};font-weight:${token.fontStyle&2?'700':'400'};text-decoration:${token.fontStyle&4?'underline':'none'}}`);
                }
                editorMarks.push(editor.markText({line,ch:start},{line,ch},{className:classes.get(key)}));
              });
            });
          });
          const wrapper=editor.getWrapperElement();wrapper.style.setProperty('--source-bg',highlight.background);wrapper.style.setProperty('--source-fg',highlight.foreground);wrapper.style.setProperty('--source-muted',highlight.colors['editorLineNumber.foreground']||highlight.foreground);marks.push(editorMarks);
        });
        styleSheet.textContent=rules.join('\n');document.getElementById('diff-syntax-engine').textContent=`${data[1].language} · ${data[1].theme} · TextMate diff`;
      }catch(error){if(error.name!=='AbortError'&&version===highlightVersion)status.textContent=error.message||'Highlighting unavailable'}
    },180)
  }
  function playback(action,extra={}){document.querySelector('#diff-preview-panel iframe')?.contentWindow.postMessage({type:'diff:command',action,...extra},'*')}
  function receive(event){const frame=document.querySelector('#diff-preview-panel iframe');if(event.source!==frame?.contentWindow||event.data?.type!=='diff:state')return;const state=event.data;const button=document.getElementById('diff-preview-play');button.textContent=state.playing?'Pause':'Play';button.setAttribute('aria-label',state.playing?'Pause animation':'Play animation');document.getElementById('diff-preview-scrubber').value=String(state.time/state.duration*1000);document.getElementById('diff-preview-time').textContent=`${(state.time/1000).toFixed(1)} / ${(state.duration/1000).toFixed(1)}s`;}
  window.addEventListener('message',receive,{signal});
  document.getElementById('diff-preview-play').addEventListener('click',()=>playback('toggle'),{signal});
  document.getElementById('diff-preview-restart').addEventListener('click',()=>playback('restart'),{signal});
  document.getElementById('diff-replay-action').addEventListener('click',()=>playback('restart'),{signal});
  const scrubber=document.getElementById('diff-preview-scrubber');scrubber.addEventListener('input',()=>playback('seek',{progress:Number(scrubber.value)/1000}),{signal});
  function fit(){const ratios={display:[700,300],'16_9':[1280,720],'9_16':[720,1280],'1_1':[1080,1080],'4_5':[1080,1350],'4_3':[1024,768]};const [w,h]=ratios[document.getElementById('diff-aspect-ratio').value]||ratios['16_9'];const panel=document.getElementById('diff-preview-panel');panel.style.aspectRatio=`${w}/${h}`;document.querySelector('#diff-form .studio-preview-wrap').style.maxWidth=`${Math.min(920,580*w/h)}px`}
  form.querySelectorAll('input,select,textarea').forEach(control=>{control.addEventListener('input',()=>schedule(control.matches('textarea')?650:280),{signal});control.addEventListener('change',()=>{fit();schedule(100)},{signal})});
  editors.forEach(editor=>editor.on('change',()=>{syncAreas();schedule(650)}));
  form.addEventListener('htmx:afterSwap',event=>{if(event.detail.target.id==='diff-preview-panel')status.textContent='Ready'},{signal});
  form.addEventListener('htmx:responseError',event=>{status.textContent=event.detail.xhr?.responseText||'Preview could not be rendered'},{signal});
  form.addEventListener('submit',async event=>{const button=event.submitter;if(!button?.formAction.includes('/code-diff/download/'))return;event.preventDefault();syncAreas();const label=button.textContent,buttons=[...form.querySelectorAll('button[type="submit"]')];buttons.forEach(item=>item.disabled=true);button.textContent='Rendering…';status.textContent='Rendering export…';try{const response=await fetch(button.formAction,{method:'POST',body:new FormData(form),signal});if(!response.ok)throw new Error(await response.text());const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||'code-diff-animation';link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);status.textContent='Export ready'}catch(error){if(error.name!=='AbortError')status.textContent=error.message||'Export failed'}finally{buttons.forEach(item=>item.disabled=false);button.textContent=label}},{signal});
  window.cleanupCodeDiffStudio=()=>{abort.abort();clearTimeout(timer);clearTimeout(highlightTimer);editors.forEach(editor=>editor.toTextArea());form.dataset.initialized='false'};
  fit();scheduleHighlight();
}
document.addEventListener('htmx:load',initCodeDiffStudio);initCodeDiffStudio();
