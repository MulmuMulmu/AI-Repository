# v0.1 검증 기록

기준:
- 저장소: `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh`
- 비교 기준: `origin/main @ e3e375db71a25a613ade39b6ad2039ac0bc9eb99`

## 1. 테스트 검증

실행 명령:

```powershell
python -m pytest -q
```

실행 결과:

```text
........                                                                 [100%]
8 passed, 5 warnings in 1.48s
```

주의:
- 경고는 `python_multipart` pending deprecation과 FastAPI `on_event` deprecation이다.
- 현재 실패 테스트는 없다.

## 2. 샘플 OCR 연기 검증

실행 대상:
- `img2.jpg`
- `img3.jpg`
- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`

### warm-up / 처리 시간

실행 결과:

```text
warm_up_seconds = 11.095
img2.jpg = 4.174s
img3.jpg = 2.373s
SE-...jpg = 3.723s
```

해석:
- CPU 기준 cold start는 아직 무겁다.
- warm 상태에서는 Qwen 없이 2~4초대 처리다.
- 사용자 실시간 업로드 응답으로는 가능하지만, 여유가 큰 편은 아니다.

## 3. 샘플별 품질 결과

### `img2.jpg`

- `purchased_at`: `2020-06-09`
- `food_count`: `2`
- `review_required`: `true`
- `review_reasons`: `["unresolved_items"]`

대표 품목:
- `라라스윗)바널라파인트474 행상` / `6900`
- `라라스윗)초코파인트474m1` / `6900`

판단:
- 품목 블록은 잡지만 OCR 오독 alias 보정이 더 필요하다.

### `img3.jpg`

- `purchased_at`: `2015-01-20`
- `food_count`: `4`
- `review_required`: `true`
- `review_reasons`: `["unresolved_items"]`

대표 품목:
- `속이면한 누룸지` / `5600`
- `속이면한 누룸지` / `39200`
- `[(야] 7 -11,760` / `11760`
- `롯데앤디카페조릿 다크` / `4800`

판단:
- 날짜는 복원했지만 false positive 1건이 남아 있다.
- 숫자 줄 제거 규칙 강화가 필요하다.

### `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`

- `purchased_at`: `2023-11-25`
- `food_count`: `9`
- `review_required`: `true`
- `review_reasons`: `["total_mismatch", "unresolved_items"]`

대표 품목:
- `투썸딸기피지` / `2800`
- `허쉬쿠키앤크림` / `1600`
- `어쉬밀크클릿 [` / `1600`
- `허쉬쿠키앤초코` / `null`
- `호가든캔330ML` / `3500`

판단:
- item section 복원은 되었지만 총액 mismatch와 OCR 오독이 남아 있다.

## 4. 현재 남은 핵심 이슈

1. OCR alias / 정규화 사전 부족
2. 숫자 기반 false positive item 제거 부족
3. `SE` 유형 totals mismatch
4. Qwen을 동기 경로에 상시 붙이면 응답 지연 위험

## 5. 다음 권장 작업

1. `ocr_qwen/receipts.py`에서 false positive 제거 규칙 강화
2. `data/ingredient_alias.generated.json` 확장
3. `tests/test_receipt_quality_rules.py`에 totals mismatch 고정 케이스 추가
4. low-confidence item만 Qwen 보조로 제한
