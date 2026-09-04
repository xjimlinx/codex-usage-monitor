# Codex Usage Monitor for KDE Plasma

一个面向 KDE Plasma 6 的 Codex 用量监视器。任务栏组件显示当前 Codex 限额的剩余
百分比；点击后可以查看全部用量窗口、重置时间、Credits 余额和可用重置次数。

后端是一个零第三方 Python 依赖的本地服务。它通过 Codex CLI 的 app-server 协议读取
当前登录账户的用量，不需要 API Key，也不会解析网页或读取浏览器 Cookie。

## 功能

- Plasma 任务栏中显示主要限额窗口的剩余百分比
- 使用系统安装的 ChatGPT 应用图标，与组件列表和设置页保持一致
- 可在设置中动态调节任务栏紧凑视图的横向和纵向内边距
- 点击展开全部限额窗口、Credits、重置次数和重置时间
- 右键菜单支持立即更新用量数据
- 右键配置 5–3600 秒的界面刷新间隔
- 在配置页设置后端使用的 HTTP、HTTPS 或 SOCKS5 代理
- 监听 `account/rateLimits/updated`，并以 30 秒后端轮询兜底
- 短暂网络或代理故障时保留上一次成功数据，不让面板状态来回闪烁
- systemd 用户服务登录自启、失败自动重启
- 仅监听 `127.0.0.1`，不暴露到局域网
- 兼容当前 app-server v2 和较早的 rate-limit 字段格式

## 要求

- Linux、KDE Plasma 6、Python 3.10+
- 已安装并登录的 Codex CLI
- `systemd --user` 和 `kpackagetool6`

## 快速安装

```bash
git clone https://github.com/xjimlinx/codex-usage-monitor.git
cd codex-usage-monitor
bash install-user-service.sh
bash install-plasmoid.sh
```

进入 Plasma 任务栏编辑模式，选择“添加部件”，搜索“Codex 用量”。面板默认读取
<http://127.0.0.1:9000/api/usage>，后端服务只绑定回环地址。

## 独立运行后端

```bash
python3 codex_usage_monitor.py --port 9000
```

如果 `codex` 不在 `PATH`：

```bash
python3 codex_usage_monitor.py --codex /path/to/codex --port 9000
```

## 使用和配置

- 左键任务栏组件：展开用量详情
- 右键任务栏组件 →“立即更新”：立即重新读取用量
- 展开页面右上角：立即刷新
- 右键组件 →“配置 Codex 用量…”：设置界面刷新间隔
- 配置页“代理地址”：保存后后端自动重新连接；留空则使用 systemd 服务环境

服务管理：

```bash
systemctl --user status codex-usage-monitor.service
systemctl --user restart codex-usage-monitor.service
journalctl --user -u codex-usage-monitor.service -f
```

如果当前 shell 使用代理，安装器会把相关代理变量写入
`~/.config/codex-usage-monitor/environment`，权限设置为 `0600`。再次运行安装器可以同步
新的程序版本或代理设置。

## 数据流

```text
KDE Plasmoid
  → http://127.0.0.1:9000/api/usage
  → codex_usage_monitor.py
  → codex app-server --stdio
  → account/rateLimits/read
```

## 隐私和安全

- 不要求、保存或展示 OpenAI API Key
- 不读取浏览器 Cookie 或浏览器配置
- 不把账户用量写入磁盘
- 不提供消费 rate-limit reset credit 的操作
- HTTP 服务仅监听 `127.0.0.1`
- systemd 环境文件权限为 `0600`，并被 `.gitignore` 排除
- 自定义代理保存在本机 `~/.config/codex-usage-monitor/proxy.json`，权限为 `0600`
- 为避免凭据泄漏，代理 URL 不允许包含用户名或密码

用量数据仍由本机 Codex CLI 使用其已有登录状态获取。请不要把个人配置目录、环境文件、
日志或 Codex 登录文件提交到仓库。

## 卸载

```bash
bash uninstall-plasmoid.sh
bash uninstall-user-service.sh
```

## 开发与验证

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v
qmllint plasmoid/contents/ui/main.qml \
  plasmoid/contents/ui/configGeneral.qml \
  plasmoid/contents/config/config.qml
bash -n install-user-service.sh uninstall-user-service.sh \
  install-plasmoid.sh uninstall-plasmoid.sh
```

## License

[MIT](LICENSE)
