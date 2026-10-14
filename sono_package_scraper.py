import os
import sys
import datetime
import requests
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경변수 로드 (sonopackage 봇 토큰 기본값 설정)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8967025162:AAGIYw6TnhlsgMtD-mmzzOOhRDbeRrXO7rg")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8784137781")
SONO_ID = os.getenv("SONO_ID", "p122568")
SONO_PW = os.getenv("SONO_PW", "park1202!")

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("텔레그램 토큰 또는 CHAT_ID가 설정되지 않았습니다.", flush=True)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            print(f"텔레그램 전송 실패: {resp.status_code} {resp.text}", flush=True)
        else:
            print("텔레그램 전송 성공", flush=True)
    except Exception as e:
        print(f"텔레그램 전송 예외: {e}", flush=True)

def scrape_all_packages():
    if not SONO_ID or not SONO_PW:
        print("SONO_ID 또는 SONO_PW가 설정되지 않았습니다.", flush=True)
        sys.exit(1)

    print(f"[{datetime.datetime.now()}] 소노호텔 패키지 전체 스크래핑 시작...", flush=True)
    all_packages = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # 1. 로그인
        print("1. 로그인 페이지 접속...", flush=True)
        page.goto("https://www.sonohotelsresorts.com/member/login")
        page.wait_for_selector("input#lginId", timeout=10000)
        page.fill("input#lginId", SONO_ID)
        page.fill("input#lginPw", SONO_PW)
        page.click("button.btn.xl.fill")
        page.wait_for_timeout(3000)

        # 2. 패키지 첫 페이지 이동
        print("2. 패키지 목록 페이지 접속...", flush=True)
        page.goto("https://www.sonohotelsresorts.com/reserve/package?page=1")
        try:
            page.wait_for_selector(".area-card-list", timeout=10000)
        except Exception:
            page.wait_for_timeout(4000)

        if page.locator("input#lginId").is_visible():
            msg = "소노호텔 로그인에 실패했습니다. (아이디/비밀번호를 확인해주세요)"
            print(msg, flush=True)
            send_telegram(f"🚨 <b>소노호텔 스크래핑 오류</b>\n{msg}")
            browser.close()
            sys.exit(1)

        # 3. 마지막 페이지 번호 확인
        max_page = 1
        dr_btn = page.locator("button.icon-arrow_dr")
        if dr_btn.count() > 0 and not dr_btn.is_disabled():
            dr_btn.click()
            page.wait_for_timeout(2000)
            page_numbers = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('.pageNo button'));
                return btns.map(b => parseInt(b.innerText.trim(), 10)).filter(n => !isNaN(n));
            }""")
            if page_numbers:
                max_page = max(page_numbers)
        print(f"3. 총 {max_page}개 페이지 확인 완료.", flush=True)

        # 4. 1페이지부터 max_page까지 순회하며 데이터 수집
        for page_num in range(1, max_page + 1):
            print(f"[{page_num}/{max_page}] 페이지 수집 중...", flush=True)
            page.goto(f"https://www.sonohotelsresorts.com/reserve/package?page={page_num}")
            try:
                page.wait_for_selector(".area-card-list a.box-card", timeout=8000)
            except Exception:
                page.wait_for_timeout(2500)

            # 패키지 카드 추출
            cards_data = page.evaluate("""() => {
                const items = [];
                const cards = document.querySelectorAll('.area-card-list a.box-card');
                cards.forEach(c => {
                    const brandEl = c.querySelector('li.brand-name');
                    const titEl = c.querySelector('li.tit');
                    const constituteEl = c.querySelector('li.constitute');
                    const dateEl = c.querySelector('li.date');
                    const priceEl = c.querySelector('li.price');
                    const href = c.getAttribute('href');

                    items.push({
                        brand: brandEl ? brandEl.innerText.replace(/\\s+/g, ' ').trim() : '',
                        title: titEl ? titEl.innerText.trim() : '',
                        constitute: constituteEl ? constituteEl.innerText.trim() : '',
                        date: dateEl ? dateEl.innerText.trim() : '',
                        price: priceEl ? priceEl.innerText.trim() : '',
                        link: href ? ('https://www.sonohotelsresorts.com' + href) : ''
                    });
                });
                return items;
            }""")

            if not cards_data:
                print(f"{page_num}페이지에서 카드를 찾지 못했습니다.", flush=True)
                break

            all_packages.extend(cards_data)
            print(f" -> {page_num}페이지: {len(cards_data)}개 수집 완료 (누적: {len(all_packages)}개)", flush=True)

        browser.close()

    return all_packages

def format_and_send(packages):
    if not packages:
        send_telegram("⚠️ 조회된 소노호텔 패키지가 없습니다.")
        return

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"🏨 <b>[소노호텔&리조트] 전체 패키지 안내</b>\n"
    header += f"📅 확인 시각: {now_str}\n"
    header += f"📦 총 <b>{len(packages)}개</b> 패키지가 검색되었습니다.\n\n"

    # 지역/리조트별 그룹화
    grouped = {}
    for p in packages:
        brand = p["brand"] if p["brand"] else "기타"
        main_brand = brand.split()[0] if brand else "기타"
        if main_brand not in grouped:
            grouped[main_brand] = []
        grouped[main_brand].append(p)

    # 메시지 묶음 만들기 (텔레그램 4096자 제한 고려하여 3000자 단위 분할)
    messages = []
    current_msg = header

    for brand_name, items in grouped.items():
        section_text = f"📍 <b>{brand_name}</b> ({len(items)}개)\n"
        for item in items:
            item_text = f"▪️ <b>{item['title']}</b>\n"
            if item['constitute']:
                item_text += f"   - 구성: {item['constitute']}\n"
            if item['date']:
                item_text += f"   - 기간: {item['date']}\n"
            if item['price']:
                item_text += f"   - 금액: <b>{item['price']}</b>\n"
            if item['link']:
                item_text += f"   - <a href='{item['link']}'>상세보기 바로가기</a>\n"
            item_text += "\n"

            if len(current_msg) + len(item_text) > 3000:
                messages.append(current_msg)
                current_msg = item_text
            else:
                current_msg += (section_text if section_text else "") + item_text
            section_text = ""

    if current_msg:
        messages.append(current_msg)

    # 전송
    total_parts = len(messages)
    print(f"총 {total_parts}개 메시지로 분할 전송 시작...", flush=True)
    for idx, msg in enumerate(messages, 1):
        if total_parts > 1:
            part_header = f"[{idx}/{total_parts}]\n"
            msg = part_header + msg
        send_telegram(msg)

def main():
    packages = scrape_all_packages()
    print(f"총 {len(packages)}개 패키지 수집 완료. 텔레그램 발송 시작...", flush=True)
    format_and_send(packages)
    print("전체 작업 완료!", flush=True)

if __name__ == "__main__":
    main()
