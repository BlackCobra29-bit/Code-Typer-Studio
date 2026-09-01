function initCodeDiffStudio(){
  const form=document.getElementById('diff-form');
  if(!form||form.dataset.initialized==='true')return;
  form.dataset.initialized='true';
  const abort=new AbortController(),signal=abort.signal;
  const originalArea=document.getElementById('original_code'),revisedArea=document.getElementById('revised_code');
  const trigger=document.getElementById('diff-preview-trigger'),status=document.getElementById('diff-preview-status');
  const language=document.getElementById('diff-language'),theme=document.getElementById('diff-theme');
  const styleSheet=document.getElementById('diff-token-styles');
  const languageCatalog=JSON.parse(document.getElementById('diff-language-catalog').textContent);
  const languageLabels=Object.fromEntries(Object.entries(languageCatalog).map(([key,value])=>[key,value.label||key]));
  const languageIcons=Object.fromEntries(Object.entries(languageCatalog).map(([key,value])=>[key,value.icon||'json.svg']));
  const customSelects=new Map();
  let timer=0,highlightTimer=0,highlightVersion=0,marks=[];
  const editorOptions={mode:null,theme:'textmate',lineNumbers:true,lineWrapping:false,tabSize:2,indentUnit:2,viewportMargin:Infinity};
  const editors=window.CodeMirror?[CodeMirror.fromTextArea(originalArea,editorOptions),CodeMirror.fromTextArea(revisedArea,editorOptions)]:[];
  editors.forEach((editor,index)=>editor.getInputField().setAttribute('aria-label',index?'Updated source code':'Original source code'));

  function selectLabel(select,value){return select===language?(languageLabels[value]||value):(Array.from(select.options).find(option=>option.value===value)?.textContent||value)}
  function renderSelectIcon(container,select,value){
    container.replaceChildren();
    if(select===language){
      const image=document.createElement('img');image.className='h-6 w-6 object-contain';image.src=`/static/icons/${languageIcons[value]||'json.svg'}`;image.alt=`${selectLabel(select,value)} icon`;container.appendChild(image);return;
    }
    const badge=document.createElement('span');badge.className='grid h-6 w-6 place-items-center rounded bg-slate-900 text-[10px] font-bold text-white';badge.setAttribute('aria-hidden','true');badge.textContent='fn';container.appendChild(badge);
  }
  function closeSelect(select){const item=customSelects.get(select.id);if(!item)return;item.menu.classList.add('hidden');item.trigger.setAttribute('aria-expanded','false')}
  function syncSelect(select){
    const item=customSelects.get(select.id);if(!item)return;
    item.value.textContent=selectLabel(select,select.value);renderSelectIcon(item.icon,select,select.value);
    item.options.forEach(option=>{const selected=option.dataset.value===select.value;option.setAttribute('aria-selected',String(selected));option.classList.toggle('bg-slate-50',selected);option.classList.toggle('font-bold',selected)});
  }
  function openSelect(select){customSelects.forEach(item=>{if(item.select!==select)closeSelect(item.select)});const item=customSelects.get(select.id);if(!item)return;item.menu.classList.remove('hidden');item.trigger.setAttribute('aria-expanded','true');syncSelect(select)}
  function initSelect(select){
    const wrapper=form.querySelector(`[data-diff-custom-select="${select.id}"]`);if(!wrapper)return;
    const trigger=wrapper.querySelector('[data-diff-select-trigger]'),menu=wrapper.querySelector('[data-diff-select-menu]'),value=trigger.querySelector('[data-diff-select-value]'),icon=trigger.querySelector('[data-diff-select-icon]');
    menu.replaceChildren();
    const options=Array.from(select.options).map((source,index)=>{
      const option=document.createElement('button');option.type='button';option.id=`${select.id}-custom-option-${index}`;option.dataset.value=source.value;option.className='flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-slate-800 transition hover:bg-slate-50 focus:bg-slate-50 focus:outline-none';option.setAttribute('role','option');
      const optionIcon=document.createElement('span');optionIcon.className='grid h-6 w-6 shrink-0 place-items-center';renderSelectIcon(optionIcon,select,source.value);
      const optionLabel=document.createElement('span');optionLabel.className='flex-1 whitespace-nowrap';optionLabel.textContent=selectLabel(select,source.value);option.append(optionIcon,optionLabel);
      option.addEventListener('click',()=>{if(select.value!==source.value){select.value=source.value;select.dispatchEvent(new Event('change',{bubbles:true}))}syncSelect(select);closeSelect(select);trigger.focus()},{signal});menu.appendChild(option);return option;
    });
    customSelects.set(select.id,{select,wrapper,trigger,menu,value,icon,options});
    trigger.addEventListener('click',event=>{event.stopPropagation();menu.classList.contains('hidden')?openSelect(select):closeSelect(select)},{signal});
    trigger.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();menu.classList.contains('hidden')?openSelect(select):closeSelect(select)}else if(event.key==='Escape'){closeSelect(select)}else if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();openSelect(select);options[Math.max(0,select.selectedIndex)].focus()}},{signal});
    menu.addEventListener('click',event=>event.stopPropagation(),{signal});
    menu.addEventListener('keydown',event=>{const current=options.indexOf(document.activeElement);if(event.key==='Escape'){closeSelect(select);trigger.focus()}else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?options.length-1:(current+(event.key==='ArrowDown'?1:-1)+options.length)%options.length;options[next].focus()}},{signal});
    syncSelect(select);
  }
  [language,theme].forEach(initSelect);
  [language,theme].forEach(select=>select.addEventListener('change',()=>syncSelect(select),{signal}));
  form.addEventListener('click',()=>customSelects.forEach(item=>closeSelect(item.select)),{signal});
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
          const wrapper=editor.getWrapperElement(),colors=highlight.colors||{};
          wrapper.style.setProperty('--source-bg',highlight.background);
          wrapper.style.setProperty('--source-fg',highlight.foreground);
          wrapper.style.setProperty('--source-muted',colors['editorLineNumber.foreground']||highlight.foreground);
          wrapper.style.setProperty('--source-cursor',colors['editorCursor.foreground']||highlight.foreground);
          wrapper.style.setProperty('--source-selection',colors['editor.selectionBackground']||'#8094b044');
          marks.push(editorMarks);
        });
        styleSheet.textContent=rules.join('\n');document.getElementById('diff-syntax-engine').textContent=`${languageLabels[data[1].language]||data[1].language} · ${data[1].theme} · TextMate diff`;
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
  const exportButtons=[...form.querySelectorAll('[data-diff-export]')];
  async function downloadExport(button){
    if(button.disabled)return;
    syncAreas();
    const label=button.textContent;
    exportButtons.forEach(item=>item.disabled=true);
    button.textContent='Rendering…';status.textContent='Rendering export…';
    try{
      const response=await fetch(button.formAction,{method:button.formMethod||'POST',body:new FormData(form)});
      if(!response.ok)throw new Error((await response.text()).trim()||`Export failed (${response.status})`);
      const blob=await response.blob();
      if(!blob.size)throw new Error('The exported file was empty.');
      const url=URL.createObjectURL(blob),link=document.createElement('a');
      link.href=url;link.download=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||'code-diff-animation';link.hidden=true;
      document.body.appendChild(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),30000);status.textContent='Export ready';
    }catch(error){status.textContent=error.message||'Export failed'}
    finally{exportButtons.forEach(item=>item.disabled=false);button.textContent=label}
  }
  exportButtons.forEach(button=>button.addEventListener('click',event=>{event.preventDefault();downloadExport(button)},{signal}));
  form.addEventListener('submit',event=>{if(event.submitter?.matches('[data-diff-export]'))event.preventDefault()},{signal});
  window.cleanupCodeDiffStudio=()=>{abort.abort();clearTimeout(timer);clearTimeout(highlightTimer);editors.forEach(editor=>editor.toTextArea());form.dataset.initialized='false'};
  fit();scheduleHighlight();
}
document.addEventListener('htmx:load',initCodeDiffStudio);initCodeDiffStudio();
