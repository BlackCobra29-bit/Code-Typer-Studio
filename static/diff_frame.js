(() => {
  'use strict';
  const options=JSON.parse(document.getElementById('diffOptions').textContent);
  const timeline=options.timeline, stage=document.getElementById('stage'), editor=document.getElementById('editorWindow');
  const viewport=document.getElementById('viewport'), content=document.getElementById('diffContent');
  const badge=document.getElementById('changeBadge');
  const rows=[...content.querySelectorAll('.diff-row')], playButton=document.getElementById('playPause');
  const scrubber=document.getElementById('scrubber'), reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  let playing=false,elapsed=0,lastStamp=null,raf=0,lastReported=-1,rowHeight=options.fontSize*options.lineHeight;
  const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
  const ease=t=>1-Math.pow(1-clamp(t),4);
  const smooth=t=>{t=clamp(t);return t*t*t*(t*(t*6-15)+10)};
  const progress=(time,start,duration)=>reduced?time>=start?1:0:ease((time-start)/Math.max(1,duration));
  function fit(){const controls=document.body.classList.contains('embedded')||document.body.classList.contains('flush-frame')?0:46;const scale=Math.min(innerWidth/options.width,(innerHeight-controls)/options.height);stage.style.transform=`translate(${(innerWidth-options.width*scale)/2}px,${(innerHeight-controls-options.height*scale)/2}px) scale(${scale})`;}
  function draw(time){
    elapsed=clamp(time,0,timeline.duration);
    const resolve=progress(elapsed,timeline.resolveStart,timeline.resolveEnd-timeline.resolveStart);
    const entrance=reduced?1:smooth(elapsed/Math.max(1,Math.min(650,timeline.startDelay)));
    editor.style.transform=`translate3d(0,${(1-entrance)*14}px,0) scale(${.992+entrance*.008})`;
    editor.style.opacity=String(.76+entrance*.24);
    rows.forEach((element,index)=>{
      const row=options.rows[index], kind=row.kind;
      const intro=row.originalOrder<0?0:progress(elapsed,timeline.startDelay+row.originalOrder*timeline.lineStagger,260);
      const changeAt=timeline.changeStart+Math.max(0,row.changeOrder)*72;
      const deletion=kind==='delete'?progress(elapsed,changeAt,timeline.transition*.72):0;
      const insertion=kind==='insert'?progress(elapsed,timeline.insertStart+Math.max(0,row.changeOrder)*72,timeline.transition*.78):0;
      let height=rowHeight,opacity=intro,translate=(1-intro)*4;
      if(kind==='delete'){height=rowHeight*(1-resolve);opacity=intro*(1-resolve*.96);translate=-resolve*5;}
      if(kind==='insert'){height=rowHeight*insertion;opacity=insertion;translate=(1-insertion)*-5;}
      element.style.height=`${Math.max(0,height)}px`;
      element.style.opacity=String(clamp(opacity));
      element.style.transform=`translate3d(0,${translate}px,0)`;
      const strength=kind==='delete'?deletion*(1-resolve):insertion*(1-resolve*.90);
      element.style.backgroundColor=kind==='delete'?`rgba(248,81,73,${.18*strength})`:kind==='insert'?`rgba(46,160,67,${.18*strength})`:'transparent';
      element.querySelector('.change-rail').style.opacity=String(strength);
      element.querySelector('.diff-marker').style.opacity=String(strength);
      if(kind==='delete'){
        const strike=element.querySelector('.delete-strike'),text=element.querySelector('.code-text');strike.style.width=`${Math.max(12,text.scrollWidth-32)}px`;strike.style.transform=`scaleX(${deletion})`;strike.style.opacity=String(deletion*(1-resolve));
        element.querySelector('.code-text').style.opacity=String(1-deletion*.20);
      }
      const oldNumber=element.querySelector('.old-number'),newNumber=element.querySelector('.new-number');
      oldNumber.style.opacity=String(.48*(1-resolve));newNumber.style.opacity=String(.48*Math.max(resolve,kind==='insert'?insertion:0));
    });
    const firstChanged=rows.find((_,i)=>options.rows[i].kind!=='equal');
    const focusP=smooth((elapsed-timeline.changeStart)/520);
    if(firstChanged){const target=Math.max(0,Math.min(content.scrollHeight-viewport.clientHeight,firstChanged.offsetTop-viewport.clientHeight*.42));content.style.transform=`translate3d(0,${-target*focusP}px,0)`;}
    if(elapsed<timeline.changeStart)badge.textContent='Original';else if(elapsed<timeline.resolveEnd)badge.textContent='Changes detected';else badge.textContent='Updated';
    scrubber.value=String(elapsed/timeline.duration*1000);document.getElementById('timecode').textContent=`${(elapsed/1000).toFixed(1)} / ${(timeline.duration/1000).toFixed(1)}s`;
    content.dataset.time=elapsed.toFixed(1);if(Math.abs(elapsed-lastReported)>80){report();lastReported=elapsed;}
  }
  function report(){playButton.textContent=playing?'Pause':'Play';if(parent!==window)parent.postMessage({type:'diff:state',playing,time:elapsed,duration:timeline.duration,language:options.language,theme:options.theme,stats:options.stats},'*');}
  function tick(stamp){if(!playing)return;if(lastStamp!==null)elapsed+=stamp-lastStamp;lastStamp=stamp;if(elapsed>=timeline.duration){if(options.loop)elapsed%=timeline.duration;else{draw(timeline.duration);pause();return}}draw(elapsed);raf=requestAnimationFrame(tick);}
  function play(){if(playing)return;if(elapsed>=timeline.duration)elapsed=0;playing=true;lastStamp=null;raf=requestAnimationFrame(tick);report();}
  function pause(){playing=false;cancelAnimationFrame(raf);lastStamp=null;report();}
  function seek(time){pause();draw(time);report();}
  function restart(){pause();draw(0);play();}
  playButton.addEventListener('click',()=>playing?pause():play());document.getElementById('restart').addEventListener('click',restart);
  scrubber.addEventListener('input',()=>seek(Number(scrubber.value)/1000*timeline.duration));
  window.addEventListener('message',event=>{if(event.source!==parent||event.data?.type!=='diff:command')return;if(event.data.action==='toggle')playing?pause():play();if(event.data.action==='restart')restart();if(event.data.action==='seek')seek(Number(event.data.progress)*timeline.duration);});
  window.addEventListener('resize',fit);document.addEventListener('visibilitychange',()=>{lastStamp=null});
  window.codeDiff=Object.freeze({play,pause,restart,seek,duration:timeline.duration});
  document.fonts.ready.then(()=>{rowHeight=parseFloat(getComputedStyle(rows[0]||content).height)||rowHeight;fit();draw(reduced?timeline.duration:0);if(options.autoplay&&!reduced)play();else report();});
})();
