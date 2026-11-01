import json
import os
import re
import requests

TOKEN = os.environ["BOT_TOKEN"]
API = f"https://api.telegram.org/bot{TOKEN}"
CFG_PATH = "config.json"
CFG = json.load(open(CFG_PATH, encoding="utf-8"))
CHANGED = False

BOOLS = ["keep_original_text", "remove_links", "remove_mentions",
         "remove_hashtags", "reply_confirm"]
STRS = ["tag", "header", "footer"]
SETTABLE = BOOLS + STRS + ["tag_position"]

CAPTION_TYPES = ("photo", "video", "audio", "document", "animation", "voice")
URL_RE = re.compile(r"(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+|tg://\S+)", re.I)
MENTION_RE = re.compile(r"(?<!\w)@\w{3,}")
HASHTAG_RE = re.compile(r"(?<!\w)#\w+")

HELP = """دستورها (فقط توی پیوی ربات):
/settings : نمایش تنظیمات
/set کلید مقدار : تغییر تنظیم (مثلا /set tag @mychannel)
/set remove_links off : خاموش/روشن کردن گزینه‌ها (on/off)
/set tag_position start|end : جای تگ
/addtarget مقصد : افزودن کانال/گروه (@username یا آیدی عددی)
/deltarget مقصد : حذف مقصد
/settarget مقصد کلید مقدار : تنظیم مخصوص یک مقصد (مقدار default = حذف)
/replace قدیمی|جدید : جایگزینی کلمه (جدید خالی = حذف)
/delreplace قدیمی : حذف جایگزینی
/adduser آیدی  و  /deluser آیدی : مدیریت کاربران مجاز
داخل گروه: /register  (افزودن همون گروه به مقصدها)
کلیدها: """ + ", ".join(SETTABLE)


def call(method, **params):
    r = requests.post(f"{API}/{method}", json=params, timeout=60)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", str(data)))
    return data["result"]


def mark():
    global CHANGED
    CHANGED = True


def save():
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(CFG, f, ensure_ascii=False, indent=2)
        f.write("\n")


def ident(x):
    x = str(x).strip()
    if re.fullmatch(r"-?\d+", x):
        return int(x)
    return x if x.startswith("@") else "@" + x


def parse_val(key, val):
    if key in BOOLS:
        v = val.strip().lower()
        if v in ("on", "1", "true", "yes", "روشن"):
            return True
        if v in ("off", "0", "false", "no", "خاموش"):
            return False
        raise ValueError("مقدار باید on یا off باشه")
    if key == "tag_position":
        v = val.strip().lower()
        if v not in ("start", "end"):
            raise ValueError("مقدار باید start یا end باشه")
        return v
    return val.strip()


# ---------- مقصدها ----------
def chat_of(t):
    return t["chat"] if isinstance(t, dict) else t


def targets():
    out = []
    for t in CFG.get("targets", []):
        ov = {k: v for k, v in t.items() if k in SETTABLE} if isinstance(t, dict) else {}
        out.append((chat_of(t), ov))
    return out


def add_target(chat, name=""):
    ts = CFG.setdefault("targets", [])
    if any(str(chat_of(t)).lower() == str(chat).lower() for t in ts):
        return False
    ts.append({"chat": chat, "name": name} if name else chat)
    mark()
    return True


def del_target(chat):
    ts = CFG.get("targets", [])
    new = [t for t in ts if str(chat_of(t)).lower() != str(chat).lower()]
    if len(new) == len(ts):
        return False
    CFG["targets"] = new
    mark()
    return True


def find_target(chat):
    ts = CFG.get("targets", [])
    for i, t in enumerate(ts):
        if str(chat_of(t)).lower() == str(chat).lower():
            if not isinstance(t, dict):
                t = {"chat": chat_of(t)}
                ts[i] = t
            return t
    return None


# ---------- ساخت کپشن ----------
def clean(text, c):
    for old, new in c.get("replacements", {}).items():
        text = text.replace(old, new)
    if c.get("remove_links"):
        text = URL_RE.sub("", text)
    if c.get("remove_mentions"):
        text = MENTION_RE.sub("", text)
    if c.get("remove_hashtags"):
        text = HASHTAG_RE.sub("", text)
    text = "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build(text, c):
    body = clean(text, c) if c.get("keep_original_text", True) else ""
    parts = []
    if c.get("header"):
        parts.append(c["header"])
    if body:
        parts.append(body)
    if c.get("footer"):
        parts.append(c["footer"])
    tag = c.get("tag", "")
    if tag:
        if c.get("tag_position", "end") == "start":
            parts.insert(0, tag)
        else:
            parts.append(tag)
    return "\n\n".join(parts)


def process(msg, chat, c):
    text = msg.get("text") or msg.get("caption") or ""
    out = build(text, c)
    if "text" in msg:
        if out:
            call("sendMessage", chat_id=chat, text=out[:4096],
                 link_preview_options={"is_disabled": True})
        return
    params = dict(chat_id=chat, from_chat_id=msg["chat"]["id"],
                  message_id=msg["message_id"])
    if any(k in msg for k in CAPTION_TYPES):
        params["caption"] = out[:1024]
    call("copyMessage", **params)


