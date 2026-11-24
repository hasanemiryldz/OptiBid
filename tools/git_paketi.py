"""Etiketli demo ve kaynak koduyla temiz OptiBid.zip üretir."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

from paket_hazirla import APP, MAIN


REQUIRED={
    '.env.example','.gitignore','.github/workflows/kanit.yml','README.md','tools/git_paketi.py',
    'tests/_ortak.py','tests/test_ajan_kanit.py','tests/test_belge_rapor.py',
    'tests/fixtures/a4_sentetik.txt','tests/fixtures/vakalar.py','tests/fixtures/ornek-sartname.pdf',
    'docs/ekranlar/ana-ekran.png','docs/ekranlar/belge-inceleme.png',
    'docs/ekranlar/belge-raporu.png','docs/ekranlar/mobil-yukleme.png'
}
SECRET=re.compile(rb'(?m)^\s*(?:(?:BRAVE_SEARCH_API_KEY|OPENAI_API_KEY|PASSWORD|API_TOKEN)\s*=\s*["\x27]?[A-Za-z\d_-]{18,}|-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----)')


def paketle(target):
    target=Path(target).resolve()
    if target.name!='OptiBid.zip':
        raise ValueError('Teslim arşivinin adı OptiBid.zip olmalı.')
    assets={p.relative_to(APP).as_posix() for pattern in ('static/brand/*.webp','static/brand/*.png','static/brand/*.css',
                                                       'static/fonts/*.ttf','static/fonts/OFL-*.txt')
            for p in APP.glob(pattern) if p.is_file()}
    files=sorted(set(MAIN)|REQUIRED|assets)
    contents={}
    manifest=[]
    for rel in files:
        file=APP/rel
        if not file.is_file() or not file.resolve().is_relative_to(APP):
            raise ValueError(f'Paket girdisi bulunamadı: {rel}')
        raw=file.read_bytes()
        if len(raw)>8*1024*1024 or SECRET.search(raw):
            raise ValueError(f'Paket boyut/anahtar kontrolü başarısız: {rel}')
        contents['OptiBid/'+rel]=raw
        manifest.append({'yol':rel,'bayt':len(raw),'sha256':sha256(raw).hexdigest()})
    contents['OptiBid/PAKET_MANIFESTOSU.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
    target.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(target,'x',ZIP_DEFLATED) as archive:
        for rel,raw in contents.items():
            archive.writestr(rel,raw)
    with ZipFile(target) as archive:
        assert archive.testzip() is None and set(archive.namelist())==contents.keys()
        for entry in manifest:
            assert sha256(archive.read('OptiBid/'+entry['yol'])).hexdigest()==entry['sha256']
    return {'dosya':str(target),'girdi':len(contents),'bayt':target.stat().st_size,
            'sha256':sha256(target.read_bytes()).hexdigest()}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hedef',type=Path)
    print(json.dumps(paketle(parser.parse_args().hedef),ensure_ascii=False))
