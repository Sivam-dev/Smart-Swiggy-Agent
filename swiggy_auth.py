import json
import os
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import OAuthClientMetadata, OAuthClientInformationFull, OAuthToken

REDIRECT_URI = "http://127.0.0.1:8765/callback"
TOKEN_FILE = ".swiggy_tokens.json"


class FileTokenStorage(TokenStorage):
    async def get_tokens(self):
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE) as f:
                return OAuthToken(**json.load(f))
        return None

    async def set_tokens(self, tokens: OAuthToken):
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens.model_dump(), f)

    async def get_client_info(self):
        return None

    async def set_client_info(self, client_info: OAuthClientInformationFull):
        pass


_auth_code = {"code": None, "state": None}

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        _auth_code["code"] = query.get("code", [None])[0]
        _auth_code["state"] = query.get("state", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Login successful! You can close this tab.")

    def log_message(self, format, *args):
        pass

async def _redirect_handler(auth_url: str):
    print(f"Opening browser for Swiggy login:\n{auth_url}")
    webbrowser.open(auth_url)



async def _callback_handler():
    server = HTTPServer(("127.0.0.1", 8765), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    thread.join()
    return _auth_code["code"], _auth_code["state"]

def create_oauth_provider(server_url: str = "https://mcp.swiggy.com"):
    storage = FileTokenStorage()
    client_metadata = OAuthClientMetadata(
        redirect_uris=[REDIRECT_URI],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        client_name="My Nutrition Agent",
        scope="mcp:tools mcp:resources mcp:prompts",
    )
    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=_redirect_handler,
        callback_handler=_callback_handler,
        timeout=120.0,
    )