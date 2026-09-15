import importlib.util
import http.client
import pathlib
import threading
import unittest.mock
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("codex_usage_monitor.py")
SPEC = importlib.util.spec_from_file_location("codex_usage_monitor", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class UsageMonitorTests(unittest.TestCase):
    def test_page_contains_usage_fields_and_escapes_dynamic_values(self):
        page = MODULE.INDEX_HTML
        self.assertIn("usedPercent", page)
        self.assertIn("rateLimitsByLimitId", page)
        self.assertIn("Credits 余额", page)
        self.assertIn("当前账号", page)
        self.assertIn("const esc =", page)

    def test_server_uses_read_only_rate_limit_method(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('self.request("account/rateLimits/read", None)', source)
        self.assertIn('self.request("account/read", {"refreshToken": False})', source)
        self.assertNotIn('request("account/rateLimitResetCredit/consume"', source)

    def test_account_response_exposes_only_display_fields(self):
        account = MODULE.normalize_account_result({
            "account": {
                "type": "chatgpt", "email": "user@example.com",
                "planType": "plus", "accessToken": "secret", "accountId": "hidden",
            },
            "requiresOpenaiAuth": True,
        })
        self.assertEqual(account, {
            "type": "chatgpt", "email": "user@example.com", "planType": "plus",
        })
        self.assertIsNone(MODULE.normalize_account_result({"account": None}))

    def test_normalizes_raw_rate_limit_response(self):
        result = MODULE.normalize_rate_limits_result({
            "rate_limit": {
                "primary_window": {
                    "used_percent": 27,
                    "limit_window_seconds": 18_000,
                    "resets_at": 123,
                },
                "plan_type": "plus",
            }
        })
        window = result["rateLimits"]["primary"]
        self.assertEqual(window["usedPercent"], 27)
        self.assertEqual(window["windowDurationMins"], 300)
        self.assertEqual(result["rateLimits"]["planType"], "plus")

    def test_rejects_silent_empty_response(self):
        with self.assertRaisesRegex(RuntimeError, "缺少 rateLimits"):
            MODULE.normalize_rate_limits_result({"ok": True})

    def test_refresh_keeps_last_successful_data_on_transient_failure(self):
        client = MODULE.AppServerClient("codex")
        account = {"type": "chatgpt", "email": "user@example.com", "planType": "plus"}
        previous = {"rateLimits": {"primary": {"usedPercent": 12}}}
        client.snapshot = {"account": account, "data": previous, "updatedAt": 100}
        with unittest.mock.patch.object(client, "request", side_effect=[
            {"account": account}, RuntimeError("proxy down")
        ]):
            client.refresh()
        self.assertEqual(client.snapshot["data"], previous)
        self.assertEqual(client.snapshot["updatedAt"], 100)
        self.assertTrue(client.snapshot["stale"])
        self.assertEqual(client.snapshot["warning"], "proxy down")

    def test_changed_account_does_not_keep_previous_usage(self):
        client = MODULE.AppServerClient("codex")
        client.snapshot = {
            "account": {"type": "chatgpt", "email": "old@example.com", "planType": "free"},
            "data": {"rateLimits": {"primary": {"usedPercent": 12}}},
            "updatedAt": 100,
        }
        with unittest.mock.patch.object(client, "request", side_effect=[
            {"account": {"type": "chatgpt", "email": "new@example.com", "planType": "plus"}},
            RuntimeError("proxy down"),
        ]):
            client.refresh()
        self.assertNotIn("data", client.snapshot)
        self.assertEqual(client.snapshot["account"]["email"], "new@example.com")

    def test_revoked_token_clears_old_account_and_requests_reconnect(self):
        client = MODULE.AppServerClient("codex")
        client.snapshot = {
            "account": {"type": "chatgpt", "email": "old@example.com", "planType": "free"},
            "data": {"rateLimits": {"primary": {"usedPercent": 12}}},
            "updatedAt": 100,
        }
        reconnect = unittest.mock.Mock()
        client.auto_reconnect = reconnect
        with unittest.mock.patch.object(client, "request", side_effect=[
            {"account": {"type": "chatgpt", "email": "old@example.com", "planType": "free"}},
            RuntimeError("401 Unauthorized: token_revoked"),
        ]):
            client.refresh()
        self.assertNotIn("data", client.snapshot)
        self.assertIsNone(client.snapshot["account"])
        reconnect.assert_called_once_with()

    def test_manual_refresh_requests_backend_reconnect(self):
        client = MODULE.AppServerClient("codex")
        reconnect = unittest.mock.Mock()
        server = MODULE.ThreadingHTTPServer(
            ("127.0.0.1", 0), MODULE.make_handler(client, reconnect)
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
            connection.request("POST", "/api/refresh")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn(b'"restarting": true', response.read())
            connection.close()
            reconnect.assert_called_once_with()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_proxy_validation_accepts_supported_urls(self):
        self.assertEqual(
            MODULE.validate_proxy_url(" http://127.0.0.1:7890 "),
            "http://127.0.0.1:7890",
        )
        self.assertEqual(
            MODULE.validate_proxy_url("socks5://localhost:1080"),
            "socks5://localhost:1080",
        )

    def test_proxy_validation_rejects_credentials_and_unknown_protocols(self):
        with self.assertRaisesRegex(ValueError, "用户名或密码"):
            MODULE.validate_proxy_url("http://user:secret@localhost:8080")
        with self.assertRaisesRegex(ValueError, "代理协议"):
            MODULE.validate_proxy_url("ftp://localhost:21")


if __name__ == "__main__":
    unittest.main()
