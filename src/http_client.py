import ssl
import socket
import http.client
import urllib.parse
from typing import Tuple, Optional, Dict

class HttpClientError(Exception):
    """Base exception for client errors."""
    pass

class HttpRedirectError(HttpClientError):
    """Raised when max redirects are exceeded."""
    pass

def create_ssl_context() -> ssl.SSLContext:
    """Creates a secure SSL context."""
    return ssl.create_default_context()

def request(
    method: str,
    url: str,
    body: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 10,
    max_redirects: int = 5
) -> Tuple[int, Dict, str]:
    """
    Performs an HTTP/HTTPS request with strict security controls.
    Returns (status_code, response_headers, response_body).
    """
    if headers is None:
        headers = {}
    
    # Default User-Agent to avoid being blocked or fingerprinted easily
    if "User-Agent" not in headers:
        headers["User-Agent"] = "InHouseHttpClient/1.0"

    parsed_url = urllib.parse.urlparse(url)
    
    if parsed_url.scheme not in ("http", "https"):
        raise HttpClientError(f"Unsupported scheme: {parsed_url.scheme}")

    current_url = url
    redirects = 0

    while True:
        parsed = urllib.parse.urlparse(current_url)
        is_https = parsed.scheme == "https"
        
        # Extract host and path
        host = parsed.hostname
        port = parsed.port or (443 if is_https else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"

        conn = None
        try:
            # Use context manager to ensure connection closure
            if is_https:
                conn = http.client.HTTPSConnection(host, port=port, timeout=timeout, context=create_ssl_context())
            else:
                conn = http.client.HTTPConnection(host, port=port, timeout=timeout)

            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            
            # Handle Redirects
            if response.status in (301, 302, 303, 307, 308):
                if redirects >= max_redirects:
                    raise HttpRedirectError(f"Max redirects ({max_redirects}) exceeded")
                
                location = response.getheader("Location")
                if not location:
                    raise HttpClientError("Redirect with no Location header")
                
                # Resolve relative redirects
                current_url = urllib.parse.urljoin(current_url, location)
                
                # Per RFC, 303 means switch to GET
                if response.status == 303:
                    method = "GET"
                    body = None
                
                redirects += 1
                # Read response to allow connection reuse/close
                response.read()
                continue

            # Success or Non-Redirect Error
            resp_body = response.read().decode("utf-8", errors="ignore")
            resp_headers = dict(response.getheaders())
            return response.status, resp_headers, resp_body

        except (socket.timeout, socket.error, http.client.HTTPException) as e:
            raise HttpClientError(f"Network error: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass