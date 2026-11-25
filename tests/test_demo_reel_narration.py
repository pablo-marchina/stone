import shutil
import wave
import pytest
from scripts.demo_reel_narration import synthesize


def test_narration_rejects_invalid_packet(tmp_path):
    with pytest.raises(ValueError,match='PACKET_INVALID'):
        synthesize({'scenes':['x']},tmp_path/'a.wav')
    with pytest.raises(ValueError,match='TEXT_INVALID'):
        synthesize({'schema_version':'tapi-demo-reel-narration.v1','scenes':['x','', 'z']},tmp_path/'a.wav')
    assert not (tmp_path/'a.wav').exists()


@pytest.mark.skipif(not (shutil.which('espeak-ng') or shutil.which('espeak')) or not shutil.which('ffmpeg'),reason='optional local voice tools')
def test_narration_scene_timing(tmp_path):
    p=tmp_path/'voice.wav'
    r=synthesize({'schema_version':'tapi-demo-reel-narration.v1','scenes':['Organize sua rotina.','Escolha uma prioridade.','Siga para mais dicas.']},p)
    with wave.open(str(p),'rb') as f:
        assert (f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getnframes())==(1,2,16000,240000)
        data=f.readframes(f.getnframes());assert any(data)
    assert all(w['start_ms']<w['end_ms']<=limit for w,limit in zip(r['scene_speech_windows'],(3000,10000,15000)))
    assert not r['publication_allowed'] and not r['word_alignment_verified']
