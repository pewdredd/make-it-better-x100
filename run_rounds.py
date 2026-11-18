#!/usr/bin/env python3
"""100 раз подряд просит Claude «сделай лучше» один и тот же сайт.

Как у Nate Herk: каждый круг - новая чистая сессия (--safe-mode: без CLAUDE.md, скиллов,
плагинов, хуков, MCP и памяти), один и тот же промпт из PROMPT.md, effort medium.
После круга: git-коммит в рабочей папке, копия сайта в snapshots/{model}/rNNN/, строка
статистики в stats/{model}.jsonl. Прерванный прогон продолжается с последнего круга.

    python3 run_rounds.py sonnet          # 100 кругов Sonnet
    python3 run_rounds.py opus --rounds 100
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
START = HERE / "start-site"
PROMPT = (HERE / "PROMPT.md").read_text(encoding="utf-8").strip()
CODE_EXT = {".html", ".css", ".js", ".mjs", ".ts", ".json", ".svg"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".svg"}
VID_EXT = {".mp4", ".webm", ".mov"}
SKIP_DIRS = {".git", "node_modules", ".claude"}
ERROR_WAIT = 2 * 60  # обычная ошибка - пробуем снова через 2 минуты
LIMIT_POLL = 2 * 60  # время сброса лимита не нашли - проверяем каждые 2 минуты
ROUND_TIMEOUT = 60 * 60


def log(model: str, msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {model}: {msg}", flush=True)


def site_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS):
            yield p


def measure(root: Path) -> dict:
    """Что сейчас лежит на сайте: строки кода, картинки, видео и признаки для вех."""
    lines = imgs = vids = 0
    text = ""
    for p in site_files(root):
        ext = p.suffix.lower()
        if ext in IMG_EXT:
            imgs += 1
        if ext in VID_EXT:
            vids += 1
        if ext in CODE_EXT and ext != ".json":
            try:
                t = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lines += t.count("\n") + 1
            text += t.lower() + "\n"
    has_js = bool(re.search(r"<script", text)) or any(p.suffix in {".js", ".mjs"} for p in site_files(root))
    return {
        "lines": lines,
        "images": imgs,
        "videos": vids,
        "f_js": has_js,
        "f_mobile": "@media" in text,
        "f_anim": bool(re.search(r"@keyframes|animation\s*:|\.animate\(", text)),
        "f_img": imgs > 0 or "<img" in text or "<svg" in text,
        "f_form": "<form" in text or "<input" in text,
        "f_canvas": bool(re.search(r"<canvas|webgl|getcontext\(", text)),
        "f_video": vids > 0 or "<video" in text,
    }


def init_work(work: Path) -> None:
    if (work / ".git").exists():
        return
    shutil.copytree(START, work, dirs_exist_ok=True)
    git(work, "init", "-q")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "круг 0: стартовый уродливый сайт")


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "round", "GIT_AUTHOR_EMAIL": "round@local",
           "GIT_COMMITTER_NAME": "round", "GIT_COMMITTER_EMAIL": "round@local"}
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)
    return r.stdout


def snapshot(work: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(work, dest, ignore=shutil.ignore_patterns(*SKIP_DIRS))


def load_env() -> dict:
    """.env с OPENROUTER_API_KEY - только для прогона с --images."""
    env = {}
    f = HERE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"')
    return env


IMAGES_NOTE = ("\n\nВ переменной окружения OPENROUTER_API_KEY лежит ключ OpenRouter "
               "(https://openrouter.ai/api/v1) - через него можно генерировать картинки и видео.")


def run_claude(model: str, n: int, work: Path, log_file: Path, effort: str, images: bool) -> dict:
    name = f"Кофейня · {model.capitalize()} · круг {n:03d}"
    # Песочница: Bash сам разрешён, но пишет только в папку сайта (bubblewrap).
    # Правки файлов - acceptEdits. Веб-поиск разрешён, как у Nate («любые инструменты»).
    sandbox = {"enabled": True, "autoAllowBashIfSandboxed": True, "allowUnsandboxedCommands": False}
    env = dict(os.environ)
    prompt = PROMPT
    if images:
        extra = load_env()
        if not extra.get("OPENROUTER_API_KEY"):
            sys.exit("Нет OPENROUTER_API_KEY в .env")
        env.update(extra)
        prompt += IMAGES_NOTE
        sandbox["network"] = {"allowedDomains": ["openrouter.ai", "*.openrouter.ai"]}
    settings = json.dumps({"sandbox": sandbox, "permissions": {"allow": ["WebSearch", "WebFetch"]}})
    cmd = ["claude", "-p", prompt, "--safe-mode", "--model", model, "--effort", effort,
           "--permission-mode", "acceptEdits", "--settings", settings,
           "--output-format", "stream-json", "--verbose", "-n", name]
    tools: dict[str, int] = {}
    result: dict = {}
    with log_file.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8")
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                fh.write(line)
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "assistant":
                    for block in ev.get("message", {}).get("content", []):
                        if block.get("type") == "tool_use":
                            tools[block["name"]] = tools.get(block["name"], 0) + 1
                elif ev.get("type") == "result":
                    result = ev
            proc.wait(timeout=ROUND_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
    return {"result": result, "tools": tools, "exit": proc.returncode}


def looks_like_limit(res: dict) -> bool:
    text = json.dumps(res.get("result", {}), ensure_ascii=False).lower()
    return any(k in text for k in ("usage limit", "rate limit", "limit reached", "resets", "overloaded"))


def limit_wait(res: dict) -> int:
    """Сколько секунд ждать до сброса лимита. Claude пишет: «limit resets 8:50pm (UTC)»."""
    text = str(res.get("result", {}).get("result", ""))
    m = re.search(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*\(UTC\)", text, re.I)
    if not m:
        return LIMIT_POLL
    h, mi = int(m.group(1)) % 12, int(m.group(2) or 0)
    if m.group(3).lower() == "pm":
        h += 12
    now = time.gmtime()
    wait = (h * 3600 + mi * 60) - (now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec)
    if wait < 0:
        wait += 24 * 3600
    if wait > 6 * 3600:  # сброс уже прошёл, а ответ ещё старый - проверяем почаще
        return LIMIT_POLL
    return wait + 30


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", help="sonnet или opus (алиас claude --model)")
    ap.add_argument("--rounds", type=int, default=100)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--images", action="store_true", help="дать Claude ключ OpenRouter из .env")
    a = ap.parse_args()

    work = HERE / "work" / a.model
    snaps = HERE / "snapshots" / a.model
    logs = HERE / "logs" / a.model
    stats = HERE / "stats" / f"{a.model}.jsonl"
    for d in (work, snaps, logs, stats.parent):
        d.mkdir(parents=True, exist_ok=True)

    init_work(work)
    git(work, "reset", "-q", "--hard")  # прошлый запуск мог оборваться посреди круга
    git(work, "clean", "-qfd")
    if not (snaps / "r000").exists():
        snapshot(work, snaps / "r000")
        with stats.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"round": 0, **measure(work)}, ensure_ascii=False) + "\n")

    done = {json.loads(l)["round"] for l in stats.read_text(encoding="utf-8").splitlines() if l.strip()}
    n = max(done) + 1
    while n <= a.rounds:
        log(a.model, f"круг {n}")
        t0 = time.time()
        res = run_claude(a.model, n, work, logs / f"r{n:03d}.jsonl", a.effort, a.images)
        r = res["result"]
        if not r or r.get("is_error"):
            limit = looks_like_limit(res)
            wait = limit_wait(res) if limit else ERROR_WAIT
            until = time.strftime("%H:%M", time.localtime(time.time() + wait))
            log(a.model, f"круг {n} не прошёл ({'лимит' if limit else 'ошибка'}), откатываю, повтор в {until}")
            git(work, "reset", "-q", "--hard")
            git(work, "clean", "-qfd")
            time.sleep(wait)
            continue

        git(work, "add", "-A")
        changed = bool(git(work, "status", "--porcelain").strip())
        git(work, "commit", "-q", "--allow-empty", "-m", f"круг {n}")
        snapshot(work, snaps / f"r{n:03d}")
        row = {
            "round": n,
            "session_id": r.get("session_id"),
            "cost_usd": r.get("total_cost_usd"),
            "duration_s": round(time.time() - t0),
            "turns": r.get("num_turns"),
            "tool_calls": sum(res["tools"].values()),
            "tools": res["tools"],
            "web_search": res["tools"].get("WebSearch", 0) + res["tools"].get("WebFetch", 0),
            "changed": changed,
            "summary": (r.get("result") or "")[:1500],
            **measure(work),
        }
        with stats.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        log(a.model, f"круг {n} готов: {row['lines']} строк, ${row['cost_usd'] or 0:.2f}, "
                     f"{row['tool_calls']} вызовов, {row['duration_s']} с")
        n += 1
    log(a.model, "все круги пройдены")


if __name__ == "__main__":
    sys.exit(main())
