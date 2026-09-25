#!/usr/bin/env python3
"""Vault bakım raporu.

Kullanım:
    python check.py "<vault yolu>"          # Markdown rapor
    python check.py "<vault yolu>" --json   # makine okunur çıktı

Sadece okur, hiçbir dosyayı değiştirmez. Yalnızca standart kütüphane kullanır.
"""
from __future__ import annotations  # `Path | None` Python 3.8-3.9'da da çalışsın

import argparse
import json
import posixpath
import re
import sys
import unicodedata
import urllib.parse
from collections import defaultdict
from pathlib import Path

WIKILINK_RE = re.compile(r"!?\[\[([^\]]+?)\]\]")
# [metin](hedef), ![alt](resim.png), [metin](<boşluklu ad.md>), [metin](hedef "başlık")
MDLINK_RE = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^)\s]+)(?:\s+\"[^\"\n]*\")?\s*\)")
URL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)  # https:, mailto:, obsidian:
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*$")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)


def nfc(s: str) -> str:
    """macOS dosya adlarını NFD (ayrışık) verir, notlar NFC yazılır; hepsini NFC'ye çevir."""
    return unicodedata.normalize("NFC", s)


def strip_code(text: str) -> str:
    """Kod bloklarını (``` ve ~~~) ve satır içi kodu çıkar; içlerindeki linkler sayılmaz.

    Blok, aynı karakterle ve en az açılış uzunluğunda bir çitle kapanır; böylece
    ```` içindeki ``` bloğu dış bloğu kapatmaz.
    """
    out, fence = [], None
    for line in text.split("\n"):
        if fence:
            m = FENCE_CLOSE_RE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            out.append("")
        elif m := FENCE_OPEN_RE.match(line):
            fence = m.group(1)
            out.append("")
        else:
            out.append(line)
    return INLINE_CODE_RE.sub("", "\n".join(out))

IGNORED_DIRS = {".obsidian", ".trash", ".git"}
HUB_NOTES = {"index.md", "log.md"}  # kökteki giriş ve log; her şeye link verir


# ── Yardımcılar (is_orphan içinde kullanılabilir) ────────────────────────────

def top_dir(rel: Path) -> str:
    """Notun kökteki klasörü ('Projeler', 'Kavramlar', …); kökteyse ''."""
    return rel.parts[0] if len(rel.parts) > 1 else ""


def in_claude_area(rel: Path) -> bool:
    """Skill'in yönettiği alan mı? Kullanıcının kendi notları bu alanın dışında."""
    return top_dir(rel) in {"Projeler", "Kavramlar"} or rel.as_posix() in {
        "index.md", "log.md", "Vault Kullanımı.md"}


def is_category(rel: Path) -> bool:
    """Kavramlar/Kategoriler/ altındaki kategori sayfası mı?"""
    return rel.parts[:2] == ("Kavramlar", "Kategoriler")


def is_concept(rel: Path) -> bool:
    return top_dir(rel) == "Kavramlar" and not is_category(rel)


def is_hub(rel: Path) -> bool:
    """index, log ya da kategori sayfası mı? Bunlar içerik değil, gezinti sayfası."""
    return rel.as_posix() in HUB_NOTES or rel.name.endswith(" Log.md") or is_category(rel)


# ── Yetim sayfa kuralı ───────────────────────────────────────────────────────

def is_orphan(note: Path, sources: set[Path]) -> bool:
    """`note` yetim sayılmalı mı?

    note    : vault'a göre yol, ör. Path('Kavramlar/Chunking.md')
    sources : bu nota link veren notlar (kendisi hariç)

    Kural:
    - Kullanıcının kendi notları kontrol edilmez; onların bağlantısız olması normal.
    - Giriş sayfaları (index, log'lar, proje sayfaları, Vault Kullanımı) yetim sayılmaz.
    - index ve log'lardan gelen linkler sayılmaz: bir sayfa sadece listelenmiş ama
      hiçbir içerik notu onu kullanmıyorsa yetimdir.
    """
    if not in_claude_area(note):
        return False
    if is_hub(note) or note.name.endswith(" Projesi.md") or note.as_posix() == "Vault Kullanımı.md":
        return False
    return not any(not is_hub(s) for s in sources)


