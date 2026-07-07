# (주)이난 상품배송 인수증 웹앱

Render에 업로드한 뒤 PC와 스마트폰에서 같은 인수증 목록을 저장/불러오기/출력할 수 있는 웹앱입니다.

## Render 배포

GitHub 저장소 최상단에 아래 파일들이 있어야 합니다.

- `receipt_web_app.py`
- `requirements.txt`
- `Procfile`
- `render.yaml`
- `README.md`

Render Web Service 설정:

- Runtime: `Python`
- Build Command: `pip install -r requirements.txt`
- Start Command: `python receipt_web_app.py`
- Health Check Path: `/health`

## 사용 방법

1. Render 배포가 끝나면 `https://서비스이름.onrender.com` 주소로 접속합니다.
2. PC 또는 스마트폰에서 인수증을 입력합니다.
3. `저장`을 누르면 서버 DB에 저장됩니다.
4. `저장된 인수증` 목록에서 다시 불러올 수 있습니다.
5. `카카오톡 전달용 공유`를 누르면 저장 후 해당 인수증 직접 링크가 공유됩니다.
6. 출력은 A4 가로 용지를 반으로 접었을 때의 한 면 기준입니다.

## 저장 자료 보관

기본 DB 파일은 `inan_receipts.db`입니다.

Render에서 장기 보관하려면 Persistent Disk를 붙이고 환경변수를 설정하세요.

- Disk Mount Path: `/var/data`
- Environment Variable: `DB_PATH=/var/data/inan_receipts.db`

무료 인스턴스의 임시 파일 저장소는 재시작/재배포 시 사라질 수 있습니다.
