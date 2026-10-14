import os
import sys
import datetime
import requests
from playwright.sync_api import sync_playwright
import google.generativeai as genai
from dotenv import load_dotenv

# .env 파일 로드 (로컬 실행 시)
load_dotenv()

# 환경변수 로드
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SONO_ID = os.getenv("SONO_ID")
SONO_PW = os.getenv("SONO_PW")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("텔레그램 토큰이 설정되지 않았습니다.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    resp = requests.post(url, json=payload)
    print(f"텔레그램 전송 결과: {resp.status_code}")

def send_telegram_photo(photo_path, caption=""):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, files={"photo": f})
    except Exception as e:
        print(f"사진 전송 오류: {e}")

def parse_with_gemini(raw_text):
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY가 없습니다. 원본 텍스트 일부를 반환합니다.")
        return raw_text[:1000]

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')

    prompt = f"""
    아래는 소노호텔 패키지 안내 웹페이지의 텍스트 데이터입니다.
    이 데이터에서 패키지 상품들을 찾아 다음 형식으로 보기 좋게 정리해주세요:

    - 지역: [지역명]
    - 예약기간: [예약기간]
    - 패키지 이름: [패키지명]
    - 패키지 구성내용: [구성내용]
    - 금액: [금액]

    데이터에서 추출할 수 있는 최대한 많은 패키지를 정리해주세요.
    텍스트에 해당 내용이 부족하다면, 파악 가능한 정보만이라도 추출해주세요.

    [원본 텍스트 시작]
    {raw_text[:20000]}
    [원본 텍스트 끝]
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Gemini API 호출 중 오류: {e}")
        return "데이터를 가져왔지만 정리에 실패했습니다. 구조 확인이 필요합니다."

def main():
    if not SONO_ID or not SONO_PW:
        msg = "SONO_ID 또는 SONO_PW가 설정되지 않았습니다. .env 파일 또는 GitHub Secrets를 확인하세요."
        print(msg)
        send_telegram(f"🚨 소노호텔 스크래핑 오류\n{msg}")
        sys.exit(1)

    print(f"[{datetime.datetime.now()}] 소노호텔 패키지 스크래핑 시작...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # 1. 로그인 페이지 접속
        print("로그인 페이지 접속 중...")
        page.goto("https://www.sonohotelsresorts.com/member/login", wait_until="networkidle")

        # 2. 아이디/비번 입력 및 로그인 버튼 클릭
        page.fill("input#lginId", SONO_ID)
        page.fill("input#lginPw", SONO_PW)
        page.click('button.btn.xl.fill')

        # 3. 로그인 처리 대기
        page.wait_for_timeout(3000)

        # 4. 패키지 페이지 접속
        print("패키지 페이지로 이동 중...")
        page.goto("https://www.sonohotelsresorts.com/reserve/package?page=1", wait_until="networkidle")
        page.wait_for_timeout(5000)  # 데이터 로딩 대기

        # 5. 로그인 실패 감지
        if page.locator("input#lginId").is_visible():
            msg = "소노호텔 로그인에 실패했습니다. (아이디/비밀번호 오류 또는 방화벽 차단)"
            print(msg)
            page.screenshot(path="error.png")
            send_telegram_photo("error.png", f"🚨 소노호텔 스크래핑 오류\n{msg}\n현재 화면 상태입니다.")
            browser.close()
            sys.exit(1)

        print("텍스트 추출 및 Gemini를 통한 정보 정리 중...")
        # 불필요한 스크립트, 스타일 태그 제외하고 텍스트만 추출
        raw_text = page.evaluate("document.body.innerText")
        browser.close()

    # Gemini로 정보 파싱
    parsed_result = parse_with_gemini(raw_text)

    # 6. 텔레그램 전송
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    final_message = f"🏨 <b>소노호텔 패키지 정보 ({current_time})</b>\n\n{parsed_result}"

    # 텔레그램 메시지 4096자 제한 처리
    if len(final_message) > 4096:
        chunks = [final_message[i:i+4096] for i in range(0, len(final_message), 4096)]
        for chunk in chunks:
            send_telegram(chunk)
    else:
        send_telegram(final_message)

    print("스크래핑 및 텔레그램 전송 완료!")

if __name__ == "__main__":
    main()
