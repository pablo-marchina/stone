/* CAP-023 E8: visual, versioned storyboard/timeline editing and local draft queue.
 * No network URLs, auto-publish, automatic worker invocation or credentials in URLs.
 * Loaded before studio.mjs; all requests are made through its authenticated API.
 */
(function (root) {
  'use strict';
  const $ = id => document.getElementById(id);
  const clampInt = (value, min, max) => {
    const n = Number(value);
    if (!Number.isInteger(n) || n < min || n > max) throw Error('VALOR_FORA_DOS_LIMITES');
    return n;
  };
  const deepCopy = value => JSON.parse(JSON.stringify(value));
  function updateTimeline(document, sceneId, patch, requestedOrder) {
    const draft = deepCopy(document);
    const ids = draft.clips.map(x => x.scene_id);
    if (!ids.includes(sceneId)) throw Error('CENA_NAO_ENCONTRADA');
    if (requestedOrder) {
      if (requestedOrder.length !== ids.length || new Set(requestedOrder).size !== ids.length ||
          requestedOrder.some(id => !ids.includes(id))) throw Error('ORDEM_INVALIDA');
      const byId = new Map(draft.scenes.map(x => [x.scene_id, x]));
      const clips = new Map(draft.clips.map(x => [x.scene_id, x]));
      draft.scenes = requestedOrder.map(id => byId.get(id));
      draft.clips = requestedOrder.map(id => clips.get(id));
    }
    const scene = draft.scenes.find(x => x.scene_id === sceneId);
    const clip = draft.clips.find(x => x.scene_id === sceneId);
    if (patch) {
      if (patch.duration_ms !== undefined) {
        scene.duration_ms = clampInt(patch.duration_ms, 500, 30000);
        clip.duration_ms = scene.duration_ms;
      }
      if (patch.narration !== undefined) {
        if (typeof patch.narration !== 'string' || !patch.narration.trim() || patch.narration.length > 1000)
          throw Error('NARRACAO_INVALIDA');
        scene.narration = patch.narration;
      }
      if (patch.transition !== undefined) {
        if (!['cut','crossfade'].includes(patch.transition)) throw Error('TRANSICAO_INVALIDA');
        clip.transition = patch.transition;
        clip.transition_ms = patch.transition === 'cut' ? 0 : clampInt(patch.transition_ms,100,500);
      }
      if (patch.overlay_text !== undefined) {
        const text = String(patch.overlay_text).trim();
        if (text.length > 500) throw Error('OVERLAY_INVALIDO');
        const old = scene.overlays?.[0] || {};
        if (!text) scene.overlays = (scene.overlays||[]).slice(1);
        else {
          const endMs = Math.min(scene.duration_ms, Math.max(500, old.end_ms || 1500));
          const keyframes = patch.keyframes || old.keyframes || [];
          if (keyframes.length > 20 || keyframes.some(k => !Number.isInteger(k.at_ms) ||
              k.at_ms < 0 || k.at_ms > endMs ||
              !Number.isInteger(k.x) || k.x < 0 || k.x > 1000 ||
              !Number.isInteger(k.y) || k.y < 0 || k.y > 1000 ||
              !Number.isInteger(k.opacity) || k.opacity < 0 || k.opacity > 100))
            throw Error('KEYFRAME_FORA_DOS_LIMITES');
          const times = keyframes.map(k=>k.at_ms);
          if (new Set(times).size !== times.length || times.some((v,i)=>i>0 && v<times[i-1]))
            throw Error('KEYFRAME_ORDEM_INVALIDA');
          scene.overlays = [{...old, text, start_ms:0, end_ms:endMs, keyframes},
            ...(scene.overlays||[]).slice(1)];
        }
      }
    }
    // Clamp old text overlays when scene is shortened; cannot preserve invalid keyframes.
    for (const item of draft.scenes) {
      item.overlays = item.overlays.map(overlay => ({...overlay,
        end_ms: Math.min(overlay.end_ms, item.duration_ms),
        keyframes: overlay.keyframes.filter(k => k.at_ms <= Math.min(overlay.end_ms,item.duration_ms))}));
    }
    let elapsed = 0;
    for (const item of draft.clips) {
      item.start_ms = elapsed;
      elapsed += item.duration_ms;
    }
    if (elapsed > 180000) throw Error('TIMELINE_LONGA_DEMAIS');
    // The last scene cannot transition to a missing following scene.
    const last = draft.clips[draft.clips.length-1];
    last.transition = 'cut'; last.transition_ms = 0;
    for (let i=0; i<draft.clips.length-1; i++) {
      const thisClip = draft.clips[i], next = draft.clips[i+1];
      if (thisClip.transition === 'crossfade' &&
          thisClip.transition_ms > Math.floor(Math.min(thisClip.duration_ms,next.duration_ms)/2))
        throw Error('CROSSFADE_MAIOR_QUE_CENA');
    }
    return { expected_version: document.version, scenes:draft.scenes, clips:draft.clips };
  }
  function formatTime(ms) {return (ms/1000).toFixed(1).replace('.',',')+'s';}
  async function asBase64(file, maxSize) {
    if (!file || file.size < 100 || file.size > maxSize) throw Error('ARQUIVO_FORA_DO_LIMITE');
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary=''; for (let i=0;i<bytes.length;i+=16384)
      binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
    return btoa(binary);
  }
  function initTimelineEditor({api, canWrite, getToken, status}) {
    const state={storyboard:null, sceneId:null, bindings:new Map(), audioTracks:[],
                 currentJobId:null, currentArtifactId:null, dragged:null, busy:false};
    const timeline = $('timeline-visual');
    function needsWrite() {if (!canWrite()) throw Error('EDITOR_NAO_AUTORIZADO');}
    function selected() {return state.storyboard?.scenes.find(x=>x.scene_id===state.sceneId);}
    function clipSelected() {return state.storyboard?.clips.find(x=>x.scene_id===state.sceneId);}
    function controls() {
      const has=!!state.storyboard, edit=has && canWrite() && !state.busy;
      for (const id of ['timeline-save','timeline-bind-source','timeline-upload-video','timeline-upload-wav',
          'timeline-queue','timeline-attest-image','timeline-audio-add','timeline-revoke-source-audio'])
        $(id).disabled=!edit;
      $('timeline-open').disabled=state.busy;
      $('timeline-refresh').disabled=!state.currentJobId;
      $('timeline-download').disabled=!state.currentArtifactId;
    }
    function bindingFor(sceneId) {
      if (!state.bindings.has(sceneId)) state.bindings.set(sceneId,{
        video_asset_id:'',image_asset_id:'',trim_start_ms:0,
        include_source_audio:false,source_audio_gain_percent:100});
      return state.bindings.get(sceneId);
    }
    function displayScene() {
      const scene=selected(), clip=clipSelected();
      if (!scene || !clip) return;
      $('timeline-scene-id').textContent=scene.scene_id;
      $('timeline-duration').value=String(scene.duration_ms);
      $('timeline-narration').value=scene.narration;
      $('timeline-overlay').value=scene.overlays?.[0]?.text||'';
      const keyframes=scene.overlays?.[0]?.keyframes||[];
      const first=keyframes[0]||{x:100,y:100,opacity:100},
        last=keyframes[keyframes.length-1]||{x:350,y:100,opacity:100};
      for(const [id,value] of [['timeline-kf-x0',first.x],['timeline-kf-y0',first.y],
        ['timeline-kf-o0',first.opacity],['timeline-kf-x1',last.x],
        ['timeline-kf-y1',last.y],['timeline-kf-o1',last.opacity]]) $(id).value=String(value);
      $('timeline-transition').value=clip.transition;
      $('timeline-crossfade').value=String(clip.transition_ms||200);
      const media=bindingFor(scene.scene_id);
      $('timeline-video-id').value=media.video_asset_id||'';
      $('timeline-image-id').value=media.image_asset_id||'';
      $('timeline-trim').value=String(media.trim_start_ms);
      $('timeline-source-audio').checked=!!media.include_source_audio;
      $('timeline-source-gain').value=String(media.source_audio_gain_percent);
      $('timeline-scene-source').textContent='Ativos vinculados ao job; não modificam a origem do storyboard';
      controls();
    }
    function render() {
      timeline.replaceChildren();
      const story=state.storyboard;
      if (!story) {$('timeline-revision').textContent='Nenhum storyboard aberto';controls();return;}
      $('timeline-storyboard-id').value=story.storyboard_id;
      $('timeline-revision').textContent=`${story.storyboard_id} · versão ${story.version} · ${formatTime(story.clips.reduce((n,c)=>n+c.duration_ms,0))}`;
      const total=story.clips.reduce((n,c)=>n+c.duration_ms,0);
      const label=document.createElement('p');label.className='timeline-caption';
      label.textContent='Faixa de vídeo e sobreposições · arraste uma cena para reordenar';
      timeline.appendChild(label);
      const lane=document.createElement('div');lane.className='timeline-scene-lane';lane.setAttribute('role','group');
      lane.setAttribute('aria-label','Faixa visual do storyboard');
      for (const clip of story.clips) {
        const scene=story.scenes.find(x=>x.scene_id===clip.scene_id);
        const button=document.createElement('button');button.type='button';
        button.className='timeline-scene'+(clip.scene_id===state.sceneId?' selected':'');
        button.style.flexGrow=String(clip.duration_ms);
        button.style.flexBasis='0';
        button.dataset.sceneId=clip.scene_id;
        button.textContent=`${clip.scene_id} · ${formatTime(clip.duration_ms)} · ${clip.transition}`;
        button.title='Selecionar cena; Alt+seta esquerda/direita para reordenar';
        button.draggable=canWrite();
        button.setAttribute('aria-pressed',clip.scene_id===state.sceneId?'true':'false');
        button.addEventListener('click',()=>selectScene(clip.scene_id));
        button.addEventListener('dragstart',event=>{
          if (!canWrite()) {event.preventDefault();return;}
          state.dragged=clip.scene_id;event.dataTransfer.effectAllowed='move';
          event.dataTransfer.setData('text/plain',clip.scene_id);
        });
        button.addEventListener('dragover',event=>{if(state.dragged)event.preventDefault();});
        button.addEventListener('drop',event=>{
          event.preventDefault(); const id=state.dragged; state.dragged=null;
          if(id && id!==clip.scene_id) void reorderScene(id,clip.scene_id);
        });
        button.addEventListener('dragend',()=>{state.dragged=null;});
        button.addEventListener('keydown',event=>{
          if(!event.altKey || !['ArrowLeft','ArrowRight'].includes(event.key))return;
          event.preventDefault(); const index=story.clips.findIndex(x=>x.scene_id===clip.scene_id);
          const target=story.clips[index+(event.key==='ArrowLeft'?-1:1)];
          if(target) void reorderScene(clip.scene_id,target.scene_id);
        });
        lane.appendChild(button);
      }
      timeline.appendChild(lane);
      const overlay=document.createElement('div');overlay.className='timeline-overlay-lane';
      overlay.setAttribute('role','group');overlay.setAttribute('aria-label','Faixa de overlays');
      for(const clip of story.clips){
        const scene=story.scenes.find(x=>x.scene_id===clip.scene_id);
        const span=document.createElement('span');span.style.flexGrow=String(clip.duration_ms);span.style.flexBasis='0';
        span.textContent=scene.overlays?.length?`${scene.overlays.length} texto(s)`:'Sem texto';
        span.className='timeline-overlay-clip';overlay.appendChild(span);
      }
      timeline.appendChild(overlay);
      const audio=document.createElement('p');audio.className='timeline-caption';
      audio.textContent=`Áudio: ${state.audioTracks.length} faixa(s) WAV adicional(is). Áudio embutido exige atestação separada.`;
      timeline.appendChild(audio);
      if(!story.scenes.some(s=>s.scene_id===state.sceneId))state.sceneId=story.scenes[0].scene_id;
      displayScene();controls();
    }
    function selectScene(sceneId) {state.sceneId=sceneId;render();}
    function setStoryboard(story) {
      state.storyboard=story; state.sceneId=story.scenes.some(x=>x.scene_id===state.sceneId)?state.sceneId:story.scenes[0].scene_id;
      state.bindings.clear();state.audioTracks=[];state.currentJobId=null;state.currentArtifactId=null;
      render();status('Timeline versionada aberta. Fonte e áudio precisam ser atestados antes do render.');
    }
    async function openStory() {
      try{
        const id=$('timeline-storyboard-id').value.trim();
        if(!id)throw Error('INFORME_ID_STORYBOARD');
        const doc=await api('/v1/studio/storyboards/'+encodeURIComponent(id));setStoryboard(doc);
      }catch(error){status('Não foi possível abrir timeline: '+error.message);}
    }
    async function saveTimeline(patch,order) {
      needsWrite();if(!state.storyboard)throw Error('STORYBOARD_NAO_ABERTO');
      const body=updateTimeline(state.storyboard,state.sceneId,patch,order);
      const updated=await api('/v1/studio/storyboards/'+encodeURIComponent(state.storyboard.storyboard_id)+'/timeline',
        {method:'POST',payload:body});
      state.storyboard=updated;render();status('Timeline salva na versão '+updated.version);
    }
    async function saveSelected() {
      try{await saveTimeline({duration_ms:$('timeline-duration').value,
        narration:$('timeline-narration').value,
        overlay_text:$('timeline-overlay').value,
        keyframes:$('timeline-overlay').value.trim() ? [
          {at_ms:0,x:clampInt($('timeline-kf-x0').value,0,1000),
           y:clampInt($('timeline-kf-y0').value,0,1000),
           opacity:clampInt($('timeline-kf-o0').value,0,100)},
          {at_ms:Math.min(clampInt($('timeline-duration').value,500,30000),
                           Math.max(500, selected().overlays?.[0]?.end_ms||1500)),
           x:clampInt($('timeline-kf-x1').value,0,1000),
           y:clampInt($('timeline-kf-y1').value,0,1000),
           opacity:clampInt($('timeline-kf-o1').value,0,100)}] : [],
        transition:$('timeline-transition').value,
        transition_ms:$('timeline-crossfade').value});}
      catch(error){status('Alteração não aplicada: '+error.message);}
    }
    async function reorderScene(source,target) {
      try{
        const ids=state.storyboard.clips.map(x=>x.scene_id),start=ids.indexOf(source),dest=ids.indexOf(target);
        if(start<0||dest<0||start===dest)return;
        ids.splice(start,1);ids.splice(dest,0,source);
        await saveTimeline(null,ids);state.sceneId=source;render();
      }catch(error){status('Reordenação negada: '+error.message);}
    }
    function saveMediaBinding() {
      if(!selected())return;
      const binding=bindingFor(state.sceneId);
      binding.video_asset_id=$('timeline-video-id').value.trim();
      binding.image_asset_id=$('timeline-image-id').value.trim();
      binding.trim_start_ms=clampInt($('timeline-trim').value,0,30000);
      binding.include_source_audio=$('timeline-source-audio').checked;
      binding.source_audio_gain_percent=clampInt($('timeline-source-gain').value,0,100);
      if(!!binding.video_asset_id===!!binding.image_asset_id)throw Error('ESCOLHA_APENAS_MP4_OU_PNG');
      if(binding.image_asset_id && binding.include_source_audio)throw Error('AUDIO_EMBUTIDO_REQUER_MP4');
      status('Origem da cena preparada para o próximo job. Nenhum direito presumido.');
    }
    function expiry() {
      const d=$('timeline-expiry').value;
      if(!/^\d{4}-\d{2}-\d{2}$/.test(d))throw Error('INFORME_EXPIRACAO');
      return new Date(d+'T23:59:59Z').toISOString();
    }
    async function uploadVideo() {
      try{
        needsWrite();if(!$('timeline-video-rights').checked)throw Error('ATESTE_DIREITOS_VIDEO');
        const audioRights=$('timeline-embedded-rights').checked;
        const payload={data_base64:await asBase64($('timeline-video-file').files[0],7*1024*1024),
          evidence_reference:$('timeline-rights-ref').value.trim(),expires_at:expiry(),rights_attested:true,
          embedded_audio_rights_attested:audioRights};
        if(audioRights)payload.embedded_audio_evidence_reference=$('timeline-audio-rights-ref').value.trim();
        const result=await api('/v1/studio/video-sources/mp4',{method:'POST',payload});
        const b=bindingFor(state.sceneId);b.video_asset_id=result.asset_id;b.image_asset_id='';
        displayScene();status('Vídeo local autenticado e armazenado: '+result.asset_id);
      }catch(error){status('Vídeo rejeitado: '+error.message);}
    }
    async function revokeSourceAudio() {
      try{
        needsWrite();const asset=bindingFor(state.sceneId).video_asset_id;
        if(!asset)throw Error('INFORME_ID_VIDEO');
        const result=await api('/v1/studio/video-sources/'+encodeURIComponent(asset)+'/embedded-audio/revoke',
          {method:'POST'});
        $('timeline-source-audio').checked=false;
        status('Direito de áudio embutido revogado. Vídeo permanece separado.');
      }catch(error){status('Revogação não efetuada: '+error.message);}
    }
    async function attestImage() {
      try{
        needsWrite();if(!$('timeline-video-rights').checked)throw Error('ATESTE_DIREITOS_IMAGEM');
        const asset=$('timeline-image-id').value.trim();
        const result=await api('/v1/studio/assets/draft-render-rights',{method:'POST',payload:{
          asset_id:asset,evidence_reference:$('timeline-rights-ref').value.trim(),
          expires_at:expiry(),rights_attested:true}});
        status('Direitos locais de PNG atestados para rascunho.');
      }catch(error){status('Atestação PNG rejeitada: '+error.message);}
    }
    async function uploadWav(){
      try{
        needsWrite();if(!$('timeline-video-rights').checked)throw Error('ATESTE_DIREITOS_AUDIO');
        const data=await asBase64($('timeline-wav-file').files[0],2*1024*1024);
        const outcome=await api('/v1/studio/audio/wav',{method:'POST',payload:{
          data_base64:data,evidence_reference:$('timeline-rights-ref').value.trim(),
          expires_at:expiry(),rights_attested:true}});
        $('timeline-wav-id').value=outcome.asset_id;
        status('WAV autorizado recebido. Adicione-o à timeline.');
      }catch(error){status('WAV rejeitado: '+error.message);}
    }
    function addAudioTrack(){
      try{
        needsWrite();const asset=$('timeline-wav-id').value.trim();
        if(!asset)throw Error('INFORME_ID_WAV');
        if(state.audioTracks.length>=4)throw Error('LIMITE_FAIXAS_WAV');
        state.audioTracks.push({asset_id:asset,
          start_ms:clampInt($('timeline-wav-start').value,0,15000),
          gain_percent:clampInt($('timeline-wav-gain').value,0,100)});
        render();status('Faixa WAV adicionada ao rascunho do próximo job.');
      }catch(error){status('Faixa inválida: '+error.message);}
    }
    async function queue() {
      try{
        needsWrite();if(!state.storyboard)throw Error('STORYBOARD_NAO_ABERTO');
        const entries=state.storyboard.clips.map(clip=>{
          const b=bindingFor(clip.scene_id);
          if(!!b.video_asset_id===!!b.image_asset_id)throw Error('CENA_SEM_VIDEO_OU_PNG: '+clip.scene_id);
          if(b.video_asset_id)return {scene_id:clip.scene_id,video_asset_id:b.video_asset_id,
            trim_start_ms:b.trim_start_ms,include_source_audio:b.include_source_audio,
            source_audio_gain_percent:b.source_audio_gain_percent};
          return {scene_id:clip.scene_id,image_asset_id:b.image_asset_id};
        });
        const jobId='draft.'+crypto.randomUUID().replaceAll('-','').slice(0,22);
        const outcome=await api('/v1/studio/advanced-render-jobs',{method:'POST',payload:{
          job_id:jobId,storyboard_id:state.storyboard.storyboard_id,
          storyboard_version:state.storyboard.version,scenes:entries,
          audio_tracks:state.audioTracks,
          quality_profile:$('timeline-quality').value}});
        state.currentJobId=outcome.job_id;state.currentArtifactId=null;
        $('timeline-job-id').value=outcome.job_id;controls();
        status('Job em fila. Execute o worker local explicitamente; nenhuma execução automática.');
      }catch(error){status('Job não criado: '+error.message);}
    }
    async function refresh() {
      try{
        const id=$('timeline-job-id').value.trim()||state.currentJobId;
        if(!id)throw Error('INFORME_JOB_ID');
        const outcome=await api('/v1/studio/advanced-render-jobs/'+encodeURIComponent(id));
        state.currentJobId=outcome.job_id;state.currentArtifactId=outcome.artifact_id;
        $('timeline-job-status').textContent=outcome.status+' · tentativas '+outcome.attempts+
          (outcome.error_code?' · '+outcome.error_code:'');controls();
        status('Job '+outcome.status+' (somente rascunho).');
      }catch(error){status('Não foi possível consultar job: '+error.message);}
    }
    async function download() {
      try{
        const id=state.currentArtifactId;
        if(!id)throw Error('ARTEFATO_AINDA_NAO_EXISTE');
        // Never leak bearer credentials to a URL, query string or external player.
        const response=await fetch('/v1/studio/advanced-render-artifacts/'+encodeURIComponent(id),
          {headers:{Authorization:'Bearer '+getToken()},cache:'no-store'});
        if(!response.ok)throw Error('HTTP '+response.status);
        const blob=await response.blob();
        const url=URL.createObjectURL(blob),a=document.createElement('a');
        a.href=url;a.download='stone-rascunho-e8.mp4';document.body.appendChild(a);
        a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
        status('Rascunho MP4 salvo. Não aprovado para publicar.');
      }catch(error){status('Download bloqueado: '+error.message);}
    }
    function reset(){state.storyboard=null;state.sceneId=null;state.bindings.clear();state.audioTracks=[];
      state.currentJobId=null;state.currentArtifactId=null;render();}
    const actions=[['timeline-open',openStory],['timeline-save',saveSelected],
      ['timeline-bind-source',()=>{try{needsWrite();saveMediaBinding();}catch(error){status('Vínculo rejeitado: '+error.message);}}],
      ['timeline-upload-video',uploadVideo],['timeline-revoke-source-audio',revokeSourceAudio],
      ['timeline-attest-image',attestImage],['timeline-upload-wav',uploadWav],
      ['timeline-audio-add',addAudioTrack],['timeline-queue',queue],
      ['timeline-refresh',refresh],['timeline-download',download]];
    for(const [id,callback] of actions)$(id).addEventListener('click',()=>void callback());
    render();
    return {setStoryboard,reset,openStory,render};
  }
  root.StoneTimelineE8={initTimelineEditor,updateTimeline,formatTime};
})(window);