# ---------- دستورها ----------
def show():
    lines = [f"{k}: {CFG.get(k)!r}" for k in SETTABLE]
    ts = []
    for t in CFG.get("targets", []):
        if isinstance(t, dict):
            extra = {k: v for k, v in t.items() if k != "chat"}
            ts.append(f"{t['chat']} {extra}" if extra else str(t["chat"]))
        else:
            ts.append(str(t))
    lines.append("مقصدها:\n" + ("\n".join(ts) if ts else "—"))
    lines.append("جایگزینی‌ها: " + (json.dumps(CFG.get("replacements", {}), ensure_ascii=False) or "—"))
    lines.append("کاربران مجاز: " + ", ".join(map(str, CFG["allowed_users"])))
    return "\n".join(lines)


def handle_command(msg):
    text = msg["text"].strip()
    p = text.split(None, 1)
    cmd = p[0].split("@")[0].lower()
    arg = p[1].strip() if len(p) > 1 else ""
    ctype = msg["chat"]["type"]

    if cmd == "/register":
        if ctype in ("group", "supergroup"):
            added = add_target(msg["chat"]["id"], msg["chat"].get("title", ""))
            return "✅ این گروه به مقصدها اضافه شد" if added else "این گروه از قبل توی مقصدها هست"
        return "این دستور رو داخل گروه بفرست"
    if ctype != "private":
        return None

    if cmd in ("/start", "/help"):
        return HELP
    if cmd == "/settings":
        return show()

    if cmd == "/set":
        kv = arg.split(None, 1)
        if not kv or kv[0] not in SETTABLE:
            return "❌ کلید نامعتبر. کلیدها: " + ", ".join(SETTABLE)
        try:
            CFG[kv[0]] = parse_val(kv[0], kv[1] if len(kv) > 1 else "")
        except ValueError as e:
            return f"❌ {e}"
        mark()
        return f"✅ {kv[0]} تنظیم شد"

    if cmd == "/addtarget":
        if not arg:
            return "فرمت: /addtarget @channel"
        return "✅ اضافه شد" if add_target(ident(arg)) else "از قبل هست"

    if cmd == "/deltarget":
        return "✅ حذف شد" if del_target(ident(arg)) else "❌ پیدا نشد"

    if cmd == "/settarget":
        a = arg.split(None, 2)
        if len(a) < 2 or a[1] not in SETTABLE:
            return "فرمت: /settarget مقصد کلید مقدار"
        entry = find_target(ident(a[0]))
        if entry is None:
            return "❌ این مقصد پیدا نشد"
        val = a[2] if len(a) > 2 else ""
        if val.strip().lower() == "default":
            entry.pop(a[1], None)
        else:
            try:
                entry[a[1]] = parse_val(a[1], val)
            except ValueError as e:
                return f"❌ {e}"
        mark()
        return "✅ انجام شد"

    if cmd == "/replace":
        if "|" not in arg:
            return "فرمت: /replace قدیمی|جدید"
        old, new = arg.split("|", 1)
        old = old.strip()
        if not old:
            return "❌ کلمه قدیمی خالیه"
        CFG.setdefault("replacements", {})[old] = new.strip()
        mark()
        return "✅ ثبت شد"

    if cmd == "/delreplace":
        if CFG.get("replacements", {}).pop(arg, None) is None:
            return "❌ پیدا نشد"
        mark()
        return "✅ حذف شد"

    if cmd in ("/adduser", "/deluser"):
        if not re.fullmatch(r"\d+", arg):
            return "آیدی عددی بده"
        uid = int(arg)
        users = CFG["allowed_users"]
        if cmd == "/adduser" and uid not in users:
            users.append(uid)
        elif cmd == "/deluser" and uid in users:
            if len(users) == 1:
                return "❌ نمیشه آخرین کاربر رو حذف کرد"
            users.remove(uid)
        mark()
        return "✅ انجام شد"

    return "دستور ناشناخته. /help"


def main():
    updates = call("getUpdates", timeout=0, allowed_updates=["message"])
    if not updates:
        return
    for u in updates:
        msg = u.get("message")
        if not msg:
            continue
        uid = (msg.get("from") or {}).get("id")
        if uid not in CFG["allowed_users"]:
            continue
        chat_id = msg["chat"]["id"]
        text = msg.get("text") or ""

        try:
            if text.startswith("/"):
                reply = handle_command(msg)
                if reply:
                    call("sendMessage", chat_id=chat_id, text=reply[:4000])
                continue
            if msg["chat"]["type"] != "private":
                continue

            ts = targets()
            if not ts:
                call("sendMessage", chat_id=chat_id,
                     text="❌ هیچ مقصدی تنظیم نشده. /addtarget یا /register")
                continue
            ok, bad = 0, []
            for chat, ov in ts:
                c = dict(CFG)
                c.update(ov)
                try:
                    process(msg, chat, c)
                    ok += 1
                except Exception as e:
                    bad.append(f"{chat}: {e}"[:200])
            if CFG.get("reply_confirm", True) or bad:
                res = f"✅ ارسال شد ({ok})"
                if bad:
                    res += "\n❌ خطا:\n" + "\n".join(bad)
                call("sendMessage", chat_id=chat_id, text=res[:4000])
        except Exception as e:
            print("error:", e)

    if CHANGED:
        save()
    call("getUpdates", offset=updates[-1]["update_id"] + 1, timeout=0)


main()
