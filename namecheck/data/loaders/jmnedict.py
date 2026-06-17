"""Source C: JMnedict Japanese name readings (japan only).

Raw: data/source/JMnedict.xml. The <reb> kana readings are converted to Hepburn
romaji (pykakasi) into data/cache/japan/jmnedict_romaji.txt (intermediate, made
once), then tokenized. Frequency = occurrence count.
"""
import os
import re

from namecheck.data.config import source_dir, cache_dir, cache_file
from namecheck.data.loaders.base import TokenLoader, valid_tokens


class JmnedictLoader(TokenLoader):
    name = "jmnedict"
    stage = 0
    curated = False
    scope = {"japan"}

    def _romaji_path(self):
        return cache_file("japan", "jmnedict_romaji.txt")

    def _ensure_romaji(self):
        out_path = self._romaji_path()
        if os.path.exists(out_path):
            return out_path
        xml_path = os.path.join(source_dir(), "JMnedict.xml")
        if not os.path.exists(xml_path):
            print(f"    jmnedict: no {xml_path} -- skipped")
            return None
        try:
            import pykakasi
        except ImportError:
            print("    jmnedict: JMnedict.xml found but pykakasi not installed "
                  "(pip install pykakasi) -- skipped")
            return None
        print(f"    jmnedict: extracting kana readings from {xml_path} ...")
        reb = re.compile(r"<reb>([^<]+)</reb>")
        readings = set()
        with open(xml_path, encoding="utf-8") as f:
            for line in f:
                m = reb.search(line)
                if m:
                    readings.add(m.group(1))
        kks = pykakasi.kakasi()
        romaji = set()
        for r in readings:
            s = "".join(p["hepburn"] for p in kks.convert(r))
            if s.isascii() and s.isalpha() and len(s) >= 2:
                romaji.add(s.lower())
        os.makedirs(cache_dir("japan"), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(romaji)))
        print(f"    jmnedict: wrote {len(romaji)} romaji names -> {out_path}")
        return out_path

    def contribute(self, country):
        if country != "japan":
            return {}
        path = self._ensure_romaji()
        if not path or not os.path.exists(path):
            return {}
        freq = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                for tok in valid_tokens(line):
                    freq[tok] = freq.get(tok, 0) + 1
        print(f"    jmnedict[japan]: {len(freq)} tokens")
        return freq
