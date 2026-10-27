"""Copy current previews into the distribution, deduplicating identical PNGs."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]

def copy_previews():
    cache=ROOT/'artifacts/monster-cache'
    manifest=json.loads((cache/'manifest.json').read_text(encoding='utf8'))
    output=ROOT/'src/sinisistar_dglab/assets/monster-previews';images=output/'images';images.mkdir(parents=True,exist_ok=True)
    assert output.resolve().is_relative_to((ROOT/'src/sinisistar_dglab/assets').resolve())
    copied={};kept=set()
    for key,value in manifest['images'].items():
        source=(cache/value['file']).resolve();assert source.is_relative_to(cache.resolve())
        data=source.read_bytes();sha=hashlib.sha256(data).hexdigest();name=sha+'.png';target=images/name
        if not target.is_file():target.write_bytes(data)
        copied[key]=dict(file='images/'+name,width=value['width'],height=value['height'],sha256=sha)
        kept.add(name)
    bundled=dict(schema=1,game_version=manifest['game_version'],catalog_sha256=manifest['catalog_sha256'],images=copied)
    temporary=output/'manifest.tmp';temporary.write_text(json.dumps(bundled,separators=(',',':')),encoding='utf8');temporary.replace(output/'manifest.json')
    for path in images.iterdir():
        if re.fullmatch('[a-f0-9]{64}\.png',path.name) and path.name not in kept and not path.is_symlink():
            assert path.resolve().parent==images.resolve();path.unlink()
    result=dict(preview_entries=len(copied),unique_pngs=len(kept),png_bytes=sum((images/n).stat().st_size for n in kept),manifest_bytes=(output/'manifest.json').stat().st_size)
    report=ROOT/'artifacts/research/monster-audit/bundled-size.json';report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2),encoding='utf8')
    return result

if __name__=='__main__':print(json.dumps(copy_previews()))
