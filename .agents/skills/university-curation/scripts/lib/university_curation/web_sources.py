"""Bounded, one-time capture of external primary sources for native Research.

The host discovers URLs; this adapter fetches each allowed page once and
preserves a short, locatable, integrity-bound text snapshot. No web crawler.
"""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import hashlib
import ipaddress
import json
import re
import socket
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .integrity import private_path, sha
from .records import encode
from .records import instant
from .cache_lock import request_lock

MAX_QUERIES=8
MAX_PAGES=12
MAX_DOMAINS=5
MAX_DEPTH=2
MAX_SECONDS=900
MAX_BYTES=1024*1024
MAX_TEXT=18000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Redirects require a new explicitly budgeted URL')


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.skip=0; self.parts=[]; self.current=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg','iframe'): self.skip+=1
        if tag in ('p','li','h1','h2','h3','h4','td','th','title'): self._flush()
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg','iframe') and self.skip: self.skip-=1
        if tag in ('p','li','h1','h2','h3','h4','td','th','title'): self._flush()
    def handle_data(self,data):
        if not self.skip: self.current.append(data)
    def _flush(self):
        value=' '.join(' '.join(self.current).split()); self.current=[]
        if len(value)>=20: self.parts.append(value)
    def finish(self):
        self._flush(); return self.parts


def _host(url):
    parts=urlsplit(url)
    if (parts.scheme!='https' or not parts.hostname or parts.username or parts.password or
            parts.port not in (None,443) or parts.fragment or len(url)>2048):
        raise ValueError('Only plain public HTTPS URLs are permitted')
    name=parts.hostname.lower().rstrip('.')
    if name in ('localhost','localhost.localdomain') or name.endswith(('.local','.internal','.localhost')):
        raise ValueError('Local network sources are forbidden')
    try:
        addresses=socket.getaddrinfo(name,443,type=socket.SOCK_STREAM)
    except socket.gaierror as exc: raise ValueError('External source DNS resolution failed') from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('External source resolves to a non-public IP')
    return name


def _fetch(url):
    request=Request(url,headers={'User-Agent':'UniversitySeedCuration/0.3 (research; https://github.com/ider-zh/university-seed-curation)',
                                 'Accept':'text/html, text/plain;q=0.9'})
    opener=build_opener(_NoRedirect())
    with opener.open(request,timeout=12) as response:
        mime=response.headers.get_content_type()
        if mime not in ('text/html','text/plain'): raise ValueError('Unsupported external content type')
        raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES: raise ValueError('Oversized external source')
        charset=response.headers.get_content_charset() or 'utf-8'
    decoded=raw.decode(charset,errors='replace')
    if mime=='text/html':
        parser=_Text(); parser.feed(decoded); paragraphs=parser.finish()
    else: paragraphs=[v.strip() for v in decoded.splitlines() if len(v.strip())>=20]
    rows=[]; remaining=MAX_TEXT
    for index,line in enumerate(paragraphs):
        line=line[:2000]
        if not remaining: break
        text=line[:remaining]; remaining-=len(text)
        if text: rows.append({'locator':'paragraph:'+str(index+1),'text':text})
    if not rows: raise ValueError('External page contains no useful readable text')
    return rows


def collect(leads, source_map, source_corpus, capture_dir, fetch=_fetch, now=None):
    """Validate explicit host-discovered URLs and add snapshots to one packet.

    No search or arbitrary follow-up is performed here; search-depth and query
    accounting are supplied by the host and fail closed against hard caps.
    """
    if not isinstance(leads,dict) or set(leads)!={'search_queries','elapsed_seconds','pages'}:
        raise ValueError('Search budget manifest must declare queries, elapsed time and pages')
    queries=leads['search_queries']; pages=leads['pages']; elapsed=leads['elapsed_seconds']
    if (not isinstance(queries,list) or len(queries)>MAX_QUERIES or any(not isinstance(q,str) or not q.strip() or len(q)>300 for q in queries)
            or type(elapsed) not in (float,int) or not 0<=elapsed<=MAX_SECONDS or
            not isinstance(pages,list) or len(pages)>MAX_PAGES):
        raise ValueError('External research budget exceeded')
    hosts=set(); urls=set(); checked=[]
    for page in pages:
        if not isinstance(page,dict) or set(page)!={'url','publisher_role','query_index','depth'}:
            raise ValueError('Invalid external page descriptor')
        url=page['url']; role=page['publisher_role']; q=page['query_index']; depth=page['depth']
        if not isinstance(url,str) or url in urls or role not in ('institution_official','government','academic_publisher','other'):
            raise ValueError('Duplicate URL or unsupported source role')
        if type(q) is not int or not 0<=q<len(queries) or type(depth) is not int or not 0<=depth<=MAX_DEPTH:
            raise ValueError('External search query/depth not accounted for')
        host=_host(url); hosts.add(host); urls.add(url); checked.append((page,host))
    if len(hosts)>MAX_DOMAINS: raise ValueError('External domain budget exceeded')
    cache=private_path(capture_dir); cache.mkdir(parents=True,exist_ok=True)
    at=now or datetime.now(timezone.utc).isoformat(); captures=[]
    for page,host in checked:
        url=page['url']; key=hashlib.sha256(url.encode('utf-8')).hexdigest()
        path=cache/(key+'.json')
        with request_lock(cache/'locks'/(key+'.lock')):
            saved=None
            if path.exists():
                prior=json.loads(path.read_text(encoding='utf-8'))
                if prior['url']!=url or sha(encode(prior['rows']))!=prior['digest']:
                    raise ValueError('Corrupt external source cache')
                if timedelta(0)<=instant(at)-instant(prior['retrieved_at'])<timedelta(days=30):
                    saved=prior
            if saved is None:
                rows=fetch(url)
                saved={'url':url,'rows':rows,'digest':sha(encode(rows)),'retrieved_at':at}
                temporary=path.with_suffix('.part')
                temporary.write_bytes(encode(saved)); temporary.replace(path)
        ref='s'+str(len(source_map)+1)
        source_map[ref]={'kind':'website','url':url,'publisher_role':page['publisher_role'],
                         'family':host,'retrieved_at':saved['retrieved_at'],'snapshot_id':'sha256:'+saved['digest']}
        source_corpus[ref]=saved['rows']
        captures.append({'source_ref':ref,'url':url,'capture_path':str(path),'digest':saved['digest']})
    return {'queries':len(queries),'pages':len(checked),'domains':len(hosts),'elapsed_seconds':elapsed,'captures':captures}


def verify_packet(packet):
    for ref,source in packet['sources'].items():
        if source['kind']!='website': continue
        rows=packet['source_corpus'].get(ref)
        if not isinstance(rows,list) or source.get('snapshot_id')!='sha256:'+sha(encode(rows)):
            raise ValueError('External source snapshot digest mismatch')
        if not re.fullmatch(r'[a-z][a-z0-9.-]*',source.get('family','')):
            raise ValueError('Invalid external source family')
