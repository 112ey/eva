"""Eva (fork): память — поиск по дневнику и рабочая память (по мотивам alex2772/kuni).

Три вещи из Kuni, переложенные на Еву без внешних зависимостей (без эмбеддингов и Ollama):

* **Вспоминание при чтении** (``recall_block``) — когда ей пишут, по тексту сообщения ищутся
  её же дневниковые записи, похожие по словам, и подклеиваются в конец сообщения блоком
  ``<вспомнилось>``. Это аналог kuni-шного «related diary entries в конец последнего сообщения»:
  у живого человека при чтении всплывают связанные воспоминания сами.
* **Рабочая память** (``read_working_memory``) — ``<home>/working_memory.md``: слой на 1–3 дня
  (обещания, напоминания, незакрытые дела, настроение и самочувствие), который всегда висит в
  промте как ``<things_to_remember>``.
* **Похожесть записей** (``similarity``) — для дедупа при записи и для «сна»-консолидации.

Скоринг намеренно простой: пересечение слов с весами IDF по всему дневнику, плюс небольшой
бонус за свежесть. Без эмбеддингов — у Евы нет своей инфраструктуры для них, а на её объёме
(десятки страниц) этого достаточно.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / "eva-home"))
DIARY_DIR = HOME / "diary"
WORKING_MEMORY = HOME / "working_memory.md"

_WORD = re.compile(r"[а-яёa-z0-9]{3,}", re.IGNORECASE)
# Слова, которые не помогают искать воспоминания.
_STOP = {
    "что", "как", "это", "его", "её", "ее", "мой", "моя", "мне", "тебя", "тебе", "они", "она",
    "есть", "был", "была", "было", "были", "для", "или", "если", "тоже", "ещё", "еще", "вообще",
    "там", "тут", "вот", "уже", "все", "всё", "всех", "меня", "нас", "вас", "них", "кто", "чем",
    "почему", "зачем", "когда", "ну", "да", "нет", "привет", "пока", "ок", "окей", "ага",
}


@dataclass
class Page:
    """Дневниковая запись: имя, описание из шапки, тело и путь."""

    name: str
    description: str
    body: str
    path: Path
    mtime: float

    @property
    def text(self) -> str:
        return f"{self.name} {self.description} {self.body}"


def _strip_frontmatter(raw: str) -> tuple[str, str]:
    """``(description, body)`` из SKILL.md-подобной страницы."""
    text = raw.lstrip("\ufeff")
    description, body = "", text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            head, body = text[3:end], text[end + 4:]
            match = re.search(r"^description:\s*(.+)$", head, re.M)
            if match:
                description = match.group(1).strip().strip('"').strip("'")
            body = body.lstrip("\n")
    return description, body.strip()


def diary_pages(diary_dir: Path | None = None) -> list[Page]:
    """Все страницы дневника (у Евы это ``<home>/diary/<имя>/SKILL.md``)."""
    root = Path(diary_dir or DIARY_DIR)
    pages: list[Page] = []
    for path in sorted(root.rglob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            stat = path.stat()
        except OSError:
            continue
        description, body = _strip_frontmatter(raw)
        if not body and not description:
            continue
        pages.append(Page(name=path.parent.name if path.name == "SKILL.md" else path.stem,
                          description=description, body=body, path=path, mtime=stat.st_mtime))
    return pages


def words(text: str) -> list[str]:
    return [w for w in (m.group(0).lower() for m in _WORD.finditer(text or "")) if w not in _STOP]


# Русская морфология ломает простое сравнение по словам: «наехал» и «наехать», «ответила» и
# «ответить» — для машины разные слова. Обрезаем частые окончания — этого хватает, чтобы
# записи про одно и то же событие находились, а разные темы не склеивались.
_ENDINGS = ("ами", "ями", "ать", "ять", "ить", "еть", "его", "ого", "ему", "ому", "ыми", "ими",
            "ая", "яя", "ые", "ие", "ый", "ий", "ой", "ей", "ов", "ев", "ам", "ям", "ах", "ях",
            "ил", "ел", "ал", "ял", "ит", "ет", "ут", "ют", "ла", "ло", "ли", "ть", "ся", "сь",
            "у", "ю", "а", "я", "е", "ы", "и", "о", "ь")


def _stem(word: str) -> str:
    word = word.replace("ё", "е")
    for ending in _ENDINGS:
        if len(word) - len(ending) >= 4 and word.endswith(ending):
            return word[: -len(ending)]
    return word


def stems(text: str) -> list[str]:
    """Слова текста, обрезанные до основы (для сравнения записей между собой)."""
    return [_stem(w) for w in words(text)]


def shared_stems(left: str, right: str) -> set[str]:
    """Общие основы двух текстов — для «слишком ли это вообще про одно и то же»."""
    return set(stems(left)) & set(stems(right))


def _idf(pages: list[Page]) -> dict[str, float]:
    """IDF: редкие слова (имена, «вархаммер», «зарядник») весят больше частых."""
    total = max(1, len(pages))
    df: dict[str, int] = {}
    for page in pages:
        for word in set(stems(page.text)):
            df[word] = df.get(word, 0) + 1
    return {w: math.log(1 + total / (1 + n)) for w, n in df.items()}


def similarity(left: str, right: str) -> float:
    """Близость двух текстов по основам слов, 0..1 (для дедупа и «сна»).

    Мера — коэффициент пересечения (``|A∩B| / min(|A|,|B|)``), а не косинус: у коротких живых
    записей косинус слишком строгий (косинус двух записей про один и тот же скандал даёт ~0.2).
    """
    a, b = set(stems(left)), set(stems(right))
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def rank(query: str, pages: list[Page] | None = None, *, idf: dict[str, float] | None = None) -> list[tuple[float, Page]]:
    """Страницы по убыванию близости к ``query`` (IDF-взвешенное пересечение + свежесть)."""
    pages = diary_pages() if pages is None else pages
    if not pages or not query.strip():
        return []
    weights = _idf(pages) if idf is None else idf
    # Сравниваем основы, а не сырые слова: «Алексея» из сообщения должно находить «Алексей» в записи.
    q = set(stems(query))
    if not q:
        return []
    newest = max(p.mtime for p in pages)
    scored: list[tuple[float, Page]] = []
    for page in pages:
        page_words = set(stems(page.text))
        hit = sum(weights.get(w, 1.0) for w in q & page_words)
        if hit <= 0:
            continue
        # Нормировка на длину страницы: иначе длинные «страницы дня» (в них сваливается вся
        # переписка) выигрывают у короткой точной записи про конкретного человека.
        hit /= math.sqrt(len(page_words)) or 1.0
        # Свежесть — слабый бонус (до 15%): важнее слова, но «вчера» вспоминается охотнее «весны».
        age_days = max(0.0, (newest - page.mtime) / 86400)
        freshness = 1.0 / (1.0 + age_days / 7.0)
        scored.append((hit * (1.0 + 0.15 * freshness), page))
    scored.sort(key=lambda row: -row[0])
    return scored


def recall_block(query: str, *, limit: int = 3, min_share: float = 0.35,
                 pages: list[Page] | None = None, max_chars: int = 900) -> str:
    """Блок ``<вспомнилось>`` с связанными записями — или пустая строка, если нечего вспомнить.

    ``min_share`` — какая доля от лучшего совпадения считается «достаточно похожим», чтобы
    не тянуть в ответ случайные страницы.
    """
    ranked = rank(query, pages)
    if not ranked:
        return ""
    best = ranked[0][0]
    picked: list[str] = []
    for score, page in ranked[:max(1, limit)]:
        if score < best * min_share:
            break
        body = " ".join(page.body.split())
        if len(body) > max_chars // max(1, limit):
            body = body[: max_chars // max(1, limit)].rstrip() + "…"
        picked.append(f"• {page.name}: {body}")
    if not picked:
        return ""
    return (
        "<вспомнилось>\n"
        "Это твои собственные записи из дневника, которые всплыли в голове при чтении. "
        "Не цитируй их дословно, не пересказывай списком и не показывай, что у тебя есть файл — "
        "просто ты это помнишь.\n" + "\n".join(picked) + "\n</вспомнилось>"
    )


def read_working_memory() -> str:
    try:
        return WORKING_MEMORY.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def working_memory_block() -> str:
    """``<things_to_remember>`` для промта — пустая строка, если файла нет."""
    content = read_working_memory()
    if not content:
        return ""
    return f"<things_to_remember>\n{content}\n</things_to_remember>"


def write_working_memory(content: str) -> Path:
    """Атомарная запись рабочей памяти (предыдущая версия уходит в .bak)."""
    WORKING_MEMORY.parent.mkdir(parents=True, exist_ok=True)
    if WORKING_MEMORY.exists():
        try:
            WORKING_MEMORY.with_suffix(".md.bak").write_text(
                WORKING_MEMORY.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        except OSError:
            pass
    tmp = WORKING_MEMORY.with_suffix(".md.tmp")
    tmp.write_text(content.strip() + "\n", encoding="utf-8")
    tmp.replace(WORKING_MEMORY)
    return WORKING_MEMORY
