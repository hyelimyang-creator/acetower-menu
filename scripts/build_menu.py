"""
에이스타워 한식뷔페(카카오채널 _xoxcxcxen) 급식 데이터 생성 서비스.

브라이언씨의 gbsa-cafeteria-menu 크롤러와 같은 역할이지만, 이 채널은 카카오 JSON API가
있어서 Playwright(브라우저 렌더링)가 필요 없다. 훨씬 가볍다.

동작:
  1) 카카오 채널 posts JSON API에서 최근 글을 가져온다.
  2) 끼니별로 분류: 석식 = 텍스트 글(메뉴 그대로), 중식 = 사진 글(첫 장이 '오늘의 메뉴' 인쇄판).
  3) 중식 메뉴판이 이미지는 Google Gemini(gemini-2.5-flash)로 OCR해 텍스트로 만든다.
     (키는 GitHub Actions Secret의 GEMINI_API_KEY 하나만 사용 → 개인 앱은 키가 필요 없음)
  4) 기존 data/acetower.json과 병합(과거 날짜 보존)해 다시 저장한다.
     이미 중식 메뉴가 채워진 날짜는 Gemini를 다시 부르지 않는다(무료 할당량 절약).

출력 형식은 브라이언씨 archive.json과 동일해서, 지비 앱이 그대로 읽는다.

필요 환경변수: GEMINI_API_KEY  (GitHub Actions Secrets에 등록)
무료 키 발급: https://aistudio.google.com/apikey  (신용카드 불필요)
"""

import base64
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

CHANNEL_ID = "_xoxcxcxen"
LABEL = "에이스타워 한식뷔페"
KEY_NAME = "acetower"
POSTS_API = f"https://pf.kakao.com/rocket-web/web/profiles/{CHANNEL_ID}/posts?includePinnedPost=true"
CHANNEL_URL = f"https://pf.kakao.com/{CHANNEL_ID}/posts"
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_SYSTEM = "당신은 한국 구내식당 메뉴판 이미지를 읽어 메뉴 항목만 정확히 추출하는 도우미입니다. 이미지에 없는 메뉴를 추측해서 지어내지 마세요."
GEMINI_PROMPT = (
    "이 이미지는 어느 구내식당의 '오늘의 메뉴' 한 끼 메뉴판입니다. 메뉴 항목들을 이미지에 적힌 그대로 정확히 뽑아 "
    'JSON으로만 답하세요. 형식: {"items":["항목1","항목2"]}. '
    "제목('오늘의 메뉴')과 안내 문구는 제외하고 음식/메뉴 항목만 넣으세요."
)

KST = timezone(timedelta(hours=9))
WEEKDAY_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "acetower.json"


def parse_ymd(title: str, now: datetime):
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", title or "")
    if not m:
        return None
    month, dom = int(m.group(1)), int(m.group(2))
    year = now.year
    if now.month == 1 and month == 12:
        year -= 1
    elif now.month == 12 and month == 1:
        year += 1
    return f"{year:04d}-{month:02d}-{dom:02d}"


def meal_type(title: str):
    if re.search(r"석식|저녁", title or ""):
        return "dinner"
    if re.search(r"중식|점심", title or ""):
        return "lunch"
    return None


def fetch_posts():
    r = requests.get(POSTS_API, headers={"User-Agent": MOBILE_UA, "Referer": CHANNEL_URL}, timeout=20)
    r.raise_for_status()
    return r.json().get("items", []) or []


def first_image_url(item):
    media = item.get("media") or []
    for m in media:
        if m.get("type") == "image":
            return m.get("large_url") or m.get("xlarge_url") or m.get("url") or m.get("medium_url")
    return media[0].get("large_url") if media else None


def text_items(item):
    parts = item.get("contents") or []
    text = "\n".join(p.get("v", "") for p in parts if p.get("t") == "text")
    return [s.strip() for s in text.splitlines() if s.strip()]


def gemini_ocr_items(image_url: str, api_key: str):
    img = requests.get(image_url.replace("http://", "https://"),
                       headers={"User-Agent": MOBILE_UA, "Referer": "https://pf.kakao.com/"}, timeout=20)
    img.raise_for_status()
    b64 = base64.b64encode(img.content).decode("ascii")
    body = {
        "systemInstruction": {"parts": [{"text": GEMINI_SYSTEM}]},
        "contents": [{"parts": [
            {"text": GEMINI_PROMPT},
            {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    r = requests.post(GEMINI_URL, params={"key": api_key}, json=body, timeout=40)
    r.raise_for_status()
    data = r.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(text)
    return [str(s).strip() for s in parsed.get("items", []) if str(s).strip()]


def load_existing():
    try:
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def existing_lunch_items(archive, date_key):
    try:
        for g in archive[KEY_NAME]["days"][date_key]["lunch_groups"]:
            if g.get("group_name") == "중식" and g.get("items"):
                return g["items"]
    except Exception:
        pass
    return None


def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GEMINI_API_KEY 환경변수가 없습니다 (GitHub Actions Secret에 등록하세요).", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(KST)
    items = fetch_posts()
    print(f"가져온 글: {len(items)}개")

    # 끼니별 원자료 수집
    days = {}  # date -> {"lunch": {...}, "dinner": {...}}
    for it in items:
        meal = meal_type(it.get("title"))
        if not meal:
            continue
        key = parse_ymd(it.get("title"), now)
        if not key:
            continue
        slot = days.setdefault(key, {})
        if meal in slot:
            continue  # API는 최신순 → 같은 끼니는 먼저 나온 글 유지
        slot[meal] = {
            "text_items": text_items(it),
            "image": first_image_url(it),
            "permalink": it.get("permalink") or CHANNEL_URL,
        }

    archive = load_existing()
    node = archive.setdefault(KEY_NAME, {"label": LABEL, "post_url": CHANNEL_URL, "days": {}})
    node["label"] = LABEL
    out_days = node.setdefault("days", {})

    ocr_calls = 0
    for date_key in sorted(days):
        slot = days[date_key]
        lunch = slot.get("lunch")
        dinner = slot.get("dinner")

        # 중식: 텍스트가 있으면 그대로, 없으면 메뉴판 이미지 OCR (이미 채워진 날짜는 재OCR 안 함)
        lunch_items = []
        if lunch:
            if lunch["text_items"]:
                lunch_items = lunch["text_items"]
            else:
                prev = existing_lunch_items(archive, date_key)
                if prev:
                    lunch_items = prev
                elif lunch["image"]:
                    try:
                        lunch_items = gemini_ocr_items(lunch["image"], api_key)
                        ocr_calls += 1
                        print(f"  [{date_key}] 중식 OCR: {len(lunch_items)}개")
                    except Exception as e:
                        print(f"  [{date_key}] 중식 OCR 실패: {e}", file=sys.stderr)

        lunch_groups = []
        if lunch_items:
            lunch_groups.append({"group_name": "중식", "items": lunch_items})
        if dinner and dinner["text_items"]:
            lunch_groups.append({"group_name": "석식", "items": dinner["text_items"]})
        if not lunch_groups:
            continue

        d = datetime.strptime(date_key, "%Y-%m-%d")
        out_days[date_key] = {
            "date": date_key,
            "weekday_label": WEEKDAY_KR[d.weekday()],
            "is_holiday": False,
            "holiday_name": None,
            "lunch_groups": lunch_groups,
        }
        post_url = (lunch or dinner or {}).get("permalink") or CHANNEL_URL
        node["post_url"] = post_url

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {OUT_PATH}  (Gemini 호출 {ocr_calls}회, 총 {len(out_days)}일치)")


if __name__ == "__main__":
    main()
