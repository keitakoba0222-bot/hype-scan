#!/usr/bin/env python3
import json, subprocess, sys, os, tempfile, glob, time
from pathlib import Path
from collections import defaultdict

def ensure_deps():
    pkgs = [("flask", "flask"), ("flask-cors", "flask_cors")]
    for pip_name, import_name in pkgs:
        try:
            __import__(import_name)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name, "-q"])

ensure_deps()

from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
print(f"BASE_DIR: {BASE_DIR}")
print(f"index.html exists: {os.path.exists(os.path.join(BASE_DIR, 'index.html'))}")

app = Flask(__name__, static_folder=BASE_DIR)
CORS(app)

# ============================================================
# RATE LIMIT (IPごとに1日5回まで)
# ============================================================
RATE_LIMIT  = int(os.environ.get("RATE_LIMIT", 3))
RATE_WINDOW = int(os.environ.get("RATE_WINDOW", 86400))  # 24h

_rate_store = defaultdict(list)

def get_client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"

def check_rate_limit(ip):
    now = time.time()
    window_start = now - RATE_WINDOW
    _rate_store[ip] = [t for t in _rate_store[ip] if t > window_start]
    used = len(_rate_store[ip])
    if used >= RATE_LIMIT:
        return False, used, RATE_LIMIT
    _rate_store[ip].append(now)
    return True, used + 1, RATE_LIMIT

# ============================================================
# yt-dlp
# ============================================================
def yt_dlp_cmd():
    for cmd in ["yt-dlp"]:
        try:
            r = subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return [cmd]
        except FileNotFoundError:
            pass
    return [sys.executable, "-m", "yt_dlp"]

YT_DLP = yt_dlp_cmd()
print(f"yt-dlp: {' '.join(YT_DLP)}")

# ============================================================
# ROUTES
# ============================================================
@app.route("/")
@app.route("/app")
def index():
    html_file = os.path.join(BASE_DIR, "index.html")
    if not os.path.exists(html_file):
        return f"<h2>Not found: {html_file}</h2>", 404
    with open(html_file, encoding="utf-8") as f:
        html = f.read()
    resp = Response(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/rate_status")
def rate_status():
    ip = get_client_ip()
    now = time.time()
    window_start = now - RATE_WINDOW
    _rate_store[ip] = [t for t in _rate_store[ip] if t > window_start]
    used = len(_rate_store[ip])
    remaining = max(0, RATE_LIMIT - used)
    reset_at = int((_rate_store[ip][0] + RATE_WINDOW) if _rate_store[ip] else now)
    return jsonify({"used": used, "limit": RATE_LIMIT, "remaining": remaining, "reset_at": reset_at})

@app.route("/api/chat/stream")
def chat_stream():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "url required"}), 400

    ip = get_client_ip()
    allowed, used, limit = check_rate_limit(ip)
    if not allowed:
        def deny():
            yield f"event: fail\ndata: {json.dumps({'error': f'1日の利用上限（{limit}回）に達しました。24時間後にリセットされます。', 'rate_limited': True}, ensure_ascii=False)}\n\n"
        return Response(stream_with_context(deny()), status=200,
                        mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                 "Access-Control-Allow-Origin": "*"})

    def generate():
        def send(evt, data):
            return f"event: {evt}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield send("rate_info", {"used": used, "limit": limit, "remaining": limit - used})
        yield send("progress", {"msg": "yt-dlp 起動中...", "pct": 5})

        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = YT_DLP + [
                "--skip-download",
                "--write-subs", "--sub-langs", "live_chat",
                "--write-info-json",
                "--no-playlist", "--newline",
                "-o", os.path.join(tmpdir, "%(id)s.%(ext)s"),
                url,
            ]
            print(f"Running: {' '.join(cmd)}")
            yield send("progress", {"msg": "YouTube から情報取得中...", "pct": 10})

            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", cwd=tmpdir,
            )

            lines_seen = []
            pct = 10
            for line in proc.stdout:
                line = line.rstrip()
                if not line: continue
                lines_seen.append(line)
                print(line)
                if "[download]" in line:
                    pct = min(pct + 1, 70)
                    yield send("progress", {"msg": line[:80], "pct": pct})
                elif "live_chat" in line.lower():
                    yield send("progress", {"msg": "チャット取得中...", "pct": 60})

            proc.wait()
            if proc.returncode != 0:
                log = "\n".join(lines_seen[-10:])
                yield send("fail", {"error": parse_error(log, proc.returncode)})
                return

            yield send("progress", {"msg": "ファイル解析中...", "pct": 75})

            info_files = glob.glob(os.path.join(tmpdir, "*.info.json"))
            video_id, title, duration = "unknown", "不明", 3600
            if info_files:
                info = json.loads(Path(info_files[0]).read_text(encoding="utf-8"))
                video_id = info.get("id", "unknown")
                title    = info.get("title", "不明")
                duration = info.get("duration") or 3600

            all_files = os.listdir(tmpdir)
            chat_files = [os.path.join(tmpdir, f) for f in all_files
                         if "live_chat" in f and not f.endswith(".info.json")]

            if not chat_files:
                yield send("fail", {"error": "ライブチャットが見つかりません。\nライブアーカイブ動画か確認してください。"})
                return

            yield send("progress", {"msg": "コメント解析中...", "pct": 85})
            comments = []
            for cf in chat_files:
                comments.extend(parse_chat_file(cf))
            comments.sort(key=lambda x: x["offsetMs"])
            print(f"Comments: {len(comments)}")

            yield send("progress", {"msg": f"{len(comments):,}件 取得完了", "pct": 100})
            yield send("done", {
                "video_id": video_id, "title": title,
                "duration": duration, "comments": comments, "count": len(comments),
            })

    def safe_generate():
        try:
            yield from generate()
        except Exception as e:
            import traceback; traceback.print_exc()
            yield f"event: fail\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(safe_generate()), status=200,
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                             "Access-Control-Allow-Origin": "*"})

