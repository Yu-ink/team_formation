# 팀 프로젝트를 위한 팀 편성 웹 앱

학생이 스스로 팀에 지원하고 팀원이 투표로 받아들이며, 마감 뒤 남은 학생은 AI가 배정하고 앱이 규칙으로 검사하는 Streamlit 앱.

## 1. 배포 주소
https://teamformation-snqsmxudaj2ubyjawarth4.streamlit.app

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
- 1차 `google/gemma-4-31b-it:free`
- 2차 `nvidia/nemotron-3-ultra-550b-a55b:free`
- 3차 `thinkingmachines/inkling:free`

## 5. 오픈라우터 AI 모델 호출 실패 사례
- 부록 3(어려움) 15단계에서 'AI 배정'을 누르자 **1차 모델 `google/gemma-4-31b-it:free`가 0.5초 만에 HTTP 429(사용량이 많다며 거절)를 돌려줌**. 앱이 이를 실패로 처리하고 2차 모델로 넘어감.
  - 2차 모델 `nvidia/nemotron-3-ultra-550b-a55b:free`를 기다리는 동안 "2차 모델(…)의 응답을 기다리는 중… 15초 / 120초"가 보임 (화면 [`img/ai-waiting.png`](img/ai-waiting.png))
  - 2차 모델이 104.3초 만에 응답했고, 배정안이 검사 다섯 가지를 통과해 확정함. 3차 모델은 부르지 않음 (AI 호출 기록 [`img/ai-log.png`](img/ai-log.png), 배정안 [`img/assign-plan.png`](img/assign-plan.png), 확정 뒤 팀 현황 [`img/final.png`](img/final.png))

## 6. 클로드가 잘못된 추론이나 답변을 한 사례
1. **기본 모델 3개가 이미 없어진 모델이었음.** 클로드가 만든 코드의 `tf/config.py` 기본 모델(`nvidia/nemotron-3-super-120b-a12b:free`, `openai/gpt-oss-120b:free`, `meta-llama/llama-3.3-70b-instruct:free`)과 `.env.example`·README에 적힌 모델이, 11/2 배포 직전 오픈라우터 모델 목록(`https://openrouter.ai/api/v1/models`)에 하나도 없었음. 그대로 배포했다면 1·2·3차 호출이 모두 실패해 매번 앱 직접 배정으로 넘어갔을 것임.
   - 알아챈 방법: 배포 전에 모델 목록을 조회해 세 이름이 있는지 확인함.
   - 고친 커밋: `db892cf`(지금 응답하는 무료 모델 3개로 바꿈). 5항처럼 바꾼 2차 모델이 실제로 배정안을 냄.
2. **한국 시간을 잘못 읽어 마감까지 남은 시간을 틀리게 안내함.** 클로드가 Windows의 Git Bash에서 `TZ=Asia/Seoul date`를 실행하고 그 결과(08:09)를 한국 시간으로 보고 "지금 11/2 08시라 시간 여유가 있다"고 답함. 실제로는 Git Bash가 그 시간대 이름을 처리하지 못해 세계 표준시(UTC)가 나온 것이었고, 한국 시간은 17:09였음.
   - 알아챈 방법: Supabase 대시보드의 요청 그래프 시각(Nov 2, 5:00pm~5:59pm)이 안내한 시각과 맞지 않았음. PowerShell의 시간대 변환으로 다시 재어 한국 시간이 17:59임을 확인한 뒤 안내를 고침.

## 7. 발견한 문제점이나 개선 필요 사항
1. **들어온 지원이 첫 화면에 보이지 않음.** 부록 3(어려움) 2단계에서 학생4(WP;PL)가 팀1에 지원해 "대기"가 된 뒤, 학생1(PL;RW)의 첫 화면에는 학생4의 지원이 보이지 않았음 (화면 [`img/step2-wait.png`](img/step2-wait.png), [`img/vote-hidden.png`](img/vote-hidden.png)).
   - 원인: '내 팀에 들어온 지원'과 찬성/거부 단추가 팀 4개 목록 아래에 있어 스크롤해야 보임 (화면 [`img/vote-below.png`](img/vote-below.png)). 처음 쓰는 사람은 투표할 지원이 온 줄 모를 수 있음.
   - 개선: 들어온 지원이 있으면 팀 목록 위에 알림을 띄우거나 투표 영역을 팀 목록 위로 올림. (자동 채점은 key로 단추를 찾으므로 채점에는 영향이 없음)
2. **AI 배정 중 관리자 화면 전체가 흐려지고 다른 단추를 쓸 수 없음.** 15단계에서 2차 모델을 기다린 약 104초 동안 관리자 화면 전체가 흐리게 바뀌고 오른쪽 위에 'Stop'이 보였음 (화면 [`img/ai-waiting.png`](img/ai-waiting.png)). 배정 요청이 화면을 그리는 실행 안에서 끝날 때까지 기다리기 때문임. 3개 모델이 모두 늦으면 최대 6분 동안 이렇게 됨.
   - 개선: 배정을 백그라운드에서 돌리고, 진행 안내 영역만 `st.fragment`로 갱신함.
3. **1차 모델이 사용량 제한(HTTP 429)으로 바로 거절되고, 2차 모델은 120초 제한에 가깝게 걸림.** 같은 15단계에서 1차는 0.5초 만에 HTTP 429, 2차는 104.3초가 걸림 ([`img/ai-log.png`](img/ai-log.png)). 무료 모델이 붐비는 시간에는 2차도 시간 초과가 날 수 있음.
   - 개선: 429가 자주 나는 모델은 뒤 순서로 옮기고, 응답이 빠른 모델을 1차로 둠.
4. **'AI 호출 기록'의 걸린 시간이 `0.5000`, `104.3000`처럼 소수 넷째 자리까지 나옴** ([`img/ai-log.png`](img/ai-log.png)). 소수 첫째 자리까지만 보이도록 표 형식을 고치면 읽기 쉬움.

## 실행 방법(내 컴퓨터)
```bash
pip install -r requirements.txt
cp .env.example .env      # 값을 채운다(.env는 깃허브에 올라가지 않음)
streamlit run streamlit_app.py
```
- 테스트: `python -m tests.test_rules` / `TEST_DATABASE_URL="연습용 DB" python -m tests.test_scenarios` (tf_ 표를 지우므로 채점용 DB에서는 돌리지 않는다)

작성자: 권유진
