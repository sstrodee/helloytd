"""Поиск маршрута до YouTube: системный прокси, напрямую или локальный вход VPN-клиента.

VPN-клиенты в TUN-режиме часто пускают «системный» трафик к YouTube напрямую,
где его режет DPI, а браузер ходит через свой локальный прокси. Поэтому
маршрут не угадываем, а проверяем: первый, по которому YouTube ответил, и берём.
"""

import socket

# Локальные входы популярных VPN-клиентов, в порядке проверки.
LOCAL_PROXY_CANDIDATES = (
    (10809, "http"),    # v2rayN и прочие xray-клиенты: HTTP
    (10808, "socks5"),  # v2rayN и прочие xray-клиенты: SOCKS
    (2080, "http"),     # sing-box, NekoBox: mixed
    (7890, "http"),     # Clash, mihomo: mixed
    (7897, "http"),     # Clash Verge: mixed
    (12334, "http"),    # Hiddify: mixed
    (1080, "socks5"),   # классический SOCKS
)
PROBE_URL = "https://www.youtube.com/generate_204"
_INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def parse_wininet_proxy(enabled, server):
    """Прокси из настроек Windows в виде URL, либо None если он выключен."""
    if not enabled or not server or not server.strip():
        return None
    server = server.strip()
    if "=" not in server:
        return server if "://" in server else f"http://{server}"

    # Формат «http=host:port;https=host:port;socks=host:port».
    entries = {}
    for chunk in server.split(";"):
        scheme, _, address = chunk.partition("=")
        if address.strip():
            entries[scheme.strip().lower()] = address.strip()
    for scheme in ("https", "http"):
        if scheme in entries:
            return f"http://{entries[scheme]}"
    if "socks" in entries:
        return f"socks5://{entries['socks']}"
    return None


def candidate_routes(system_proxy, open_ports):
    """Маршруты в порядке проверки; None означает «напрямую»."""
    routes = [system_proxy] if system_proxy else []
    routes.append(None)
    for port, scheme in LOCAL_PROXY_CANDIDATES:
        url = f"{scheme}://127.0.0.1:{port}"
        if port in open_ports and url not in routes:
            routes.append(url)
    return routes


def read_system_proxy():
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _INTERNET_SETTINGS) as key:
            enabled = _registry_value(key, "ProxyEnable", 0)
            server = _registry_value(key, "ProxyServer", "")
    except OSError:
        return None
    return parse_wininet_proxy(enabled, server)


def _registry_value(key, name, default):
    import winreg

    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def open_local_ports(ports, timeout=0.3):
    found = set()
    for port in ports:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout):
                found.add(port)
        except OSError:
            pass
    return found


def probe(route, timeout=6.0):
    """True, если YouTube отвечает по этому маршруту.

    Проверяем сетевым стеком самого yt-dlp — он умеет SOCKS и ходит ровно
    так же, как потом пойдёт скачивание. Пустая строка в proxy — «напрямую»,
    без оглядки на переменные окружения.
    """
    from yt_dlp import YoutubeDL

    params = {"quiet": True, "no_warnings": True, "socket_timeout": timeout, "proxy": route or ""}
    try:
        with YoutubeDL(params) as ydl, ydl.urlopen(PROBE_URL) as response:
            return response.status in (200, 204)
    except Exception:
        return False


def detect_route(timeout=6.0):
    """(маршрут, доступен ли YouTube). Маршрут None — напрямую."""
    open_ports = open_local_ports(port for port, _ in LOCAL_PROXY_CANDIDATES)
    for route in candidate_routes(read_system_proxy(), open_ports):
        if probe(route, timeout):
            return route, True
    return None, False
