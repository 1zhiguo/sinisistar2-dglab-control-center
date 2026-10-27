"""Presentation-only localization; game identifiers and stored rules stay intact."""
from functools import lru_cache
from pathlib import Path
import json,re

LANGUAGES=('zh-CN','ja','en')
ROOT=Path(__file__).parent/'assets/i18n'

class Localizer:
    def __init__(self):
        self.catalogs={lang:json.loads((ROOT/(lang+'.json')).read_text(encoding='utf-8')) if (ROOT/(lang+'.json')).exists() else {} for lang in ('ja','en')}
        self.patterns={lang:re.compile('|'.join(re.escape(k) for k in sorted(catalog,key=len,reverse=True)
            if len(k.strip())>1 or len(k)>1 and (k[0].isspace() or k[-1].isspace()))) if catalog else None for lang,catalog in self.catalogs.items()}
    @lru_cache(maxsize=8192)
    def translate(self,text,language):
        if language=='zh-CN' or language not in self.catalogs or text in ('中文','日本語','English'):return text
        catalog=self.catalogs[language]
        if text in catalog:return catalog[text]
        pattern=self.patterns[language]
        return pattern.sub(lambda m:catalog[m.group()],text) if pattern else text