# ── Vault modeli ─────────────────────────────────────────────────────────────

class Vault:
    def __init__(self, root: Path):
        self.root = root
        # Rapor ve eşleştirme NFC yollarla yapılır; diskten okumak için gerçek yol saklanır
        self.real = {}
        for p in root.rglob("*"):
            rel = p.relative_to(root)
            if p.is_file() and not IGNORED_DIRS.intersection(rel.parts):
                self.real[Path(nfc(rel.as_posix()))] = p
        self.files = sorted(self.real)
        self.notes = [f for f in self.files if f.suffix == ".md"]

        # Obsidian linkleri dosya adıyla ve büyük/küçük harf duyarsız çözer
        self.by_stem = defaultdict(list)   # "chunking" → [Kavramlar/Chunking.md]
        self.by_name = defaultdict(list)   # "er_diagram.png" → [ER_diagram.png]
        self.by_path = {}                  # "kavramlar/chunking.md" → Kavramlar/Chunking.md
        for f in self.files:
            self.by_name[f.name.lower()].append(f)
            self.by_path[f.as_posix().lower()] = f
            if f.suffix == ".md":
                self.by_stem[f.stem.lower()].append(f)

        self.text = {n: self._read(n) for n in self.notes}
        # not → [(ham link, çözülen hedef ya da None)]; aynı sayfa başlık linkleri hariç
        self.links = {n: self._extract_links(n, self.text[n]) for n in self.notes}

        self.incoming = defaultdict(set)
        for src, links in self.links.items():
            for _, target in links:
                if target and target != src:
                    self.incoming[target].add(src)

    def _read(self, rel: Path) -> str:
        # utf-8-sig: bazı Windows editörlerinin eklediği BOM'u atar (yoksa frontmatter eşleşmez)
        return nfc(self.real[rel].read_text(encoding="utf-8-sig", errors="replace"))

    def _extract_links(self, src: Path, text: str):
        """[(nottaki yazılışı, çözülen hedef ya da None)]; aynı sayfa başlık linkleri ve dış URL'ler hariç."""
        body = strip_code(text)
        out = []
        for m in WIKILINK_RE.finditer(body):
            raw = m.group(1)
            target = raw.replace("\\|", "|").split("|", 1)[0].split("#", 1)[0].strip()
            if target:
                out.append((m.group(0), self.resolve(target, src)))
        for m in MDLINK_RE.finditer(body):
            raw = m.group(1).strip("<>")
            if URL_SCHEME_RE.match(raw):
                continue
            target = nfc(urllib.parse.unquote(raw)).split("#", 1)[0].strip()
            if target:
                out.append((m.group(0), self.resolve(target, src)))
        return out

    def resolve(self, target: str, src: Path | None = None):
        t = target.replace("\\", "/")
        if "/" not in t:
            key = t.lower()
            hits = self.by_stem.get(key) or self.by_name.get(key)
            return hits[0] if hits else None

        # Yol içeren link: önce notun klasörüne göre, sonra vault kökünden, en son sonek eşleşmesi
        candidates = []
        if src is not None:
            candidates.append(posixpath.normpath(posixpath.join(src.parent.as_posix(), t)))
        candidates.append(posixpath.normpath(t.lstrip("/")))
        for c in candidates:
            if c.startswith(".."):  # vault dışına çıkıyor
                continue
            hit = self.by_path.get(c.lower()) or self.by_path.get(c.lower() + ".md")
            if hit:
                return hit
        suffix = "/" + t.lower().lstrip("./")
        for p, f in self.by_path.items():
            if p.endswith(suffix) or p.endswith(suffix + ".md"):
                return f
        return None

    def frontmatter(self, rel: Path) -> str:
        m = FRONTMATTER_RE.match(self.text.get(rel, ""))
        return m.group(1) if m else ""

    def linked_from(self, rel: Path) -> set:
        return {t for _, t in self.links.get(rel, []) if t}

    def projects(self):
        base = self.root / "Projeler"
        return sorted(d.name for d in base.iterdir() if d.is_dir()) if base.is_dir() else []


