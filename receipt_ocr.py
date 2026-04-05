"""
PaddleOCR 기반 영수증 식품명 인식 시스템

영수증 이미지에서 텍스트를 감지/인식하고,
식품명을 추출하는 파이프라인을 제공합니다.
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
from paddleocr import PaddleOCR


FOOD_KEYWORDS = {
    # === 과일 ===
    "사과", "배", "포도", "딸기", "바나나", "귤", "오렌지", "수박", "참외", "복숭아",
    "감", "단감", "홍시", "곶감", "키위", "골드키위", "망고", "블루베리", "체리", "자몽",
    "레몬", "라임", "파인애플", "멜론", "천도복숭아", "자두", "살구", "앵두", "무화과",
    "석류", "유자", "한라봉", "천혜향", "레드향", "샤인머스캣", "거봉", "캠벨", "청포도",
    "아보카도", "코코넛", "패션프루츠", "용과", "리치", "두리안", "구아바", "대추",
    "건포도", "크랜베리", "산딸기", "라즈베리", "감귤", "밀감",

    # === 채소 ===
    "양파", "마늘", "감자", "고구마", "당근", "무", "배추", "양배추", "시금치", "상추",
    "깻잎", "파", "대파", "쪽파", "부추", "고추", "풋고추", "청양고추", "홍고추", "오이고추",
    "꽈리고추", "피망", "파프리카", "브로콜리", "콩나물", "숙주나물", "오이", "호박", "애호박",
    "단호박", "주키니", "가지", "토마토", "방울토마토", "대추토마토", "버섯", "팽이버섯",
    "새송이", "새송이버섯", "표고버섯", "느타리버섯", "양송이버섯", "목이버섯", "송이버섯",
    "셀러리", "아스파라거스", "비트", "래디시", "순무", "연근", "우엉", "도라지", "더덕",
    "콜라비", "케일", "루꼴라", "청경채", "적채", "치커리", "로메인", "미나리", "냉이",
    "달래", "씀바귀", "취나물", "고사리", "두릅", "참나물", "방풍나물", "머위", "곤드레",
    "쑥", "쑥갓", "열무", "총각무", "알타리", "비타민", "적양배추", "콜리플라워",
    "생강", "강황", "고춧잎", "미니양배추", "옥수수", "찰옥수수",

    # === 육류 (소) ===
    "소고기", "한우", "육우", "수입소", "호주산소", "미국산소",
    "등심", "안심", "채끝", "부채살", "살치살", "토시살", "갈비살", "꽃등심",
    "차돌박이", "업진살", "치마살", "양지", "사태", "우둔", "홍두깨",
    "갈비", "LA갈비", "꼬리", "설도", "목심",
    "불고기", "국거리", "장조림", "산적", "스테이크",

    # === 육류 (돼지) ===
    "돼지고기", "삼겹살", "오겹살", "대패삼겹", "목살", "앞다리", "뒷다리",
    "갈매기살", "항정살", "가브리살", "등갈비", "돼지갈비",
    "안심", "등심", "돈까스용", "제육용", "찌개용", "수육용",
    "족발", "보쌈", "편육",

    # === 육류 (닭/오리/기타) ===
    "닭고기", "닭가슴살", "닭다리", "닭날개", "닭봉", "닭안심", "닭정육",
    "통닭", "반마리", "닭볶음탕용", "닭갈비용", "백숙용",
    "오리고기", "오리훈제", "오리로스",
    "양고기", "램", "램찹", "양갈비",
    "곱창", "대창", "막창", "소곱창", "돼지곱창", "양",
    "메추리알",

    # === 수산물 (생선) ===
    "고등어", "갈치", "꽁치", "삼치", "조기", "민어", "도미", "광어", "우럭", "농어",
    "방어", "참돔", "볼락", "장어", "뱅어", "가자미", "서대", "아귀", "대구", "명태",
    "동태", "황태", "코다리", "북어", "홍어", "전어", "임연수", "은갈치",
    "연어", "훈제연어", "참치", "참치회", "다랑어",

    # === 수산물 (갑각류/연체류) ===
    "새우", "대하", "중하", "왕새우", "흰다리새우", "건새우",
    "오징어", "한치", "갑오징어", "꼴뚜기", "주꾸미", "낙지", "문어",
    "게", "꽃게", "대게", "킹크랩", "랍스터",
    "조개", "바지락", "모시조개", "백합", "가리비", "전복", "소라", "골뱅이",
    "굴", "홍합", "피조개", "키조개", "맛조개", "꼬막",

    # === 수산물 (건어물/해조류) ===
    "멸치", "건멸치", "볶음멸치", "포멸치",
    "김", "구운김", "조미김", "돌김", "파래김", "김자반",
    "미역", "건미역", "미역줄기", "다시마", "톳", "매생이", "파래", "청각",
    "오징어채", "쥐포", "황태채", "북어채", "건오징어",
    "어묵", "사각어묵", "꼬치어묵", "부산어묵",
    "맛살", "게맛살", "크래미",

    # === 유제품/계란 ===
    "우유", "저지방우유", "무지방우유", "딸기우유", "초코우유", "바나나우유",
    "두유", "검은콩두유", "아몬드밀크", "귀리우유", "오트밀크",
    "치즈", "슬라이스치즈", "모짜렐라", "체다치즈", "크림치즈", "스트링치즈",
    "버터", "무염버터", "가공버터", "마가린",
    "요구르트", "요거트", "그릭요거트", "떠먹는요거트", "마시는요거트",
    "생크림", "휘핑크림", "사워크림",
    "계란", "달걀", "유정란", "무항생제란", "구운계란", "메추리알",

    # === 두부/콩 제품 ===
    "두부", "순두부", "연두부", "부침두부", "찌개두부", "유부", "유부초밥",
    "콩", "검은콩", "서리태", "백태", "완두콩", "강낭콩", "병아리콩", "렌틸콩",
    "팥", "녹두", "땅콩", "호두", "아몬드", "캐슈넛", "피스타치오", "잣", "밤",
    "해바라기씨", "호박씨", "피칸",

    # === 쌀/곡류 ===
    "쌀", "백미", "현미", "잡곡", "찹쌀", "흑미", "오곡", "십곡",
    "보리", "보리쌀", "귀리", "오트밀", "퀴노아", "수수", "조", "기장",
    "밀가루", "강력분", "중력분", "박력분",
    "부침가루", "튀김가루", "빵가루", "전분", "감자전분", "옥수수전분",

    # === 면류 ===
    "라면", "신라면", "진라면", "삼양라면", "너구리", "안성탕면", "짜파게티",
    "불닭볶음면", "참깨라면", "컵라면",
    "국수", "소면", "중면", "칼국수", "우동", "메밀국수", "냉면", "비빔면",
    "파스타", "스파게티", "펜네", "마카로니", "퓨실리", "링귀네",
    "쌀국수", "당면", "잔치국수", "자장면",
    "떡", "떡국떡", "떡볶이떡", "송편", "인절미", "백설기", "가래떡",

    # === 빵/베이커리 ===
    "빵", "식빵", "모닝빵", "바게트", "크루아상", "베이글", "호밀빵", "통밀빵",
    "케이크", "롤케이크", "생크림케이크", "파운드케이크", "머핀", "스콘",
    "도넛", "와플", "핫도그빵", "햄버거빵", "피자도우",
    "또띠아", "난", "잉글리쉬머핀",

    # === 과자/간식 ===
    "과자", "초콜릿", "사탕", "젤리", "껌", "캔디",
    "감자칩", "포테이토칩", "새우깡", "양파링", "꼬깔콘", "칙촉",
    "포카칩", "프링글스", "오감자", "눈을감자", "허니버터칩",
    "초코파이", "오레오", "칸쵸", "빼빼로", "에이스", "마가렛트",
    "건빵", "크래커", "비스킷", "쿠키",
    "아이스크림", "아이스바", "빙과", "빙수",
    "견과바", "에너지바", "시리얼바", "그래놀라",

    # === 조미료/양념/소스 ===
    "간장", "양조간장", "진간장", "국간장", "맛간장",
    "된장", "쌈장", "청국장",
    "고추장", "초고추장", "태양초고추장",
    "식초", "현미식초", "사과식초", "발사믹",
    "소금", "천일염", "꽃소금", "맛소금", "히말라야소금",
    "설탕", "흑설탕", "백설탕", "황설탕",
    "참기름", "들기름", "식용유", "카놀라유", "올리브유", "포도씨유", "해바라기유",
    "고춧가루", "후추", "깨", "통깨", "들깨", "참깨",
    "마요네즈", "케첩", "머스터드", "핫소스", "칠리소스", "굴소스",
    "카레", "카레가루", "카레분말",
    "미림", "맛술", "요리당", "물엿", "올리고당", "꿀", "조청", "매실청",
    "쯔유", "폰즈", "간장소스", "데리야끼",
    "다시다", "소고기다시다", "멸치다시다", "치킨스톡", "쇠고기스톡",
    "MSG", "미원", "감치미",
    "드레싱", "참깨드레싱", "시저드레싱", "오리엔탈드레싱",
    "바비큐소스", "돈까스소스", "스테이크소스", "우스터소스",
    "토마토소스", "파스타소스", "크림소스", "알리오올리오",
    "쌈무", "초생강", "후리가게",

    # === 음료 ===
    "커피", "원두", "믹스커피", "캡슐커피", "아메리카노", "라떼",
    "녹차", "홍차", "보이차", "루이보스", "허브차", "캐모마일", "페퍼민트",
    "보리차", "옥수수수염차", "현미차", "결명자차", "둥굴레차",
    "주스", "오렌지주스", "포도주스", "사과주스", "토마토주스", "야채주스",
    "콜라", "사이다", "환타", "스프라이트", "밀키스", "갈아만든배", "2프로",
    "탄산수", "생수", "이온음료", "게토레이", "파워에이드", "포카리스웨트",
    "에너지드링크", "레드불", "핫식스", "몬스터",
    "식혜", "수정과", "매실음료", "알로에음료", "비타민워터",

    # === 주류 ===
    "맥주", "카스", "하이트", "테라", "클라우드", "필스너",
    "소주", "참이슬", "처음처럼", "진로", "새로",
    "와인", "레드와인", "화이트와인", "로제", "스파클링",
    "막걸리", "생막걸리", "탁주",
    "위스키", "브랜디", "보드카", "진", "럼", "사케", "청하", "백세주",

    # === 즉석식품/가공식품 ===
    "만두", "물만두", "군만두", "찐만두", "교자만두", "왕만두", "김치만두", "고기만두",
    "피자", "냉동피자", "또띠아피자",
    "햄버거", "치킨너겟", "닭강정",
    "햄", "슬라이스햄", "런천미트", "스팸",
    "소시지", "비엔나소시지", "프랑크소시지", "핫도그",
    "베이컨", "훈제오리", "훈제닭가슴살",
    "치킨", "떡볶이", "김밥", "유부초밥",
    "즉석밥", "컵밥", "볶음밥", "덮밥", "비빔밥",
    "국", "찌개", "된장찌개", "김치찌개", "순두부찌개", "미역국",
    "카레", "짜장", "짬뽕", "탕수육",

    # === 냉동식품 ===
    "냉동밥", "냉동볶음밥", "냉동만두", "냉동피자",
    "냉동새우", "냉동오징어", "냉동생선", "냉동닭가슴살",
    "냉동채소", "냉동과일", "냉동딸기", "냉동블루베리", "냉동망고",
    "감자튀김", "치즈스틱", "돈까스", "탕수육",

    # === 통조림/캔 ===
    "참치캔", "동원참치", "사조참치", "꽁치캔", "골뱅이캔",
    "햄통조림", "스팸", "리챔",
    "옥수수캔", "콩통조림", "토마토캔",
    "과일캔", "복숭아캔", "파인애플캔",

    # === 김치/절임/반찬 ===
    "김치", "배추김치", "총각김치", "깍두기", "열무김치", "갓김치", "파김치",
    "물김치", "백김치", "동치미", "보쌈김치",
    "장아찌", "단무지", "오이소박이", "피클", "올리브",
    "젓갈", "새우젓", "멸치젓", "오징어젓", "명란젓", "창란젓", "어리굴젓",

    # === 시리얼/잼/스프레드 ===
    "시리얼", "콘프레이크", "그래놀라", "뮤즐리", "오트밀",
    "잼", "딸기잼", "블루베리잼", "포도잼", "사과잼", "마멀레이드",
    "땅콩버터", "누텔라", "초코스프레드",

    # === 영양제/건강식품 ===
    "홍삼", "인삼", "흑마늘", "프로폴리스",
    "비타민", "유산균", "프로바이오틱스", "오메가3", "루테인", "칼슘",
    "선식", "미숫가루", "율무", "칡",
}

NON_FOOD_KEYWORDS = [
    "비닐", "봉투", "장바구니", "영수증", "카드", "현금", "합계", "부가세", "과세", "면세",
    "전화", "주소", "대표", "사업자", "등록", "번호", "거래", "승인", "일시",
    "단말기", "가맹점", "결제", "할인", "포인트", "적립", "잔액", "회원",
    "세금", "부가", "총액", "소계", "변경", "반품", "교환", "감사",
    "매장", "점포", "지점", "본점", "고객", "안내", "문의", "택배",
    "화장지", "티슈", "휴지", "세제", "세탁", "샴푸", "린스", "치약", "칫솔",
    "건전지", "전구", "테이프", "접착", "쓰레기",
]


class ReceiptOCR:
    """PaddleOCR 기반 영수증 식품명 인식 클래스"""

    def __init__(self, lang: str = "korean", use_gpu: bool = False):
        # PaddleOCR 3.x: device 사용, 문서 기울기/펴기는 영수증에선 보통 불필요해 속도 위해 끔
        device = "gpu" if use_gpu else "cpu"
        self.ocr = PaddleOCR(
            lang=lang,
            use_textline_orientation=True,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            device=device,
        )

    def read_image(self, image_path: str) -> np.ndarray:
        """이미지 파일을 읽어 numpy 배열로 반환"""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")
        return img

    def preprocess_image(self, img: np.ndarray) -> np.ndarray:
        """영수증 이미지 전처리 (대비 향상, 노이즈 제거)"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        denoised = cv2.fastNlMeansDenoising(enhanced, h=10)
        result = cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
        return result

    def run_ocr(self, image_path: str, preprocess: bool = True) -> List[Dict]:
        """
        이미지에서 OCR을 수행하여 텍스트와 위치 정보를 반환합니다.

        Returns:
            [{"text": "인식된 텍스트", "confidence": 신뢰도, "box": [[x1,y1], ...]}, ...]
        """
        img = self.read_image(image_path)
        if preprocess:
            img = self.preprocess_image(img)

        raw = self.ocr.predict(img)
        return self._normalize_predict_output(raw)

    @staticmethod
    def _normalize_predict_output(raw: List) -> List[Dict]:
        """PaddleOCR 3.x(OCRResult)와 2.x(박스+튜플) 형식을 공통 구조로 변환."""
        if not raw:
            return []
        first = raw[0]
        ocr_lines: List[Dict] = []

        # PaddleOCR 3.x + PaddleX: dict-like OCRResult
        if hasattr(first, "__getitem__") and "rec_texts" in first:
            texts = first["rec_texts"]
            scores = first["rec_scores"]
            boxes = first["rec_boxes"]
            for i, text in enumerate(texts):
                box_arr = np.asarray(boxes[i])
                if box_arr.shape == (4,):
                    x1, y1, x2, y2 = [float(x) for x in box_arr.flat]
                    poly = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                elif box_arr.shape == (4, 2):
                    poly = box_arr.astype(float).tolist()
                else:
                    poly = box_arr.astype(float).tolist()
                ocr_lines.append({
                    "text": str(text).strip(),
                    "confidence": round(float(scores[i]), 4),
                    "box": poly,
                })
            ocr_lines.sort(key=lambda x: x["box"][0][1])
            return ocr_lines

        # PaddleOCR 2.x
        for line in first:
            box, (text, confidence) = line[0], line[1]
            ocr_lines.append({
                "text": str(text).strip(),
                "confidence": round(float(confidence), 4),
                "box": box,
            })
        ocr_lines.sort(key=lambda x: x["box"][0][1])
        return ocr_lines

    def extract_food_names(self, ocr_lines: List[Dict], min_confidence: float = 0.6) -> List[Dict]:
        """
        OCR 결과에서 식품명을 추출합니다.

        두 가지 방식으로 식품명 판별:
        1. 사전 기반 매칭: FOOD_KEYWORDS에 포함된 단어 탐지
        2. 패턴 기반: 가격 패턴(숫자+원) 옆의 텍스트를 식품 후보로 판단
        """
        food_items = []
        price_pattern = re.compile(r"[\d,]+\s*원?$")

        for line in ocr_lines:
            text = line["text"]
            confidence = line["confidence"]

            if confidence < min_confidence:
                continue

            if any(kw in text for kw in NON_FOOD_KEYWORDS):
                continue

            matched_foods = [kw for kw in FOOD_KEYWORDS if kw in text]
            if matched_foods:
                food_items.append({
                    "name": text,
                    "matched_keywords": matched_foods,
                    "confidence": confidence,
                    "method": "keyword",
                    "box": line["box"],
                })
                continue

            text_clean = re.sub(r"[\d,.\s원개kg]+$", "", text).strip()
            if (
                text_clean
                and len(text_clean) >= 2
                and not text_clean.isdigit()
                and price_pattern.search(text)
            ):
                food_items.append({
                    "name": text_clean,
                    "matched_keywords": [],
                    "confidence": confidence,
                    "method": "pattern",
                    "box": line["box"],
                })

        return food_items

    def analyze_receipt(self, image_path: str) -> dict:
        """
        영수증 이미지를 분석하여 전체 OCR 결과와 식품명 목록을 반환합니다.

        Returns:
            {
                "image_path": str,
                "all_texts": [{"text": ..., "confidence": ...}, ...],
                "food_items": [{"name": ..., "confidence": ..., "method": ...}, ...],
                "food_count": int
            }
        """
        ocr_lines = self.run_ocr(image_path)
        food_items = self.extract_food_names(ocr_lines)

        return {
            "image_path": str(image_path),
            "all_texts": [
                {"text": l["text"], "confidence": l["confidence"]}
                for l in ocr_lines
            ],
            "food_items": food_items,
            "food_count": len(food_items),
        }

    def visualize_result(self, image_path: str, result: dict, output_path: Optional[str] = None):
        """OCR 결과를 이미지 위에 시각화합니다."""
        import matplotlib.pyplot as plt
        from matplotlib import font_manager

        img = cv2.cvtColor(self.read_image(image_path), cv2.COLOR_BGR2RGB)

        fig, ax = plt.subplots(1, figsize=(12, 16))
        ax.imshow(img)

        for item in result["food_items"]:
            box = np.array(item["box"])
            rect = plt.Polygon(box, fill=False, edgecolor="red", linewidth=2)
            ax.add_patch(rect)
            ax.text(
                box[0][0], box[0][1] - 5,
                item["name"],
                fontsize=10,
                color="red",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7),
            )

        ax.set_axis_off()
        ax.set_title(f"식품 {result['food_count']}개 감지", fontsize=14)
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            print(f"결과 이미지 저장: {output_path}")
        else:
            plt.show()
        plt.close()


