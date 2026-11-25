"""Offline synthetic narration of a locally authored three-scene draft.

No network, voice cloning, permissions creation or operational corpus access.
Output requires the normal audio rights attestation before Studio use.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

DURATIONS = (3000, 7000, 5000)
STARTS = (350, 800, 800)
RATE = 16000


def synthesize(packet, output):
    if (packet.get('schema_version') != 'tapi-demo-reel-narration.v1' or
            not isinstance(packet.get('scenes'), list) or len(packet['scenes']) != 3):
        raise ValueError('NARRATION_PACKET_INVALID')
    texts = packet['scenes']
    if any(not isinstance(t, str) or not 1 <= len(t.strip()) <= 320 for t in texts):
        raise ValueError('NARRATION_TEXT_INVALID')
    engine = shutil.which('espeak-ng') or shutil.which('espeak')
    ffmpeg = shutil.which('ffmpeg')
    if not engine or not ffmpeg:
        raise RuntimeError('NARRATION_LOCAL_TOOLS_REQUIRED')
    chunks, timings = [], []
    with tempfile.TemporaryDirectory(prefix='stone_narration_') as folder:
        root = Path(folder)
        for index, (text, duration, start) in enumerate(zip(texts, DURATIONS, STARTS)):
            for speed in (160, 180, 200, 220):
                subprocess.run([engine, '-b', '1', '-v', 'pt-br', '-s', str(speed), '-w', str(root/'speech.wav'), '--stdin'], input=text.encode('utf-8'), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, check=True)
                result = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', str(root/'speech.wav'), '-ac', '1', '-ar', str(RATE), '-f', 's16le', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8, check=True)
                pcm = result.stdout
                if len(pcm) <= (duration-start-150)*RATE*2//1000:
                    break
            else:
                raise ValueError('NARRATION_TOO_LONG_FOR_SCENE')
            if not pcm or len(pcm)%2:
                raise ValueError('NARRATION_PCM_INVALID')
            prefix = b'\0'*(start*RATE*2//1000)
            chunks.append((prefix+pcm).ljust(duration*RATE*2//1000,b'\0'))
            offset = sum(DURATIONS[:index])
            timings.append(dict(scene=index+1, start_ms=offset+start, end_ms=offset+start+len(pcm)*1000//(RATE*2), words_per_minute_setting=speed))
    output = Path(output)
    with output.open('xb') as target:
        with wave.open(target,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(RATE);wav.writeframes(b''.join(chunks))
    return dict(schema_version='tapi-demo-narration-receipt.v1', document_id=packet.get('document_id'), document_version=packet.get('document_version'), script_sha256=hashlib.sha256(json.dumps(packet,sort_keys=True,ensure_ascii=False).encode()).hexdigest(), sha256=hashlib.sha256(output.read_bytes()).hexdigest(), synthetic_voice=True, engine=Path(engine).name, locale='pt-br', duration_ms=sum(DURATIONS), scene_speech_windows=timings, word_alignment_verified=False, publication_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--confirm-original-local-draft',action='store_true',required=True)
    args=parser.parse_args()
    if not args.script.is_file() or args.script.stat().st_size>16000:
        raise ValueError('NARRATION_PACKET_INVALID')
    print(json.dumps(synthesize(json.loads(args.script.read_text(encoding='utf-8-sig')),args.output),ensure_ascii=False,indent=2))
