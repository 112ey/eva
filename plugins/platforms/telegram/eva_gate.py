"""Eva (fork): «звать ли Еву» — узкий проход модели перед её ходом.

Чат читается целиком (Hermes складывает неадресованные сообщения в observed-контекст), но ход
Евы открывается только тогда, когда в разговоре есть для неё смысл. Решение принимает не
персона, а отдельный короткий вызов модели: маленькой модели легко ответить одним словом
ДА/НЕТ, тогда как «героически молчать» в роли живого человека она не умеет.

Хук живет в адаптере: ``_gate_or_observe`` → ``should_reply(...)`` → либо ход, либо
``_observe_unmentioned_group_message`` (сообщение всё равно попадает в её контекст).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Пауза фильтра после серии неудач: иначе каждое сообщение в чате будет ждать таймаута,
# а гейтвей встанет. Пока провайдер лежит, всё равно молчим — но быстро.
_STATE: dict[str, float] = {"failures": 0.0, "cooldown_until": 0.0}
_FAILURE_LIMIT = 3
_COOLDOWN_SECONDS = 600

# Провайдер → (переменная с ключом, база по умолчанию). База из окружения приоритетнее.
_PROVIDERS = {
    "nvidia": ("NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1"),
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
    "google": ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai"),
    "z-ai": ("ZAI_API_KEY", "https://api.z.ai/api/paas/v4"),
}

SYSTEM_PROMPT = (
    "Ты — фильтр в телеграм-чате. Ты НЕ Ева: ты смотришь последние сообщения и решаешь, что Еве "
    "делать с последним сообщением: написать ответ (ДА), просто поставить смайлик-реакцию "
    "(РЕАКЦИЯ <эмодзи>) или ничего не делать (НЕТ).\n\n"
    "Решай по порядку — первое подходящее правило заканчивает проверку:\n"
    "1. Это ответ или продолжение разговора с ней: предыдущее сообщение писала Ева (в окне оно "
    "помечено «[Ева]»), или ей задали вопрос, или отвечают на её вопрос — даже если новое "
    "сообщение одно слово («молва», «ок», «в три») → ДА. Но односложная реплика в ЧУЖОМ "
    "разговоре («ок», «ага», «молва», «ну и что дальше») — это не разговор с ней, правило не "
    "срабатывает, смотри дальше. Ответ на ЕЁ сообщение одним словом («ок», «ага», «в три») — "
    "это всё равно ДА, даже если само слово ничего не значит. И если в окне ссора, обида или "
    "напряжение — короткая реплика тоже важна, срабатывает правило 2.\n"
    "2. Есть ссора, оскорбления, агрессия, кто-то кого-то гнобит или двое грызутся → ДА.\n"
    "3. К Еве обратились (её имя, @упоминание, ответ на её сообщение) или говорят о ней → ДА.\n"
    "4. Стикер. Стикеры — ОБЫЧНЫЙ способ Евы ответить коротко, а не редкий жест. Если у неё есть "
    "однозначный короткий ответ и ниже дан список стикеров — выбирай «СТИКЕР <номер>». Это: "
    "приветствие и прощание, согласие и отказ, «сам такой», «иди нафиг», «не знаю», «ну и ладно», "
    "«пфф», насмешка в ответ, смех над шуткой или мемом, восторг, удивление, сонное «отстань». "
    "Сомневаешься между текстом и стикером и ответ укладывается в картинку — бери стикер. НО если "
    "ответ надо объяснять словами, утешать, советовать или это серьёзный разговор (беда, обида, "
    "ссора, просьба) — ДА, и никакого стикера.\n"
    "4а. Смайлик. Если на её ответ слова не нужны вообще, а отклик совсем тихий — чужой успех, "
    "что-то красивое, милота, «да ладно» — → РЕАКЦИЯ <подходящий эмодзи>. Но если подходит стикер "
    "из списка (шутка, привет, согласие), правило 4 важнее.\n"
    "5. Случилось то, на что живой человек её характера отреагировал бы: важная новость "
    "(у кого-то беда или большая удача), грубость в чей-то адрес, несправедливость, что-то "
    "реально смешное → ДА.\n"
    "6. Прислали медиа: фото, видео, стикер или мем — особенно с подписью или просьбой "
    "посмотреть, оценить, угадать что это («смотри», «посмотри», «как тебе», «угадай», «мило?») "
    "→ ДА. Если медиа просто приложено к чужому разговору — смотри правило 7.\n"
    "7. Иначе — обычная болтовня двух-трёх людей между собой, ссылки, «ага», «лол», бытовые и "
    "рабочие детали не про неё → НЕТ.\n\n"
    "Сомневаешься между ДА и НЕТ — выбирай НЕТ: влезать без повода хуже, чем промолчать. "
    "Сомневаешься между ДА и РЕАКЦИЕЙ — выбирай РЕАКЦИЮ: смайлик видно тихо, за него не страшно. "
    "Эмодзи для реакции — только из этого набора: "
    "👍 👎 ❤️ 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 👌 🕊 🤡 🥱 🥴 😍 🐳 💯 🤣 ⚡ 🏆 💔 🤨 😈 😴 😭 "
    "😨 😇 🤓 🤗 🫡 🙊 🙈 👀 😐 😑 😬 🦄 🍌 🌭 🌚.\n"
    "Отвечай коротко: «ДА», «НЕТ» или «РЕАКЦИЯ 🤣» — без объяснений.\n\n"
    "Примеры:\n"
    "[Паша] кто-нибудь видел мой зарядник? → НЕТ\n"
    "[Алексей] ты дебил, Паша → ДА\n"
    "[Ева] как называется эта группа? / [Владелец] молва → ДА\n"
    "[Паша] Ева вообще чё-то притихла → ДА\n"
    "[Максим] ахахах вот мем → РЕАКЦИЯ 🤣\n"
    "[Паша] (фото) вот кот спит, лапки раскинул → РЕАКЦИЯ 🥰\n"
    "[Роман] сдал экзамен наконец → РЕАКЦИЯ 🎉\n"
    "[Владелец] (фото) Смотрите какой кошак → ДА\n"
    "[Паша] (фото) моя новая тачка → ДА\n"
    "[Алексей] у меня вчера кот умер → ДА\n"
    "[Паша] ну ладно, пошёл спать → НЕТ\n"
    "[Паша] вот мем / [Максим] ахахах / [Паша] ну и что дальше → НЕТ\n"
    "[Паша] я в два освобожусь / [Максим] понял, тогда в три / [Паша] ок → НЕТ\n"
    "[Паша] я завтра в школу не пойду / [Максим] ясно / [Алексей] молва → НЕТ\n"
    "[Алексей] ты вообще не мужик / [Паша] а ты дебил / [Паша] ну и что дальше → ДА\n"
    "[Паша] Ева, ну ты и дурак / [Ева] чего это я / [Паша] иди отсюда → СТИКЕР 7\n"
    "[Паша] Ева, привет → СТИКЕР (приветствие котом)\n"
    "[Паша] ахахахах ну ты выдал → СТИКЕР 12\n"
    "[Алексей] Ева, пойдёшь с нами гулять? → ДА (надо ответить, а не картинкой)\n"
    "[Паша] ахахах ты видел это (мем, не ей) → РЕАКЦИЯ 🤣\n"
    "[Максим] я сдал экзамен на пять! → РЕАКЦИЯ 🎉\n"
    "[Паша] Ева, ты вообще шаришь в этом? → ДА\n"
    "[Ева] ты придёшь в шесть? / [Паша] ок → ДА\n"
    "[Ева] что делаешь? / [Паша] да ничё, лежу → ДА"
    "[Алексей] ты мне надоел / [Паша] сам такой / [Алексей] всё, я обиделся / [Паша] ок → ДА"
)

_YES = re.compile(r"\b(ДА|YES|TRUE)\b", re.IGNORECASE)
_NO = re.compile(r"\b(НЕТ|НЕ|NO|FALSE)\b", re.IGNORECASE)
_REACT = re.compile(r"РЕАКЦ\w*", re.IGNORECASE)
_STICKER = re.compile(r"СТИКЕР\w*", re.IGNORECASE)
_DIGITS = re.compile(r"\d{1,3}")


def _parse_classify(text: str) -> tuple[str, str]:
    """Ответ фильтра → ``(вердикт, эмодзи)``.

    Вердикты: ``reply`` (писать словами), ``react`` (поставить смайлик), ``silent`` (ничего).
    """
    verdict = (text or "").strip()
    if not verdict:
        return "silent", ""
    sticker_match = _STICKER.search(verdict)
    if sticker_match:
        digits = _DIGITS.search(verdict[sticker_match.end():]) or _DIGITS.search(verdict)
        if digits:
            return "sticker", digits.group(0)
        log.info("eva_gate: фильтр выбрал стикер, но номер не разобрала (%r) — молчу", verdict[:40])
        return "silent", ""
    match = _REACT.search(verdict)
    if match:
        try:
            from eva_reactions import normalize
        except Exception:  # noqa: BLE001
            def normalize(value):  # type: ignore[misc]
                return ""
        emoji = normalize(verdict[match.end():]) or normalize(verdict)
        if emoji:
            return "react", emoji
        log.info("eva_gate: фильтр выбрал реакцию, но эмодзи не разобрала (%r) — молчу", verdict[:40])
        return "silent", ""
    if _YES.search(verdict) and not _NO.search(verdict):
        return "reply", ""
    if _NO.search(verdict):
        return "silent", ""
    log.info("eva_gate: неожиданный ответ фильтра %r — считаю, что ничего не делаем", verdict[:60])
    return "silent", ""


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))


def _env_file_value(name: str) -> str:
    """Значение из окружения, иначе из `<home>/.env` (гейтвей .env загружает, `--run-module` — нет)."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    for candidate in (_hermes_home() / ".env", Path.home() / ".hermes" / ".env"):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = re.search(rf"^{re.escape(name)}\s*=\s*(.+)$", text, re.M)
        if match:
            return match.group(1).strip().strip('"').strip("'")
    return ""


