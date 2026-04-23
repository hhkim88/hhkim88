"""
네이버 블로그 OAuth 2.0 인증 — 최초 1회 실행하여 refresh_token 발급

사용법:
  1. .env에 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 설정
  2. 네이버 개발자 센터에서 콜백 URL을 http://localhost:8080/callback 으로 등록
  3. python scripts/naver_blog_oauth.py
  4. 출력된 NAVER_REFRESH_TOKEN 을 .env에 복사
"""
import os
import secrets
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
CALLBACK_URL = "http://localhost:8080/callback"
STATE = secrets.token_urlsafe(16)

received_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global received_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        received_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>인증 완료! 터미널로 돌아가세요.</h2>")

    def log_message(self, *args):
        pass


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("[오류] NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 을 .env에 설정하세요")
        return

    auth_url = (
        "https://nid.naver.com/oauth2.0/authorize"
        f"?response_type=code&client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(CALLBACK_URL)}&state={STATE}"
    )

    print(f"\n브라우저에서 아래 URL을 열어 네이버 로그인 및 권한 동의를 완료하세요:\n\n{auth_url}\n")

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()  # 콜백 1회만 처리

    if not received_code:
        print("[오류] 인증 코드를 받지 못했습니다.")
        return

    resp = httpx.post("https://nid.naver.com/oauth2.0/token", data={
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": CALLBACK_URL,
        "code": received_code,
        "state": STATE,
    })

    data = resp.json()
    if "error" in data:
        print(f"[오류] 토큰 발급 실패: {data}")
        return

    refresh_token = data.get("refresh_token", "")
    access_token = data.get("access_token", "")

    print("\n=== 발급 완료 ===")
    print(f"access_token  : {access_token}")
    print(f"refresh_token : {refresh_token}")
    print(f"\n.env 파일에 아래 줄을 추가하세요:\nNAVER_REFRESH_TOKEN={refresh_token}\n")


if __name__ == "__main__":
    main()
