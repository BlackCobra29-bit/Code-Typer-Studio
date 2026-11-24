(() => {
  'use strict';
  const bytes = Uint8Array.from(atob(document.getElementById('terminal-model').textContent), c => c.charCodeAt(0));
  const m = JSON.parse(new TextDecoder().decode(bytes));
  const stage = document.getElementById('stage'), terminal = document.getElementById('terminal'), screen = document.getElementById('screen');
  Object.assign(stage.style, {width:`${m.width}px`,height:`${m.height}px`,background:m.background});
  stage.classList.toggle('padded', m.x > 0);
  Object.assign(terminal.style,{left:`${m.x}px`,top:`${m.y}px`,width:`${m.windowWidth}px`,height:`${m.windowHeight}px`});
  Object.assign(screen.style,{left:`${m.inset-1}px`,top:`${m.chrome+m.inset-1}px`,width:`${m.columns*m.cellWidth+m.cellWidth}px`,height:`${m.visibleRows*m.rowHeight}px`,fontSize:`${m.fontSize}px`,lineHeight:`${m.rowHeight}px`});
  document.getElementById('title').textContent = m.title;
  function fit() {
    const scale = Math.min(innerWidth/m.width, innerHeight/m.height);
    stage.style.transform = `translate(${(innerWidth-m.width*scale)/2}px,${(innerHeight-m.height*scale)/2}px) scale(${scale})`;
  }
  addEventListener('resize',fit); fit();
  function prefix(tokens,count) {
    const result=[];
    for(const item of tokens){if(count<=0)break; const chars=Array.from(item.text); result.push({...item,text:chars.slice(0,count).join('')});count-=chars.length;}
    return result;
  }
  function wrap(tokens) {
    const rows=[[]];let column=0;
    for(const item of tokens)for(const char of item.text){
      if(char==='\n'){rows.push([]);column=0;continue;}
      for(const glyph of char==='\t'?' '.repeat(8-column%8):char){
        if(column>=m.columns){rows.push([]);column=0;}
        rows[rows.length-1].push({...item,text:glyph});column++;
      }
    }
    return rows;
  }
  let current=0,playing=true,lastStamp=null,lastKey='',lastReport=0;
  function render(time){
    let count=0;
    for(const event of m.events){if(event.at>time)break;count=event.count;}
    const outputCount=Math.min(m.output.length,Math.max(0,Math.floor((time-m.outputStart)/m.outputInterval)+1));
    const done=time>=m.done, cursor=(time<m.outputStart||done)&&Math.floor(time/530)%2===0;
    const key=JSON.stringify([count,outputCount,done,cursor]);
    if(key===lastKey)return; lastKey=key;
    let rows=wrap([...m.prompt,...prefix(m.command,count)]).concat(m.output.slice(0,outputCount));
    if(done)rows=rows.concat(wrap(m.prompt));
    const length=row=>row.reduce((n,t)=>n+Array.from(t.text).length,0);
    if((!outputCount||done)&&length(rows[rows.length-1])>=m.columns)rows.push([]);
    rows=rows.slice(-m.visibleRows);
    const fragment=document.createDocumentFragment();
    rows.forEach((row,index)=>{
      const line=document.createElement('div');line.className='row';line.style.height=`${m.rowHeight}px`;
      for(const item of row){
        const span=document.createElement('span');span.textContent=item.text;
        Object.assign(span.style,{color:item.color,fontWeight:item.bold?'700':'400',fontStyle:item.italic?'italic':'normal',textDecoration:item.underline?'underline':'none',backgroundColor:item.background||'transparent'});
        line.append(span);
      }
      if(cursor&&index===rows.length-1){const caret=document.createElement('i');caret.className='cursor';Object.assign(caret.style,{left:`${length(row)*m.cellWidth}px`,width:`${m.cellWidth}px`,height:`${m.fontSize+4}px`});line.append(caret);}
      fragment.append(line);
    });
    screen.replaceChildren(fragment);
  }
  function report(){if(parent!==window)parent.postMessage({type:'terminal:state',time:current,duration:m.duration,playing},'*');}
  addEventListener('message',event=>{
    if(event.source!==parent)return;
    const data=event.data;
    if(data==='terminal:restart'){current=0;playing=true;lastStamp=null;}
    else if(data?.type==='terminal:toggle')playing=!playing;
    else if(data?.type==='terminal:seek'){const value=Number(data.time);if(!Number.isFinite(value))return;current=Math.max(0,Math.min(m.duration,value));playing=false;}
    else return;
    render(current);report();
  });
  function tick(stamp){
    if(playing&&lastStamp!==null){current+=Math.min(100,stamp-lastStamp);if(current>=m.duration){if(m.loop)current%=m.duration;else{current=m.duration;playing=false;}}}
    lastStamp=stamp;render(current);
    if(stamp-lastReport>100){report();lastReport=stamp;}
    requestAnimationFrame(tick);
  }
  document.fonts.ready.then(()=>{render(0);report();requestAnimationFrame(tick);});
})();
