"""Incremental six-month freshness index derived exclusively from main."""
from pathlib import Path
import os
import re
import subprocess
import tarfile
import uuid
from .attestations import load_json, private_path
from .records import encode, instant, qid as valid_qid
from .workflow_contract import baseline_at
from .git_data import git

_RECORD_PATH = re.compile(r'data/universities/[0-9a-f]{2,3}/(Q[1-9][0-9]*)\.json\Z')


def recency_index(repo, base, path):
    """Derive approved main timestamps, streaming a cold snapshot and diffing later commits."""
    path=private_path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if not git(repo,'ls-tree','--name-only',base,'--','data/universities').strip():
        return {}
    cached=None
    if path.exists():
        try:
            cached=load_json(path.read_bytes())
            if (not isinstance(cached,dict) or cached.get('version')!=1 or
                not re.fullmatch(r'[0-9a-f]{40}',cached.get('base','')) or not isinstance(cached.get('updated'),dict)):
                cached=None
            else:
                for entity,stamp in cached['updated'].items(): valid_qid(entity); instant(stamp)
        except (ValueError,TypeError,KeyError): cached=None
    if cached and cached['base']==base: return cached['updated']
    if cached:
        try:
            names=git(repo,'diff','--no-renames','--name-only','-z',cached['base'],base,'--','data/universities').decode().split('\0')
        except Exception:
            cached=None
    if cached:
        updated=dict(cached['updated'])
        changed={m.group(1) for name in names if (m:=_RECORD_PATH.fullmatch(name))}
        for entity in changed:
            record,_=baseline_at(repo,base,entity)
            if record and record.get('update_datetime'):
                instant(record['update_datetime']); updated[entity]=record['update_datetime']
            else: updated.pop(entity,None)
    else:
        updated={}; seen=set()
        env={**os.environ,'GIT_TERMINAL_PROMPT':'0'}
        process=subprocess.Popen(['git','-C',str(repo),'archive',base,'data/universities'],stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            with tarfile.open(fileobj=process.stdout,mode='r|*') as archive:
                for item in archive:
                    match=_RECORD_PATH.fullmatch(item.name)
                    if not match: continue
                    if not item.isfile() or item.size>2*1024*1024: raise ValueError('Invalid university blob in main archive')
                    entity=match.group(1)
                    if entity in seen: raise ValueError('Duplicate university QID in main archive')
                    seen.add(entity); stream=archive.extractfile(item)
                    if stream is None: raise ValueError('Unreadable university blob')
                    record=load_json(stream.read())
                    if record.get('qid')!=entity: raise ValueError('University path/QID mismatch')
                    if record.get('update_datetime'):
                        instant(record['update_datetime']); updated[entity]=record['update_datetime']
            if process.wait()!=0: raise RuntimeError('Cannot stream university data from main')
        except BaseException:
            if process.poll() is None: process.kill()
            process.wait(); raise
        finally:
            if process.stdout: process.stdout.close()
    temporary=path.with_name(path.name+'-'+uuid.uuid4().hex+'.part')
    temporary.write_bytes(encode({'version':1,'base':base,'updated':updated})); temporary.replace(path)
    return updated
