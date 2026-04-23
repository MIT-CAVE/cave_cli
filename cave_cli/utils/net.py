import re
import socket

from cave_cli.utils.constants import IP_PORT_RE


def is_port_available(port: int) -> bool:
    """
    Usage:

    - Checks if a local TCP port is available for binding

    Requires:

    - ``port``:
        - Type: int
        - What: The port number to check

    Returns:

    - ``available``:
        - Type: bool
        - What: True if the port is available, False if in use
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def find_open_port(start: int = 8000) -> int:
    """
    Usage:

    - Finds the next available TCP port starting from the given port

    Optional:

    - ``start``:
        - Type: int
        - What: The port number to start searching from
        - Default: 8000

    Returns:

    - ``port``:
        - Type: int
        - What: The first available port found
    """
    port = start
    while port < 65535:
        if is_port_available(port):
            return port
        port += 1
    raise RuntimeError("No open ports found")


def parse_ip_port(addr: str) -> tuple[str, int] | None:
    """
    Usage:

    - Parses and validates an IP:port address string

    Requires:

    - ``addr``:
        - Type: str
        - What: The address string in IP:port format

    Returns:

    - ``result``:
        - Type: tuple[str, int] | None
        - What: A tuple of (ip, port) if valid, or None if invalid
    """
    if not IP_PORT_RE.match(addr):
        return None
    ip_match = re.search(r"([0-9]{1,3}\.)+[0-9]{1,3}", addr)
    port_match = re.search(r"(?<=:)\d{4,}", addr)
    if ip_match and port_match:
        return ip_match.group(0), int(port_match.group(0))
    return None
