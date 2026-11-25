/* Derived, original social Reel frames. Never mutate the source Studio document. */
(function(root){
  'use strict';
  const ink='#102D22', cream='#F6F4EB', lime='#C9F36B', green='#176747';
  function frame(doc,index){
    if(doc.canvas.width!==1080||doc.canvas.height!==1350||doc.pages.length!==3||doc.platform_intent!=='instagram_carousel'||!Number.isInteger(index)||index<0||index>2)throw Error('Motion requer carrossel textual de três páginas.');
    const p=doc.pages[index], layers=new Map(p.layers.map(l=>[l.id,l]));
    if(p.layers.some(l=>l.kind!=='text')||!['headline','body','cta'].every(id=>layers.has(id)))throw Error('Camadas de conteúdo obrigatórias.');
    const text=id=>layers.get(id).text;
    const canvas=document.createElement('canvas');canvas.width=1080;canvas.height=1920;const c=canvas.getContext('2d');
    const bg=index===1?cream:ink, fg=index===1?ink:cream, accent=index===1?green:lime;
    c.fillStyle=bg;c.fillRect(0,0,1080,1920);
    const box=(x,y,w,h,r,color)=>{c.fillStyle=color;c.beginPath();c.roundRect(x,y,w,h,r);c.fill();};
    function write(value,x,y,w,h,max,min,color,weight=700){
      for(let size=max;size>=min;size-=2){c.font=weight+' '+size+'px sans-serif';const lineH=Math.ceil(size*1.16);const lines=[];for(const paragraph of value.split('\n')){let line='';for(const word of paragraph.split(/\s+/).filter(Boolean)){const next=line?line+' '+word:word;if(c.measureText(next).width>w&&line){lines.push(line);line=word;}else line=next;}if(line)lines.push(line);}if(lines.length&&lines.length*lineH<=h&&lines.every(l=>c.measureText(l).width<=w)){c.textBaseline='top';c.fillStyle=color;lines.forEach((l,i)=>c.fillText(l,x,y+i*lineH));return;}}
      throw Error('Texto não cabe na composição Motion. Edite a camada ou use o preset anterior.');
    }
    function line(x1,y1,x2,y2,color,width=8){c.strokeStyle=color;c.lineWidth=width;c.lineCap='round';c.beginPath();c.moveTo(x1,y1);c.lineTo(x2,y2);c.stroke();}
    write('GESTÃO NA PRÁTICA',80,182,760,64,40,32,accent);
    write('0'+(index+1)+' / 03',810,182,180,60,34,28,accent);
    line(80,270,1000,270,accent,3);
    if(index===0){
      write('COMECE AQUI',80,320,880,60,42,34,accent);
      write(text('headline'),80,414,920,420,150,76,fg);
      // Original graphic: rising steps, with no claims or data encoded.
      for(let i=0;i<4;i++)box(80+i*132,930-i*24,104,22+i*24,10,lime);
      box(80,1010,920,500,40,lime);write(text('body'),132,1070,816,382,72,42,ink,700);
    }else if(index===1){
      write('NA PRÁTICA',80,320,900,64,44,34,accent);
      write(text('headline'),80,426,920,300,132,70,fg);
      // Original check graphic, isolated from text.
      box(80,780,160,160,36,green);line(120,860,151,891,cream,16);line(151,891,203,826,cream,16);
      write('UMA AÇÃO DE CADA VEZ',280,818,700,100,44,32,green);
      box(80,1010,920,500,40,ink);write(text('body'),132,1070,816,382,70,40,cream,400);
    }else{
      write('O PRÓXIMO PASSO',80,320,920,64,42,34,accent);
      write(text('headline'),80,420,920,300,132,70,fg);
      write(text('body'),80,770,920,205,48,32,cream,400);
      box(80,1010,920,500,48,lime);write(text('cta'),132,1090,816,270,92,48,ink);
      line(132,1410,235,1410,ink,12);line(235,1410,208,1383,ink,12);line(235,1410,208,1437,ink,12);
    }
    return canvas;
  }
  async function toPng(doc,index){const canvas=frame(doc,index);return new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('PNG Motion indisponível')),'image/png'));}
  root.StoneReelMotion={frame,toPng};
})(globalThis);
