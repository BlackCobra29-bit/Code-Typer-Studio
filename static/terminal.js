function initTerminalStudio() {
  const form=document.getElementById('terminal-form');
  if(!form||form.dataset.terminalStudioInitialized==='true')return;
  form.dataset.terminalStudioInitialized='true';
  const preview=document.getElementById('terminal-preview');
  const trigger=document.getElementById('terminal-preview-trigger');
  const aspect=form.elements.aspect_ratio,background=form.elements.background_style;
  const gradient=form.elements.gradient_name,padding=form.elements.canvas_padding;
  const play=document.getElementById('play-terminal'),seek=document.getElementById('terminal-seek');
  const status=document.getElementById('terminal-export-status');
  const controller=new AbortController(),listen={signal:controller.signal};
  let timer=null,exporting=false;
  window.cleanupTerminalStudio=()=>{clearTimeout(timer);controller.abort();form.dataset.terminalStudioInitialized="false";};
  const send=data=>preview.querySelector('iframe')?.contentWindow?.postMessage(data,'*');
  const format=ms=>`${Math.floor(ms/60000)}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}`;
  function controls(){
    const display=aspect.value==='display',padded=background.value==='gradient'&&!display;
    gradient.disabled=padding.disabled=!padded;
    const sizes={display:[700,300],'16_9':[1280,720],'9_16':[720,1280],'1_1':[1080,1080],'4_5':[1080,1350],'4_3':[1024,768]};
    const [w,h]=sizes[aspect.value]||sizes['16_9'];
    preview.style.aspectRatio=`${w} / ${h}`;preview.style.maxWidth=`${Math.min(920,680*w/h)}px`;
    document.getElementById('terminal-canvas-help').textContent=display?'Display mode fits the terminal edge to edge. MP4 renders at 1920 × 824.':padded?'The gradient backdrop and soft window shadow are included in every export.':'Choose Gradient for a padded backdrop, matching the code studios.';
    document.getElementById('speed-value').textContent=`${form.elements.word_speed_ms.value} ms`;
  }
  function refresh(event){
    if(event.target===seek)return;
    if(event.target===background&&background.value==='gradient'&&aspect.value==='display')aspect.value='16_9';
    controls();clearTimeout(timer);timer=setTimeout(()=>htmx.trigger(trigger,'refreshPreview'),220);
  }
  form.addEventListener('input',refresh,listen);
  form.addEventListener('change',refresh,listen);
  document.getElementById('restart-terminal').addEventListener('click',()=>send('terminal:restart'),listen);
  play.addEventListener('click',()=>send({type:'terminal:toggle'}),listen);
  seek.addEventListener('input',()=>send({type:'terminal:seek',time:Number(seek.value)}),listen);
  window.addEventListener('message',event=>{
    if(event.source!==preview.querySelector('iframe')?.contentWindow||event.data?.type!=='terminal:state')return;
    const state=event.data;seek.max=state.duration;seek.value=state.time;
    play.textContent=state.playing?'Pause':'Play';play.setAttribute('aria-label',state.playing?'Pause animation':'Play animation');
    document.getElementById('terminal-time').textContent=`${format(state.time)} / ${format(state.duration)}`;
  },listen);
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const button=event.submitter;if(!button?.formAction||exporting)return;
    const data=new FormData(form),kind=button.formAction.split('/').pop();
    const buttons=[...form.querySelectorAll('button[type=submit]')];
    exporting=true;buttons.forEach(b=>b.disabled=true);status.dataset.error='false';
    status.textContent=kind==='mp4'?'Rendering Full HD video… You can keep editing while it exports.':`Preparing ${kind.toUpperCase()}…`;
    try{
      const response=await fetch(button.formAction,{method:'POST',body:data,signal:controller.signal});
      if(!response.ok){const text=await response.text();let message=text||'Export failed. Please try again.';try{message=JSON.parse(text).detail||message;}catch{}throw new Error(message);}
      const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
      link.href=url;link.download=`terminal-animation.${kind}`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
      status.textContent=`${kind.toUpperCase()} is ready. Your download has started.`;
    }catch(error){if(error.name!=='AbortError'){status.dataset.error='true';status.textContent=error.message;}}
    finally{exporting=false;buttons.forEach(b=>b.disabled=false);}
  },listen);
  controls();
}
document.addEventListener('htmx:load',initTerminalStudio);
initTerminalStudio();