def resolve_target() -> tuple[str, str, str]:
    """``(provider, model, base_url)`` для фильтра — её же модель, если не задано иное."""
    provider, model, base_url = "", "", ""
    try:
        from hermes_cli.config_effective import load_user_config_effective
        cfg = load_user_config_effective() or {}
        block = cfg.get("model") or {}
        provider = str(block.get("provider") or "").strip()
        model = str(block.get("default") or "").strip()
        gate = ((cfg.get("platforms") or {}).get("telegram") or {}).get("extra", {}).get("eva_gate")
        if isinstance(gate, dict):
            provider = str(gate.get("provider") or provider).strip()
            model = str(gate.get("model") or model).strip()
            base_url = str(gate.get("base_url") or "").strip()
    except Exception as exc:  # noqa: BLE001 — фильтр не должен ронять гейтвей
        log.debug("eva_gate: не смогла прочитать конфиг: %s", exc)
    return provider, model, base_url


def resolve_reasoning_effort() -> str:
    """``platforms.telegram.extra.eva_gate.reasoning_effort`` — по умолчанию ``none``.

    У reasoning-моделей (nemotron на NIM) при малом лимите токенов весь ответ уходит в
    ``reasoning``, а ``content`` приходит пустым, поэтому вердикт выталкивается без размышлений.
    """
    try:
        from hermes_cli.config_effective import load_user_config_effective
        cfg = load_user_config_effective() or {}
        gate = ((cfg.get("platforms") or {}).get("telegram") or {}).get("extra", {}).get("eva_gate")
        if isinstance(gate, dict):
            return str(gate.get("reasoning_effort") or "none").strip() or "none"
    except Exception:  # noqa: BLE001
        pass
    return "none"


