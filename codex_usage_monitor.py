#!/usr/bin/env python3
"""Small local dashboard for Codex account rate-limit usage."""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


APP_VERSION = "0.1.0"
POLL_SECONDS = 30


def proxy_config_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "codex-usage-monitor" / "proxy.json"


def validate_proxy_url(value: Any) -> str:
    proxy_url = str(value or "").strip()
    if not proxy_url:
        return ""
    if len(proxy_url) > 2048:
        raise ValueError("代理地址过长")
    parsed = urlsplit(proxy_url)
    if parsed.scheme not in {"http", "https", "socks5"}:
        raise ValueError("代理协议必须是 http、https 或 socks5")
    if not parsed.hostname:
        raise ValueError("代理地址缺少主机名")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("代理地址不能包含用户名或密码")
    try:
        parsed.port
    except ValueError as error:
        raise ValueError("代理端口无效") from error
    return proxy_url


def load_proxy_override() -> str | None:
    path = proxy_config_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return validate_proxy_url(payload.get("proxyUrl")) or None
    except FileNotFoundError:
        return None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def save_proxy_override(proxy_url: str) -> None:
    path = proxy_config_path()
    if not proxy_url:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"proxyUrl": proxy_url}, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def normalize_rate_limits_result(result: Any) -> dict[str, Any]:
    """Accept current app-server v2 data plus older/raw rate-limit field names."""
    if not isinstance(result, dict):
        raise RuntimeError("app-server 返回了空的用量响应")
    if isinstance(result.get("data"), dict):
        result = result["data"]
    if isinstance(result.get("rateLimits"), dict):
        return result

    legacy = result.get("rate_limits") or result.get("rate_limit")
    if not isinstance(legacy, dict):
        keys = ", ".join(sorted(map(str, result.keys()))) or "无字段"
        raise RuntimeError(f"app-server 用量响应缺少 rateLimits（收到：{keys}）")

    def window(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        return {
            "usedPercent": value.get("usedPercent", value.get("used_percent", 0)),
            "windowDurationMins": value.get(
                "windowDurationMins",
                value.get("window_duration_mins",
                          value.get("limit_window_seconds") / 60
                          if isinstance(value.get("limit_window_seconds"), (int, float)) else None),
            ),
            "resetsAt": value.get("resetsAt", value.get("resets_at")),
        }

    snapshot = {
        "limitId": legacy.get("limitId", legacy.get("limit_id", "codex")),
        "limitName": legacy.get("limitName", legacy.get("limit_name")),
        "primary": window(legacy.get("primary", legacy.get("primary_window"))),
        "secondary": window(legacy.get("secondary", legacy.get("secondary_window"))),
        "credits": legacy.get("credits"),
        "planType": legacy.get("planType", legacy.get("plan_type")),
        "rateLimitReachedType": legacy.get(
            "rateLimitReachedType", legacy.get("rate_limit_reached_type")
        ),
    }
    return {"rateLimits": snapshot, "rateLimitsByLimitId": {"codex": snapshot}}

INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Codex 用量</title>
  <style>
    :root { color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #101311; color: #eef2ee; min-height: 100vh; }
    main { width: min(880px, calc(100% - 32px)); margin: 0 auto; padding: 42px 0; }
    header { display:flex; justify-content:space-between; align-items:end; gap:16px; margin-bottom:24px; }
    h1 { margin:0; font-size:28px; letter-spacing:-.04em; }
    .muted { color:#9da69f; font-size:13px; }
    #status { display:flex; align-items:center; gap:7px; }
    #dot { width:8px; height:8px; border-radius:50%; background:#e9ad52; }
    #dot.live { background:#69d38b; box-shadow:0 0 12px #69d38b88; }
    .summary, .card { border:1px solid #303733; background:#181d1a; border-radius:16px; }
    .summary { display:grid; grid-template-columns:repeat(3,1fr); padding:18px; margin-bottom:16px; gap:16px; }
    .summary strong { display:block; margin-top:5px; font-size:18px; }
    #limits { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }
    .card { padding:18px; }
    .card h2 { font-size:16px; margin:0 0 16px; display:flex; justify-content:space-between; gap:12px; }
    .window { margin-top:14px; }
    .row { display:flex; justify-content:space-between; gap:12px; font-size:14px; margin-bottom:7px; }
    .bar { height:9px; overflow:hidden; background:#2b322e; border-radius:999px; }
    .bar > i { display:block; height:100%; background:#69d38b; border-radius:inherit; transition:width .35s ease; }
    .bar > i.warn { background:#e9ad52; } .bar > i.danger { background:#e06b65; }
    .error { border-color:#713d3a; color:#f2aaa4; padding:18px; }
    button { border:1px solid #3a433e; background:#222824; color:inherit; border-radius:9px; padding:7px 11px; cursor:pointer; }
    button:hover { background:#2b332e; }
    @media(max-width:600px){ .summary{grid-template-columns:1fr 1fr} header{align-items:start;flex-direction:column} }
  </style>
</head>
<body><main>
  <header><div><h1>Codex 用量</h1><div class="muted">来自本机 Codex app-server</div></div>
    <div><button id="refresh">立即刷新</button> <span id="status"><i id="dot"></i><span>连接中</span></span></div>
  </header>
  <section id="summary" class="summary"></section><section id="limits"></section>
</main>
<script>
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const duration = mins => mins == null ? '用量窗口' : mins >= 1440 ? `${Math.ceil(mins/1440)} 天窗口` : mins >= 60 ? `${Math.ceil(mins/60)} 小时窗口` : `${mins} 分钟窗口`;
const resetAt = seconds => seconds ? new Date(seconds*1000).toLocaleString() : '未知';
const windowHtml = w => { if (!w) return ''; const used=Math.max(0,Math.min(100,w.usedPercent??0)), remain=100-used;
  const tone=remain<=10?'danger':remain<=30?'warn':''; return `<div class="window"><div class="row"><span>${esc(duration(w.windowDurationMins))}</span><strong>剩余 ${remain}%</strong></div><div class="bar"><i class="${tone}" style="width:${remain}%"></i></div><div class="row muted"><span>已用 ${used}%</span><span>重置：${esc(resetAt(w.resetsAt))}</span></div></div>`; };
function render(payload){ const dot=document.querySelector('#dot'), status=document.querySelector('#status span');
  if(payload.error && !payload.data){ dot.className=''; status.textContent='读取失败'; document.querySelector('#summary').innerHTML=`<div>状态<strong>不可用</strong></div>`; document.querySelector('#limits').innerHTML=`<div class="card error">${esc(payload.error)}</div>`; return; }
  const result=payload.data; if(!result || !result.rateLimits){ render({error:'收到的用量数据结构无效，请重启监视器后重试'}); return; }
  const warning=payload.warning||payload.error||''; dot.className=warning?'':'live'; status.textContent=warning?'显示上次数据':'实时连接'; const base=result.rateLimits, credits=base.credits||{}, resets=result.rateLimitResetCredits;
  document.querySelector('#summary').innerHTML=`<div><span class="muted">套餐</span><strong>${esc(base.planType||'未知')}</strong></div><div><span class="muted">Credits 余额</span><strong>${credits.unlimited?'无限':esc(credits.balance??'—')}</strong></div><div><span class="muted">可用重置</span><strong>${esc(resets?.availableCount??'—')}</strong></div>`;
  const buckets=result.rateLimitsByLimitId&&Object.keys(result.rateLimitsByLimitId).length?result.rateLimitsByLimitId:{default:base};
  document.querySelector('#limits').innerHTML=(warning?`<div class="card error">暂时无法更新，正在保留上次成功数据：${esc(warning)}</div>`:'')+Object.entries(buckets).map(([id,item])=>`<article class="card"><h2><span>${esc(item.limitName||id)}</span><span class="muted">${esc(item.planType||'')}</span></h2>${windowHtml(item.primary)}${windowHtml(item.secondary)}${!item.primary&&!item.secondary?'<div class="muted">暂无窗口数据</div>':''}</article>`).join('');
}
async function refresh(){ try{const r=await fetch('/api/usage',{cache:'no-store'});render(await r.json())}catch(e){render({error:e.message})} }
document.querySelector('#refresh').onclick=()=>fetch('/api/refresh',{method:'POST'}).then(refresh);
const events=new EventSource('/events'); events.onmessage=e=>render(JSON.parse(e.data)); events.onerror=()=>{document.querySelector('#dot').className='';document.querySelector('#status span').textContent='正在重连'};
refresh();
</script></body></html>"""


class AppServerClient:
    def __init__(self, command: str, proxy_override: str | None = None) -> None:
        self.command = command
        self.proxy_override = proxy_override
        self.process: subprocess.Popen[str] | None = None
        self.pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self.lock = threading.Lock()
        self.next_id = 1
        self.snapshot: dict[str, Any] = {"error": "正在连接 Codex app-server"}
        self.subscribers: set[queue.Queue[dict[str, Any]]] = set()
        self.stopped = threading.Event()

    def start(self) -> None:
        child_environment = os.environ.copy()
        if self.proxy_override:
            for variable in (
                "http_proxy", "https_proxy", "all_proxy",
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
            ):
                child_environment[variable] = self.proxy_override
        self.process = subprocess.Popen(
            [self.command, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=child_environment,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.request("initialize", {
            "clientInfo": {"name": "codex-usage-monitor", "version": APP_VERSION},
            "capabilities": {"experimentalApi": True},
        })
        self.notify("initialized", {})
        self.refresh()
        threading.Thread(target=self._poll, daemon=True).start()

    def _write(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None or self.process.poll() is not None:
            raise RuntimeError("Codex app-server 未运行")
        with self.lock:
            self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any], timeout: float = 15) -> Any:
        with self.lock:
            request_id = self.next_id
            self.next_id += 1
            response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self.pending[request_id] = response_queue
        try:
            self._write({"id": request_id, "method": method, "params": params})
            try:
                response = response_queue.get(timeout=timeout)
            except queue.Empty as error:
                raise RuntimeError(f"app-server 请求超时：{method}") from error
            if "error" in response:
                error = response["error"]
                raise RuntimeError(error.get("message", str(error)))
            return response.get("result")
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"method": method, "params": params})

    def refresh(self) -> None:
        try:
            result = normalize_rate_limits_result(
                self.request("account/rateLimits/read", {})
            )
            self._publish({"data": result, "updatedAt": int(time.time())})
        except Exception as error:
            now = int(time.time())
            previous_data = self.snapshot.get("data")
            if isinstance(previous_data, dict):
                self._publish({
                    "data": previous_data,
                    "warning": str(error),
                    "stale": True,
                    "updatedAt": self.snapshot.get("updatedAt", now),
                    "lastAttemptAt": now,
                })
            else:
                self._publish({"error": str(error), "updatedAt": now})

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            request_id = message.get("id")
            if request_id is not None:
                with self.lock:
                    response_queue = self.pending.get(request_id)
                if response_queue is not None:
                    response_queue.put(message)
            elif message.get("method") == "account/rateLimits/updated":
                threading.Thread(target=self.refresh, daemon=True).start()
        if not self.stopped.is_set():
            self._publish({"error": "Codex app-server 已退出", "updatedAt": int(time.time())})

    def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        for _line in self.process.stderr:
            pass

    def _poll(self) -> None:
        while not self.stopped.wait(POLL_SECONDS):
            self.refresh()

    def _publish(self, payload: dict[str, Any]) -> None:
        self.snapshot = payload
        for subscriber in list(self.subscribers):
            try:
                subscriber.put_nowait(payload)
            except queue.Full:
                pass

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=2)
        self.subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        self.subscribers.discard(subscriber)

    def stop(self) -> None:
        self.stopped.set()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()


def make_handler(
    client: AppServerClient,
    restart_callback: Any,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _headers(self, content_type: str, length: int | None = None) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.end_headers()

        def _json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(HTTPStatus.OK)
            self._headers("application/json; charset=utf-8", len(body))
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                body = INDEX_HTML.encode()
                self.send_response(HTTPStatus.OK)
                self._headers("text/html; charset=utf-8", len(body))
                self.wfile.write(body)
            elif self.path == "/api/usage":
                self._json(client.snapshot)
            elif self.path == "/api/config":
                self._json({
                    "proxyUrl": load_proxy_override() or "",
                    "usesEnvironmentProxy": load_proxy_override() is None,
                })
            elif self.path == "/events":
                self.send_response(HTTPStatus.OK)
                self._headers("text/event-stream; charset=utf-8")
                subscriber = client.subscribe()
                try:
                    self.wfile.write(b": connected\n\n")
                    self.wfile.flush()
                    while True:
                        try:
                            payload = subscriber.get(timeout=20)
                            data = json.dumps(payload, ensure_ascii=False)
                            self.wfile.write(f"data: {data}\n\n".encode())
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    client.unsubscribe(subscriber)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/api/config":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 0 or length > 4096:
                        raise ValueError("配置请求过大")
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    proxy_url = validate_proxy_url(payload.get("proxyUrl"))
                    save_proxy_override(proxy_url)
                except (ValueError, json.JSONDecodeError) as error:
                    body = json.dumps({"error": str(error)}, ensure_ascii=False).encode()
                    self.send_response(HTTPStatus.BAD_REQUEST)
                    self._headers("application/json; charset=utf-8", len(body))
                    self.wfile.write(body)
                    return
                self._json({"ok": True, "restarting": True})
                restart_callback()
                return
            if self.path != "/api/refresh":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            threading.Thread(target=client.refresh, daemon=True).start()
            self._json({"ok": True})

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="在浏览器中实时显示 Codex 账户用量")
    parser.add_argument("--port", type=int, default=8765, help="本地监听端口（默认：8765）")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--codex", default=os.environ.get("CODEX_CLI_PATH", "codex"), help="Codex CLI 路径")
    args = parser.parse_args()
    command = shutil.which(args.codex) if os.path.sep not in args.codex else args.codex
    if not command or not os.path.isfile(command):
        parser.error(f"找不到 Codex CLI：{args.codex}")

    client = AppServerClient(command, load_proxy_override())
    try:
        client.start()
    except Exception as error:
        client.stop()
        print(f"启动失败：{error}", file=sys.stderr)
        return 1

    restart_lock = threading.Lock()
    restart_started = False

    def restart_self() -> None:
        nonlocal restart_started
        with restart_lock:
            if restart_started:
                return
            restart_started = True

        def perform_restart() -> None:
            time.sleep(0.3)
            client.stop()
            executable = os.path.abspath(__file__)
            os.execv(sys.executable, [sys.executable, executable, *sys.argv[1:]])

        threading.Thread(target=perform_restart, daemon=True).start()

    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port), make_handler(client, restart_self)
    )
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Codex 用量监视器：{url}")
    print("按 Ctrl+C 退出")
    if not args.no_open:
        threading.Timer(0.25, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        client.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
