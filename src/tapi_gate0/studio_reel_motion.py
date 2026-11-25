"""CAP-023 draft-only motion: animate a lower content card independently."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from PIL import Image, ImageDraw, ImageFont
from .studio_e1 import StudioError


def encode_social_motion(frames, audio, *, editorial=False, kinetic=False):
    from .studio_render_e6 import MAX_OUTPUT_BYTES, FFMPEG_TIMEOUT_SECONDS
    if len(frames) != 3 or [d for _,d in frames] != [3000,7000,5000]:
        raise StudioError('STUDIO_MOTION_TIMELINE_REQUIRED',422)
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        raise StudioError('STUDIO_FFMPEG_UNAVAILABLE_OR_FAILED',503)
    with tempfile.TemporaryDirectory(prefix='tapi_motion_') as folder:
        root=Path(folder)
        env={**{k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','TMP','TEMP') if k in os.environ},'HOME':str(root)}
        deadline=time.monotonic()+FFMPEG_TIMEOUT_SECONDS
        def run(args):
            try:
                subprocess.run([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y',*args],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=max(0.01,deadline-time.monotonic()),check=True)
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired,FileNotFoundError) as exc:
                raise StudioError('STUDIO_FFMPEG_UNAVAILABLE_OR_FAILED',503) from exc
        for i,(png,duration) in enumerate(frames):
            with Image.open(io.BytesIO(png)) as im:
                if im.size != (1080,1920):
                    raise StudioError('STUDIO_SOCIAL_VERTICAL_FRAME_REQUIRED',422)
                base=im.convert('RGB')
            card=base.crop((80,1010,1000,1510));card.save(root/'card.png')
            draw=ImageDraw.Draw(base);bg=base.getpixel((20,1010));draw.rectangle((80,1010,999,1509),fill=bg)
            if editorial:
                base.crop((80,320,1000,790)).save(root/'title.png')
                draw.rectangle((80,320,999,789),fill=base.getpixel((20,320)))
            if kinetic:
                for name, top, bottom in [('lead',320,550),('hero',550,790),('art',810,990)]:
                    base.crop((80,top,1000,bottom)).save(root/(name+'.png'))
                    draw.rectangle((80,top,999,bottom-1),fill=base.getpixel((20,top)))
            draw.rounded_rectangle((80,1580,1000,1598),radius=9,fill='#A4B7A8')
            draw.rounded_rectangle((80,1580,80+round(920*(i+1)/3),1598),radius=9,fill='#43A878')
            draw.rounded_rectangle((72,1710,580,1772),radius=14,fill='#102D22')
            draw.text((92,1724),'RASCUNHO - NAO PUBLICAR',font=ImageFont.load_default(size=30),fill='white')
            base.save(root/'base.png')
            # The artwork is stationary; only the card translates. All variants use the same easing.
            filt="[0:v][1:v]overlay=x=80:y='1010+54*pow(max(0,1-t/0.40),2)':eval=frame,format=yuv420p,setsar=1[v]"
            inputs=['-loop','1','-framerate','30','-i','base.png','-loop','1','-framerate','30','-i','card.png']
            if editorial:
                inputs+=['-loop','1','-framerate','30','-i','title.png']
                filt="[0:v][2:v]overlay=x='80-36*pow(max(0,1-t/0.30),2)':y=320:eval=frame[h];[h][1:v]overlay=x=80:y='1010+54*pow(max(0,1-max(0,t-0.16)/0.40),2)':eval=frame,format=yuv420p,setsar=1[v]"
            if kinetic:
                for name in ('lead','hero','art'):
                    inputs+=['-loop','1','-framerate','30','-i',name+'.png']
                filt=("[0:v][2:v]overlay=x=80:y=320:enable='gte(t,0.10)'[a];"
                      "[a][3:v]overlay=x=80:y=550:enable='gte(t,0.30)'[b];"
                      "[b][4:v]overlay=x='80-28*pow(max(0,1-max(0,t-0.46)/0.28),2)':y=810:enable='gte(t,0.46)':eval=frame[c];"
                      "[c][1:v]overlay=x=80:y='1010+40*pow(max(0,1-max(0,t-0.64)/0.32),2)':enable='gte(t,0.64)':eval=frame,format=yuv420p,setsar=1[v]")
            run(['-filter_complex_threads','1',*inputs,'-filter_complex',filt,'-map','[v]','-an','-c:v','libx264','-threads','2','-preset','veryfast','-crf','23','-r','30','-t',f'{duration/1000:.3f}',f'scene{i}.mp4'])
        (root/'concat.txt').write_text(''.join(f"file 'scene{i}.mp4'\n" for i in range(3)),encoding='ascii')
        args=['-f','concat','-safe','1','-i','concat.txt']
        if audio is not None:
            (root/'audio.wav').write_bytes(audio);args+=['-i','audio.wav','-map','0:v:0','-map','1:a:0','-af','apad','-c:a','aac','-b:a','64k']
        else:
            args+=['-map','0:v:0','-an']
        run([*args,'-c:v','copy','-t','15','-movflags','+faststart','draft.mp4'])
        out=root/'draft.mp4'
        if not out.is_file() or not 0 < out.stat().st_size <= MAX_OUTPUT_BYTES:
            raise StudioError('STUDIO_RENDER_OUTPUT_SIZE_INVALID',422)
        return out.read_bytes()
