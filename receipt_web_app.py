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
    .saved-item{display:grid;grid-template-columns:1fr;gap:6px;padding:7px;border:1px solid #dde6e8;border-radius:6px;background:#f8fbfc;font-size:12px;line-height:1.35}
    .saved-item strong{display:block;font-size:13px}
    .saved-item button{min-height:30px;padding:4px 8px;font-size:12px}
    .saved-actions{display:grid;grid-template-columns:1fr 1fr;gap:5px}
    .saved-actions button{width:100%}
    .saved-actions .delete{color:#fff;border-color:var(--warn);background:var(--warn)}
    .field{display:grid;gap:5px;margin-bottom:9px}
    .row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .inline-field{display:grid;grid-template-columns:1fr auto;gap:6px}
    label{font-size:13px;font-weight:700}
    input,textarea{width:100%;border:1px solid #b8c6ca;border-radius:6px;background:#fff;color:var(--ink);padding:8px 10px;font:inherit;line-height:1.35}
    input[readonly]{background:#edf3f4}
    textarea{min-height:66px;resize:vertical}
    .preview{display:grid;align-content:start;justify-items:center;padding:20px;overflow:auto}
    .sheet{width:210mm;min-height:148.5mm;background:#fff;box-shadow:0 10px 34px rgba(0,0,0,.18);padding:3mm 5mm}
    #receipt{width:200mm;min-height:142.5mm;margin:0 auto;background:#fff;font-size:11.5px;line-height:1.18}
    .topline{font-size:10px;font-weight:700}
    .title{margin:.5mm 0 1mm;text-align:center;font-size:24px;font-weight:800;letter-spacing:.18em;text-decoration:underline;text-underline-offset:4px}
    .company{display:grid;grid-template-columns:1fr 48mm;gap:5mm;align-items:end;margin-bottom:1mm;font-size:11.5px;font-weight:700}
    .company-name{text-align:center;font-size:18px;font-weight:800;font-style:italic}
    table{width:100%;border-collapse:collapse;table-layout:fixed}
    th,td{border:1.4px solid var(--line);padding:1.15mm 1.8mm;vertical-align:middle;word-break:keep-all;overflow-wrap:anywhere}
    th{width:24mm;text-align:center;font-size:13px;font-weight:800}
    td{font-size:12.5px;font-weight:700}
    .items td{padding-top:1mm;padding-bottom:1mm}
    .product-line{display:grid;grid-template-columns:1fr 18mm 15mm;align-items:center;margin:-1.15mm -1.8mm}
    .product-line>div{min-height:5.8mm;padding:1.15mm 1.8mm;border-left:1.4px solid var(--line)}
    .product-line>div:first-child{border-left:0}
    .content-text{font-size:16px;letter-spacing:.06em}
    .address-cell{min-height:19mm;display:grid;grid-template-rows:auto 1fr auto;gap:1.5mm}
    .contact-grid{display:grid;grid-template-columns:1fr 1fr;gap:5mm}
    .memo-cell{min-height:24mm;display:grid;grid-template-rows:1fr auto;align-items:end}
    .signature{margin-top:1mm}
    .signature td,.signature th{height:10mm}
    .sign-note{display:grid;grid-template-columns:1fr auto;align-items:end;gap:5mm;min-height:10mm}
    .accounts{margin-top:1mm}
    .accounts th,.accounts td{padding-top:.9mm;padding-bottom:.9mm}
    .accounts th{line-height:1.25}
    .accounts td{height:6.4mm}
    .account-line{display:grid;grid-template-columns:22mm minmax(62mm,1fr) 44mm;gap:2mm;align-items:center;white-space:nowrap;font-size:11px;line-height:1.1}
    .account-line span{display:block;overflow:hidden;text-overflow:ellipsis}
    .account-line span:nth-child(2){text-align:left}
    .account-line span:nth-child(3){text-align:center}
    .promise{margin-top:.6mm;font-size:10.5px;font-weight:800}
    .muted-line{white-space:pre-line}
    @media(max-width:1000px){.app{grid-template-columns:1fr}.editor{border-right:0;border-bottom:1px solid #c9d3d7}.sheet{transform:scale(.72);transform-origin:top center;margin-bottom:-38mm}}
    @media(max-width:640px){.editor{padding:12px}.actions{position:sticky;top:0;z-index:2;padding:8px 0;background:var(--panel)}.actions button{min-height:42px}.row{grid-template-columns:1fr}.saved-list{max-height:130px}.preview{padding:12px}.sheet{transform:scale(.56);margin-bottom:-80mm}}
    @page{size:A4 portrait;margin:0}
    @media print{body{background:#fff}.editor{display:none}.app,.preview{display:block;min-height:0;padding:0;overflow:visible}.sheet{position:relative;width:210mm;height:148.5mm;min-height:148.5mm;padding:0;box-shadow:none;page-break-after:avoid;overflow:hidden}#receipt{position:absolute;left:6mm;top:5mm;width:198mm;min-height:110mm;margin:0;transform:none;transform-origin:top left}}
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
        <button type="button" id="imageBtn">이미지 저장</button>
        <button type="button" id="shareBtn">카카오톡 전달용 공유</button>
        <button type="button" id="smsBtn">문자 전송</button>
      </div>
      <p class="hint">서버에 저장되므로 PC와 스마트폰에서 같은 목록을 불러올 수 있습니다. 출력은 A4 세로 용지의 위쪽 반 페이지 안에서 인수증만 왼쪽 90도로 회전하는 기준입니다.</p>
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
          <tr><th>배달장소</th><td><div class="address-cell"><div class="muted-line" data-out="address"></div><div></div><div class="contact-grid"><div>전화 : <span data-out="phone"></span></div><div>받는분: <span data-out="receiverName"></span><br>휴대폰: <span data-out="receiverMobile"></span></div></div></div></td></tr>
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
      async get(id){ return fetch(`/api/receipts/${id}`).then(r=>r.json()); },
      async delete(id){ return fetch(`/api/receipts/${id}`, {method:"DELETE"}).then(r=>r.json()); }
    };

    function setStatus(text){ document.getElementById("statusText").textContent = text || ""; }
    function receiptUrl(id=currentReceiptId){ return id ? `${location.origin}${location.pathname}?id=${id}` : location.href; }
    function setReceiptUrl(id){
      if(!id) history.replaceState(null,"",location.pathname);
      else history.replaceState(null,"",`?id=${id}`);
    }
    function pad(value){ return String(value).padStart(2,"0"); }
    function todayIso(){ const d=new Date(); return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`; }
    function nowLocal(){ const d=new Date(); return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; }
    function normalizeDate(value){ if(/^\d{4}-\d{2}-\d{2}T/.test(value)) return value.slice(0,10); if(/^\d{4}-\d{2}-\d{2}$/.test(value)) return value; return todayIso(); }
    function normalizeDateTime(value){ if(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) return value.slice(0,16); return `${normalizeDate(value)}T13:00`; }
    function deliveryText(value){ const v=normalizeDateTime(value); const [date,time]=v.split("T"); const [y,m,d]=date.split("-").map(Number); return `${String(y).slice(2)}.${pad(m)}.${pad(d)}(${weekdays[new Date(y,m-1,d).getDay()]}) ${time}`; }
    function receiptData(){ return Object.fromEntries(fields.map(field => [field.dataset.bind, field.value])); }
    function setText(name,value){ document.querySelectorAll(`[data-out="${name}"]`).forEach(node => node.textContent = value || ""); }
    function displayValue(field){ if(field.id==="deliveryDate") return deliveryText(field.value); if(field.id==="orderDate") return normalizeDate(field.value); return field.value; }
    function splitReceiver(value){
      const raw = String(value || "").trim();
      const match = raw.match(/(01[016789][-\s]?\d{3,4}[-\s]?\d{4})/);
      if(!match) return {name:raw, mobile:""};
      return {
        name: raw.replace(match[0],"").replace(/\s{2,}/g," ").trim(),
        mobile: match[0].replace(/\s+/g,"-")
      };
    }
    function sync(){
      fields.forEach(field => setText(field.dataset.bind, displayValue(field)));
      const receiverParts = splitReceiver(document.getElementById("receiver").value);
      setText("receiverName", receiverParts.name);
      setText("receiverMobile", receiverParts.mobile);
      renderAccount("account1","account1Out");
      renderAccount("account2","account2Out");
    }
    function accountParts(value){
      const raw = value.trim();
      if(!raw) return ["","",""];
      const pipeParts = raw.split("|").map(part => part.trim()).filter(Boolean);
      if(pipeParts.length >= 3) return [pipeParts[0], pipeParts[1], pipeParts.slice(2).join(" ")];
      if(pipeParts.length === 2){
        const match = pipeParts[1].match(/^([0-9-]+)\s+(.+)$/);
        if(match) return [pipeParts[0], match[1], match[2]];
        return [pipeParts[0], pipeParts[1], ""];
      }
      const match = raw.match(/^(\S+)\s+([0-9-]+)\s+(.+)$/);
      if(match) return [match[1], match[2], match[3]];
      return [raw, "", ""];
    }
    function renderAccount(inputId, outputId){
      const parts = accountParts(document.getElementById(inputId).value);
      const out = document.getElementById(outputId); out.innerHTML = "";
      const wrap = document.createElement("div");
      wrap.className = "account-line";
      parts.forEach(part => { const span=document.createElement("span"); span.textContent=part; wrap.appendChild(span); });
      out.appendChild(wrap);
    }
    function applyData(data){
      const merged = {...defaults, ...data};
      fields.forEach(field => field.value = merged[field.dataset.bind] || "");
      document.getElementById("deliveryDate").value = normalizeDateTime(document.getElementById("deliveryDate").value || nowLocal());
      document.getElementById("orderDate").value = normalizeDate(document.getElementById("orderDate").value || todayIso());
      sync();
    }
    function blankReceiptData(){
      return {
        ...defaults,
        receiptNo:"",
        farmName:"",
        deliveryDate:nowLocal(),
        productName:"",
        quantity:"",
        message:"",
        sender:"",
        address:"",
        phone:"",
        receiver:"",
        memo:"",
        orderDate:todayIso()
      };
    }
    async function generateReceiptNo(){
      const result = await api.nextNo(document.getElementById("orderDate").value || todayIso());
      document.getElementById("receiptNo").value = result.receiptNo;
      currentReceiptId = null;
      sync();
    }
    async function saveCurrent(showMessage=true){
      try{
        sync();
        const data = receiptData();
        const saved = await api.save(currentReceiptId, data);
        if(saved.error) throw new Error(saved.error);
        currentReceiptId = saved.id;
        setReceiptUrl(saved.id);
        await loadList();
        if(showMessage) setStatus(`저장되었습니다. ${saved.receiptNo}`);
        return saved;
      }catch(error){
        alert(`저장에 실패했습니다. 다시 시도해 주세요. (${error.message})`);
        throw error;
      }
    }
    async function loadList(){
      const records = await api.list();
      const list = document.getElementById("savedList"); list.innerHTML = "";
      if(!records.length){ const empty=document.createElement("div"); empty.className="hint"; empty.textContent="아직 저장된 인수증이 없습니다."; list.appendChild(empty); return; }
      records.forEach(record => {
        const item=document.createElement("div"); item.className="saved-item";
        const text=document.createElement("div"); const title=document.createElement("strong"); title.textContent=`${record.receiptNo || "번호 없음"} / ${record.farmName || "상호 없음"}`;
        const meta=document.createElement("span"); meta.textContent=`${record.deliveryDate || ""} · 저장 ${record.updatedAt || ""}`;
        const actions=document.createElement("div"); actions.className="saved-actions";
        const loadButton=document.createElement("button"); loadButton.type="button"; loadButton.textContent="불러오기"; loadButton.dataset.loadId=record.id;
        const deleteButton=document.createElement("button"); deleteButton.type="button"; deleteButton.className="delete"; deleteButton.textContent="삭제"; deleteButton.dataset.deleteId=record.id;
        actions.append(loadButton,deleteButton);
        text.append(title,meta); item.append(text,actions); list.appendChild(item);
      });
    }
    async function loadReceipt(id){ const record = await api.get(id); currentReceiptId = record.id; setReceiptUrl(record.id); applyData(record.data); setStatus(`불러왔습니다. ${record.receiptNo}`); }
    async function deleteReceipt(id){
      const label = document.querySelector(`[data-delete-id="${id}"]`)?.closest(".saved-item")?.querySelector("strong")?.textContent || "선택한 인수증";
      if(!confirm(`${label}을(를) 삭제할까요?`)) return;
      await api.delete(id);
      if(String(currentReceiptId) === String(id)){ currentReceiptId = null; setReceiptUrl(null); }
      await loadList();
      setStatus(`${label}을(를) 삭제했습니다.`);
    }
    async function newReceipt(){
      currentReceiptId = null;
      setReceiptUrl(null);
      applyData(blankReceiptData());
      setStatus("새 인수증을 준비하는 중입니다.");
      await generateReceiptNo();
      setStatus("새 인수증을 작성합니다.");
    }
    function imageFromUrl(url){
      return new Promise((resolve,reject)=>{
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error("image load failed"));
        image.src = url;
      });
    }
    function drawText(ctx, text, x, y, maxWidth, lineHeight){
      const words = String(text || "").split(/\s+/);
      let line = "";
      let yy = y;
      words.forEach(word => {
        const next = line ? `${line} ${word}` : word;
        if(ctx.measureText(next).width > maxWidth && line){
          ctx.fillText(line, x, yy);
          line = word;
          yy += lineHeight;
        }else{
          line = next;
        }
      });
      if(line) ctx.fillText(line, x, yy);
      return yy + lineHeight;
    }
    function drawCell(ctx, x, y, w, h, label, value, options={}){
      ctx.strokeRect(x, y, w, h);
      ctx.font = "700 23px Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      String(label || "").split("\\n").forEach((line, i, arr) => ctx.fillText(line, x + 58, y + h / 2 + (i - (arr.length - 1) / 2) * 26));
      ctx.beginPath();
      ctx.moveTo(x + 115, y);
      ctx.lineTo(x + 115, y + h);
      ctx.stroke();
      ctx.textAlign = options.align || "left";
      ctx.font = options.font || "700 24px Arial, sans-serif";
      ctx.textBaseline = "top";
      String(value || "").split("\\n").forEach((line, i) => drawText(ctx, line, x + 130, y + 12 + i * (options.lineHeight || 30), w - 145, options.lineHeight || 30));
    }
    async function receiptBlob(){
      const data = receiptData();
      const NL = String.fromCharCode(10);
      const canvas = document.createElement("canvas");
      const width = 1600;
      const height = 900;
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0,0,width,height);
      ctx.fillStyle = "#111";
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 2;

      ctx.font = "700 20px Arial, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(`No:${data.receiptNo || ""}`, 48, 52);
      ctx.font = "800 52px Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("인 수 증", width / 2, 92);
      ctx.beginPath();
      ctx.moveTo(width / 2 - 115, 110);
      ctx.lineTo(width / 2 + 115, 110);
      ctx.stroke();

      ctx.font = "700 24px Arial, sans-serif";
      ctx.textAlign = "left";
      String(data.companyInfo || "").split("\\n").forEach((line, i) => ctx.fillText(line, 48, 145 + i * 28));
      ctx.font = "800 34px Arial, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(data.farmName || "", width - 48, 248);

      const x = 48;
      const tableW = width - 96;
      let y = 270;
      drawCell(ctx, x, y, tableW, 48, "품   명", `${data.productName || ""}          수량   ${data.quantity || ""}`);
      y += 48;
      drawCell(ctx, x, y, tableW, 54, "내   용", data.message || "", {font:"800 30px Arial, sans-serif"});
      y += 54;
      drawCell(ctx, x, y, tableW, 52, "보내는이", data.sender || "");
      y += 52;
      drawCell(ctx, x, y, tableW, 120, "배달장소", `${data.address || ""}\\n\\n전화 : ${data.phone || ""}        받는분: ${data.receiver || ""}`);
      y += 120;
      drawCell(ctx, x, y, tableW, 50, "배달일시", deliveryText(data.deliveryDate));
      y += 50;
      drawCell(ctx, x, y, tableW, 150, "참고사항", `${data.memo || ""}\\n\\n주문일자 : ${normalizeDate(data.orderDate)}`, {lineHeight:32});
      y += 160;
      drawCell(ctx, x, y, tableW, 75, "인수\\n하신분", "(반드시 성명으로 기록바랍니다)                         (서명)        인수시간      시      분", {font:"700 24px Arial, sans-serif"});
      y += 85;
      const acc1 = accountParts(data.account1 || "").join("        ");
      const acc2 = accountParts(data.account2 || "").join("        ");
      drawCell(ctx, x, y, tableW, 78, "온라인\\n계좌번호", `${acc1}\\n${acc2}`, {lineHeight:34});
      ctx.font = "800 22px Arial, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(data.promise || "", 48, y + 110);

      return await new Promise((resolve,reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("PNG blob failed")), "image/png", .96));
    }
    function fileName(ext){
      const no = document.getElementById("receiptNo").value.replace(/[\\\\/:*?"<>|]/g, "_") || "receipt";
      return `inan_receipt_${no}.${ext}`;
    }
    function wrapReceiptLines(ctx, text, maxWidth, maxLines){
      const result = [];
      String(text || "").split(/\\r?\\n/).forEach(rawLine => {
        const chars = rawLine || " ";
        let line = "";
        [...chars].forEach(char => {
          const next = line + char;
          if(ctx.measureText(next).width > maxWidth && line){
            result.push(line);
            line = char;
          }else{
            line = next;
          }
        });
        result.push(line);
      });
      if(result.length > maxLines){
        const trimmed = result.slice(0, maxLines);
        trimmed[maxLines - 1] = `${trimmed[maxLines - 1].slice(0, -1)}…`;
        return trimmed;
      }
      return result;
    }
    function drawReceiptText(ctx, text, x, y, maxWidth, lineHeight, maxLines){
      wrapReceiptLines(ctx, text, maxWidth, maxLines).forEach((line,index) => ctx.fillText(line, x, y + index * lineHeight));
    }
    function drawReceiptRow(ctx, x, y, w, h, label, value, options={}){
      const labelW = options.labelW || 145;
      ctx.strokeRect(x, y, w, h);
      ctx.beginPath();
      ctx.moveTo(x + labelW, y);
      ctx.lineTo(x + labelW, y + h);
      ctx.stroke();
      ctx.save();
      ctx.font = "800 25px Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      String(label).split(/\\r?\\n/).forEach((line,index,lines) => ctx.fillText(line, x + labelW / 2, y + h / 2 + (index - (lines.length - 1) / 2) * 29));
      ctx.restore();
      ctx.save();
      ctx.font = options.font || "700 27px Arial, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      drawReceiptText(ctx, value, x + labelW + 18, y + 14, w - labelW - 36, options.lineHeight || 34, options.maxLines || Math.max(1, Math.floor((h - 18) / (options.lineHeight || 34))));
      ctx.restore();
    }
    function drawReceiptAccountRow(ctx, x, y, w, h, label, account1, account2){
      const labelW = 145;
      const valueX = x + labelW;
      const bankW = 120;
      const ownerW = 250;
      const numberW = w - labelW - bankW - ownerW;
      ctx.strokeRect(x, y, w, h);
      ctx.beginPath();
      ctx.moveTo(valueX, y);
      ctx.lineTo(valueX, y + h);
      ctx.moveTo(valueX + bankW, y);
      ctx.lineTo(valueX + bankW, y + h);
      ctx.moveTo(valueX + bankW + numberW, y);
      ctx.lineTo(valueX + bankW + numberW, y + h);
      ctx.moveTo(valueX, y + h / 2);
      ctx.lineTo(x + w, y + h / 2);
      ctx.stroke();
      ctx.font = "800 25px Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      label.split(/\\r?\\n/).forEach((line,index,lines) => ctx.fillText(line, x + labelW / 2, y + h / 2 + (index - (lines.length - 1) / 2) * 29));
      [account1, account2].forEach((account,row) => {
        const parts = accountParts(account || "");
        const cy = y + h * (row ? 0.75 : 0.25);
        ctx.font = "800 24px Arial, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(parts[0] || "", valueX + bankW / 2, cy);
        ctx.fillText(parts[1] || "", valueX + bankW + numberW / 2, cy);
        ctx.fillText(parts[2] || "", valueX + bankW + numberW + ownerW / 2, cy);
      });
    }
    async function receiptBlob(){
      const data = receiptData();
      const canvas = document.createElement("canvas");
      const width = 1800;
      const height = 1240;
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0,0,width,height);
      ctx.fillStyle = "#111";
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 2.5;

      const x = 58;
      const tableW = width - 116;
      ctx.font = "800 22px Arial, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(`No:${data.receiptNo || ""}`, x, 42);

      ctx.font = "900 58px Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("인 수 증", width / 2, 68);
      ctx.beginPath();
      ctx.moveTo(width / 2 - 125, 135);
      ctx.lineTo(width / 2 + 125, 135);
      ctx.stroke();

      ctx.font = "800 24px Arial, sans-serif";
      ctx.textAlign = "left";
      String(data.companyInfo || "").split(/\\r?\\n/).slice(0,5).forEach((line,index) => ctx.fillText(line, x, 155 + index * 30));
      ctx.font = "900 38px Arial, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(data.farmName || "", width - x, 255);

      let y = 290;
      drawReceiptRow(ctx, x, y, tableW, 58, "품   명", `${data.productName || ""}     수량   ${data.quantity || ""}`, {maxLines:1});
      y += 58;
      drawReceiptRow(ctx, x, y, tableW, 66, "내   용", data.message || "", {font:"900 34px Arial, sans-serif", maxLines:1});
      y += 66;
      drawReceiptRow(ctx, x, y, tableW, 60, "보내는이", data.sender || "", {maxLines:1});
      y += 60;
      drawReceiptRow(ctx, x, y, tableW, 170, "배달장소", `${data.address || ""}\\n\\n전화 : ${data.phone || ""}          받는분 : ${data.receiver || ""}\\n휴대폰 :`, {maxLines:4, lineHeight:36});
      y += 170;
      drawReceiptRow(ctx, x, y, tableW, 60, "배달일시", deliveryText(data.deliveryDate), {maxLines:1});
      y += 60;
      drawReceiptRow(ctx, x, y, tableW, 210, "참고사항", `${data.memo || ""}\\n\\n주문일자 : ${normalizeDate(data.orderDate)}`, {maxLines:5, lineHeight:36});
      y += 220;
      drawReceiptRow(ctx, x, y, tableW, 95, "인수\\n하신분", "(반드시 성명으로 기록바랍니다)                                      (서명)        인수시간      시      분", {font:"800 24px Arial, sans-serif", maxLines:2, lineHeight:36});
      y += 105;
      drawReceiptAccountRow(ctx, x, y, tableW, 92, "온라인\\n계좌번호", data.account1, data.account2);

      ctx.font = "900 24px Arial, sans-serif";
      ctx.textAlign = "left";
      drawReceiptText(ctx, data.promise || "", x, y + 112, tableW, 30, 2);

      return await new Promise((resolve,reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("PNG blob failed")), "image/png", .96));
    }
    function safeReceiptLines(text){
      return String(text || "")
        .replaceAll(String.fromCharCode(92) + "n", String.fromCharCode(10))
        .replaceAll(String.fromCharCode(13), "")
        .split(String.fromCharCode(10));
    }
    function wrapSafeText(ctx, text, maxWidth, maxLines){
      const out = [];
      safeReceiptLines(text).forEach(raw => {
        let line = "";
        [...(raw || " ")].forEach(char => {
          const next = line + char;
          if(ctx.measureText(next).width > maxWidth && line){
            out.push(line);
            line = char;
          }else{
            line = next;
          }
        });
        out.push(line);
      });
      if(out.length > maxLines){
        const trimmed = out.slice(0, maxLines);
        trimmed[maxLines - 1] = `${trimmed[maxLines - 1].slice(0, -2)}...`;
        return trimmed;
      }
      return out;
    }
    function drawSafeText(ctx, text, x, y, maxWidth, lineHeight, maxLines){
      wrapSafeText(ctx, text, maxWidth, maxLines).forEach((line,index) => ctx.fillText(line, x, y + index * lineHeight));
    }
    function drawSafeRow(ctx, x, y, w, h, label, value, options={}){
      const labelW = options.labelW || 145;
      ctx.strokeRect(x, y, w, h);
      ctx.beginPath();
      ctx.moveTo(x + labelW, y);
      ctx.lineTo(x + labelW, y + h);
      ctx.stroke();
      ctx.save();
      ctx.font = "800 25px Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      safeReceiptLines(label).forEach((line,index,lines) => ctx.fillText(line, x + labelW / 2, y + h / 2 + (index - (lines.length - 1) / 2) * 29));
      ctx.restore();
      ctx.save();
      ctx.font = options.font || "700 27px Arial, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      drawSafeText(ctx, value, x + labelW + 18, y + 14, w - labelW - 36, options.lineHeight || 34, options.maxLines || Math.max(1, Math.floor((h - 18) / (options.lineHeight || 34))));
      ctx.restore();
    }
    function drawSafeAccounts(ctx, x, y, w, h, account1, account2){
      const labelW = 145;
      const bankW = 120;
      const ownerW = 250;
      const valueX = x + labelW;
      const numberW = w - labelW - bankW - ownerW;
      ctx.strokeRect(x, y, w, h);
      ctx.beginPath();
      [valueX, valueX + bankW, valueX + bankW + numberW].forEach(lineX => {
        ctx.moveTo(lineX, y);
        ctx.lineTo(lineX, y + h);
      });
      ctx.moveTo(valueX, y + h / 2);
      ctx.lineTo(x + w, y + h / 2);
      ctx.stroke();
      ctx.font = "800 24px Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ["\\uc628\\ub77c\\uc778", "\\uacc4\\uc88c\\ubc88\\ud638"].forEach((line,index) => ctx.fillText(line, x + labelW / 2, y + h / 2 + (index - 0.5) * 29));
      [account1, account2].forEach((account,row) => {
        const parts = accountParts(account || "");
        const cy = y + h * (row ? 0.75 : 0.25);
        ctx.fillText(parts[0] || "", valueX + bankW / 2, cy);
        ctx.fillText(parts[1] || "", valueX + bankW + numberW / 2, cy);
        ctx.fillText(parts[2] || "", valueX + bankW + numberW + ownerW / 2, cy);
      });
    }
    async function receiptBlob(){
      const data = receiptData();
      const canvas = document.createElement("canvas");
      const width = 1800;
      const height = 1240;
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0,0,width,height);
      ctx.fillStyle = "#111";
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 2.5;

      const x = 58;
      const tableW = width - 116;
      ctx.font = "800 22px Arial, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(`No:${data.receiptNo || ""}`, x, 42);
      ctx.font = "900 58px Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("인 수 증", width / 2, 68);
      ctx.beginPath();
      ctx.moveTo(width / 2 - 125, 135);
      ctx.lineTo(width / 2 + 125, 135);
      ctx.stroke();
      ctx.font = "800 24px Arial, sans-serif";
      ctx.textAlign = "left";
      safeReceiptLines(data.companyInfo).slice(0,5).forEach((line,index) => ctx.fillText(line, x, 155 + index * 30));
      ctx.font = "900 38px Arial, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(data.farmName || "", width - x, 255);

      let y = 290;
      drawSafeRow(ctx, x, y, tableW, 58, "품   명", `${data.productName || ""}     수량   ${data.quantity || ""}`, {maxLines:1});
      y += 58;
      drawSafeRow(ctx, x, y, tableW, 66, "내   용", data.message || "", {font:"900 34px Arial, sans-serif", maxLines:1});
      y += 66;
      drawSafeRow(ctx, x, y, tableW, 60, "보내는이", data.sender || "", {maxLines:1});
      y += 60;
      drawSafeRow(ctx, x, y, tableW, 170, "배달장소", [data.address || "", "", `전화 : ${data.phone || ""}          받는분 : ${data.receiver || ""}`, "휴대폰 :"].join(NL), {maxLines:4, lineHeight:36});
      y += 170;
      drawSafeRow(ctx, x, y, tableW, 60, "배달일시", deliveryText(data.deliveryDate), {maxLines:1});
      y += 60;
      drawSafeRow(ctx, x, y, tableW, 210, "참고사항", [data.memo || "", "", `주문일자 : ${normalizeDate(data.orderDate)}`].join(NL), {maxLines:5, lineHeight:36});
      y += 220;
      drawSafeRow(ctx, x, y, tableW, 95, ["인수", "하신분"].join(NL), "(반드시 성명으로 기록바랍니다)                                      (서명)        인수시간      시      분", {font:"800 24px Arial, sans-serif", maxLines:2, lineHeight:36});
      y += 105;
      drawSafeAccounts(ctx, x, y, tableW, 92, data.account1, data.account2);
      ctx.font = "900 24px Arial, sans-serif";
      ctx.textAlign = "left";
      drawSafeText(ctx, data.promise || "", x, y + 112, tableW, 30, 2);
      return await new Promise((resolve,reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("PNG blob failed")), "image/png", .96));
    }
    function finalOutText(name){
      const node = document.querySelector(`[data-out="${name}"]`);
      return node ? node.textContent.trim() : "";
    }
    function finalImageData(){
      sync();
      const raw = receiptData();
      const receiverParts = splitReceiver(finalOutText("receiver") || raw.receiver);
      return {
        ...raw,
        receiptNo: finalOutText("receiptNo") || raw.receiptNo || "",
        companyInfo: finalOutText("companyInfo") || raw.companyInfo || "",
        farmName: finalOutText("farmName") || raw.farmName || "",
        productName: finalOutText("productName") || raw.productName || "",
        quantity: finalOutText("quantity") || raw.quantity || "",
        message: finalOutText("message") || raw.message || "",
        sender: finalOutText("sender") || raw.sender || "",
        address: finalOutText("address") || raw.address || "",
        phone: finalOutText("phone") || raw.phone || "",
        receiver: receiverParts.name || "",
        receiverMobile: receiverParts.mobile || "",
        memo: finalOutText("memo") || raw.memo || "",
        deliveryDateText: finalOutText("deliveryDate") || deliveryText(raw.deliveryDate),
        orderDateText: finalOutText("orderDate") || normalizeDate(raw.orderDate),
        promise: finalOutText("promise") || raw.promise || ""
      };
    }
    function finalLines(text){
      return String(text || "")
        .replaceAll(String.fromCharCode(92) + "n", String.fromCharCode(10))
        .replaceAll(String.fromCharCode(13), "")
        .split(String.fromCharCode(10));
    }
    function finalWrap(ctx,text,maxWidth,maxLines){
      const lines = [];
      finalLines(text).forEach(raw => {
        let line = "";
        [...(raw || " ")].forEach(ch => {
          const next = line + ch;
          if(ctx.measureText(next).width > maxWidth && line){
            lines.push(line);
            line = ch;
          }else{
            line = next;
          }
        });
        lines.push(line);
      });
      if(lines.length <= maxLines) return lines;
      const cut = lines.slice(0,maxLines);
      cut[maxLines - 1] = `${cut[maxLines - 1].slice(0,-2)}...`;
      return cut;
    }
    function finalDrawText(ctx,text,x,y,maxWidth,lineHeight,maxLines){
      finalWrap(ctx,text,maxWidth,maxLines).forEach((line,index) => ctx.fillText(line,x,y + index * lineHeight));
    }
    function finalDrawLabel(ctx,label,x,y,w,h){
      ctx.save();
      ctx.font = "800 25px 'Malgun Gothic', Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      finalLines(label).forEach((line,index,lines) => ctx.fillText(line,x + w / 2,y + h / 2 + (index - (lines.length - 1) / 2) * 29));
      ctx.restore();
    }
    function finalDrawRow(ctx,x,y,w,h,label,value,options={}){
      const labelW = options.labelW || 145;
      ctx.strokeRect(x,y,w,h);
      ctx.beginPath();
      ctx.moveTo(x + labelW,y);
      ctx.lineTo(x + labelW,y + h);
      ctx.stroke();
      finalDrawLabel(ctx,label,x,y,labelW,h);
      ctx.save();
      ctx.font = options.font || "800 27px 'Malgun Gothic', Arial, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      finalDrawText(ctx,value,x + labelW + 18,y + 14,w - labelW - 36,options.lineHeight || 34,options.maxLines || Math.max(1,Math.floor((h - 18) / (options.lineHeight || 34))));
      ctx.restore();
    }
    function finalDrawProductRow(ctx,x,y,w,h,data){
      const labelW = 145;
      const qtyLabelW = 90;
      const qtyValueW = 75;
      ctx.strokeRect(x,y,w,h);
      ctx.beginPath();
      [x + labelW, x + w - qtyLabelW - qtyValueW, x + w - qtyValueW].forEach(lineX => {
        ctx.moveTo(lineX,y);
        ctx.lineTo(lineX,y + h);
      });
      ctx.stroke();
      finalDrawLabel(ctx,"\ud488   \uba85",x,y,labelW,h);
      ctx.save();
      ctx.font = "800 27px 'Malgun Gothic', Arial, sans-serif";
      ctx.textBaseline = "middle";
      ctx.textAlign = "left";
      ctx.fillText(data.productName || "",x + labelW + 18,y + h / 2);
      ctx.textAlign = "center";
      ctx.fillText("\uc218\ub7c9",x + w - qtyValueW - qtyLabelW / 2,y + h / 2);
      ctx.fillText(data.quantity || "",x + w - qtyValueW / 2,y + h / 2);
      ctx.restore();
    }
    function finalDrawAccounts(ctx,x,y,w,h,account1,account2){
      const labelW = 145;
      const bankW = 120;
      const ownerW = 250;
      const valueX = x + labelW;
      const numberW = w - labelW - bankW - ownerW;
      ctx.strokeRect(x,y,w,h);
      ctx.beginPath();
      [valueX,valueX + bankW,valueX + bankW + numberW].forEach(lineX => {
        ctx.moveTo(lineX,y);
        ctx.lineTo(lineX,y + h);
      });
      ctx.moveTo(valueX,y + h / 2);
      ctx.lineTo(x + w,y + h / 2);
      ctx.stroke();
      finalDrawLabel(ctx,"\uc628 \ub77c \uc778\n\uacc4\uc88c\ubc88\ud638",x,y,labelW,h);
      ctx.save();
      ctx.font = "800 24px 'Malgun Gothic', Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      [account1,account2].forEach((account,row) => {
        const parts = accountParts(account || "");
        const cy = y + h * (row ? 0.75 : 0.25);
        ctx.fillText(parts[0] || "",valueX + bankW / 2,cy);
        ctx.fillText(parts[1] || "",valueX + bankW + numberW / 2,cy);
        ctx.fillText(parts[2] || "",valueX + bankW + numberW + ownerW / 2,cy);
      });
      ctx.restore();
    }
    async function receiptBlob(){
      const data = finalImageData();
      const nl = String.fromCharCode(10);
      const canvas = document.createElement("canvas");
      const width = 1800;
      const height = 1240;
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0,0,width,height);
      ctx.fillStyle = "#111";
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 2.5;

      const x = 58;
      const tableW = width - 116;
      ctx.font = "800 22px 'Malgun Gothic', Arial, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(`No:${data.receiptNo || ""}`,x,42);
      ctx.font = "900 58px 'Malgun Gothic', Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("\uc778 \uc218 \uc99d",width / 2,68);
      ctx.beginPath();
      ctx.moveTo(width / 2 - 125,135);
      ctx.lineTo(width / 2 + 125,135);
      ctx.stroke();

      ctx.font = "800 24px 'Malgun Gothic', Arial, sans-serif";
      ctx.textAlign = "left";
      finalLines(data.companyInfo).slice(0,5).forEach((line,index) => ctx.fillText(line,x,155 + index * 30));
      ctx.font = "900 38px 'Malgun Gothic', Arial, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(data.farmName || "",width - x,250);

      let y = 315;
      finalDrawProductRow(ctx,x,y,tableW,58,data);
      y += 58;
      finalDrawRow(ctx,x,y,tableW,66,"\ub0b4   \uc6a9",data.message || "",{font:"900 34px 'Malgun Gothic', Arial, sans-serif",maxLines:1});
      y += 66;
      finalDrawRow(ctx,x,y,tableW,60,"\ubcf4\ub0b4\ub294\uc774",data.sender || "",{maxLines:1});
      y += 60;
      finalDrawRow(ctx,x,y,tableW,170,"\ubc30\ub2ec\uc7a5\uc18c",[data.address || "","",`\uc804\ud654 : ${data.phone || ""}          \ubc1b\ub294\ubd84 : ${data.receiver || ""}`,`\ud734\ub300\ud3f0 : ${data.receiverMobile || ""}`].join(nl),{maxLines:4,lineHeight:36});
      y += 170;
      finalDrawRow(ctx,x,y,tableW,60,"\ubc30\ub2ec\uc77c\uc2dc",data.deliveryDateText || "",{maxLines:1});
      y += 60;
      finalDrawRow(ctx,x,y,tableW,210,"\ucc38\uace0\uc0ac\ud56d",[data.memo || "","",`\uc8fc\ubb38\uc77c\uc790 : ${data.orderDateText || ""}`].join(nl),{maxLines:5,lineHeight:36});
      y += 220;
      finalDrawRow(ctx,x,y,tableW,95,"\uc778\uc218\n\ud558\uc2e0\ubd84","(\ubc18\ub4dc\uc2dc \uc131\uba85\uc73c\ub85c \uae30\ub85d\ubc14\ub78d\ub2c8\ub2e4)                                      (\uc11c\uba85)        \uc778\uc218\uc2dc\uac04      \uc2dc      \ubd84",{font:"800 24px 'Malgun Gothic', Arial, sans-serif",maxLines:2,lineHeight:36});
      y += 105;
      finalDrawAccounts(ctx,x,y,tableW,92,data.account1,data.account2);
      ctx.font = "900 24px 'Malgun Gothic', Arial, sans-serif";
      ctx.textAlign = "left";
      finalDrawText(ctx,data.promise || "",x,y + 112,tableW,30,2);
      return await new Promise((resolve,reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("PNG blob failed")),"image/png",0.96));
    }
    function downloadBlob(blob,name){
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = name;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    }
    function openPrintBlob(blob){
      const url = URL.createObjectURL(blob);
      const printWindow = window.open("", "_blank");
      if(!printWindow){
        downloadBlob(blob, fileName("png"));
        alert("팝업이 차단되어 인수증 이미지를 저장했습니다. 저장된 이미지를 열어 인쇄 또는 PDF 저장을 해주세요.");
        return;
      }
      printWindow.document.write(`<!doctype html><html><head><title>인수증 인쇄</title><style>@page{size:A4 portrait;margin:0}body{margin:0;background:#fff}.wrap{width:210mm;height:148.5mm;display:flex;align-items:flex-start;justify-content:center;padding-top:5mm;box-sizing:border-box}img{width:198mm;height:auto}.tools{position:fixed;right:10px;bottom:10px}@media print{.tools{display:none}}</style></head><body><div class="wrap"><img src="${url}" alt="인수증"></div><div class="tools"><button onclick="window.print()">인쇄 / PDF 저장</button></div></body></html>`);
      printWindow.document.close();
      setTimeout(() => { try{ printWindow.print(); }catch{} }, 700);
    }
    async function shareReceiptImage(targetName){
      await saveCurrent(false);
      try{
        const blob = await receiptBlob();
        const file = new File([blob], fileName("png"), {type:"image/png"});
        if(navigator.canShare && navigator.canShare({files:[file]})){
          await navigator.share({files:[file], title:"(주)이난 인수증"});
          return;
        }
        downloadBlob(blob, file.name);
        alert(`인수증 이미지를 저장했습니다. ${targetName}에 저장된 PNG 파일을 첨부해서 보내시면 됩니다.`);
      }catch(error){
        alert(`이미지 생성에 실패했습니다. 다시 시도해 주세요. (${error.message})`);
      }
    }

    document.getElementById("printBtn").addEventListener("click", async()=>{
      try{
        await saveCurrent(false);
        const blob = await receiptBlob();
        openPrintBlob(blob);
      }catch(error){}
    });
    document.getElementById("saveBtn").addEventListener("click", async()=>{ await saveCurrent(true); });
    document.getElementById("newDocBtn").addEventListener("click", async()=>{ if(confirm("새 인수증을 작성할까요?")) await newReceipt(); });
    document.getElementById("newNoBtn").addEventListener("click", generateReceiptNo);
    document.getElementById("orderDate").addEventListener("change", generateReceiptNo);
    document.getElementById("imageBtn").addEventListener("click", async()=>{
      try{
        const blob = await receiptBlob();
        downloadBlob(blob, fileName("png"));
        setStatus("인수증 이미지를 저장했습니다.");
      }catch(error){
        alert(`이미지 저장에 실패했습니다. 다시 시도해 주세요. (${error.message})`);
      }
    });
    document.getElementById("shareBtn").addEventListener("click", () => shareReceiptImage("카카오톡"));
    document.getElementById("smsBtn").addEventListener("click", () => shareReceiptImage("문자"));
    document.getElementById("savedList").addEventListener("click", event => {
      const deleteButton = event.target.closest("[data-delete-id]");
      if(deleteButton){ deleteReceipt(deleteButton.dataset.deleteId); return; }
      const loadButton = event.target.closest("[data-load-id]");
      if(loadButton) loadReceipt(loadButton.dataset.loadId);
    });
    fields.forEach(field => field.addEventListener("input", sync));

    (async function init(){
      applyData({...defaults, deliveryDate:nowLocal(), orderDate:todayIso()});
      await loadList();
      const id = new URLSearchParams(location.search).get("id");
      if(id) await loadReceipt(id);
      else await generateReceiptNo();
    })();
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

    def do_DELETE(self):
        if not self.path.startswith("/api/receipts/"):
            text_response(self, 404, "페이지를 찾을 수 없습니다.", "text/plain; charset=utf-8")
            return
        receipt_id = self.path.rsplit("/", 1)[-1]
        with db() as conn:
            cur = conn.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
        if cur.rowcount == 0:
            json_response(self, 404, {"error": "인수증을 찾을 수 없습니다."})
            return
        json_response(self, 200, {"ok": True, "id": int(receipt_id)})

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
