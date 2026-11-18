"""Snapshot local de metadados Git. Não executa testes, coleta, rede, push ou merge."""
import argparse, subprocess, json, hashlib, pathlib, datetime
p=argparse.ArgumentParser();p.add_argument('--repo',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
repo=a.repo.resolve();out=a.out.resolve()
if out.exists() or repo==out or repo in out.parents:raise SystemExit('Use novo diretório privado fora do checkout')
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
head=git('rev-parse','HEAD').decode().strip();tree=git('rev-parse','HEAD^{tree}').decode().strip();dirty=bool(git('status','--porcelain'))
entries=[]
for line in git('ls-tree','-r','-z',head).split(b'\0'):
 if not line:continue
 meta,path=line.split(b'\t',1);mode,kind,sha=meta.decode().split();path=path.decode('utf-8')
 if kind=='blob' and (path.startswith(('docs/','planning/')) or path=='README.md'):
  entries.append({'path':path,'git_blob_sha1':sha})
result={'kind':'local_git_metadata_not_operational_proof','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':head,'tree':tree,'dirty':dirty,'entries':entries,'remote_prs':'not_checked','db':'not_checked','tests':'not_run','gates':'not_assessed'}
out.mkdir(parents=True);(out/'GIT_LOCAL.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'head':head,'entries':len(entries),'dirty':dirty}))
