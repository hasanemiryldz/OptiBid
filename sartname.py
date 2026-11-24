"""Yerel, içerik adresli şartname yükleme ve sayfa metni."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory, TemporaryFile
from time import time
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 100
MAX_TEXT = 500_000
WORD = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
DIGEST = re.compile(r'^[0-9a-f]{64}$')


def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS sartname_dosyalari (
        sha TEXT PRIMARY KEY, ad TEXT NOT NULL, sayfalar TEXT NOT NULL, veri BLOB NOT NULL,
        yukleme REAL NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS sartname_baglari (
        hazirlik TEXT PRIMARY KEY, sha TEXT NOT NULL)""")
    db.execute('CREATE INDEX IF NOT EXISTS sartname_baglari_sha ON sartname_baglari(sha)')
    db.execute('CREATE TABLE IF NOT EXISTS sartname_cikarimlari (sha TEXT PRIMARY KEY, surum INTEGER, sonuc TEXT)')


def purge(db, now):
    expired = [s for s, in db.execute("""SELECT DISTINCT sha FROM sartname_baglari WHERE hazirlik IN
        (SELECT id FROM silinen_hazirliklar WHERE bitis<=?)""", (now,))]
    db.execute("""DELETE FROM sartname_baglari WHERE hazirlik IN
        (SELECT id FROM silinen_hazirliklar WHERE bitis<=?)""", (now,))
    for digest in expired:
        db.execute("""DELETE FROM sartname_dosyalari WHERE sha=?
            AND NOT EXISTS (SELECT 1 FROM sartname_baglari WHERE sha=?)""", (digest, digest))
    db.execute("""DELETE FROM sartname_dosyalari WHERE yukleme<?
        AND NOT EXISTS (SELECT 1 FROM sartname_baglari WHERE sha=sartname_dosyalari.sha)""",
        (now - 86400,))
    db.execute('DELETE FROM sartname_cikarimlari WHERE sha NOT IN (SELECT sha FROM sartname_dosyalari)')


def maskele(text):
    def tc(match):
        d = list(map(int, match.group()))
        on = (7 * sum(d[:9:2]) - sum(d[1:9:2])) % 10
        return '[TC MASKELİ]' if d[0] and on == d[9] and sum(d[:10]) % 10 == d[10] else match.group()
    text = re.sub(r'(?<!\d)\d{11}(?!\d)', tc, text)
    text = re.sub(r'\bTR[ \t-]*(?:\d[ \t-]*){25}\d\b', '[IBAN MASKELİ]', text, flags=re.I)
    text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[E-POSTA MASKELİ]', text)
    return re.sub(r'(?<!\d)(?:(?:\+90|0090|0)[ .-]*)?\(?[2-5][0-9]{2}\)?[ .-]*[0-9]{3}'
                  r'[ .-]*[0-9]{2}[ .-]*[0-9]{2}(?!\d)', '[TELEFON MASKELİ]', text)


def _ocr(file, pages):
    tesseract, render = shutil.which('tesseract'), shutil.which('pdftoppm')
    if not tesseract or not render:
        raise ValueError('PDF taranmış görünüyor. Tesseract ve PDF görüntüleyicisi kuruluysa OCR kullanılabilir.')
    def run(args):
        return subprocess.run(args, capture_output=True, check=True, timeout=15)
    try:
        langs = run([tesseract, '--list-langs']).stdout.decode('utf-8', 'replace').splitlines()
        if 'tur' not in langs:
            raise ValueError('OCR için Tesseract Türkçe dil paketi gerekli.')
        with TemporaryDirectory() as folder:
            source, target = Path(folder)/'kaynak.pdf', Path(folder)/'sayfa'
            file.seek(0)
            with source.open('wb') as writer:
                shutil.copyfileobj(file, writer)
            for index, text in enumerate(pages, 1):
                if not text.strip():
                    try:
                        run([render, '-f', str(index), '-l', str(index), '-r', '140', '-singlefile',
                             '-png', str(source), str(target)])
                        pages[index-1] = run([tesseract, str(target.with_suffix('.png')), 'stdout',
                                              '-l', 'tur']).stdout.decode('utf-8', 'replace')
                    except (OSError, subprocess.SubprocessError):
                        continue
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError('Taranmış PDF üzerinde OCR tamamlanamadı.') from error
    return pages


