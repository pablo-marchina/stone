// CAP-023 / IMP-184: deterministic, dependency-free *draft preview* renderer.
// No network, no publication, no third-party SDK, no AI; this exports an exact
// immutable DesignDocument version snapshot to PNG/JPEG/SVG or ZIP of pages.
(function (root) {
  'use strict';
  function layout(text, ctx, width, lineHeight, height) {
    const lines=[];let offset=0;
    for (const paragraph of String(text).split('\n')) {
      let line='';
      for (const word of paragraph.split(/\s+/)) {
        const next=line?line+' '+word:word;
        if (line && ctx.measureText(next).width>width) {
          if (offset+lineHeight>height)return lines;
          lines.push({text:line,y:offset});offset+=lineHeight;line=word;
        } else line=next;
      }
      if (offset+lineHeight>height)return lines;
      if (line)lines.push({text:line,y:offset});
      offset+=lineHeight;
    }
    return lines;
  }
  function drawTo(ctx, doc, page, bitmaps, preview=null) {
    const {width,height,background}=doc.canvas;
    ctx.canvas.width=width;ctx.canvas.height=height;
    ctx.fillStyle=background;ctx.fillRect(0,0,width,height);
    for (const layer of page.layers) {
      const move=preview?.id===layer.id?preview:{dx:0,dy:0};
      const x=layer.x+(move.dx||0),y=layer.y+(move.dy||0);
      if(layer.kind==='text') {
        const size=layer.style.font_size;
        ctx.fillStyle=layer.style.color;ctx.textBaseline='top';
        ctx.font=size+'px sans-serif';
        for(const line of layout(layer.text,ctx,layer.w,size*1.2,layer.h))
          ctx.fillText(line.text,x,y+line.y);
      } else if(layer.kind==='image') {
        if(!bitmaps.has(layer.asset_id)) {
          ctx.fillStyle='#E6EFE9';ctx.fillRect(x,y,layer.w,layer.h);
        } else ctx.drawImage(bitmaps.get(layer.asset_id),x,y,layer.w,layer.h);
      }
    }
    // All current DesignDocuments are drafts with pending editorial/rights review.
    // Mark derived output so it cannot be mistaken for approved publication art.
    if(doc.approval_status!=='approved'||doc.rights_status!=='approved') {
      ctx.save();ctx.font='22px sans-serif';ctx.textAlign='right';
      ctx.fillStyle='rgba(130,40,40,0.85)';
      ctx.fillText('RASCUNHO - NAO PUBLICAR',width-18,height-20);
      ctx.restore();
    }
  }
  function createCanvas(doc) {
    const canvas=document.createElement('canvas');
    canvas.width=doc.canvas.width;canvas.height=doc.canvas.height;
    return canvas;
  }
  async function toRaster(doc,page,bitmaps,format) {
    const canvas=createCanvas(doc),ctx=canvas.getContext('2d');
    drawTo(ctx,doc,page,bitmaps);
    const type=format==='jpeg'?'image/jpeg':'image/png';
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,type,format==='jpeg'?0.92:undefined));
    if(!blob)throw Error('Não foi possível renderizar '+format);
    return blob;
  }
  function escapeXml(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));}
  async function toSvg(doc,page,bitmaps) {
    const c=createCanvas(doc),ctx=c.getContext('2d');
    const {width,height,background}=doc.canvas;
    let body=`<rect width="${width}" height="${height}" fill="${background}"/>`;
    for(const layer of page.layers) {
      const {x,y,w,h}=layer;
      if(layer.kind==='text') {
        const size=layer.style.font_size;
        ctx.font=size+'px sans-serif';
        for(const line of layout(layer.text,ctx,w,size*1.2,h)) {
          body+=`<text x="${x}" y="${y+line.y+size}" fill="${layer.style.color}" font-family="sans-serif" font-size="${size}">${escapeXml(line.text)}</text>`;
        }
      } else {
        const bmp=bitmaps.get(layer.asset_id);
        if(!bmp)throw Error('Ativo não carregado');
        const image=document.createElement('canvas');image.width=bmp.width;image.height=bmp.height;
        image.getContext('2d').drawImage(bmp,0,0);
        const png=image.toDataURL('image/png');
        body+=`<image x="${x}" y="${y}" width="${w}" height="${h}" href="${png}"/>`;
      }
    }
    if(doc.approval_status!=='approved'||doc.rights_status!=='approved')
      body+=`<text x="${width-18}" y="${height-20}" text-anchor="end" fill="#8b2020" font-size="22" font-family="sans-serif">RASCUNHO - NAO PUBLICAR</text>`;
    // SVG is generated from validated typed nodes, never external SVG/HTML.
    return new Blob([`<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${body}</svg>`],{type:'image/svg+xml'});
  }
  function crc32(bytes) {
    let crc=-1;
    for(let i=0;i<bytes.length;i++){
      crc^=bytes[i];for(let j=0;j<8;j++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);
    }
    return (crc^-1)>>>0;
  }
  function u16(v) {return [v&255,(v>>>8)&255];}
  function u32(v) {return [v&255,(v>>>8)&255,(v>>>16)&255,(v>>>24)&255];}
  async function zipArchive(entries) {
    const local=[],central=[];let offset=0;
    const encoder=new TextEncoder();
    for(const entry of entries) {
      const name=encoder.encode(entry.name),data=new Uint8Array(await entry.blob.arrayBuffer());
      if(name.length>200||data.length>75*1024*1024)throw Error('ZIP excede limite');
      const crc=crc32(data),n=data.length;
      const lh=Uint8Array.from([80,75,3,4,...u16(20),...u16(0x800),...u16(0),
        ...u16(0),...u16(33),...u32(crc),...u32(n),...u32(n),...u16(name.length),...u16(0)]);
      local.push(lh,name,data);
      const ch=Uint8Array.from([80,75,1,2,...u16(20),...u16(20),...u16(0x800),
        ...u16(0),...u16(0),...u16(33),...u32(crc),...u32(n),...u32(n),
        ...u16(name.length),...u16(0),...u16(0),...u16(0),...u16(0),...u32(0),...u32(offset)]);
      central.push(ch,name);offset+=lh.length+name.length+n;
      if(offset>90*1024*1024)throw Error('ZIP excede limite total');
    }
    const centerSize=central.reduce((sum,c)=>sum+c.length,0);
    const eocd=Uint8Array.from([80,75,5,6,...u16(0),...u16(0),...u16(entries.length),
      ...u16(entries.length),...u32(centerSize),...u32(offset),...u16(0)]);
    return new Blob([...local,...central,eocd],{type:'application/zip'});
  }
  function sha256Bytes(bytes) {
    // FIPS 180-4 SHA-256 fallback for an offline/insecure preview harness.
    // Crypto.subtle is preferred when available on secure origins.
    const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    const H=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    const paddedLen=Math.ceil((bytes.length+9)/64)*64;
    const buf=new Uint8Array(paddedLen);buf.set(bytes);buf[bytes.length]=128;
    const view=new DataView(buf.buffer),bitLen=bytes.length*8;
    view.setUint32(paddedLen-8,Math.floor(bitLen/0x100000000));
    view.setUint32(paddedLen-4,bitLen>>>0);
    const rr=(n,b)=>(n>>>b)|(n<<(32-b));
    for(let i=0;i<paddedLen;i+=64){
      const w=new Uint32Array(64);for(let t=0;t<16;t++)w[t]=view.getUint32(i+t*4);
      for(let t=16;t<64;t++){
        const a=w[t-15],b=w[t-2];
        const s0=rr(a,7)^rr(a,18)^(a>>>3),s1=rr(b,17)^rr(b,19)^(b>>>10);
        w[t]=(w[t-16]+s0+w[t-7]+s1)>>>0;
      }
      let [a,b,c,d,e,f,g,h]=H;
      for(let t=0;t<64;t++){
        const s1=rr(e,6)^rr(e,11)^rr(e,25);
        const ch=(e&f)^((~e)&g);
        const t1=(h+s1+ch+K[t]+w[t])>>>0;
        const s0=rr(a,2)^rr(a,13)^rr(a,22);
        const maj=(a&b)^(a&c)^(b&c);
        const t2=(s0+maj)>>>0;
        h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
      }
      for(const [j,v] of [a,b,c,d,e,f,g,h].entries())H[j]=(H[j]+v)>>>0;
    }
    return H.map(v=>v.toString(16).padStart(8,'0')).join('');
  }
  async function sha256(blob) {
    const bytes=await blob.arrayBuffer();
    if(root.crypto?.subtle){
      const digest=await root.crypto.subtle.digest('SHA-256',bytes);
      return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
    }
    return sha256Bytes(new Uint8Array(bytes));
  }
  async function exportDocument(doc, pageId, bitmaps, format, archive=false) {
    if(!['png','jpeg','svg'].includes(format))throw Error('Formato inválido');
    if(!doc?.pages?.length||doc.pages.length>10)throw Error('Documento inválido');
    if(archive && doc.platform_intent!=='instagram_carousel')throw Error('ZIP somente carrossel');
    const pages=archive?doc.pages:[doc.pages.find(p=>p.id===pageId)];
    if(pages.some(p=>!p))throw Error('Página inválida');
    const assets=[...new Set(pages.flatMap(p=>p.layers.filter(l=>l.kind==='image').map(l=>l.asset_id)))];
    if(assets.some(id=>!bitmaps.has(id)))throw Error('Ativo de mídia não carregado');
    const entries=[];const manifest={schema_version:'studio-draft-export.v1',
      document_id:doc.document_id,version:doc.version,spec_id:doc.spec_id,
      rights_status:doc.rights_status,approval_status:doc.approval_status,
      render_status:'local_preview_only',format,
      dimensions:doc.canvas,pages:[]};
    for(let i=0;i<pages.length;i++){
      const page=pages[i];
      const blob=format==='svg'?await toSvg(doc,page,bitmaps):await toRaster(doc,page,bitmaps,format);
      const file=`page-${String(archive?doc.pages.indexOf(page)+1:1).padStart(2,'0')}.${format==='jpeg'?'jpg':format}`;
      manifest.pages.push({page_id:page.id,file,sha256:await sha256(blob),bytes:blob.size});
      entries.push({name:file,blob});
      await new Promise(resolve=>setTimeout(resolve,0)); // cooperative render of bounded pages
    }
    const fileBase=doc.document_id+'-v'+doc.version+'-RASCUNHO';
    if(!archive)return {blob:entries[0].blob,filename:fileBase+'-'+entries[0].name,manifest};
    entries.push({name:'manifest.json',blob:new Blob([JSON.stringify(manifest,null,2)],{type:'application/json'})});
    return {blob:await zipArchive(entries),filename:fileBase+'.zip',manifest};
  }
  root.StoneExport={drawTo,toRaster,toSvg,zipArchive,sha256,sha256Bytes,exportDocument,crc32};
})(globalThis);
