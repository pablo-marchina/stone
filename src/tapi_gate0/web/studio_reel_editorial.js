/* Original editorial illustrations and role-specific Reel framing, no source mutation. */
(function(root){
  'use strict';
  const dark='#12352A', paper='#F7F3E8', lime='#C9F36B', green='#196646', gold='#F4C66A';
  function frame(doc,index,kinetic=false){
    if(doc.canvas.width!==1080||doc.canvas.height!==1350||doc.platform_intent!=='instagram_carousel'||doc.pages.length!==3||!Number.isInteger(index)||index<0||index>2)throw Error('Editorial requer carrossel textual de três páginas.');
    const p=doc.pages[index], ls=new Map(p.layers.map(l=>[l.id,l]));
    if(p.layers.some(l=>l.kind!=='text')||!['headline','body','cta'].every(id=>ls.has(id)))throw Error('Camadas de conteúdo obrigatórias.');
    const text=id=>ls.get(id).text;
    const canvas=document.createElement('canvas');canvas.width=1080;canvas.height=1920;const c=canvas.getContext('2d');
    const bg=index===1?paper:dark, fg=index===1?dark:paper, accent=index===1?green:lime;
    const box=(x,y,w,h,r,color)=>{c.fillStyle=color;c.beginPath();c.roundRect(x,y,w,h,r);c.fill();};
    const line=(x,y,x2,y2,color,w=10)=>{c.strokeStyle=color;c.lineWidth=w;c.lineCap='round';c.beginPath();c.moveTo(x,y);c.lineTo(x2,y2);c.stroke();};
    const circle=(x,y,r,color)=>{c.fillStyle=color;c.beginPath();c.arc(x,y,r,0,2*Math.PI);c.fill();};
    function write(value,x,y,w,h,max,min,color,weight=700){
      for(let size=max;size>=min;size-=2){c.font=weight+' '+size+'px sans-serif';const step=Math.ceil(size*1.15),lines=[];for(const para of value.split('\n')){let row='';for(const word of para.split(/\s+/).filter(Boolean)){const next=row?row+' '+word:word;if(row&&c.measureText(next).width>w){lines.push(row);row=word;}else row=next;}if(row)lines.push(row);}if(lines.length&&lines.length*step<=h&&lines.every(l=>c.measureText(l).width<=w)){c.fillStyle=color;c.textBaseline='top';lines.forEach((l,i)=>c.fillText(l,x,y+i*step));return;}}
      throw Error('Texto não cabe na composição editorial. Edite a camada ou selecione outro preset.');
    }
    c.fillStyle=bg;c.fillRect(0,0,1080,1920);
    box(80,175,60,60,16,accent);line(96,204,111,220,bg,8);line(111,220,126,190,bg,8);
    write('GESTÃO NA PRÁTICA',160,187,650,58,36,28,accent);write('0'+(index+1)+' / 03',830,187,170,55,32,26,accent);
    line(80,270,1000,270,accent,3);
    // Title zone (80,320,1000,790): flat background, isolated for the encoder.
    write(['COMECE AQUI','UMA AÇÃO POR VEZ','SEU PRÓXIMO PASSO'][index],80,330,920,60,40,30,accent);
    if(kinetic){
      const words=text('headline').trim().split(/\s+/);
      if(words.length<2)throw Error('Kinetic requer título com pelo menos duas palavras.');
      const split=Math.ceil(words.length/2), lead=words.slice(0,split).join(' '), hero=words.slice(split).join(' ');
      write(lead,80,414,920,132,106,44,fg);
      write(hero,80,565,920,205,144,52,accent);
    }else write(text('headline'),80,430,920,345,132,64,fg);
    // Hand-drawn vector motifs occupy a separate band; no external images or data claims.
    if(index===0){
      box(80,810,920,180,34,'#215544');
      box(118,858,180,105,10,paper);box(142,884,48,79,6,green);box(208,884,65,43,6,lime);
      for(let i=0;i<5;i++)box(108+i*39,835,39,38,5,i%2?gold:lime);
      write('PARA O SEU NEGÓCIO',340,854,620,110,46,30,paper);
    }else if(index===1){
      box(80,810,920,180,34,'#E1EAD9');box(118,837,150,126,14,green);box(132,864,122,87,6,paper);
      line(153,883,232,883,green,8);line(153,907,212,907,green,8);line(153,931,195,931,green,8);
      write('DA IDEIA À PRÁTICA',310,854,650,110,46,30,green);
    }else{
      box(80,810,920,180,34,'#215544');circle(175,900,57,lime);line(150,900,200,900,dark,9);line(185,882,203,900,dark,9);line(203,900,185,918,dark,9);
      write(text('body'),265,837,680,140,42,28,paper,400);
    }
    // Card zone (80,1010,1000,1510): independent entrance; no other objects overlap it.
    box(80,1010,920,500,46,index===1?dark:lime);
    const cardInk=index===1?paper:dark;
    write(index===2?'CONTINUE A CONVERSA':index===1?'FAÇA HOJE':'PENSE NISSO',130,1060,820,60,36,28,cardInk);
    line(130,1140,950,1140,cardInk,3);
    write(index===2?text('cta'):text('body'),130,1190,820,270,index===2?86:64,36,cardInk,index===2?700:400);
    return canvas;
  }
  async function toPng(doc,index,kinetic=false){const canvas=frame(doc,index,kinetic);return new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('PNG editorial indisponível')),'image/png'));}
  root.StoneReelEditorial={frame,toPng};
  root.StoneReelKinetic={frame:(doc,index)=>frame(doc,index,true),toPng:(doc,index)=>toPng(doc,index,true)};
})(globalThis);