def main():
    if len(sys.argv) < 2:
        print("사용법: python receipt_ocr.py <영수증_이미지_경로> [--visualize] [--qwen]")
        print("예시:   python receipt_ocr.py receipt.jpg")
        print("        python receipt_ocr.py receipt.jpg --visualize")
        print("        python receipt_ocr.py receipt.jpg --qwen   # Qwen으로 상품명 보정(환경변수 설정 필요)")
        return

    image_path = sys.argv[1]
    visualize = "--visualize" in sys.argv
    use_qwen = "--qwen" in sys.argv

    ocr = ReceiptOCR()
    result = ocr.analyze_receipt(image_path)

    print("\n" + "=" * 50)
    print(" 영수증 OCR 분석 결과 (PaddleOCR)")
    print("=" * 50)

    print(f"\n[전체 인식 텍스트] ({len(result['all_texts'])}줄)")
    print("-" * 50)
    for item in result["all_texts"]:
        conf_bar = "*" * int(item["confidence"] * 10)
        print(f"  {item['text']:<30s}  ({item['confidence']:.2f}) {conf_bar}")

    print(f"\n[추출된 식품명] ({result['food_count']}개)")
    print("-" * 50)
    for i, food in enumerate(result["food_items"], 1):
        method_tag = "사전" if food["method"] == "keyword" else "패턴"
        print(f"  {i}. {food['name']:<25s}  [{method_tag}]  (신뢰도: {food['confidence']:.2f})")
        if food["matched_keywords"]:
            print(f"     매칭 키워드: {', '.join(food['matched_keywords'])}")

    print("=" * 50)

    if use_qwen:
        try:
            from qwen_receipt_assistant import QwenReceiptAssistant, print_refined_summary

            assistant = QwenReceiptAssistant()
            refined = assistant.refine_analysis(result)
            result["qwen_refined"] = {k: v for k, v in refined.items() if k != "raw_text"}
            print_refined_summary(refined)
        except ImportError as e:
            print(f"\n[Qwen 보조 생략] {e}")
        except ValueError as e:
            print(f"\n[Qwen 보조 생략] {e}")
        except Exception as e:
            print(f"\n[Qwen 보조 오류] {e}")

    if visualize:
        output_path = str(Path(image_path).stem) + "_result.png"
        ocr.visualize_result(image_path, result, output_path)


if __name__ == "__main__":
    main()
