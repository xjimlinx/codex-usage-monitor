import importlib.util
import pathlib
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
        self.assertIn("const esc =", page)

    def test_server_uses_read_only_rate_limit_method(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('self.request("account/rateLimits/read", {})', source)
        self.assertNotIn('request("account/rateLimitResetCredit/consume"', source)

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


if __name__ == "__main__":
    unittest.main()
