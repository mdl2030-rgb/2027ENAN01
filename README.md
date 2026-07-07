# (주)이난 상품배송 인수증 웹앱

PC와 스마트폰에서 같은 저장 목록을 사용하는 서버형 인수증 프로그램입니다.

## PC에서 실행

`run_receipt_web_app.bat`를 실행한 뒤 표시되는 주소로 접속합니다.

- PC: `http://127.0.0.1:8780/`
- 스마트폰: 같은 와이파이에서 터미널에 표시되는 `http://내부IP:8780/` 주소로 접속

## 웹 배포

Render 등에 업로드할 때 이 폴더 전체를 올립니다.

- Start command: `python receipt_web_app.py`
- Health check path: `/health`
- 저장 DB 파일: 기본 `inan_receipts.db`, Render 영구 디스크 사용 시 `DB_PATH=/var/data/inan_receipts.db`

무료 서버는 재배포 시 DB가 사라질 수 있으므로, 장기 보관이 필요하면 Render Disk 또는 별도 DB를 사용하세요.
