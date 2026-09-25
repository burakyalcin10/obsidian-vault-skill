#!/usr/bin/env python3
"""Vault bakım raporu.

Kullanım:
    python check.py "<vault yolu>"          # Markdown rapor
    python check.py "<vault yolu>" --json   # makine okunur çıktı

Sadece okur, hiçbir dosyayı değiştirmez. Yalnızca standart kütüphane kullanır.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

LINK_RE = re.compile(r"(!?)\[\[([^\]]+?)\]\]")
FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)

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


def is_hub(rel: Path) -> bool:
    """index, kök log ya da bir proje log'u mu? Bunlar içerik değil, gezinti sayfası."""
    return rel.as_posix() in HUB_NOTES or rel.name.endswith(" Log.md")


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
        self.files = sorted(
            p.relative_to(root) for p in root.rglob("*")
            if p.is_file() and not IGNORED_DIRS.intersection(p.relative_to(root).parts)
        )
        self.notes = [f for f in self.files if f.suffix == ".md"]

        # Obsidian linkleri dosya adıyla ve büyük/küçük harf duyarsız çözer
        self.by_stem = defaultdict(list)   # "chunking" → [Kavramlar/Chunking.md]
        self.by_name = defaultdict(list)   # "er_diagram.png" → [ER_diagram.png]
        for f in self.files:
            self.by_name[f.name.lower()].append(f)
            if f.suffix == ".md":
                self.by_stem[f.stem.lower()].append(f)

        self.text = {n: self._read(n) for n in self.notes}
        # not → [(ham link, çözülen hedef ya da None)]; aynı sayfa başlık linkleri hariç
        self.links = {n: self._extract_links(self.text[n]) for n in self.notes}

        self.incoming = defaultdict(set)
        for src, links in self.links.items():
            for _, target in links:
                if target and target != src:
                    self.incoming[target].add(src)

    def _read(self, rel: Path) -> str:
        return (self.root / rel).read_text(encoding="utf-8", errors="replace")

    def _extract_links(self, text: str):
        body = INLINE_CODE_RE.sub("", FENCE_RE.sub("", text))
        out = []
        for m in LINK_RE.finditer(body):
            raw = m.group(2)
            target = raw.replace("\\|", "|").split("|", 1)[0].split("#", 1)[0].strip()
            if target:
                out.append((raw, self.resolve(target)))
        return out

    def resolve(self, target: str):
        t = target.replace("\\", "/").lower()
        if "/" in t:
            for f in self.files:
                p = f.as_posix().lower()
                if p in (t, t + ".md") or p.endswith("/" + t) or p.endswith("/" + t + ".md"):
                    return f
            return None
        hits = self.by_stem.get(t) or self.by_name.get(t)
        return hits[0] if hits else None

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
    return [f"{src.as_posix()} → [[{raw}]]"
            for src, links in v.links.items() for raw, t in links if t is None]


def check_duplicates(v: Vault):
    return [" | ".join(p.as_posix() for p in paths)
            for paths in v.by_stem.values() if len(paths) > 1]


def check_index(v: Vault):
    index = Path("index.md")
    if index not in v.text:
        return ["index.md yok"]
    linked = v.linked_from(index)
    out = [f"kavram: {n.as_posix()}" for n in v.notes
           if top_dir(n) == "Kavramlar" and n not in linked]
    out += [f"proje: {p}" for p in v.projects()
            if Path("Projeler", p, f"{p} Projesi.md") not in linked]
    return out


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
        if top_dir(n) != "Kavramlar":
            continue
        fm = v.frontmatter(n)
        if re.search(r"^proje\s*:", fm, re.M) or "proje/" in fm:
            out.append(n.as_posix())
    return out


def check_orphans(v: Vault):
    return [n.as_posix() for n in v.notes if is_orphan(n, v.incoming.get(n, set()))]


def check_inbox(v: Vault):
    logs = [n for n in v.notes if is_hub(n) and n.as_posix() != "index.md"]
    log_text = "\n".join(v.text[l] for l in logs)
    return [f.as_posix() for f in v.files
            if top_dir(f) == "Inbox" and f"Inbox/{f.name}" not in log_text]


CHECKS = [
    ("broken_links", "Kırık wikilink'ler", check_broken),
    ("duplicate_names", "Aynı adlı notlar (link belirsizliği)", check_duplicates),
    ("missing_from_index", "index'te olmayan kavram ve projeler", check_index),
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
