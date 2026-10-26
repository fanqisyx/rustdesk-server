# Windows 10：为现有 hbbs/hbbr 增加公司管理服务

适用环境：已有 hbbs.exe／hbbr.exe、固定公网 IPv4、暂时没有域名。使用本仓库的 **Windows 管理扩展 ZIP**，无需安装 Python 或 Docker。本包不含 hbbs/hbbr；这两项服务继续使用原安装、原端口和原密钥。

服务器最终运行：原有 hbbs、原有 hbbr、新增 RustDeskCompanyAPI、新增 RustDeskCompanyHTTPS。远控客户端 EXE 不能替代管理 API。

推荐下载 v1.1.17-company.2 的 Setup.exe 双击安装，在向导中填写公网 IPv4 和管理员密码。默认安装目录为 C:\Program Files\RustDesk Company Server，开始菜单和 Windows 应用列表提供说明书及卸载入口；卸载保留 data。配套六页中文 PDF 在 Release 中可单独下载。以下继续说明手动 ZIP 方式，核心服务和检查要求相同。

## 1. 升级前确认

在公司服务器的管理员 PowerShell 中检查：

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -in @('hbbs.exe', 'hbbr.exe') } |
  Select-Object Name, ExecutablePath, ProcessId
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in @(80, 443, 21114) } |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

保存原服务启动方式、配置和密钥备份，不重新生成 id_ed25519／id_ed25519.pub，私钥不发给别人。旧数据库使用 SQLite 在线备份，或在维护窗口停服务后复制完整数据目录再启动。新管理服务使用独立 data/management.sqlite3，不修改或自动导入旧 db_v2.sqlite3；收藏、密码及 ID 注册记录不自动转换为资产权限。

若 80/443 已有 IIS 或其他代理，勿停止未知服务。可复用原代理并手动部署 API，不运行默认双服务安装脚本。若 21114 占用，需同时调整 API 服务 XML、Caddy 上游和健康检查端口。

## 2. 下载并安装新增服务