def parse_chat_file(filepath):
    comments = []
    try:
        content = Path(filepath).read_text(encoding="utf-8").strip()
        if content.startswith("["):
            try:
                for ev in json.loads(content):
                    c = extract_comment(ev)
                    if c: comments.append(c)
                return comments
            except: pass
        for line in content.splitlines():
            line = line.strip().rstrip(",")
            if not line or line in ("[", "]"): continue
            try:
                c = extract_comment(json.loads(line))
                if c: comments.append(c)
            except: pass
    except Exception as e:
        print(f"parse error: {e}")
    return comments

def extract_comment(ev):
    replay = ev.get("replayChatItemAction")
    if replay:
        offset_ms = int(replay.get("videoOffsetTimeMsec", 0))
        for action in replay.get("actions", []):
            item = action.get("addChatItemAction", {}).get("item", {})
            r = extract_from_item(item, offset_ms)
            if r: return r
        return None
    return extract_from_item(ev.get("item", ev), int(ev.get("videoOffsetTimeMsec", 0)))

def extract_from_item(item, offset_ms):
    renderer = (item.get("liveChatTextMessageRenderer")
                or item.get("liveChatPaidMessageRenderer")
                or item.get("liveChatMembershipItemRenderer"))
    if not renderer: return None
    msg_obj = renderer.get("message") or renderer.get("headerSubtext") or renderer.get("primaryText")
    if not msg_obj: return None
    parts = []
    for r in msg_obj.get("runs", []):
        if "text" in r: parts.append(r["text"])
        elif "emoji" in r:
            em = r["emoji"]
            parts.append(em["shortcuts"][0] if em.get("shortcuts") else
                         f":{em['emojiId']}:" if em.get("emojiId") else "🔥")
    message = "".join(parts).strip()
    if not message: return None
    is_paid = "liveChatPaidMessageRenderer" in item
    return {"offsetMs": offset_ms, "message": message,
            "author": renderer.get("authorName", {}).get("simpleText", "匿名"),
            "isPaid": is_paid,
            "amount": renderer.get("purchaseAmountText", {}).get("simpleText", "") if is_paid else ""}

def parse_error(log, code):
    s = log.lower()
    if "sign in" in s or "login" in s: return "ログインが必要な動画です"
    if "private" in s: return "非公開動画です"
    if "unable to extract" in s: return "情報取得失敗。pip install -U yt-dlp で更新してください"
    return f"yt-dlpエラー(code {code}):\n{log[-200:]}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 55)
    print("🔥 HYPE SCAN")
    print(f"   http://localhost:{port}/app")
    print(f"   Rate limit: {RATE_LIMIT}回/日")
    print("=" * 55)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
