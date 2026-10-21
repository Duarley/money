import os, hmac, hashlib, json, sqlite3, urllib.parse
from flask import Flask, request, jsonify, render_template_string

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
app = Flask(__name__)
DB = os.environ.get("DB_PATH", "money.db")

def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

with con() as c:
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY, nome TEXT, saldo INTEGER DEFAULT 0,
        energia INTEGER DEFAULT 1000, tap INTEGER DEFAULT 1, nivel INTEGER DEFAULT 1)""")

def valida(init_data):
    if not init_data:
        return None
    p = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    recebido = p.pop("hash", None)
    if not recebido:
        return None
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(p.items()))
    segredo = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(
            hmac.new(segredo, dcs.encode(), hashlib.sha256).hexdigest(), recebido):
        return None
    try:
        return json.loads(p.get("user", "{}")) or None
    except Exception:
        return None

def usuario():
    init = (request.headers.get("Authorization", "").removeprefix("tma ").strip()
            or request.args.get("initData", ""))
    u = valida(init)
    if not u:
        return None
    with con() as c:
        c.execute("INSERT OR IGNORE INTO users(id, nome) VALUES(?,?)",
                  (u["id"], u.get("first_name", "")))
    return u["id"]

HTML = """<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://telegram.org/js/telegram-web-app.js"></script><title>Money</title>
<style>body{font-family:sans-serif;text-align:center;padding:35px 15px;
background:var(--tg-theme-bg-color,#101820);color:var(--tg-theme-text-color,#fff)}
button{padding:15px 30px;border:0;border-radius:12px;font-size:18px;margin:6px}</style>
</head><body><h1>Money</h1><p>Saldo: <b id="s">0</b></p>
<button onclick="tap()">Ganhar moedas</button>
<button onclick="boost()">Upgrade</button>
<script>
const tg = Telegram.WebApp; tg.ready(); tg.expand();
const H = {Authorization: "tma " + tg.initData, "Content-Type": "application/json"};
async function me(){const r=await fetch("/api/me",{headers:H});const d=await r.json();
  document.getElementById("s").textContent=d.saldo;}
async function tap(){const r=await fetch("/api/tap",{method:"POST",headers:H,
  body:JSON.stringify({count:1})});const d=await r.json();me();}
async function boost(){await fetch("/api/boost",{method:"POST",headers:H});me();}
me();
</script></body></html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/me")
def me():
    uid = usuario()
    if not uid:
        return jsonify(erro="auth"), 401
    with con() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return jsonify(dict(r))

@app.route("/api/tap", methods=["POST"])
def tap():
    uid = usuario()
    if not uid:
        return jsonify(erro="auth"), 401
    n = min(int((request.get_json(silent=True) or {}).get("count", 1)), 500)
    with con() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        ganho = n * r["tap"]
        c.execute("UPDATE users SET saldo=saldo+? WHERE id=?", (ganho, uid))
    return jsonify(ganho=ganho, saldo=r["saldo"] + ganho)

@app.route("/api/boost", methods=["POST"])
def boost():
    uid = usuario()
    if not uid:
        return jsonify(erro="auth"), 401
    with con() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        custo = 100 * r["nivel"]
        if r["saldo"] < custo:
            return jsonify(erro="saldo", saldo=r["saldo"], custo=custo), 400
        c.execute("UPDATE users SET saldo=saldo-?, nivel=nivel+1, tap=tap+1 WHERE id=?",
                  (custo, uid))
    return jsonify(ok=True, nivel=r["nivel"] + 1)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