def _endpoint(provider: str, base_url: str) -> tuple[str, str]:
    env_key, default_base = _PROVIDERS.get(provider, ("", ""))
    base = base_url or _env_file_value(f"{provider.upper().replace('-', '_')}_BASE_URL") or default_base
    return base.rstrip("/"), _env_file_value(env_key)


def _call(base: str, api_key: str, model: str, messages: list, *, timeout: float,
          reasoning_effort: str, max_tokens: int = 16) -> Optional[str]:
    """Один вызов chat/completions. ``None`` — не получилось (сеть, ключ, статус)."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        # Nemotron/NIM reasoning models spend a tiny budget on `reasoning` and return empty
        # content, so the verdict must be forced out with reasoning off.
        "reasoning_effort": reasoning_effort,
        "stream": False,
    }).encode()
    request = urllib.request.Request(
        f"{base}/chat/completions", data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        log.warning("eva_gate: HTTP %s от %s: %s", exc.code, model,
                    exc.read().decode(errors="replace")[:200])
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("eva_gate: вызов не удался (%s): %s", model, exc)
        return None
    return (body.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""


def _parse_verdict(text: str) -> Optional[bool]:
    verdict = (text or "").strip()
    if not verdict:
        return None
    if _YES.search(verdict) and not _NO.search(verdict):
        return True
    if _NO.search(verdict):
        return False
    log.info("eva_gate: неожиданный ответ фильтра %r — считаю, что не звать", verdict[:60])
    return False


def resolve_fallback() -> tuple[str, str, str]:
    """Запасной провайдер для фильтра, если основной не отвечает.

    ``platforms.telegram.extra.eva_gate.fallback`` (``provider``/``model``/``base_url``); по
    умолчанию — DeepSeek, если в её ``.env`` есть ``DEEPSEEK_API_KEY``.
    """
    try:
        from hermes_cli.config_effective import load_user_config_effective
        cfg = load_user_config_effective() or {}
        gate = ((cfg.get("platforms") or {}).get("telegram") or {}).get("extra", {}).get("eva_gate")
        if isinstance(gate, dict):
            fb = gate.get("fallback")
            if isinstance(fb, dict) and fb.get("model"):
                return (str(fb.get("provider") or "deepseek").strip(),
                        str(fb["model"]).strip(), str(fb.get("base_url") or "").strip())
            if gate.get("fallback") is False:
                return "", "", ""
    except Exception:  # noqa: BLE001
        pass
    return ("deepseek", "deepseek-v4-pro", "") if _env_file_value("DEEPSEEK_API_KEY") else ("", "", "")


def _ask(lines: list[str], incoming: str, *, timeout: float = 10.0,
         reasoning_effort: Optional[str] = None, stickers: str = "") -> Optional[str]:
    """Спросить фильтр и вернуть его сырой ответ (None — не удалось: сеть/ключ/модель).

    Фильтр не должен ни ронять гейтвей, ни молотить по таймауту на каждое сообщение, если
    провайдер лёг: после трёх неудач подряд он замолкает на десять минут (в чате в это время
    тихо — но так же тихо было бы и без фильтра, потому что её же модель недоступна).
    """
    now = time.monotonic()
    if now < _STATE["cooldown_until"]:
        return None
    provider, model, base_url = resolve_target()
    if not model:
        log.warning("eva_gate: модель не определена, фильтр пропускает без решения")
        return None
    effort = reasoning_effort or resolve_reasoning_effort()
    chat_context = "\n".join(lines[-12:]).strip()
    user_text = (
        (f"Последние сообщения в чате:\n{chat_context}\n\n" if chat_context else "")
        + (f"Стикеры, которыми можно ответить (номер + описание):\n{stickers}\n\n" if stickers else "")
        + f"Новое сообщение:\n{incoming}\n\n"
        + ("Что Еве делать? Ответь коротко: ДА, НЕТ, РЕАКЦИЯ <эмодзи> или СТИКЕР <номер>."
           if stickers else
           "Что Еве делать? Ответь коротко: ДА, НЕТ или РЕАКЦИЯ <эмодзи>.")
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_text}]

    answer: Optional[str] = None
    base, api_key = _endpoint(provider, base_url)
    if base and api_key:
        answer = _call(base, api_key, model, messages, timeout=timeout, reasoning_effort=effort)
    if answer is None:
        fb_provider, fb_model, fb_base = resolve_fallback()
        if fb_model:
            fb_url, fb_key = _endpoint(fb_provider, fb_base)
            if fb_url and fb_key:
                log.warning("eva_gate: %s не ответил, пробую запасную модель %s", model, fb_model)
                answer = _call(fb_url, fb_key, fb_model, messages, timeout=timeout,
                               reasoning_effort=effort)
    if answer is None:
        _STATE["failures"] += 1
        if _STATE["failures"] >= _FAILURE_LIMIT and now >= _STATE["cooldown_until"]:
            _STATE["cooldown_until"] = now + _COOLDOWN_SECONDS
            log.warning("eva_gate: провайдер не отвечает %d раза подряд — фильтр на паузе %d мин "
                        "(в чате будет тихо, пока провайдер не вернётся)",
                        _STATE["failures"], _COOLDOWN_SECONDS // 60)
        return None
    _STATE["failures"] = 0
    return answer


def classify(lines: list[str], incoming: str, *, timeout: float = 10.0,
             reasoning_effort: Optional[str] = None, stickers: str = "") -> Optional[tuple[str, str]]:
    """``("reply"|"react"|"sticker"|"silent", эмодзи|номер)``; ``None`` — решить не удалось.

    Реакция — это её «ответ без слов»: откликнуться смайликом на мем, шутку, милую картинку или
    чужой успех. Спрашивать её саму об этом дорого (полный ход с промтом), а фильтр уже вызван,
    поэтому решение о реакции принимает он — и в чат ничего не пишется, только смайлик.
    """
    answer = _ask(lines, incoming, timeout=timeout, reasoning_effort=reasoning_effort, stickers=stickers)
    if answer is None:
        return None
    return _parse_classify(answer)


def should_reply(lines: list[str], incoming: str, *, timeout: float = 10.0,
                 reasoning_effort: Optional[str] = None) -> Optional[bool]:
    """True — она ответит словами; False — слов не будет (реакция или тишина); None — не решить."""
    parsed = classify(lines, incoming, timeout=timeout, reasoning_effort=reasoning_effort)
    if parsed is None:
        return None
    return parsed[0] == "reply"