# ── Kontroller ───────────────────────────────────────────────────────────────

def check_broken(v: Vault):
    return [f"{src.as_posix()} → {raw}"
            for src, links in v.links.items() for raw, t in links if t is None]


def check_duplicates(v: Vault):
    return [" | ".join(p.as_posix() for p in paths)
            for paths in v.by_stem.values() if len(paths) > 1]


def check_index(v: Vault):
    index = Path("index.md")
    if index not in v.text:
        return ["index.md yok"]
    linked = v.linked_from(index)
    out = [f"proje: {p}" for p in v.projects()
           if Path("Projeler", p, f"{p} Projesi.md") not in linked]
    out += [f"kategori: {n.as_posix()}" for n in v.notes
            if is_category(n) and n not in linked]
    return out


def check_uncategorized(v: Vault):
    listed = set()
    for n in v.notes:
        if is_category(n):
            listed |= v.linked_from(n)
    return [n.as_posix() for n in v.notes if is_concept(n) and n not in listed]


def check_project_pages(v: Vault):
    out = []
    for p in v.projects():
        page = Path("Projeler", p, f"{p} Projesi.md")
        if page not in v.text:
            out.append(f"{p}: proje sayfası yok ({page.as_posix()})")
            continue
        linked = v.linked_from(page)
        out += [f"{p}: {n.as_posix()}" for n in v.notes
                if n.parts[:2] == ("Projeler", p) and n != page and n not in linked]
    return out


def check_concept_rules(v: Vault):
    out = []
    for n in v.notes:
        if not is_concept(n):
            continue
        fm = v.frontmatter(n)
        if re.search(r"^proje\s*:", fm, re.M) or "proje/" in fm:
            out.append(n.as_posix())
    return out


def check_orphans(v: Vault):
    return [n.as_posix() for n in v.notes if is_orphan(n, v.incoming.get(n, set()))]


def check_inbox(v: Vault):
    # İşlenen kaynak Inbox/İşlendi/'ye taşınır; geri kalan her şey (alt klasörler dahil) bekliyor.
    return [f.as_posix() for f in v.files if top_dir(f) == "Inbox" and f.parts[1] != "İşlendi"]


CHECKS = [
    ("broken_links", "Kırık linkler", check_broken),
    ("duplicate_names", "Aynı adlı notlar (link belirsizliği)", check_duplicates),
    ("missing_from_index", "index'te olmayan proje ve kategoriler", check_index),
    ("uncategorized_concepts", "Hiçbir kategori sayfasında olmayan kavramlar", check_uncategorized),
    ("unlisted_project_files", "Proje sayfasında listelenmeyen dosyalar", check_project_pages),
    ("concepts_with_project", "`proje:` alanı taşıyan kavram sayfaları", check_concept_rules),
    ("orphans", "Yetim sayfalar", check_orphans),
    ("inbox_pending", "Inbox'ta bekleyenler", check_inbox),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore  # Windows konsolu cp1254
    ap = argparse.ArgumentParser(description="Obsidian vault bakım raporu")
    ap.add_argument("vault", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.vault.is_dir():
        sys.exit(f"Vault bulunamadı: {args.vault}")

    v = Vault(args.vault)
    results = {key: fn(v) for key, _, fn in CHECKS}

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    total = sum(len(r) for r in results.values())
    print(f"# Vault bakım raporu\n\n{len(v.notes)} not, {len(v.files)} dosya, {total} bulgu\n")
    for key, title, _ in CHECKS:
        items = results[key]
        print(f"## {title} ({len(items)})")
        print("\n".join(f"- {i}" for i in items) if items else "- yok")
        print()


if __name__ == "__main__":
    main()
