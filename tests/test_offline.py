"""Offline checks — no network, no real account: Telegram and the AI providers are faked.
تست آفلاین — بدون شبکه و بدون اکانت واقعی: تلگرام و ارائه‌دهنده‌های هوش مصنوعی شبیه‌سازی می‌شوند.

    python tests/test_offline.py
"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import assistant_bot as ab  # noqa: E402

tmp = tempfile.mkdtemp()
fails = []


def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  → {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ───────── config / .env ─────────
print("config")
ab.ENV_FILE = os.path.join(tmp, ".env")
for k in ab.REQUIRED:
    os.environ.pop(k, None)
check("all three required values missing on a clean install", ab.missing_config() == list(ab.REQUIRED))
ab.save_env({"TG_API_ID": "1234567", "TG_API_HASH": "0123456789abcdef0123456789abcdef"})
ab.save_env({"PANEL_BOT_TOKEN": "123456789:" + "A" * 35, "TG_API_ID": "7654321"})
body = open(ab.ENV_FILE).read()
check(".env keeps one line per key after an update", body.count("TG_API_ID=") == 1 and "7654321" in body, body)
check(".env is chmod 600", oct(os.stat(ab.ENV_FILE).st_mode & 0o777) == "0o600")
ab.load_env()
check("config complete after load_env", ab.missing_config() == [])
ab.load_config()
check("load_config parsed values", ab.API_ID == 7654321 and len(ab.API_HASH) == 32 and ab.BOT_TOKEN.startswith("123456789:"))
os.environ["TG_API_HASH"] = "not-a-hash"
check("bad hash is reported missing", ab.missing_config() == ["TG_API_HASH"])
os.environ["TG_API_HASH"] = "0123456789abcdef0123456789abcdef"

# ───────── state ─────────
ab.db = ab.Store(os.path.join(tmp, "t.db"))
ab.S = ab.Settings(ab.db)
ab.OWNER_ID, ab.OWNER_NAME, ab.ADMINS = 1, "Sam", {1}
S = ab.S

print("language + dates")
check("default language is fa before any choice", ab.lang() == "fa")
S.set("lang", "en")
check("L() follows the panel language", ab.L("الف", "A") == "A")
check("en default timezone is UTC", ab.tz_name() == "UTC")
check("en date is Gregorian", ab.fmt_date(date(2026, 10, 6), year=True) == "Tuesday 6 October 2026")
check("en parses ISO date", ab.parse_date("2026-10-17") == date(2026, 10, 17))
check("en rejects ambiguous short date", ab.parse_date("7/25") is None)
S.set("lang", "fa")
check("fa default timezone is Tehran", ab.tz_name() == "Asia/Tehran")
check("fa date is Jalali", ab.fmt_date(date(2026, 10, 6), year=True) == "سه‌شنبه 14 مهر 1405", ab.fmt_date(date(2026, 10, 6), year=True))
check("fa parses Jalali date", ab.parse_date("1405/07/25") == date(2026, 10, 17), str(ab.parse_date("1405/07/25")))
check("fa parses «25 مهر»", ab.parse_date("۲۵ مهر 1405") == date(2026, 10, 17))
check("j2g∘g2j round trip", all(ab.j2g(*ab.g2j(2026, m, 15)) == (2026, m, 15) for m in range(1, 13)))

print("readiness + keys")
check("not ready without key/model", not ab.ai_ready())
S.set("keys", {"openrouter": "sk-test-0123456789abcdef"})
check("key alone is not enough", not ab.ai_ready())
cfg = S.get("providers")
cfg["openrouter"]["models"].append({"id": "vendor/model-a", "on": True})
S.set("providers", cfg)
check("ready with key + model", ab.ai_ready())
check("defaults were not mutated by the edit", ab.DEFAULT_PROVIDERS["openrouter"]["models"] == [])
os.environ["GAPGPT_KEY"] = "env-key-0123456789"
check("env key is the fallback", ab.api_key("gapgpt") == "env-key-0123456789")
check("panel key wins over env", ab.api_key("openrouter").startswith("sk-test"))
check("mask hides the middle", ab.mask("sk-test-0123456789abcdef") == "sk-tes…cdef")

# ───────── prompts ─────────
print("prompts")


def row(i, role, text, ts=None):
    return {"id": i, "role": role, "text": text, "ts": ts or ab.now() - 100 + i}


def mk_user():
    return {"id": 50, "first_name": "Ali", "last_name": "", "username": "ali", "summary": "wants a shop bot",
            "intent": "price", "category": "pricing"}


for lg in ("fa", "en"):
    S.set("lang", lg)
    S.set("business_text", "")
    old = [row(1, "user", "سلام"), row(2, "assistant", "سلام، من دستیار هستم"), row(3, "owner", "قیمت حدود ۵ تومنه")]
    new = [row(4, "user", "چقدر طول میکشه؟")]
    ab.db.run("DELETE FROM messages")
    ab.db.run("INSERT INTO messages(user_id, role, text, ts) VALUES(50,'owner','قیمت حدود ۵ تومنه',?)", (ab.now(),))
    S.set("workload_on", True)
    S.set("workload_text", "busy with two projects")
    S.set("workload_set_at", ab.now())
    S.set("workload_until", date.fromtimestamp(ab.now() + 5 * 86400).isoformat())
    msgs = ab.build_messages(mk_user(), old, new)
    sysm, usr = msgs[0]["content"], msgs[1]["content"]
    check(f"[{lg}] no unreplaced {{owner}} placeholder", "{owner}" not in sysm + usr)
    check(f"[{lg}] owner name injected", "Sam" in sysm and "Sam" in usr)
    check(f"[{lg}] JSON format block survived", '"reply"' in sysm and '"needs_owner"' in sysm)
    check(f"[{lg}] empty business → model told to defer", ("Nothing written yet" if lg == "en" else "هنوز چیزی نوشته نشده") in sysm)
    check(f"[{lg}] workload + owner memory + history present",
          all(x in usr for x in (("workload", "own messages", "Conversation history") if lg == "en"
                                 else ("وضعیت کاری", "حرف‌های خود", "تاریخچه گفتگو"))))
    S.set("business_text", "Shop bots from 3 to 8 million.")
    sysm = ab.build_messages(mk_user(), old, new)[0]["content"]
    check(f"[{lg}] business text reaches the model", "Shop bots from 3 to 8 million." in sysm)
    print(f"       system prompt {len(sysm)} chars, user prompt {len(usr)} chars")
S.set("system_prompt", "My own prompt for {owner}. " * 5)
check("custom prompt replaces the default and keeps placeholders working",
      ab.build_messages(mk_user(), [], [row(1, "user", "hi")])[0]["content"].startswith("My own prompt for Sam."))
S.set("system_prompt", "")
S.set("owner_memory", False)
ab.add_owner_msg(50, "secret price")
last = ab.db.one("SELECT text FROM messages ORDER BY id DESC LIMIT 1")["text"]
check("owner text not stored when memory is off", last == ab.OWNER_HIDDEN and "secret" not in ab.shown(last))
S.set("owner_memory", True)
ab.db.run("INSERT INTO messages(user_id, role, text, ts) VALUES(50,'owner','(پیام دستی فلانی؛ متن ذخیره نشده)',1)")
st2 = ab.Store(os.path.join(tmp, "t.db"))
check("legacy hidden marker migrated on start",
      st2.one("SELECT COUNT(*) c FROM messages WHERE text LIKE '(پیام دستی%'")["c"] == 0)
check("reaction needs ≥80% confidence", ab.pick_reaction({"reaction": "🙏", "reaction_confidence": 85}) == "🙏"
      and ab.pick_reaction({"reaction": "🙏", "reaction_confidence": 60}) == "")
check("parse_ai handles fenced JSON", ab.parse_ai('```json\n{"reply": "hi"}\n```') == {"reply": "hi"})
check("strip_regreeting drops a repeated hello", ab.strip_regreeting("Hello again! The price is around 5.") == "The price is around 5.")
check("strip_regreeting drops «سلام»", ab.strip_regreeting("سلام علی جان، قیمت حدوداً ۵ تومنه") == "قیمت حدوداً ۵ تومنه")


# ───────── panel ─────────
class FakePanel(ab.Panel):
    def __init__(self):
        super().__init__("123456789:" + "A" * 35)
        self.calls = []

    async def api(self, method, **p):
        self.calls.append((method, p))
        return {"message_id": 1, "username": "x_bot"}

    def last_text(self):
        return [p.get("text", "") for m, p in self.calls if m in ("sendMessage", "editMessageText")][-1]


async def fake_call(prov, model, messages, timeout, max_tokens=900, check=None):
    if model == "bad/model":
        return None, "HTTP 404: model not found"
    return ab.Result('{"reply": "OK"}', prov, model, 0.4), ""


async def fake_verify(prov):
    return True, ""


ab._call = fake_call
ab.verify_key = fake_verify


def validate(text, kb, where):
    ok = isinstance(text, str) and 0 < len(text) <= 4096
    for r in kb or []:
        for b in r:
            if len(b["callback_data"].encode()) > 64 or not b["text"]:
                ok = False
    # HTML tags must be balanced for Telegram's parser
    for tag in ("b", "i", "code", "pre"):
        if text.count(f"<{tag}>") != text.count(f"</{tag}>"):
            ok = False
    if not ok:
        fails.append(where)
        print("  FAIL screen", where)
    return ok


async def crawl(lg):
    """Press every button reachable from the home screen, in one language."""
    S.set("lang", lg)
    pn = FakePanel()
    ab.panel = pn
    ab.db.run("INSERT OR REPLACE INTO users(id, first_name, last_name, username, first_seen, last_seen, needs_owner, category)"
              " VALUES(50,'Ali','','ali',?,?,1,'pricing')", (ab.now(), ab.now()))
    ab.db.run("INSERT INTO calls(ts, provider, model, ok, latency, err) VALUES(?,?,?,?,?,?)", (ab.now(), "openrouter", "vendor/model-a", 1, 0.5, ""))
    seen, queue, n = set(), ["home"], 0
    skip = ("clr2", "delkey2", "rst2", "mod:del:", "lng:")  # destructive ones are tested separately
    while queue:
        d = queue.pop()
        if d in seen or d == "noop":
            continue
        seen.add(d)
        if d == "hlt":
            out = await pn.scr_health()
        else:
            out = await pn.route(1, d)
        if out is None:
            fails.append(f"route {d} returned None")
            print("  FAIL route returned None:", d)
            continue
        text, kb = out[0], out[1]
        validate(text, kb, f"[{lg}] {d}")
        n += 1
        for r in kb or []:
            for b in r:
                cd = b["callback_data"]
                if not any(s in cd for s in skip):
                    queue.append(cd)
    return n, seen


async def panel_tests():
    print("panel crawl")
    for lg in ("fa", "en"):
        n, seen = await crawl(lg)
        check(f"[{lg}] crawled {n} screens without errors", n > 40, str(n))
    need = {"mod:key:gapgpt", "mod:key:openrouter", "mod:add:openrouter", "biz:edit", "set:own", "set:tz", "lng", "prm:edit", "wl:edit"}
    check("all new screens are reachable from home", need <= seen, str(need - seen))

    print("panel flows")
    S.set("lang", "")
    pn = FakePanel()
    ab.panel = pn

    def msg(text, **extra):
        return {"chat": {"type": "private"}, "from": {"id": 1}, "message_id": 77, "text": text, **extra}

    await pn.on_message(msg("/start"))
    check("first /start shows the language picker in both languages", "Choose the panel language" in pn.last_text() and "زبان پنل" in pn.last_text())
    await pn.on_callback({"id": "c", "from": {"id": 1}, "data": "lng:en", "message": {"chat": {"id": 1}, "message_id": 5}})
    check("picking English switches the panel", S.get("lang") == "en" and "assistant panel" in pn.last_text())
    await pn.on_message({"chat": {"type": "private"}, "from": {"id": 999}, "message_id": 1, "text": "/start"})
    check("strangers are refused", "⛔" in pn.last_text())

    # API key from the panel
    S.set("keys", {})
    await pn.route(1, "mod:key:gapgpt")
    pn.calls.clear()
    await pn.on_message(msg("gk-SECRETSECRETSECRET-1234"))
    methods = [m for m, _ in pn.calls]
    check("key message is deleted from the chat", methods[0] == "deleteMessage" and pn.calls[0][1]["message_id"] == 77)
    check("key stored", S.get("keys").get("gapgpt") == "gk-SECRETSECRETSECRET-1234")
    check("reply shows only a masked key", "SECRETSECRET" not in pn.last_text() and "gk-SEC…1234" in pn.last_text(), pn.last_text())
    await pn.route(1, "mod:key:gapgpt")
    await pn.on_message(msg("two words"))
    check("invalid key rejected and old key kept", S.get("keys")["gapgpt"].startswith("gk-") and 1 in pn.state)
    pn.state.clear()

    # models
    out = await pn.route(1, "mod:add:gapgpt")
    check("add-model prompt opens when a key exists", pn.state.get(1, {}).get("type") == "addmodel")
    await pn.on_message(msg("model-x"))
    check("model added + tested", [m["id"] for m in S.get("providers")["gapgpt"]["models"]] == ["model-x"] and "✅" in pn.last_text())
    await pn.route(1, "mod:add:gapgpt")
    await pn.on_message(msg("bad/model"))
    check("failing model reports the provider error", "404" in pn.last_text())
    await pn.route(1, "mod:del:gapgpt:1")
    check("model deleted", len(S.get("providers")["gapgpt"]["models"]) == 1)
    os.environ.pop("GAPGPT_KEY", None)
    await pn.route(1, "mod:delkey2:gapgpt")
    out = await pn.route(1, "mod:add:gapgpt")
    check("add-model blocked without a key", 1 not in pn.state and "key first" in out[2], str(out[2]))

    # business / owner / timezone / fallback
    await pn.route(1, "biz:edit")
    await pn.on_message(msg("I build shop bots. Prices 3–8M. Delivery 3–5 days."))
    check("business text saved", "shop bots" in S.get("business_text"))
    await pn.route(1, "set:own")
    await pn.on_message(msg("Samuel"))
    check("owner name override", ab.owner() == "Samuel")
    await pn.route(1, "set:own")
    await pn.on_message(msg("-"))
    check("owner name reset to the account name", ab.owner() == "Sam")
    await pn.route(1, "set:tz")
    await pn.on_message(msg("Mars/Olympus"))
    check("unknown timezone rejected", S.get("timezone") == "" and 1 in pn.state)
    await pn.on_message(msg("Europe/Berlin"))
    check("timezone saved", ab.tz_name() == "Europe/Berlin" and 1 not in pn.state)
    check("default fallback text is localized and names the owner", "Sam" in ab.fallback_text() and "Auto-reply" in ab.fallback_text())
    await pn.route(1, "set:fb")
    await pn.on_message(msg("Back soon."))
    check("custom fallback text", ab.fallback_text() == "Back soon.")
    out = await pn.route(1, "set:t:ai_enabled")
    check("toggle endpoint ignores keys outside the whitelist", S.get("ai_enabled") is True)
    await pn.route(1, "wl:date")
    await pn.on_message(msg("2030-01-05"))
    check("workload end date saved (en)", S.get("workload_until") == "2030-01-05")
    await pn.route(1, "prm:edit")
    await pn.on_message(msg("x" * 60))
    await pn.route(1, "prm:rst2")
    check("prompt reset returns to the language default", ab.base_prompt().startswith("You are"))


# ───────── answering pipeline ─────────
class FakeAction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeClient:
    def __init__(self):
        self.sent, self.n = [], 100

    async def send_message(self, uid, text):
        self.n += 1
        self.sent.append((uid, text))
        return type("M", (), {"id": self.n})()

    async def send_read_acknowledge(self, uid):
        pass

    def action(self, uid, kind):
        return FakeAction()

    async def __call__(self, req):
        self.sent.append(("reaction", req))


async def pipeline_tests():
    print("answering pipeline")
    S.set("lang", "en")
    S.set("timezone", "")
    S.set("debounce", 2)
    ab.client = FakeClient()
    pn = FakePanel()
    ab.panel = pn
    ab.db.run("DELETE FROM messages")
    ab.db.run("DELETE FROM users")
    ab.db.run("INSERT INTO users(id, first_name, last_name, username, first_seen, last_seen) VALUES(60,'Mina','','',?,?)", (ab.now(), ab.now()))
    u = ab.get_user(60)

    S.set("keys", {})
    os.environ.pop("OPENROUTER_KEY", None)
    check("no key → assistant stays silent (not_ready)", ab.can_answer(u) == (False, "not_ready"))
    S.set("keys", {"openrouter": "sk-test-0123456789abcdef"})
    check("key + model → may answer", ab.can_answer(u) == (True, ""))

    seen_prompt = {}

    async def call_json(prov, model, messages, timeout, max_tokens=900, check=None):
        seen_prompt["sys"] = messages[0]["content"]
        body = json.dumps({"intent": "wants a price", "category": "pricing", "needs_owner": True, "summary": "asks price",
                           "reaction": "👍", "reaction_confidence": 90, "reply": "Hello! Roughly 3–8M; Sam confirms the final price."})
        return (ab.Result(body, prov, model, 0.3), "") if (not check or check(body)) else (None, "bad format")

    ab._call = call_json
    rid = ab.add_msg(60, "user", "how much for a shop bot?")
    ab.in_tg_ids[60][rid] = 555
    await ab.respond(60)
    texts = [t for uid, t in ab.client.sent if uid == 60]
    check("reply sent from the account", texts == ["Hello! Roughly 3–8M; Sam confirms the final price."], str(texts))
    check("reaction sent", any(x[0] == "reaction" for x in ab.client.sent))
    u = ab.get_user(60)
    check("intent/category/needs_owner stored", (u["intent"], u["category"], u["needs_owner"]) == ("wants a price", "pricing", 1))
    check("owner got a 'waiting for you' notice", any("waiting for you" in p.get("text", "") for m, p in pn.calls))
    check("business text was in the prompt", "shop bots" in seen_prompt["sys"])
    check("sent message is recognised as the bot's own", await ab.is_own_message(60, 101))

    async def call_fail(prov, model, messages, timeout, max_tokens=900, check=None):
        return None, "HTTP 500: boom"

    ab._call = call_fail
    ab.add_msg(60, "user", "and delivery time?")
    ab.client.sent.clear()
    S.set("fallback_text", "")
    await ab.respond(60)
    check("all models failing → localized fallback text goes out once", [t for uid, t in ab.client.sent] == [ab.fallback_text()])

    S.set("takeover_min", 120)  # the crawl above cycled this setting
    ab.add_owner_msg(60, "I'll call you tonight")
    check("owner's manual reply silences the assistant (takeover)", ab.can_answer(ab.get_user(60)) == (False, "takeover"))


asyncio.run(panel_tests())
asyncio.run(pipeline_tests())
print("\nFAILED: " + ", ".join(fails) if fails else "\nALL PASSED")
sys.exit(1 if fails else 0)