在 [本仓库 Releases](https://github.com/fanqisyx/rustdesk-server/releases) 下载 `rustdesk-server-company-windows-x86_64-v1.1.17-company.2.zip`，对照同版本 SHA256SUMS 校验。将解压后的完整目录放到 C:\RustDesk-Management，使 rustdesk-management.exe 就在该目录，旁边有 windows 和 licenses 子目录。不要覆盖旧 hbbs/hbbr 安装目录。

在管理员 PowerShell 执行，示例 IP 必须替换为自己的真实固定公网 IPv4：

```powershell
Set-Location C:\RustDesk-Management
.\windows\Install-Management.ps1 -PublicIp '203.0.113.10' -WhatIf
.\windows\Install-Management.ps1 -PublicIp '203.0.113.10'
```

加 -WhatIf 只检查文件／冲突并显示计划，不安装服务或改配置。实际执行会交互创建 admin，密码至少 12 位，无默认密码。若下载脚本被 Windows 锁定，先核对来源与内容，再按公司脚本策略解除锁定或仅在当前 PowerShell 进程允许执行，勿全局关闭策略。

脚本检查端口与服务冲突，以 LocalService 运行两个新增服务，设为自动启动、失败重启，授予本包读取执行及数据目录写入权限，并只新增 Caddy 的 TCP 80/443 防火墙规则。需要统一管理防火墙时加 -SkipFirewall 并自行放行。脚本不停止、替换或重新配置 hbbs/hbbr。

失败会报出步骤，保留已有数据，不自动覆盖服务。部分安装失败时，先查看 Get-Service 和 data/logs，停止／卸载两个新增服务后修复再装，勿删除数据库。若已有管理数据库，脚本不会重置管理员密码，需确认原管理员账号可用。

## 3. 仅公网 IP 的 HTTPS

Let's Encrypt 自 2026 年已公开提供 IP 证书，使用 shortlived profile，有效期约六天。包内 Caddy 2.11.7 显式使用公共签发方并自动续期，default_sni 用于不携带 SNI 的 IP 客户端。

- 公网 TCP 80/443 必须到达这台服务器；IP 在路由器上时增加对应映射，运营商也须允许入站验证。
- 服务器需能出站访问证书签发服务。API 21114 只监听 127.0.0.1，不映射公网。
- 持续运行服务器、关闭自动睡眠、保留 data/caddy，并保持续期验证端口可达。
- 运营商封锁验证端口时，此方案无法签发，需调整网络或另选验证方式；不能用明文登录或关闭客户端证书校验解决。

安装后检查：

```powershell
Get-Service RustDeskCompanyAPI, RustDeskCompanyHTTPS
Invoke-RestMethod http://127.0.0.1:21114/healthz
```

再用外网设备访问 https://自己的公网IP/healthz 和管理台首页，确认有效、可信且匹配 IP 的证书。服务 Running、本地健康检查成功均不代表公网签发成功。日志在 data/logs；Caddy 管理接口已关闭，改配置后使用 windows\rdm-https-service.exe restart。

## 4. 两台电脑试点，再逐批迁移

1. 保留旧客户端、配置、原 ID／中继地址和公钥，先升级一台控制电脑、一台被控电脑，使用 [客户端 v1.5.1-company.1](https://github.com/fanqisyx/rustdesk/releases/tag/v1.5.1-company.1) 的 Flutter 原生版，不使用 Sciter。
2. 两端 ID／中继地址继续填原值；控制端公司账号服务填 https://自己的公网IP，注册或登录。新注册默认无设备权限。
3. 管理员在网页创建内部／外部分组，登记升级后被控电脑实际显示的 ID，保存只显示一次的设备独立凭据。
4. 在被控电脑系统服务实际读取的 RustDesk2.toml 现有 [options] 段添加以下键，再重启该电脑的 RustDesk 服务。服务账户与普通用户配置位置可能不同。

```toml
[options]
enterprise-server = 'https://自己的公网IP'
enterprise-device-token = 'rd_device_替换成这台设备的独立凭据'
```

5. 管理员为账号授权分组，需要分享时同时授予 share 和对应操作权限；控制端刷新「设备组」再连接，设备密码／人工确认继续有效。
6. 验证合法连接、越权拒绝、单台分享及撤销、服务重启后登录，再逐批升级其他电脑。

受管端拒绝旧控制端和无公司票据的连接。旧被控端继续使用旧密码规则，仅隐藏目录不能使其受管。公司版被控端配置未完成会拒绝连接，因此不要盲目升级唯一远程入口，先保留现场或其他已验证的维护方式。撤权不即时断开已建立会话，Web 远控和 Sciter 登录暂不支持。

## 5. 更新与回退

更新管理服务前停止两个新服务，备份整个 data（含存在时的 SQLite WAL 文件及 Caddy 存储），更新程序但保留实际配置与数据，再启动。schema v2 回退旧程序需要恢复升级前备份，不能用空 data 覆盖生产数据。

试点失败可仅撤销新增服务：

```powershell
Set-Location C:\RustDesk-Management
.\windows\rdm-https-service.exe stop
.\windows\rdm-api-service.exe stop
.\windows\rdm-https-service.exe uninstall
.\windows\rdm-api-service.exe uninstall
```

以上不操作 hbbs/hbbr，不删除数据。停止管理服务会使已受管电脑拒绝新的公司连接。客户端回退需恢复旧程序及配置，并明确设备暂时退出集中授权；不要删除旧 RustDesk 防火墙规则。

## 源码与验证范围

源码仍可用 Python 3.11+ 按上级 README 运行，API 与发布 EXE 一致；Windows 打包脚本是 tools/build_management_windows.ps1，自动服务安装要求完整发布 ZIP。

目标公司实际服务安装、公网签发、路由映射及双机远控须在目标环境验收。构建、独立 EXE HTTP 和 CI 服务检查的实际结果见管理源码或发布包中的 VALIDATION.md。

来源：[IP 证书](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)、[Caddy ACME profile](https://caddyserver.com/docs/caddyfile/directives/tls)、[Caddy Windows 服务](https://caddyserver.com/docs/running#windows-service)、[WinSW 配置](https://github.com/winsw/winsw/blob/v2.12.0/doc/xmlConfigFile.md)。
