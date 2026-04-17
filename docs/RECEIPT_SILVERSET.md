# Receipt Silver Set Workflow

기준 레포:
- `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh`

입력 폴더:
- `C:\Users\USER-PC\Desktop\jp\.worktrees\codex-hwpx-proposal-patch\output\제비`

목적:
- 현재 엔진이 추출한 결과를 기준 JSON 스키마로 저장해, 이후 파서 고도화 시 회귀 비교에 사용한다.

중요:
- 이 데이터는 사람이 직접 검수한 golden set이 아니다.
- 현재 엔진 출력 기반의 `silver set`이다.
- 따라서 "정확도 절대 기준"보다는 "변화 추적 / 회귀 검출"에 먼저 사용한다.

## 1. 생성 스크립트

파일:
- `scripts/build_receipt_silver_set.py`

실행 예시:

```powershell
python scripts/build_receipt_silver_set.py `
  --input-dir "C:\Users\USER-PC\Desktop\jp\.worktrees\codex-hwpx-proposal-patch\output\제비" `
  --output-dir "C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\data\receipt_silver\jevi-silver-v0" `
  --dataset-name "jevi-silver-v0"
```

동작:
- `.jpg`, `.jpeg`, `.png` 원본 후보만 수집
- `items-crop` 이미지는 제외
- 각 이미지에 대해 현재 `ReceiptParseService.parse()` 결과를 실행
- per-image JSON annotation 저장
- 전체 `manifest.json` 생성

## 2. 생성된 위치

- `data/receipt_silver/jevi-silver-v0/manifest.json`
- `data/receipt_silver/jevi-silver-v0/annotations/*.json`

현재 생성 결과:
- 이미지 수: 11
- 총 item 수: 113
- review_required 이미지 수: 11
- failures: 0

## 3. Annotation 스키마

예시 구조:

```json
{
  "dataset_name": "jevi-silver-v0",
  "label_source": "silver-current-engine",
  "generated_at": "2026-04-16T04:25:19Z",
  "image": {
    "file_name": "img2.jpg",
    "source_path": "C:\\...\\img2.jpg"
  },
  "parser": {
    "engine_version": "receipt-engine-v2"
  },
  "expected": {
    "vendor_name": "세계1등 문이",
    "purchased_at": "2020-06-09",
    "ocr_texts": [],
    "items": [],
    "totals": {},
    "review_required": true,
    "review_reasons": ["unresolved_items"],
    "diagnostics": {}
  }
}
```

핵심:
- `expected`가 이후 비교의 기준이 된다.
- 즉, 지금 단계에서 "정답 JSON 스키마"는 현재 엔진이 뽑은 구조화 결과다.

## 4. 평가 스크립트

파일:
- `scripts/evaluate_receipt_silver_set.py`

실행 예시:

```powershell
python scripts/evaluate_receipt_silver_set.py `
  --manifest "C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\data\receipt_silver\jevi-silver-v0\manifest.json"
```

파서 수정 이후 재평가 현재 요약 결과:

```json
{
  "image_count": 11,
  "vendor_name_accuracy": 1.0,
  "purchased_at_accuracy": 1.0,
  "payment_amount_accuracy": 1.0,
  "item_name_f1_avg": 1.0
}
```

## 5. 현재 해석

흥미로운 점:
- refreshed silver set를 다시 생성한 뒤 순차 평가하면 전부 `1.0`으로 맞는다
- 직전 `2a4dd... -> 0.0`은 생성과 평가를 병렬로 돌리면서 old annotation을 읽은 탓이었다
- 즉, 현재 silver set 기준선은 정상적으로 재고정됐다

이 의미:
- silver set는 현재 파서 출력과 동기화된 회귀 기준선이다.
- 따라서 self-check 1.0은 정상이다.
- 절대 품질 평가는 별도로 봐야 한다.
  - 예를 들어 `165288...`는 아직 날짜 OCR이 비고, `img3.jpg`는 품목 중복/정규화 이슈가 남아 있다.
- silver set는 앞으로 parser를 바꿀 때 회귀 여부를 빠르게 확인하는 용도로 계속 유효하다.

## 6. 다음 단계

1. `jevi-silver-v0`에서 대표 5장 정도를 골라 수동 검수해 `golden-v0`로 승격
2. `2a4dd...jpg` 장문/밀집 케이스를 우선 분석
3. 날짜 OCR 약한 케이스와 vendor 후보 규칙을 분리 평가
4. alias/정규화와 false positive 제거를 계속 개선
5. 개선 전후를 `evaluate_receipt_silver_set.py`로 다시 비교
6. silver set self-check와 별도로 실사 대표 샘플(`165288...`)은 수동 확인 로그를 유지
   - 이유: self-check 1.0은 절대 품질이 아니라 현재 baseline 동기화 상태만 보여주기 때문
