# Receipt Dataset Next Steps And Agent Team Assessment

기준 레포:
- `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh`

외부 샘플 폴더:
- `C:\Users\USER-PC\Desktop\jp\.worktrees\codex-hwpx-proposal-patch\output\제비`

목적:
- `제비` 폴더를 현재 OCR 고도화의 평가 시작점으로 어떻게 써야 하는지 정리한다.
- 에이전트 팀 + loop 구조가 지금 단계에서 실제로 맞는지 판단 기준을 남긴다.

## 1. 현재 `제비` 폴더 상태

관찰 기준:
- 원본 이미지 후보: 14개
- crop 이미지: 3개
- 기존 JSON 산출물: 3개
- webp 참고 이미지: 24개

현재 보이는 파일 그룹:

### 원본/실사 후보

- `1652882389756.jpg`
- `2a4dd3c18f06cec1571dc9ca52dc5946.jpg`
- `b5cfea0f38a019d94cdb2ac2b434f87f_res.jpeg`
- `image.png`
- `img2.jpg`
- `img3.jpg`
- `R.jpg`
- `R (1).jpg`
- `R (2).jpg`
- `R (3).jpg`
- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`

### 파생 crop

- `img2.items-crop.jpg`
- `img3.items-crop.jpg`
- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.items-crop.jpg`

### 기존 산출물

- `img2.qwen.json`
- `img3.qwen.json`
- `paddleocr-vl-timing-crop.json`

### 참고용 웹 이미지

- `OIP*.webp`

## 2. 지금 바로 해야 하는 일

핵심은 이 폴더를 "학습 데이터"가 아니라 "평가 시작점"으로 바꾸는 것이다.

### Step 1. 파일을 세 그룹으로 분리

1. 골든셋 후보
   - 실제 평가에 쓸 원본 영수증
2. 테스트 fixture
   - `items-crop` 같은 규칙 검증용 파생 이미지
3. 참고 자료
   - `webp`, 기존 JSON 산출물

정리 원칙:
- crop 이미지는 unit/regression 테스트용으로만 쓴다.
- webp는 출처/권리/대표성이 불명확하므로 골든셋에 바로 넣지 않는다.
- 골든셋은 원본 실사 이미지 위주로 시작한다.

### Step 2. 골든셋 v0를 만든다

현재 권장 수:
- 시작: 8~12장
- 1차 목표: 30~50장
- 2차 목표: 100장

`제비` 폴더에서는 우선 원본 실사 이미지 8~12장을 골라 `golden-v0`로 지정하는 게 맞다.

### Step 3. 정답 라벨을 붙인다

각 이미지마다 아래 JSON이 필요하다.

```json
{
  "image": "img2.jpg",
  "vendor_name": "세븐일레븐",
  "purchased_at": "2020-06-09",
  "layout_type": "barcode-detail",
  "items": [
    {
      "name": "라라스윗 바닐라 파인트",
      "quantity": 1,
      "unit": "개",
      "amount": 6900
    }
  ],
  "totals": {
    "payment_amount": 13800
  }
}
```

중요:
- ground truth에는 "OCR이 읽은 값"이 아니라 "사람이 최종 확인한 정답"을 넣는다.
- 품목명 정규화 기준을 먼저 고정해야 한다.

### Step 4. 현재 엔진 baseline을 저장한다

각 이미지에 대해 현재 `ReceiptParseService` 또는 `ReceiptOCR.analyze_receipt()` 결과를 저장한다.

목적:
- 전처리/파서/정규화/Qwen 보조를 바꾸기 전 baseline 확보
- 단계별 기여도 비교

### Step 5. 평가 스크립트를 붙인다

최소 지표:
- 날짜 정확도
- vendor_name 정확도
- item precision / recall / F1
- totals consistency accuracy
- review flag rate
- 평균 처리 시간

이 단계가 끝나야 "무엇을 고쳐야 하는지"가 수치로 나온다.

## 3. 우리 현재 상태에서의 정답 우선순위

`docs/OCR_QUALITY_BASELINE.md` 기준으로 다음 세 가지가 가장 먼저다.

1. alias / 정규화
   - `투썸딸기피지`
   - `어쉬밀크클릿 [`
   - `속이면한 누룸지`

2. false positive 제거
   - `img3`의 `[(야] 7 -11,760`

3. totals mismatch 개선
   - `SE-...jpg`

즉, 지금 단계에서 제일 먼저 필요한 것은:
- 더 많은 모델
- 더 많은 팀원
- 더 복잡한 오케스트레이션

