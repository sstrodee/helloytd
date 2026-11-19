from app.network import candidate_routes, parse_wininet_proxy


class TestParseWininetProxy:
    def test_disabled_proxy_is_ignored(self):
        assert parse_wininet_proxy(0, "127.0.0.1:8080") is None

    def test_bare_host_port_becomes_http_url(self):
        assert parse_wininet_proxy(1, "127.0.0.1:10809") == "http://127.0.0.1:10809"

    def test_per_protocol_list_prefers_https_entry(self):
        server = "http=127.0.0.1:8080;https=127.0.0.1:8443"
        assert parse_wininet_proxy(1, server) == "http://127.0.0.1:8443"

    def test_per_protocol_list_falls_back_to_http_entry(self):
        server = "http=127.0.0.1:8080;ftp=127.0.0.1:21"
        assert parse_wininet_proxy(1, server) == "http://127.0.0.1:8080"

    def test_socks_only_list_becomes_socks5_url(self):
        assert parse_wininet_proxy(1, "socks=127.0.0.1:1080") == "socks5://127.0.0.1:1080"

    def test_explicit_scheme_is_kept(self):
        assert parse_wininet_proxy(1, "http://proxy.local:3128") == "http://proxy.local:3128"

    def test_enabled_but_empty_server_is_ignored(self):
        assert parse_wininet_proxy(1, "") is None
        assert parse_wininet_proxy(1, None) is None


class TestCandidateRoutes:
    def test_without_hints_only_direct_is_tried(self):
        assert candidate_routes(None, set()) == [None]

    def test_system_proxy_is_tried_before_direct(self):
        assert candidate_routes("http://10.0.0.1:3128", set()) == ["http://10.0.0.1:3128", None]

    def test_open_local_ports_follow_in_known_priority(self):
        assert candidate_routes(None, {7890, 10809}) == [
            None,
            "http://127.0.0.1:10809",
            "http://127.0.0.1:7890",
        ]

    def test_unknown_open_ports_are_ignored(self):
        assert candidate_routes(None, {5040, 49664}) == [None]

    def test_system_proxy_matching_local_port_is_not_repeated(self):
        assert candidate_routes("http://127.0.0.1:10809", {10809}) == [
            "http://127.0.0.1:10809",
            None,
        ]
