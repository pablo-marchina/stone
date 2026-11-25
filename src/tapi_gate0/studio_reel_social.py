"""Bounded native vertical motion preset for the rights-checked E6 worker."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont
from .studio_e1 import StudioError


def encode_social_vertical(frames, audio):
    from .studio_render_e6 import MAX_OUTPUT_BYTES, MAX_RENDER_SCENES, MAX_RENDER_MILLISECONDS, FFMPEG_TIMEOUT_SECONDS
    if not frames or len(frames) > MAX_RENDER_SCENES or sum(d for _, d in frames) > MAX_RENDER_MILLISECONDS or any(d <= 0 for _, d in frames):
        raise StudioError('STUDIO_RENDER_LOCAL_PILOT_LIMIT',422)
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        raise StudioError('STUDIO_FFMPEG_UNAVAILABLE_OR_FAILED',503)
    with tempfile.TemporaryDirectory(prefix='tapi_social_reel_') as folder:
        root=Path(folder)
        cmd=[ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-threads','1','-filter_complex_threads','1']
        filters=[]
        for i,(png,duration) in enumerate(frames):
            with Image.open(io.BytesIO(png)) as im:
                if im.size != (1080,1920):
                    raise StudioError('STUDIO_SOCIAL_VERTICAL_FRAME_REQUIRED',422)
                canvas=im.convert('RGB')
            draw=ImageDraw.Draw(canvas)
            draw.rounded_rectangle((72,1710,580,1772),radius=14,fill='#102D22')
            draw.text((92,1724),'RASCUNHO - NAO PUBLICAR',font=ImageFont.load_default(size=30),fill='white')
            path=root/f'frame{i}.png';canvas.save(path,'PNG')
            cmd+=['-i',str(path)]
            n=max(1,round(duration*30/1000))
            # Small centered push-in. No crop of text inside the prescribed safe margins.
            filters.append(f"[{i}:v]zoompan=z='1+0.018*on/{n}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={n}:s=1080x1920:fps=30,format=yuv420p,setsar=1[v{i}]")
        if audio is not None:
            wav=root/'audio.wav';wav.write_bytes(audio);cmd+=['-i',str(wav)]
        filters.append(''.join(f'[v{i}]' for i in range(len(frames)))+f'concat=n={len(frames)}:v=1:a=0[v]')
        cmd+=['-filter_complex',';'.join(filters),'-map','[v]']
        if audio is None:
            cmd+=['-an']
        else:
            cmd+=['-map',f'{len(frames)}:a:0','-af','apad','-c:a','aac','-b:a','64k']
        out=root/'draft.mp4'
        cmd+=['-c:v','libx264','-threads','1','-preset','ultrafast','-crf','27','-r','30','-pix_fmt','yuv420p','-t',f'{sum(d for _,d in frames)/1000:.3f}','-movflags','+faststart',str(out)]
        try:
            subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=FFMPEG_TIMEOUT_SECONDS,check=True,cwd=root,env={**{k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','TMP','TEMP') if k in os.environ},'HOME':str(root)})
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired,FileNotFoundError) as exc:
            raise StudioError('STUDIO_FFMPEG_UNAVAILABLE_OR_FAILED',503) from exc
        if not out.is_file() or not 0 < out.stat().st_size <= MAX_OUTPUT_BYTES:
            raise StudioError('STUDIO_RENDER_OUTPUT_SIZE_INVALID',422)
        return out.read_bytes()
