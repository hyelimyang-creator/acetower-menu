# 에이스타워 한식뷔페 급식 서비스

카카오채널(광교다인푸드 `_xoxcxcxen`)에서 매일 급식을 가져와, 점심 메뉴판은 Google
Gemini로 읽어 텍스트로 만든 뒤 `data/acetower.json`에 저장하는 서비스입니다.
GitHub Actions가 하루 3번 자동 실행합니다. **키는 이 저장소 한 곳,��만** 넣으므로,
지비 앱을 쓰는 개인들은 키를 넣을 필요가 없습니다.

## 설치 한 번만, 약 10분)

### 1) 무료 Gemini 키 발급(신용카드 불필요)
1. https://aistudio.google.com/apikey 접속 → 구글 로그인
2. **Create API key** 클릭
3. 나온 키(`AIza...`)를 복사해 둞니다.

### 2) GitHub 저장소 만들기
1. https://github.com 로그인 (계정이 없으면 무분 가입)
2. 오른쬽 위 **+** → **New repository**
3. 이름: 예) `acetower-menu` · **Public** 선택 · **Create repository**

### 3) 이 파일들 올리기
- 새 저장소 페이지에서 **Add file → Upload files**
- 이 폴더(`에이스타워_급식서비스`) 안의 **모든 파일/폴더**를 통째로 끌어다 녓기
  (`scripts/`, `.github/`, `data/`, `README.md` 구조가 그대로 유지될야 합니다)
- **Commit changes**

### 4) Gemini 키를 Secret에 등록
1. 저장소 **Settings** → 왓쪽 **Secrets and variables → Actions**
2. **New repository secret**
3. Name: `GEMINI_API_KEY` · Secret: 1)에서 복사한 키 · **Add secret**

### 5) 자동화 켜고 첫 실행
1. 상틨 **Actions** 탭 → (안내 나오면) **I understand my workflows, enable them**
2. 왓쪽 **에이스타워 급식 갱신** → 오륶쪽 **Run workflow** 클릭
3. 몷 초~1분 럼 초록체크 ✅ 가 뜨면 성공

### 6) 데이터 주소(URL) 확인
아래 주소가 급식 JSON입니다 (`<아이디>`, `<저장소>`를 본인 것으로):

```
https://raw.githubusercontent.com/<아이디>/acetower-menu/main/data/acetower.json
```

브라우저로 열어 메뉴가 보이면 완성입니다. **이 주소를 저(클로드)에게 알려주시면*
지비 앱이 이 주소를 읽계.해 드립니다.

## 참고
- 실행 주기는 `.github/workflows/update-menu.yml` 의 `cron`에서 바꿀 수 있습니다.
- Gemini 무료 할당량(분당 10·일 250회)에 한참 못 미치게 호출합니다(하루 몇 회).
- 점심 메뉴판이 안 올라온 날은 저녁(텍스트)만 저장됩니다.
