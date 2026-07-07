import json
import os
import sqlite3
import socket
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "inan_receipts.db"))
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8780"))


DEFAULT_DATA = {
    "receiptNo": "",
    "farmName": "대림농원",
    "deliveryDate": "",
    "productName": "동양란[        ]+관엽식물[ 테이블 ]",
    "quantity": "2",
    "message": "축하드립니다",
    "sender": "1.최용휘  2.배인효",
    "address": "부산시의회 배관구 시의원",
    "phone": "",
    "receiver": "",
    "memo": "",
    "orderDate": "",
    "promise": "* 언제나 한결같이 한길만을 걸어갈 것을 약속드립니다.",
    "companyInfo": "부산시 금정구 체육공원로 368\n전국.해외 꽃배달 전문업체\n수입란, 동서양란 중도매인\nTEL:051-512-0621\nFAX:051-980-1040",
    "account1": "농협 | 121067-56-074826 | 김도형",
    "account2": "농협 | 121060-51-089505 | (주)이난",
}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_no TEXT,
            farm_name TEXT,
            delivery_date TEXT,
            order_date TEXT,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS receipt_sequences (
            date_key TEXT PRIMARY KEY,
            seq INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler, status, body, content_type="text/html; charset=utf-8"):
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def next_receipt_no(order_date):
    key = "".join(ch for ch in (order_date or "") if ch.isdigit())[:8]
    if len(key) != 8:
        key = datetime.now().strftime("%Y%m%d")
    with db() as conn:
        row = conn.execute("SELECT seq FROM receipt_sequences WHERE date_key = ?", (key,)).fetchone()
        seq = (row["seq"] + 1) if row else 1
        conn.execute(
            "INSERT INTO receipt_sequences(date_key, seq) VALUES(?, ?) "
            "ON CONFLICT(date_key) DO UPDATE SET seq = excluded.seq",
            (key, seq),
        )
    return f"{key}-{seq:04d}"


def clean_data(data):
    merged = dict(DEFAULT_DATA)
    if isinstance(data, dict):
        merged.update({key: "" if value is None else str(value) for key, value in data.items()})
    return merged


