# RustDesk 公司管理服务端

本 fork 在原有 hbbs／hbbr 旁增加自建公司账号、设备分组、访问权限、单台设备分享和审计，与 [fanqisyx/rustdesk 客户端 v1.5.1-company.2](https://github.com/fanqisyx/rustdesk/releases/tag/v1.5.1-company.2) 配套，不依赖 RustDesk Server Pro。

当前服务端版本 **v1.1.17-company.3（预发布）**，管理 API 0.1.0、schema v2。新增无需证书、不占用 80/443 的 **HTTP-Setup.exe**，默认独立 TCP 21114，可自定义；须配套客户端 v1.5.1-company.2。HTTP 明文传输密码和令牌，配置与升级见 [HTTP 说明](management/windows/HTTP.md)。原 Setup.exe 保留原 HTTPS 方式。

## 已有 Windows 10 + hbbs.exe／hbbr.exe

### 无证书 HTTP 独立端口方式

在 Releases 下载 **HTTP-Setup.exe**，双击填写公网 IP、HTTP 端口和管理员密码。仅新增 API 服务并放行所选 TCP 端口（默认 21114），不占用 80/443。使用客户端 company.2，登录时勾选允许明文 HTTP；被控端须设置同值 enterprise-http-origin。完整步骤见 [HTTP 安装与配置](management/windows/HTTP.md)。已有管理扩展先备份 data、卸载，在空目录安装后恢复 data；仅有旧 hbbs/hbbr 时直接新增安装。

### 原 HTTPS 方式

在 [本仓库 Releases](https://github.com/fanqisyx/rustdesk-server/releases) 下载 **Setup.exe**，双击后填写公网 IPv4 和管理员密码，保留现有 hbbs／hbbr。中文 PDF 说明书可单独下载，也内置于安装包。默认安装到 C:\Program Files\RustDesk Company Server，卸载保留数据库和证书。

需要手动部署时下载 Windows 公司管理扩展 ZIP，解压到独立目录，再在管理员 PowerShell 执行：

```powershell
Set-Location C:\RustDesk-Management
.\windows\Install-Management.ps1 -PublicIp '替换为自己的固定公网IPv4'
```

管理包包含独立 EXE、HTTPS 和 Windows 服务工具，无需另装 Python／Docker。固定公网 IP 可申请公共 HTTPS 证书，需要 TCP 80/443 公网可达并保持自动续期。先验证 HTTPS，再以两台电脑试点纳管。

[Windows 安装及回退](management/windows/README.md) · [中文 PDF 说明书](docs/company/RustDesk-Windows-Server-Manual-zh-CN.pdf) · [权限与分享](management/README.md) · [设计与兼容性](docs/company/design.md) · [验证记录](management/VALIDATION.md) · [版本说明](docs/company/v1.1.17-company.3.md)

旧被控端不会只因更换服务器就执行公司授权，需安装配套客户端并配置设备凭据。撤权不即时断开已有会话，Web 远控／Sciter 登录暂不支持。本版新增管理进程，不改变已有 hbbs/hbbr 的网络行为、数据库或密钥路径。

## 上游 RustDesk Server Program

[![build](https://github.com/rustdesk/rustdesk-server/actions/workflows/build.yaml/badge.svg)](https://github.com/rustdesk/rustdesk-server/actions/workflows/build.yaml)

[**Download**](https://github.com/rustdesk/rustdesk-server/releases)

[**Manual**](https://rustdesk.com/docs/en/self-host/)

[**Configuration & environment variables**](docs/environment-variables.md)

[**FAQ**](https://github.com/rustdesk/rustdesk/wiki/FAQ)

[**How to migrate OSS to Pro**](https://rustdesk.com/docs/en/self-host/rustdesk-server-pro/installscript/#convert-from-open-source)

Self-host your own RustDesk server, it is free and open source.

> [!IMPORTANT]
> **Need more features?** [RustDesk Server Pro](https://rustdesk.com/pricing.html) might suit you better.
>
> **Want to develop your own server?** Start with [rustdesk-server-demo](https://github.com/rustdesk/rustdesk-server-demo), a simpler starting point than this repository.

## How to build manually

```bash
cargo build --release
```

Three executables will be generated in target/release.

- hbbs - RustDesk ID/Rendezvous server
- hbbr - RustDesk relay server
- rustdesk-utils - RustDesk CLI utilities

You can find updated binaries on the [Releases](https://github.com/rustdesk/rustdesk-server/releases) page.

## Configuration

`hbbs` and `hbbr` can be configured with command-line flags, environment
variables, or an `.env` / config file. Run `hbbs --help` or `hbbr --help` to see
the available flags.

The most common options:

| Option | Flag | Env var | Applies to | Purpose |
| --- | --- | --- | --- | --- |
| Key | `-k` | `KEY` | hbbs, hbbr | `hbbs` loads/generates one by default |
| Bind address | `-b` | `BIND` | hbbs, hbbr | Local IP address to listen on (default: all interfaces; requires 1.1.17+) |
| Port | `-p` | `PORT` | hbbs, hbbr | Listening port (hbbs `21116`, hbbr `21117`) |
| Relay servers | `-r` | `RELAY-SERVERS` | hbbs | Override when the relay uses a different address or a non-standard port |
| Force relay | — | `ALWAYS_USE_RELAY` | hbbs | `Y` disables direct connections |
| Log level | — | `RUST_LOG` | hbbs, hbbr | e.g. `debug` (default `info`) |

See **[docs/environment-variables.md](docs/environment-variables.md)** for the
full list of variables, the file/flag/env precedence rules, database and relay
bandwidth tuning, Docker image variables, and examples.

## Installation

Please follow this [doc](https://rustdesk.com/docs/en/self-host/rustdesk-server-oss/)
