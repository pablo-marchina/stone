"""Exporta todos os blobs documentais inventariados e os 48 blobs anteriores, sem rede ou escrita no repo."""
from pathlib import Path
import argparse, hashlib, subprocess, json, re
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
repo=a.repo.resolve();out=a.out.resolve();root=Path(__file__).resolve().parents[1]
s=root/'04_Snapshots/2026-11-17'
if out.exists() or repo==out or repo in out.parents:raise SystemExit('Diretorio novo e privado fora do checkout obrigatório')
entries={}
for manifest in [s/'GITHUB_DOCUMENTOS_INVENTARIO_COMPLETO.json',s/'evidencias_v6/GITHUB_SNAPSHOT_MANIFEST.json']:
 for e in json.loads(manifest.read_text(encoding='utf-8'))['entries']:
  ref=e['commit'];path=e['path'];h=e['git_blob_sha1'];key=(ref,path)
  if not re.fullmatch('[0-9a-f]{40}',ref) or not re.fullmatch('[0-9a-f]{40}',h) or Path(path).is_absolute() or '..' in Path(path).parts:raise SystemExit('Manifesto inválido')
  if key in entries and entries[key]!=h:raise SystemExit('Hashes divergentes')
  entries[key]=h
files=[]
for (ref,path),expected in sorted(entries.items()):
 content=subprocess.check_output(['git','-C',str(repo),'show',ref+':'+path]);actual=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\x00'+content).hexdigest()
 if actual!=expected:raise SystemExit('Blob diferente: '+ref+':'+path)
 files.append((out/ref/path,content))
out.mkdir(parents=True,exist_ok=False)
for f,b in files:
 f.parent.mkdir(parents=True,exist_ok=True)
 with f.open('xb') as w:w.write(b)
print(json.dumps({'exported':len(files),'kind':'exact_pinned_git_blobs','network':False,'repo_changed':False}))
