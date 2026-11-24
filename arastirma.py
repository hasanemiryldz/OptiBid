"""Gerçek web araması + EKAP sayfa okuma. Hiçbir sonuç fiyat havuzuna yazılmaz.

Arama keşif katmanıdır. Başlık, özet ve adres bir sözleşme fiyatının ya da
teknik uygunluğun doğrulanması değildir. Anahtar yalnız sunucu ortamında kalır.
"""
from contextlib import closing
from datetime import datetime,timezone
from hashlib import sha256
from html.parser import HTMLParser
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import subprocess
from urllib.error import URLError
import time
from urllib.parse import urlencode,urlsplit,urlunsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent


def ayarlar():
    return json.loads((ROOT/'arastirma_ayar.json').read_text(encoding='utf-8'))


def resmi_url(raw):
    try:
        p=urlsplit(str(raw))
        host=(p.hostname or '').lower()
        allowed=ayarlar()['ekap_alanlari']
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443):return None
        if host not in allowed:return None
        return urlunsplit(('https',host,p.path or '/',p.query,''))
    except (ValueError,TypeError):return None


class Yonlendirme(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # Result pages stay on official hosts; providers stay on provider hosts.
        target=urlsplit(newurl)
        if req.host in ('api.search.brave.com','www.bing.com'):
            if target.scheme!='https' or target.netloc!=req.host:raise ValueError('Arama sağlayıcı yönlendirmesi reddedildi.')
        elif not resmi_url(newurl):raise ValueError('EKAP dışı yönlendirme açılmadı.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def windows_ekap_indir(url,timeout):
    """Yalnız EKAP için Windows'un normal sertifika doğrulamalı HTTPS istemcisi."""
    curl=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/curl.exe'
    if os.name!='nt' or not resmi_url(url) or not curl.is_file():
        raise ValueError('Windows HTTPS istemcisi kullanılamıyor.')
    result=subprocess.run([str(curl),'--disable','--silent','--show-error','--fail',
                           '--proto','=https','--max-time',str(timeout),'--max-filesize','1000000',
                           '--write-out','%{stderr}\n%{http_code}\t%{content_type}\n',url],
                          stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout+2,
                          creationflags=subprocess.CREATE_NO_WINDOW)
    status=result.stderr.decode('utf-8',errors='replace').strip().splitlines()
    code,_,content_type=status[-1].partition('\t') if status else ('','','')
    if result.returncode or code!='200' or len(result.stdout)>1_000_000:
        raise ValueError('Windows HTTPS istemcisi EKAP sayfasını alamadı.')
    return result.stdout,content_type.split(';',1)[0],url


def indir(url,headers=None,timeout=8):
    req=Request(url,headers={'User-Agent':'OptiBid/20 (+local research assistant)','Accept-Encoding':'identity',**(headers or {})})
    try:
        with build_opener(Yonlendirme()).open(req,timeout=timeout) as response:
            raw=response.read(1_000_001)
            if len(raw)>1_000_000:raise ValueError('Yanıt boyutu sınırı aşıldı.')
            return raw,response.headers.get_content_type(),response.geturl()
    except URLError as exc:
        if os.name!='nt' or not isinstance(exc.reason,ssl.SSLError) or not resmi_url(url):
            raise
        # İstemci değişir; sertifika doğrulaması ve HTTPS korunur.
        return windows_ekap_indir(url,timeout)


class Metin(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript') and self.skip:self.skip-=1
    def handle_data(self,data):
        if not self.skip and data.strip():self.parts.append(data.strip())


def sade(raw):
    p=Metin();p.feed(raw)
    return re.sub(r'\s+',' ',' '.join(p.parts)).strip()


def baglam_sorgusu(doc,question=''):
    """Dış sorgulara yalnız kamu İKN'si veya katalog terimleri aktarılır."""
    from motor import oku
    public=ayarlar().get('kategori_sorgulari',{})
    if id_match:=re.search(r'(?<!\d)20\d{2}/[1-9]\d{0,8}(?!\d)',question):
        return id_match[0]
    tree=oku('catalog.json')['turler']
    kind=doc.get('ihale_turu')
    category=doc.get('kategori')
    if isinstance(kind,str) and isinstance(category,list) and len(category)==2 and all(isinstance(k,str) for k in category):
        main,sub=category
        if sub in tree.get(kind,{}).get(main,{}):
            return public.get('/'.join([kind,main,sub])) or f'{main} {sub} {kind}'
    from veri_merkezi import norm
    text=norm(question)
    for value in public.values():
        if norm(value) in text:
            return value
    return ''


def sorgular(sorgu):
    if not isinstance(sorgu,str) or not 2<=len(sorgu.strip())<=350:raise ValueError('Aramayı ürün, iş veya İKN ile 2–350 karakter içinde yazın.')
    if re.search(r'[\w.+-]+@[\w.-]+|\b(?:iban|tckn|maliyetim|cep telefonu)\b|\d\s*(?:₺|TL\b)',sorgu,re.I):
        raise ValueError('Arama alanına yalnız ürün, hizmet adı veya kamu İKN’si yazın.')
    # Kullanıcı tarafından eklenen site: operatörü izinli alanları değiştiremez.
    clean=re.sub(r'(?:site|filetype):\S+','',sorgu,flags=re.I)
    clean=re.sub(r'https?://\S+','',clean)
    clean=re.sub(r'[^\w\s/²³.,()\-]',' ',clean,flags=re.UNICODE)
    clean=re.sub(r'\s+',' ',clean).strip()[:220]
    if len(clean)<2:raise ValueError('Arama için ürün veya iş adını yazın.')
    return [f'site:ekap.kik.gov.tr {clean} ihale',f'site:ekapv2.kik.gov.tr {clean} sonuç ilanı'][:ayarlar()['sorgu_sayisi']]


def bul(sorgu):
    started=time.monotonic();cfg=ayarlar();queries=sorgular(sorgu)
    provider=cfg.get('saglayici','auto')
    key=os.environ.get('BRAVE_SEARCH_API_KEY','').strip()
    provider=('brave' if key else 'bing_rss') if provider=='auto' else provider
    rows=[];errors=[];events=[];seen=set()
    for query in queries:
        begin=time.monotonic()
        try:
            if provider=='brave':
                if not key:raise ValueError('Brave anahtarı yapılandırılmadı.')
                raw,_,_=indir('https://api.search.brave.com/res/v1/web/search?'+urlencode({'q':query,'count':cfg['sonuc_sayisi'],'country':'TR','search_lang':'tr'}),{'Accept':'application/json','X-Subscription-Token':key},cfg['zaman_asimi_saniye'])
                items=json.loads(raw).get('web',{}).get('results',[])
                candidates=[(r.get('title',''),r.get('url',''),r.get('description','')) for r in items]
            elif provider=='bing_rss':
                raw,_,_=indir('https://www.bing.com/search?'+urlencode({'q':query,'format':'rss'}),timeout=cfg['zaman_asimi_saniye'])
                root=ET.fromstring(raw)
                candidates=[(r.findtext('title',''),r.findtext('link',''),r.findtext('description','')) for r in root.findall('.//item')]
            else:raise ValueError('Arama sağlayıcısı yapılandırılmadı.')
            accepted=0
            for title,url,desc in candidates:
                url=resmi_url(url)
                if not url or url in seen:continue
                seen.add(url);accepted+=1
                rows.append({'id':'WEB-'+sha256(url.encode()).hexdigest()[:12],'baslik':sade(title)[:240],
                    'url':url,'ozet':sade(desc)[:700],'kaynak':'EKAP adresi · arama dizini',
                    'erisim_zamani':datetime.now(timezone.utc).isoformat(),
                    'durum':'ARAMA_SONUCU','sayfa_okundu':False,'fiyat_teyidi':False})
            events.append({'arac':'internet_ihale_ara','saglayici':provider,'sorgu':query,'durum':'tamamlandı','sonuc':accepted,'ms':round((time.monotonic()-begin)*1000)})
        except (OSError,ValueError,ET.ParseError,KeyError,TypeError) as exc:
            # Anahtar, proxy adresi ve özel URL'ler log/istemciye sızmaz.
            errors.append('Arama sağlayıcısına ulaşılamadı veya yanıt okunamadı ('+type(exc).__name__+').')
            events.append({'arac':'internet_ihale_ara','saglayici':provider,'sorgu':query,'durum':'erişilemedi','ms':round((time.monotonic()-begin)*1000)})
    if not rows:
        for proof in ilgili_resmi_adresler(sorgu):
            reading=oku(proof['kaynak_url'])
            if reading['durum']!='metin_okundu':
                events.append({'arac':'internet_kaynagini_oku','sorgu':proof['ikn'],'durum':reading['durum']})
                continue
            if not re.search(r'(?<!\d)'+re.escape(proof['ikn'])+r'(?!\d)',reading['metin']):
                continue
            rows.append({'id':'EKAP-'+proof['ikn'],'baslik':proof['ad'],'url':reading['url'],
                         'ozet':ihale_alintisi(reading['metin'],proof['ikn']),'erisim_zamani':reading['erisim_zamani'],
                         'kaynak':'Yerel bağlantı · canlı EKAP okuması','durum':'CANLI_EKAP_OKUMASI',
                         'sayfa_okundu':True,'fiyat_teyidi':False})
            events.append({'arac':'internet_kaynagini_oku','sorgu':proof['ikn'],'durum':'metin okundu'})
    value={'durum':'sonuç_bulundu' if rows else 'erişilemedi' if errors and len(errors)==len(queries) else 'sonuç_yok',
        'sorgu':sorgu,'sorgular':queries,'kaynaklar':rows,'hatalar':list(dict.fromkeys(errors)),
        'saglayici':provider,'erisim_zamani':datetime.now(timezone.utc).isoformat(),'olaylar':events,
        'ms':round((time.monotonic()-started)*1000),'not':'Arama dizini adayları ve canlı okunan EKAP sayfaları etiketlenir. Fiyat teyidi ayrıca gerekir.',
        'arama_baglantilari':[{'baslik':'Aramayı tarayıcıda aç','url':'https://www.google.com/search?'+urlencode({'q':q}),'tur':'SORGULAMA_BAGLANTISI'} for q in queries]}
    kaydet(value)
    return value


def ihale_alintisi(text,ikn):
    start=text.index(ikn)
    return text[max(0,start-28):start+420].strip()


def ilgili_resmi_adresler(sorgu):
    from ekap_veri import verified
    from veri_merkezi import norm
    identifier=re.search(r'(?<!\d)20\d{2}/[1-9]\d{0,8}(?!\d)',sorgu)
    terms=set(re.findall(r'\w{3,}',norm(sorgu))) - {'alımı','ihale','sonuç','benzer','ara','için','mal','genel','diğer','işi','hizmet','danışmanlık','yapım'}
    matches=[]
    for key,row in verified().items():
        if not resmi_url(row.get('kaynak_url')):
            continue
        if identifier:
            if key==identifier[0]:return [row]
            continue
        words=set(re.findall(r'\w{3,}',norm(' '.join([row['ad'],*row['kategori']]))))
        score=len(terms & words)
        if score:matches.append((score,key,row))
    return [row for _,_,row in sorted(matches,reverse=True)[:2]]


def oku(url):
    target=resmi_url(url)
    if not target:raise ValueError('Yalnız EKAP sayfa bağlantıları açılır.')
    base={'url':target,'erisim_zamani':datetime.now(timezone.utc).isoformat(),'fiyat_teyidi':False}
    try:
        raw,mime,final=indir(target,timeout=ayarlar()['zaman_asimi_saniye'])
        if mime not in ('text/html','text/plain','application/xhtml+xml'):
            return dict(base,durum='desteklenmeyen_içerik',metin='',**{'not':'Bu ekin metni okunmadı. Belgeyi özgün bağlantıdan inceleyin.'})
        if not resmi_url(final):raise ValueError('Yönlendirme EKAP dışı.')
        body=sade(raw.decode('utf-8',errors='replace'))
        blocked=(bool(re.search(r'captcha|access denied|erişim engellendi|enable javascript|kısa bir güvenlik kontrolü|güvenlik kontrolünü tamamlayın|oturum açmanız|oturum süresi doldu|giriş yapmanız|üyelik girişi',body,re.I))
                 or bool(re.search(rb'<input\b[^>]*\btype\s*=\s*["\']?password\b',raw,re.I))
                 or len(body)<100)
        if blocked:return dict(base,durum='okunamadı',metin='',**{'not':'Sayfa dinamik içerik veya erişim kontrolü gerektiriyor. Okunmuş kabul edilmedi.'})
        return dict(base,url=final,durum='metin_okundu',metin=body[:16000],sha256=sha256(raw).hexdigest(),**{'not':'Sayfa metni okundu. Bedel/miktar/KDV ve ürün kapsamı ayrıca doğrulanmalı.'})
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        reason='TLS bağlantısı kurulamadı' if isinstance(getattr(exc,'reason',None),ssl.SSLError) else str(exc) if isinstance(exc,ValueError) else type(exc).__name__
        return dict(base,durum='erişilemedi',metin='',**{'not':'EKAP sayfası okunamadı · '+reason+'.'})


def kaydet(value):
    path=Path(os.environ.get('OPTIBID_ARASTIRMA_DB',ROOT/'data/arastirma.db'))
    path.parent.mkdir(parents=True,exist_ok=True)
    # Salt keşif günlüğü. Hiçbir fiyat/ihale tablosu değiştirilmez.
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('CREATE TABLE IF NOT EXISTS aramalar(id TEXT PRIMARY KEY,tarih TEXT,veri TEXT)')
        digest=sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        db.execute('INSERT OR REPLACE INTO aramalar VALUES(?,?,?)',(digest,value['erisim_zamani'],json.dumps(value,ensure_ascii=False)))


def durum():
    cfg=ayarlar();key=bool(os.environ.get('BRAVE_SEARCH_API_KEY'))
    return {'saglayici':('brave' if key else 'bing_rss') if cfg['saglayici']=='auto' else cfg['saglayici'],
            'brave_anahtari_tanimli':key,'alanlar':cfg['ekap_alanlari'],'not':'Bağlantı durumu gerçek arama sırasında sınanır.'}