이 아니라

- 작은 골든셋
- baseline 저장
- 지표 계산
- 파서 수정 우선순위 확정

이다.

## 4. 붙여준 에이전트 팀 글에 대한 판단

큰 방향은 맞다. 다만 그대로 믿고 설계하면 안 된다.

### 맞는 부분

- 팀 리드 + 팀원 구조 자체는 공식 문서와 맞다.
- shared task list와 teammate messaging 개념도 공식 문서와 맞다.
- 독립된 컨텍스트를 가진 여러 세션이 병렬로 일하는 것도 맞다.

공식 근거:
- [Claude Code Agent Teams docs](https://code.claude.com/docs/en/agent-teams)

### 보정이 필요한 부분

1. 저장 경로 설명
   - 글은 `.claude/teams/<team_id>/inbox/` 같은 설명을 하고 있지만, 공식 문서에서 명시하는 로컬 저장 경로는
     - `~/.claude/teams/{team-name}/config.json`
     - `~/.claude/tasks/{team-name}/`
   - 공식 문서에는 project-local inbox 경로를 표준 저장소로 소개하지 않는다.

2. "지금 상황은 에이전트 팀 + 랄프루프를 돌리기에 가장 이상적"이라는 결론
   - 이건 과장이다.
   - 공식 문서도 agent teams는 실험 기능이고, 세션 재개/조율/종료 쪽 limitation이 있다고 명시한다.
   - 토큰 비용도 팀 규모에 비례해 늘어난다.

3. Reviewer 자동 루프
   - 공식 문서에는 `TeammateIdle`, `TaskCreated`, `TaskCompleted` 훅으로 quality gate를 걸 수 있다고 되어 있다.
   - 하지만 이걸 바로 “자동 self-healing loop”처럼 생각하면 설계가 과해진다.
   - 먼저 task 분리와 파일 충돌 방지가 선행돼야 한다.

공식 근거:
- Agent teams are experimental: [agent teams docs](https://code.claude.com/docs/en/agent-teams)
- Token cost scales with teammates: [cost docs](https://code.claude.com/docs/en/costs)
- `SendMessage` availability and subagent reuse: [subagents docs](https://code.claude.com/docs/en/sub-agents)

## 5. 우리 상황에서 agent teams가 맞는가

### 지금 당장은 "부분적으로만" 맞다

현재 OCR 고도화의 중심 수정 파일은 사실상 여기에 몰려 있다.

- `ocr_qwen/receipts.py`
- `ocr_qwen/services.py`
- `ocr_qwen/ingredient_dictionary.py`
- `docs/OCR_QUALITY_BASELINE.md`

즉, 같은 파일 충돌 위험이 높다.

공식 문서도 같은 파일을 두 teammate가 동시에 수정하는 걸 피하라고 한다.

그래서 지금 단계에서 가장 좋은 방식은:

### 권장 구조 A. 지금 바로

- 리드 1명 + 단일 구현 세션
- 필요 시 subagent / 병렬 탐색만 제한적으로 사용

병렬화 가능한 일:
- 라벨 포맷 설계
- 평가 지표 코드 초안
- alias 후보 추출

병렬화 비권장:
- `receipts.py` 규칙 수정
- 동일 문서 동시 편집

### 권장 구조 B. 골든셋과 평가 스크립트가 생긴 뒤

그때는 소규모 agent team이 의미가 생긴다.

- 팀 리드
  - baseline 측정
  - 우선순위 결정
  - 최종 merge 판단
- 팀원 A
  - 데이터셋 manifest / ground truth 정리
- 팀원 B
  - 평가 스크립트 / metric 계산
- 팀원 C
  - parser rule 개선
- Reviewer
  - test / metric gate 확인

이 구조는 서로 다른 파일 집합을 맡길 수 있어서 충돌이 줄어든다.

## 6. 결론

`제비` 폴더가 생겼으니 지금 바로 해야 할 일은 agent team 오케스트레이션이 아니라:

1. 골든셋 후보 선정
2. 정답 라벨 작성
3. baseline 저장
4. 평가 스크립트 작성
5. 그 결과로 parser 우선순위 확정

이다.

에이전트 팀은 그 다음 단계에서 쓸 도구다.

현재 단계에서 가장 현실적인 판단:
- 지금: 단일 리드 중심 + 필요한 병렬 탐색만 사용
- 다음: 골든셋/평가 스크립트가 갖춰지면 소규모 agent team 도입
