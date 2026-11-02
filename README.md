# 팀 프로젝트를 위한 팀 편성 웹 앱

학생이 스스로 팀에 지원하고 팀원이 투표로 받아들이며, 마감 뒤 남은 학생은 AI가 배정하고 앱이 규칙으로 검사하는 Streamlit 앱.

> ✍️ 표시가 있는 칸은 배포하고 직접 시험해 본 뒤 **본인이 겪은 내용으로** 채운다(꾸며 내면 시나리오 밖 점수 0점).

## 1. 배포 주소
✍️ `https://__________.streamlit.app`

## 2. PRD와 구현 계획의 위치
- PRD: [`docs/PRD.md`](docs/PRD.md)
- 구현 계획: [`docs/구현 계획.md`](docs/구현%20계획.md)
- 실행·배포 안내: [`docs/실행·배포 안내.md`](docs/실행·배포%20안내.md)

## 3. 고른 해결 방법 (모두 어려운 해결)
| 기능 | 고른 해결 |
|---|---|
| 다른 사람의 변경 보기 | 어려운 해결(`st.fragment(run_every=5)`로 팀 목록·투표 영역만 5초마다 갱신) |
| 필수 포함 역할을 지킬 수 없는 팀 | 어려운 해결(지원 단계에서 필수 포함 역할 자리가 모자라게 되는 지원은 막음) |
| 같은 팀에 대기 중인 지원이 여럿 | 어려운 해결(승인 직전에 규칙 재검사, 팀 행 잠금으로 투표가 끝난 순서대로 처리) |
| 마지막 자리에 두 명이 동시에 들어감 | 어려운 해결(`tf_members`의 `(team_id, slot_no)` 기본 키와 `student_id` 유일 제약, `schema.sql`) |
| AI 응답이 늦을 때 | 어려운 해결(모델마다 120초 전체 대기 시간을 재서 끊고 다음 모델로) |
| 3차 모델까지 실패 | 어려운 해결(앱이 모든 경우를 따져 검사 다섯 가지를 통과하는 배정을 찾음) |
| AI 대기 중 화면 | 어려운 해결(몇 차 모델의 응답을 몇 초째 기다리는지 보여 줌) |
| DB 일시정지 막기 | 어려운 해결(GitHub Actions가 매일 두 번 DB에 질의, `.github/workflows/keepalive.yml`) |

## 4. 쓴 모델 3개
✍️ Secrets의 `OPENROUTER_MODELS`에 실제로 넣은 이름으로 고친다.
- 1차 `nvidia/nemotron-3-super-120b-a12b:free`
- 2차 `openai/gpt-oss-120b:free`
- 3차 `meta-llama/llama-3.3-70b-instruct:free`

## 5. 오픈라우터 AI 모델 호출 실패 사례
✍️ 관리자 화면의 'AI 호출 기록' 표(또는 Supabase `tf_ai_logs` 표)를 캡처해 `img/`에 넣고 적는다.
- 예시 형식: "부록 3(어려움) 15단계에서 1차 모델이 120초 안에 응답하지 않아 2차 모델로 넘어감(화면 `img/ai-timeout.png`)"

## 6. 클로드가 잘못된 추론이나 답변을 한 사례
✍️ 본인이 클로드와 작업하며 겪은 사례와 알아챈 방법(화면 또는 커밋)을 적는다.

## 7. 발견한 문제점이나 개선 필요 사항
✍️ 배포 앱을 연습용 시나리오로 시험하며 찾은 것을 단계·화면과 함께 적는다. "문제 없음"은 인정되지 않는다.

## 실행 방법(내 컴퓨터)
```bash
pip install -r requirements.txt
cp .env.example .env      # 값을 채운다(.env는 깃허브에 올라가지 않음)
streamlit run streamlit_app.py
```
- 테스트: `python -m tests.test_rules` / `TEST_DATABASE_URL="연습용 DB" python -m tests.test_scenarios` (tf_ 표를 지우므로 채점용 DB에서는 돌리지 않는다)

작성자: ✍️ 본인 이름
