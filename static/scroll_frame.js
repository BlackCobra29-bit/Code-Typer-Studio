(() => {
  'use strict';
  const options=JSON.parse(document.getElementById('scrollOptions').textContent);
  const timeline=options.timeline,stage=document.getElementById('stage'),editor=document.getElementById('editorWindow');
  const viewport=document.getElementById('viewport'),content=document.getElementById('scrollContent');
  const rows=[...content.querySelectorAll('.scroll-line')],targets=rows.filter(row=>row.classList.contains('target-line'));
  const box=document.getElementById('highlightBox'),badge=document.getElementById('focusBadge');
  const playButton=document.getElementById('playPause'),scrubber=document.getElementById('scrubber');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  let playing=false,elapsed=0,lastStamp=null,raf=0,lastReported=-1,targetY=0;
  const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
  const ease=t=>1-Math.pow(1-clamp(t),4);
  const smooth=t=>{t=clamp(t);return t*t*t*(t*(t*6-15)+10)};
  const progress=(time,start,end,fn=ease)=>reduced?time>=start?1:0:fn((time-start)/Math.max(1,end-start));
  function fit(){const controls=document.body.classList.contains('embedded')?0:46;const scale=Math.min(innerWidth/options.width,(innerHeight-controls)/options.height);stage.style.transform=`translate(${(innerWidth-options.width*scale)/2}px,${(innerHeight-controls-options.height*scale)/2}px) scale(${scale})`;}
  function layout(){
    if(!targets.length)return;
    const first=targets[0],last=targets[targets.length-1],top=first.offsetTop,height=last.offsetTop+last.offsetHeight-top;
    targetY=clamp(top+height/2-viewport.clientHeight/2,0,Math.max(0,content.scrollHeight-viewport.clientHeight));
    const longest=Math.max(...targets.map(row=>row.querySelector('.line-content').scrollWidth));
    box.style.top=`${top}px`;box.style.height=`${height}px`;box.style.width=`${Math.max(42,longest-22)}px`;
  }
  function draw(time){
    elapsed=clamp(time,0,timeline.duration);
    const scroll=progress(elapsed,timeline.scrollStart,timeline.scrollEnd,smooth);
    const focus=progress(elapsed,timeline.focusStart,timeline.focusEnd);
    const entrance=reduced?1:smooth(elapsed/Math.max(1,Math.min(650,timeline.startDelay)));
    editor.style.transform=`translate3d(0,${(1-entrance)*14}px,0) scale(${.992+entrance*.008})`;editor.style.opacity=String(.76+entrance*.24);
    content.style.transform=`translate3d(0,${-targetY*scroll}px,0)`;
    box.style.opacity=String(focus);box.style.transform=`scale(${.985+focus*.015})`;
    rows.forEach(row=>{row.style.opacity=String(row.classList.contains('target-line')?1:1-focus*.65)});
    const label=options.targetStart===options.targetEnd?`Line ${options.targetStart}`:`Lines ${options.targetStart}–${options.targetEnd}`;
    badge.textContent=elapsed<timeline.scrollEnd?'Scanning':label;
    scrubber.value=String(elapsed/timeline.duration*1000);document.getElementById('timecode').textContent=`${(elapsed/1000).toFixed(1)} / ${(timeline.duration/1000).toFixed(1)}s`;
    content.dataset.time=elapsed.toFixed(1);if(Math.abs(elapsed-lastReported)>80){report();lastReported=elapsed;}
  }
  function report(){playButton.textContent=playing?'Pause':'Play';if(parent!==window)parent.postMessage({type:'scroll:state',playing,time:elapsed,duration:timeline.duration,language:options.language,theme:options.theme,targetStart:options.targetStart,targetEnd:options.targetEnd},'*');}
  function tick(stamp){if(!playing)return;if(lastStamp!==null)elapsed+=stamp-lastStamp;lastStamp=stamp;if(elapsed>=timeline.duration){if(options.loop)elapsed%=timeline.duration;else{draw(timeline.duration);pause();return}}draw(elapsed);raf=requestAnimationFrame(tick);}
  function play(){if(playing)return;if(elapsed>=timeline.duration)elapsed=0;playing=true;lastStamp=null;raf=requestAnimationFrame(tick);report();}
  function pause(){playing=false;cancelAnimationFrame(raf);lastStamp=null;report();}
  function seek(time){pause();draw(time);report();}
  function restart(){pause();draw(0);play();}
  playButton.addEventListener('click',()=>playing?pause():play());document.getElementById('restart').addEventListener('click',restart);
  scrubber.addEventListener('input',()=>seek(Number(scrubber.value)/1000*timeline.duration));
  window.addEventListener('message',event=>{if(event.source!==parent||event.data?.type!=='scroll:command')return;if(event.data.action==='toggle')playing?pause():play();if(event.data.action==='restart')restart();if(event.data.action==='seek')seek(Number(event.data.progress)*timeline.duration);});
  window.addEventListener('resize',()=>{fit();layout();draw(elapsed)});document.addEventListener('visibilitychange',()=>{lastStamp=null});
  window.codeScroll=Object.freeze({play,pause,restart,seek,duration:timeline.duration});
  document.fonts.ready.then(()=>{fit();layout();draw(reduced?timeline.duration:0);if(options.autoplay&&!reduced)play();else report();});
})();