def _pdf(file):
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as error:
        raise ValueError('PDF metni için Kurulum.bat ile pypdf paketini kurun.') from error
    try:
        reader = PdfReader(file)
        if reader.is_encrypted:
            raise ValueError('PDF şifreli. Şifresiz bir kopya yükleyin.')
        if not 0 < len(reader.pages) <= MAX_PAGES:
            raise ValueError(f'PDF en fazla {MAX_PAGES} sayfa içerebilir ve boş olamaz.')
        pages = []
        for page in reader.pages:
            try:
                text=page.extract_text() or ''
            except (PdfReadError, UnicodeError, ValueError):
                text=''
            if text.strip():
                try:
                    from sartname_alanlari import table_records
                    layout=page.extract_text(extraction_mode='layout',layout_mode_space_vertically=False) or ''
                    if any(table_records(layout)):
                        text=layout
                except (PdfReadError, UnicodeError, ValueError):
                    pass
            pages.append(text)
    except (PdfReadError, OSError, TypeError, RecursionError, KeyError, UnicodeError) as error:
        raise ValueError('PDF bozuk veya metni okunamıyor.') from error
    if any(not text.strip() for text in pages):
        try:
            return _ocr(file,pages)
        except ValueError:
            if not any(text.strip() for text in pages):
                raise
    return pages


def _docx(file):
    try:
        with ZipFile(file) as archive:
            entries=archive.infolist()
            if len(entries)>1000 or sum(row.file_size for row in entries)>80_000_000:
                raise ValueError('DOCX açılmış içerik sınırını aşıyor.')
            manifest = archive.getinfo('[Content_Types].xml')
            part = archive.getinfo('word/document.xml')
            if manifest.file_size > 128_000 or part.file_size > 5_000_000 or part.flag_bits & 1:
                raise ValueError('DOCX metni desteklenen boyutu aşıyor veya şifreli.')
            if b'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml' not in archive.read(manifest):
                raise ValueError('Bu ZIP bir DOCX belgesi içermiyor.')
            xml = archive.read(part)
            if re.search(rb'<!\s*(?:DOCTYPE|ENTITY)', xml, flags=re.I):
                raise ValueError('DOCX içindeki XML güvenli biçimde okunamıyor.')
            tree = ET.fromstring(xml)
    except (KeyError, BadZipFile, ET.ParseError, RuntimeError, NotImplementedError) as error:
        raise ValueError('DOCX paketi bozuk, şifreli veya Word belgesi içermiyor.') from error
    def paragraph(block):
        return ''.join(node.text or '' for node in block.iter(WORD+'t'))

    pages, lines = [], []
    body=tree.find(WORD+'body')
    if body is None:
        raise ValueError('DOCX belge gövdesi eksik.')
    for block in body:
        if block.tag==WORD+'p':
            lines.append(paragraph(block))
        elif block.tag==WORD+'tbl':
            if any(line.strip() for line in lines):
                pages.append('\n'.join(lines))
            lines=[]
            table=[]
            for row in block.findall(WORD+'tr'):
                cells=[' '.join(paragraph(p) for p in cell.iter(WORD+'p')).strip()
                       for cell in row.findall(WORD+'tc')]
                table.append(' | '.join(cells))
            pages.append('\n'.join(table))
    if lines:
        pages.append('\n'.join(lines))
    return pages


def oku(stream, length, expected=None):
    digest = sha256()
    with TemporaryFile() as file:
        remaining = length
        while remaining:
            block = stream.read(min(remaining, 65536))
            if not block:
                raise ValueError('Dosya yüklemesi tamamlanmadı.')
            file.write(block)
            digest.update(block)
            remaining -= len(block)
        file.seek(0)
        signature = file.read(8)
        file.seek(0)
        if signature.startswith(b'%PDF-'):
            ext, pages = '.pdf', _pdf(file)
        elif signature.startswith(b'PK\x03\x04'):
            ext, pages = '.docx', _docx(file)
        elif expected=='txt' and length<=MAX_TEXT*4:
            try:
                plain=file.read().decode('utf-8-sig')
            except UnicodeDecodeError as error:
                raise ValueError('TXT belgesi UTF-8 olmalı.') from error
            if '\x00' in plain:
                raise ValueError('TXT metin içermiyor.')
            ext,pages='.txt',plain.split('\f')
        else:
            raise ValueError('Dosya içeriği PDF veya DOCX biçiminde olmalı.')
        if expected and ext!='.'+expected:
            raise ValueError('Dosyanın seçilen uzantısı ve içeriği farklı.')
        if not any(text.strip() for text in pages):
            raise ValueError('Belgede okunabilir metin bulunamadı.')
        if len(pages) > MAX_PAGES or sum(map(len, pages)) > MAX_TEXT:
            raise ValueError('Belgenin sayfa sayısı veya metin boyutu sınırı aşıldı.')
        file.seek(0)
        return digest.hexdigest(), ext, [maskele(text) for text in pages], BytesIO(file.read())