APP_HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>(주)이난 상품배송 인수증 웹앱</title>
  <style>
    :root{--ink:#171717;--line:#1f1f1f;--panel:#f4f7f9;--accent:#226b5b;--warn:#d96c3b}
    *{box-sizing:border-box}
    body{margin:0;color:var(--ink);background:#dfe6e8;font-family:"Malgun Gothic","Apple SD Gothic Neo",Arial,sans-serif}
    .app{display:grid;grid-template-columns:minmax(350px,460px) 1fr;min-height:100vh}
    .editor{padding:16px;background:var(--panel);border-right:1px solid #c9d3d7;overflow:auto}
    h1{margin:0 0 12px;font-size:21px}
    .actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:10px}
    button{border:1px solid #b6c4c8;border-radius:6px;background:#fff;min-height:38px;padding:7px 9px;font:inherit;font-weight:700;cursor:pointer}
    button.primary{color:#fff;border-color:var(--accent);background:var(--accent)}
    button.warn{color:#fff;border-color:var(--warn);background:var(--warn)}
    .hint,.status{margin:7px 0;color:#5b5b5b;font-size:12px;line-height:1.45}
    .status{min-height:18px;color:var(--accent);font-weight:700}
    .saved-panel{margin:10px 0 14px;padding:10px;border:1px solid #c8d5d9;border-radius:6px;background:#fff}
    .saved-panel h2{margin:0 0 8px;font-size:14px}
    .saved-list{display:grid;gap:6px;max-height:170px;overflow:auto}
    .saved-item{display:grid;grid-template-columns:1fr auto;gap:6px;align-items:center;padding:7px;border:1px solid #dde6e8;border-radius:6px;background:#f8fbfc;font-size:12px;line-height:1.35}
    .saved-item strong{display:block;font-size:13px}
    .saved-item button{min-height:30px;padding:4px 8px;font-size:12px}
    .field{display:grid;gap:5px;margin-bottom:9px}
    .row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .inline-field{display:grid;grid-template-columns:1fr auto;gap:6px}
    label{font-size:13px;font-weight:700}
    input,textarea{width:100%;border:1px solid #b8c6ca;border-radius:6px;background:#fff;color:var(--ink);padding:8px 10px;font:inherit;line-height:1.35}
    input[readonly]{background:#edf3f4}
    textarea{min-height:66px;resize:vertical}
    .preview{display:grid;align-content:start;justify-items:center;padding:20px;overflow:auto}
    .sheet{width:210mm;min-height:148mm;background:#fff;box-shadow:0 10px 34px rgba(0,0,0,.18);padding:5mm 6mm}
    #receipt{width:198mm;min-height:136mm;margin:0 auto;background:#fff;font-size:12px;line-height:1.25}
    .topline{font-size:10px;font-weight:700}
    .title{margin:1mm 0 1.5mm;text-align:center;font-size:25px;font-weight:800;letter-spacing:.18em;text-decoration:underline;text-underline-offset:4px}
    .company{display:grid;grid-template-columns:1fr 48mm;gap:5mm;align-items:end;margin-bottom:1.5mm;font-size:12px;font-weight:700}
    .company-name{text-align:center;font-size:18px;font-weight:800;font-style:italic}
    table{width:100%;border-collapse:collapse;table-layout:fixed}
    th,td{border:1.4px solid var(--line);padding:1.4mm 2mm;vertical-align:middle;word-break:keep-all;overflow-wrap:anywhere}
    th{width:24mm;text-align:center;font-size:13px;font-weight:800}
    td{font-size:12.5px;font-weight:700}
    .items td{padding-top:1.3mm;padding-bottom:1.3mm}
    .product-line{display:grid;grid-template-columns:1fr 18mm 15mm;align-items:center;margin:-1.4mm -2mm}
    .product-line>div{min-height:6.5mm;padding:1.4mm 2mm;border-left:1.4px solid var(--line)}
    .product-line>div:first-child{border-left:0}
    .content-text{font-size:17px;letter-spacing:.06em}
    .address-cell{min-height:23mm;display:grid;grid-template-rows:auto 1fr auto;gap:2mm}
    .contact-grid{display:grid;grid-template-columns:1fr 1fr;gap:5mm}
    .memo-cell{min-height:30mm;display:grid;grid-template-rows:1fr auto;align-items:end}
    .signature{margin-top:2mm}
    .signature td,.signature th{height:13mm}
    .sign-note{display:grid;grid-template-columns:1fr auto;align-items:end;gap:5mm;min-height:10mm}
    .accounts{margin-top:2mm}
    .accounts th,.accounts td{padding-top:1.7mm;padding-bottom:1.7mm}
    .promise{margin-top:1mm;font-size:11px;font-weight:800}
    .muted-line{white-space:pre-line}
    @media(max-width:1000px){.app{grid-template-columns:1fr}.editor{border-right:0;border-bottom:1px solid #c9d3d7}.sheet{transform:scale(.72);transform-origin:top center;margin-bottom:-38mm}}
    @page{size:A5 landscape;margin:0}
    @media print{body{background:#fff}.editor{display:none}.app,.preview{display:block;min-height:0;padding:0;overflow:visible}.sheet{width:210mm;height:148mm;min-height:148mm;padding:4mm 5mm;box-shadow:none;page-break-after:avoid;overflow:hidden}#receipt{width:198mm;min-height:136mm;margin:0;transform:scale(.72);transform-origin:top left}}
  </style>
</head>
<body>
  <main class="app">
    <section class="editor" aria-label="인수증 입력">
      <h1>(주)이난 상품배송 인수증</h1>
      <div class="actions">
        <button class="primary" type="button" id="printBtn">인쇄 / PDF 저장</button>
        <button class="primary" type="button" id="saveBtn">저장</button>
        <button type="button" id="newDocBtn">새 인수증</button>
        <button type="button" id="shareBtn">카카오톡 전달용 공유</button>
        <button class="warn" type="button" id="clearBtn">입력 초기화</button>
      </div>
      <p class="hint">서버에 저장되므로 PC와 스마트폰에서 같은 목록을 불러올 수 있습니다. 출력은 A5 가로 용지의 반 영역 기준입니다.</p>
      <p class="status" id="statusText"></p>
      <div class="saved-panel">
        <h2>저장된 인수증</h2>
        <div class="saved-list" id="savedList"></div>
      </div>

      <div class="field"><label for="receiptNo">No.</label><div class="inline-field"><input id="receiptNo" data-bind="receiptNo" readonly><button type="button" id="newNoBtn">새 번호</button></div></div>
      <div class="row"><div class="field"><label for="farmName">상호/농원명</label><input id="farmName" data-bind="farmName"></div><div class="field"><label for="deliveryDate">배달일시</label><input id="deliveryDate" type="datetime-local" data-bind="deliveryDate"></div></div>
      <div class="row"><div class="field"><label for="productName">품명</label><input id="productName" data-bind="productName"></div><div class="field"><label for="quantity">수량</label><input id="quantity" data-bind="quantity"></div></div>
      <div class="field"><label for="message">내용</label><input id="message" data-bind="message"></div>
      <div class="field"><label for="sender">보내는이</label><input id="sender" data-bind="sender"></div>
      <div class="field"><label for="address">배달장소</label><textarea id="address" data-bind="address"></textarea></div>
      <div class="row"><div class="field"><label for="phone">전화</label><input id="phone" data-bind="phone"></div><div class="field"><label for="receiver">받는분 / 휴대폰</label><input id="receiver" data-bind="receiver"></div></div>
      <div class="field"><label for="memo">참고사항</label><textarea id="memo" data-bind="memo"></textarea></div>
      <div class="row"><div class="field"><label for="orderDate">주문일자</label><input id="orderDate" type="date" data-bind="orderDate"></div><div class="field"><label for="promise">하단 문구</label><input id="promise" data-bind="promise"></div></div>
      <div class="field"><label for="companyInfo">회사 정보</label><textarea id="companyInfo" data-bind="companyInfo"></textarea></div>
      <div class="field"><label for="account1">계좌 1</label><input id="account1" data-bind="account1"></div>
      <div class="field"><label for="account2">계좌 2</label><input id="account2" data-bind="account2"></div>
    </section>

    <section class="preview" aria-label="인수증 미리보기">
      <div class="sheet"><article id="receipt">
        <div class="topline">No:<span data-out="receiptNo"></span></div>
        <div class="title">인 수 증</div>
        <div class="company"><div class="muted-line" data-out="companyInfo"></div><div class="company-name" data-out="farmName"></div></div>
        <table class="items">
          <tr><th>품&nbsp;&nbsp;&nbsp;&nbsp;명</th><td><div class="product-line"><div data-out="productName"></div><div style="text-align:center;">수량</div><div style="text-align:center;" data-out="quantity"></div></div></td></tr>
          <tr><th>내&nbsp;&nbsp;&nbsp;&nbsp;용</th><td class="content-text" data-out="message"></td></tr>
          <tr><th>보내는이</th><td data-out="sender"></td></tr>
          <tr><th>배달장소</th><td><div class="address-cell"><div class="muted-line" data-out="address"></div><div></div><div class="contact-grid"><div>전화 : <span data-out="phone"></span></div><div>받는분: <span data-out="receiver"></span><br>휴대폰:</div></div></div></td></tr>
          <tr><th>배달일시</th><td data-out="deliveryDate"></td></tr>
          <tr><th>참고사항</th><td><div class="memo-cell"><div class="muted-line" data-out="memo"></div><div>주문일자 : &nbsp;<span data-out="orderDate"></span></div></div></td></tr>
        </table>
        <table class="signature"><tr><th>인수<br>하신분</th><td><div class="sign-note"><span>(반드시 성명으로 기록바랍니다)</span><span>(서명)</span></div></td><th style="width:16mm;">인수<br>시간</th><td style="width:41mm;text-align:center;">시&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;분</td></tr></table>
        <table class="accounts"><tr><th rowspan="2">온 라 인<br>계좌번호</th><td id="account1Out"></td></tr><tr><td id="account2Out"></td></tr></table>
        <div class="promise" data-out="promise"></div>
      </article></div>
    </section>
  </main>

  <script>
    const defaults = __DEFAULTS__;
    const fields = [...document.querySelectorAll("[data-bind]")];
    const weekdays = ["일","월","화","수","목","금","토"];
    let currentReceiptId = null;

    const api = {
      async list(){ return fetch("/api/receipts").then(r=>r.json()); },
      async nextNo(orderDate){ return fetch(`/api/next-no?date=${encodeURIComponent(orderDate)}`).then(r=>r.json()); },
      async save(id,data){
        const response = await fetch(id ? `/api/receipts/${id}` : "/api/receipts", {
          method: id ? "PUT" : "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify(data)
        });
        return response.json();
      },
      async get(id){ return fetch(`/api/receipts/${id}`).then(r=>r.json()); }
    };

    function setStatus(text){ document.getElementById("statusText").textContent = text || ""; }
    function pad(value){ return String(value).padStart(2,"0"); }
    function todayIso(){ const d=new Date(); return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`; }
    function nowLocal(){ const d=new Date(); return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; }
    function normalizeDate(value){ if(/^\d{4}-\d{2}-\d{2}T/.test(value)) return value.slice(0,10); if(/^\d{4}-\d{2}-\d{2}$/.test(value)) return value; return todayIso(); }
    function normalizeDateTime(value){ if(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) return value.slice(0,16); return `${normalizeDate(value)}T13:00`; }
    function deliveryText(value){ const v=normalizeDateTime(value); const [date,time]=v.split("T"); const [y,m,d]=date.split("-").map(Number); return `${String(y).slice(2)}.${pad(m)}.${pad(d)}(${weekdays[new Date(y,m-1,d).getDay()]}) ${time}`; }
    function receiptData(){ return Object.fromEntries(fields.map(field => [field.dataset.bind, field.value])); }
    function setText(name,value){ document.querySelectorAll(`[data-out="${name}"]`).forEach(node => node.textContent = value || ""); }
    function displayValue(field){ if(field.id==="deliveryDate") return deliveryText(field.value); if(field.id==="orderDate") return normalizeDate(field.value); return field.value; }
    function sync(){ fields.forEach(field => setText(field.dataset.bind, displayValue(field))); renderAccount("account1","account1Out"); renderAccount("account2","account2Out"); }
    function renderAccount(inputId, outputId){
      const parts = document.getElementById(inputId).value.split("|").map(part => part.trim());
      const out = document.getElementById(outputId); out.innerHTML = "";
      const wrap = document.createElement("div");
      wrap.style.display = "grid"; wrap.style.gridTemplateColumns = "30mm 1fr 48mm"; wrap.style.gap = "4mm"; wrap.style.alignItems = "center";
      parts.slice(0,3).forEach(part => { const span=document.createElement("span"); span.textContent=part; wrap.appendChild(span); });
      out.appendChild(wrap);
    }
    function applyData(data){
      const merged = {...defaults, ...data};
      fields.forEach(field => field.value = merged[field.dataset.bind] || "");
      document.getElementById("deliveryDate").value = normalizeDateTime(document.getElementById("deliveryDate").value || nowLocal());
      document.getElementById("orderDate").value = normalizeDate(document.getElementById("orderDate").value || todayIso());
      sync();
    }
    async function generateReceiptNo(){
      const result = await api.nextNo(document.getElementById("orderDate").value || todayIso());
      document.getElementById("receiptNo").value = result.receiptNo;
      currentReceiptId = null;
      sync();
    }
    async function saveCurrent(showMessage=true){
      const data = receiptData();
      const saved = await api.save(currentReceiptId, data);
      currentReceiptId = saved.id;
      await loadList();
      if(showMessage) setStatus(`저장되었습니다. ${saved.receiptNo}`);
      return saved;
    }
    async function loadList(){
      const records = await api.list();
      const list = document.getElementById("savedList"); list.innerHTML = "";
      if(!records.length){ const empty=document.createElement("div"); empty.className="hint"; empty.textContent="아직 저장된 인수증이 없습니다."; list.appendChild(empty); return; }
      records.forEach(record => {
        const item=document.createElement("div"); item.className="saved-item";
        const text=document.createElement("div"); const title=document.createElement("strong"); title.textContent=`${record.receiptNo || "번호 없음"} / ${record.farmName || "상호 없음"}`;
        const meta=document.createElement("span"); meta.textContent=`${record.deliveryDate || ""} · 저장 ${record.updatedAt || ""}`;
        const button=document.createElement("button"); button.type="button"; button.textContent="불러오기"; button.dataset.id=record.id;
        text.append(title,meta); item.append(text,button); list.appendChild(item);
      });
    }
    async function loadReceipt(id){ const record = await api.get(id); currentReceiptId = record.id; applyData(record.data); setStatus(`불러왔습니다. ${record.receiptNo}`); }
    async function newReceipt(){ currentReceiptId=null; applyData({...defaults, deliveryDate:nowLocal(), orderDate:todayIso()}); await generateReceiptNo(); setStatus("새 인수증을 작성합니다."); }
    async function shareReceipt(){
      await saveCurrent(false);
      const text = `인수증 ${document.getElementById("receiptNo").value}\n${location.href}`;
      if(navigator.share) await navigator.share({title:"(주)이난 인수증", text, url:location.href});
      else { await navigator.clipboard.writeText(text); alert("전달용 문구를 복사했습니다. 카카오톡에 붙여넣어 보내세요."); }
    }

    document.getElementById("printBtn").addEventListener("click", async()=>{ await saveCurrent(false); window.print(); });
    document.getElementById("saveBtn").addEventListener("click", ()=>saveCurrent(true));
    document.getElementById("newDocBtn").addEventListener("click", ()=>{ if(confirm("새 인수증을 작성할까요?")) newReceipt(); });
    document.getElementById("newNoBtn").addEventListener("click", generateReceiptNo);
    document.getElementById("orderDate").addEventListener("change", generateReceiptNo);
    document.getElementById("clearBtn").addEventListener("click", ()=>{ if(confirm("현재 입력 내용을 지우고 새 인수증을 작성할까요?")) newReceipt(); });
    document.getElementById("shareBtn").addEventListener("click", shareReceipt);
    document.getElementById("savedList").addEventListener("click", event => { const button = event.target.closest("[data-id]"); if(button) loadReceipt(button.dataset.id); });
    fields.forEach(field => field.addEventListener("input", sync));

    (async function init(){ applyData({...defaults, deliveryDate:nowLocal(), orderDate:todayIso()}); await generateReceiptNo(); await loadList(); })();
  </script>
</body>
</html>"""


def app_html():
    return APP_HTML.replace("__DEFAULTS__", json.dumps(DEFAULT_DATA, ensure_ascii=False))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            text_response(self, 200, app_html())
            return
        if path == "/health":
            json_response(self, 200, {"ok": True})
            return
        if path == "/api/next-no":
            query = parse_qs(parsed.query)
            json_response(self, 200, {"receiptNo": next_receipt_no(query.get("date", [""])[0])})
            return
        if path == "/api/receipts":
            with db() as conn:
                rows = conn.execute(
                    "SELECT id, receipt_no, farm_name, delivery_date, order_date, updated_at "
                    "FROM receipts ORDER BY id DESC LIMIT 100"
                ).fetchall()
            json_response(
                self,
                200,
                [
                    {
                        "id": row["id"],
                        "receiptNo": row["receipt_no"],
                        "farmName": row["farm_name"],
                        "deliveryDate": row["delivery_date"],
                        "orderDate": row["order_date"],
                        "updatedAt": row["updated_at"],
                    }
                    for row in rows
                ],
            )
            return
        if path.startswith("/api/receipts/"):
            receipt_id = path.rsplit("/", 1)[-1]
            with db() as conn:
                row = conn.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
            if not row:
                json_response(self, 404, {"error": "인수증을 찾을 수 없습니다."})
                return
            json_response(
                self,
                200,
                {
                    "id": row["id"],
                    "receiptNo": row["receipt_no"],
                    "farmName": row["farm_name"],
                    "deliveryDate": row["delivery_date"],
                    "orderDate": row["order_date"],
                    "updatedAt": row["updated_at"],
                    "data": json.loads(row["data"]),
                },
            )
            return
        text_response(self, 404, "페이지를 찾을 수 없습니다.", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path != "/api/receipts":
            text_response(self, 404, "페이지를 찾을 수 없습니다.", "text/plain; charset=utf-8")
            return
        data = self.read_json()
        data = clean_data(data)
        if not data.get("receiptNo"):
            data["receiptNo"] = next_receipt_no(data.get("orderDate"))
        created_at = now_text()
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO receipts(receipt_no, farm_name, delivery_date, order_date, data, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    data.get("receiptNo"),
                    data.get("farmName"),
                    data.get("deliveryDate"),
                    data.get("orderDate"),
                    json.dumps(data, ensure_ascii=False),
                    created_at,
                    created_at,
                ),
            )
            receipt_id = cur.lastrowid
        json_response(self, 200, {"id": receipt_id, "receiptNo": data.get("receiptNo")})

    def do_PUT(self):
        if not self.path.startswith("/api/receipts/"):
            text_response(self, 404, "페이지를 찾을 수 없습니다.", "text/plain; charset=utf-8")
            return
        receipt_id = self.path.rsplit("/", 1)[-1]
        data = clean_data(self.read_json())
        updated_at = now_text()
        with db() as conn:
            cur = conn.execute(
                """
                UPDATE receipts
                SET receipt_no = ?, farm_name = ?, delivery_date = ?, order_date = ?, data = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    data.get("receiptNo"),
                    data.get("farmName"),
                    data.get("deliveryDate"),
                    data.get("orderDate"),
                    json.dumps(data, ensure_ascii=False),
                    updated_at,
                    receipt_id,
                ),
            )
        if cur.rowcount == 0:
            json_response(self, 404, {"error": "인수증을 찾을 수 없습니다."})
            return
        json_response(self, 200, {"id": int(receipt_id), "receiptNo": data.get("receiptNo")})

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))


def get_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    db().close()
    pc_url = f"http://127.0.0.1:{PORT}/"
    mobile_url = f"http://{get_lan_ip()}:{PORT}/"
    print(f"PC 접속 주소: {pc_url}")
    print(f"휴대폰 접속 주소: {mobile_url}")
    print("휴대폰은 PC와 같은 와이파이에 연결한 뒤 위 주소로 접속하세요.")
    print("웹 배포 시에는 Render/Railway 등에서 이 파일을 실행하면 됩니다.")
    try:
        webbrowser.open(pc_url)
    except Exception:
        pass
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
