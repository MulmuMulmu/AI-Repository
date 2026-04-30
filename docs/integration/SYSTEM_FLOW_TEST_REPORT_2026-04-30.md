# System Flow Test Report 2026-04-30

## Scope

This report checks whether the current user app, backend, admin web, and AI services connect as one service flow.

Primary flows:

- User receipt upload -> backend OCR analyze -> AI OCR -> backend OCR persistence -> admin OCR review
- User OCR/manual ingredient confirmation -> backend user ingredient save -> user ingredient list
- User ingredient list -> recipe recommendation request -> backend adapter -> AI recommendation
- Admin web -> backend admin APIs -> OCR/reports/statistics/user management

## Findings And Fixes

### Receipt OCR To Admin Review

Status: fixed.

Before this pass, the backend returned AI OCR results but did not persist the receipt image or OCR items for admin review.

Current flow:

1. User app calls `POST /ingredient/analyze` with multipart `image`.
2. Backend validates `Authorization`.
3. Backend calls AI OCR `POST /ai/ocr/analyze`.
4. Backend uploads the receipt image to GCP Storage under `ocr/{userId}/{date}/...`.
5. Backend saves `Ocr` with user, image URL, purchase time, create time.
6. Backend saves extracted food items as `OcrIngredient`.
7. Admin web reads them through `/admin/ocr/list`, `/admin/ocr/one`, and `/admin/ocr/one/ingredients`.

Verified by backend tests:

- `OcrServiceTest.analyzeAndSavePersistsReceiptImageAndRecognizedItemsForAdminReview`
- `OcrControllerTest.analyzeReceiptWrapsAiResultWithBackendEnvelope`

### OCR Multi-Item Confirmation

Status: fixed in user app.

Before this pass, the user app took only the first OCR item and discarded the rest before the confirmation screen.

Current flow:

1. `ReceiptLoadingScreen` passes all `food_items` to `DirectInput`.
2. `DirectInputScreen` shows detected items as selectable chips.
3. User can edit item name, expiration date, and category per item.
4. User can remove a wrongly recognized item or add a missing item.
5. Save sends the full confirmed list to backend.

### User Ingredient Save Contract

Status: fixed in user app.

Backend `POST /ingredient/input` expects `List<UserIngredientInputRequest>`.

Before this pass, the user app sent a single JSON object.

Current flow:

```json
[
  {
    "ingredient": "우유",
    "expirationDate": "2026-05-03",
    "category": "유제품"
  }
]
```

The app now uses `createIngredients()` and always sends an array.

### User Ingredient List Contract

Status: fixed in user app.

Backend `GET /ingredient/all/my` expects a `sort` string shaped like `date&ascending`.

Before this pass, the user app omitted `sort`, so backend validation could reject the request.

Current request:

```http
GET /ingredient/all/my?sort=date%26ascending
```

`%26` is required so the backend receives one `sort` value, not a second query parameter.

## Verification Commands

Backend:

```powershell
.\gradlew.bat test
```

Result: passed.

AI:

```powershell
python -m pytest -q
```

Result: `212 passed, 5 warnings`.

User app:

```powershell
npx expo export --platform web --output-dir .tmp-flow-export
```

Result: passed. Temporary export directory was removed after verification.

Admin web:

```powershell
npx vite build --debug
```

Result: passed. Vite warns that Node.js `22.11.0` is below the recommended `22.12+` for the installed Vite version.

Note: `npm run build` returned exit code `1` without an error body in this shell, while direct `npx vite build --debug` completed successfully. Treat this as an environment/npm wrapper issue unless reproduced with full error output.

## Remaining Risks

- Full live E2E with real MySQL, GCP Storage credentials, and running AI containers was not executed in this pass.
- User ingredient saving still depends on the backend `Ingredient` master table containing the normalized ingredient names returned by AI OCR.
- Recipe recommendation currently uses frontend-provided candidate recipes in the app flow. If backend later owns recipe candidates fully, the frontend request can be simplified.
- Admin OCR image display depends on the uploaded GCP object being publicly readable or served through an accessible URL.

## Current System Flow Verdict

The previously disconnected OCR path is now connected from user upload to admin review data. The ingredient confirmation path now preserves all OCR items and matches the backend list-save contract. The remaining validation should be a live smoke test with real service processes and credentials.