def sakla(db, digest, ext, pages, original, filename=None):
    db.execute("""INSERT INTO sartname_dosyalari VALUES (?,?,?,?,?)
        ON CONFLICT(sha) DO UPDATE SET yukleme=excluded.yukleme,
        ad=CASE WHEN sartname_dosyalari.ad=? THEN excluded.ad ELSE sartname_dosyalari.ad END""",
        (digest, filename or digest+ext, json.dumps(pages, ensure_ascii=False), original.getbuffer(), time(),digest+ext))


def sayfalar(db, digest):
    if not DIGEST.fullmatch(digest):
        raise ValueError('Şartname kimliği geçersiz.')
    row = db.execute('SELECT sayfalar, ad FROM sartname_dosyalari WHERE sha=?', (digest,)).fetchone()
    if not row:
        raise FileNotFoundError('Şartname bulunamadı. Dosyayı tekrar yükleyin.')
    return json.loads(row[0]), row[1]


def cikarim_sakla(db,digest,version,result):
    db.execute('INSERT OR REPLACE INTO sartname_cikarimlari VALUES (?,?,?)',
               (digest,version,json.dumps(result,ensure_ascii=False)))


def cikarim_oku(db,digest,version=None):
    row=db.execute('SELECT surum,sonuc FROM sartname_cikarimlari WHERE sha=?',(digest,)).fetchone()
    return json.loads(row[1]) if row and (version is None or row[0]==version) else None


def taslak_kanitlari(doc,result,previous=None):
    """İstemciden gelen etiket ve alıntılara güvenme; kaynak veya kullanıcı değerini kur."""
    extra=doc['ek_bilgiler']
    attachment=extra['sartname']
    old=(previous or {}).get('ek_bilgiler',{}).get('sartname',{}).get('kanitlar',{})
    original={r['kimlik']:r for r in result['kalemler']}
    provenance={}

    def values_for(scope,fields,current):
        previous_values=old.get(scope,{})
        verified={}
        for key in dict.fromkeys([*fields,*current]):
            field=fields.get(key,{})
            value=current.get(key)
            prior=previous_values.get(key)
            proof=field.get('kural')
            if (prior and prior.get('deger')==value and
                    (prior.get('tur')!='kaynak_bulgusu' or proof and all(prior.get(k)==proof.get(k) for k in proof))):
                verified[key]=prior
            elif value is None:
                verified[key]={'deger':None,'etiket':field.get('etiket',key),'tur':'bilinmiyor','durum':field.get('durum','eksik'),
                               'adaylar':field.get('adaylar',[])}
            elif proof and str(value)==str(proof['deger']) and not prior:
                verified[key]={**proof,'etiket':field.get('etiket',key),'durum':'kaynakla destekli'}
            else:
                verified[key]={'deger':value,'etiket':field.get('etiket',key),'tur':'kullanici_beyani','durum':'kullanıcı düzenledi',
                               'onceki':{k:prior.get(k) for k in ('deger','tur','durum','alinti','konum')} if prior else proof}
        provenance[scope]=verified

    delivery=doc.get('teslimat',{})
    reported=attachment.get('genel')
    general={**({k:v for k,v in reported.items() if k in result['genel'] and (v is None or isinstance(v,str))}
                if isinstance(reported,dict) else {}),**{k:delivery.get(k) for k in ('yer','sure','gun_turu','baslangic','sure_kosulu')},
             'ikn':extra.get('ikn'),'kdv':extra.get('kdv_esasi')}
    values_for('genel',result['genel'],general)
    for item in doc.get('kalemler',[]):
        row=original.get(item.get('kaynak_kalem'),{})
        fields=row.get('alanlar',{})
        # Farklı kategorinin teknik değerlerini önceki kategoriye ait bir kaynakla etiketleme.
        current_path=[item.get('ihale_turu') or doc['ihale_turu'],*(item.get('kategori') or doc['kategori'])]
        if row.get('kategori')!=current_path:
            fields={k:v for k,v in fields.items() if not k.startswith('teknik:')}
        values_for(item['id'],fields,{**{k:item.get(k) for k in ('ad','miktar','birim')},
                   **{'teknik:'+k:v for k,v in item.get('teknik',{}).items()}})
    attachment['kanitlar']=provenance
    attachment['okuma']=result['okuma']
    attachment['model_durumu']=result.get('model_durumu')
    attachment['islem_id']=result.get('islem_id')
    attachment['inceleme_tamamlandi']=doc.get('inceleme_durumu')=='tamamlandı'
