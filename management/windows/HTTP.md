# 无证书 HTTP 模式

使用服务端 `v1.1.17-company.3` 的 **HTTP-Setup.exe**；普通 Setup.exe 仍是原 HTTPS 模式。无需域名和证书，不使用 80/443，默认独立 TCP 21114，可自定义端口。HTTP 会明文传输密码、登录令牌、设备凭据和连接票据，链路窃听或篡改可能使权限被冒用；需要保密时使用 HTTPS 或受保护的 VPN 网络。

## 安装

仅有旧 hbbs/hbbr 的 Windows x64 服务器：双击 HTTP-Setup.exe，选择专用空目录，填写实际公网 IP、端口、admin 密码。向导只检查所选端口，创建开机自启 `RustDeskCompanyAPI`，监听 `0.0.0.0:所选端口`，新增针对本应用和所选端口的防火墙规则。原 hbbs/hbbr 不改动；不创建 HTTPS 服务。

已装公司管理扩展时，先停止新增管理服务、备份整个 data，再卸载旧管理扩展。在空目录安装 HTTP 包后，停止新 API、恢复旧 data，再启动 API。不要删除旧库或向非空目录覆盖安装。仅恢复 data，不用旧服务 XML 覆盖新 HTTP XML。

手动 ZIP 方式在管理员 PowerShell 执行：

```powershell
Set-Location C:\RustDesk-Management
.\windows\Install-HttpManagement.ps1 -PublicIp '203.0.113.10' -HttpPort 21114 -WhatIf
.\windows\Install-HttpManagement.ps1 -PublicIp '203.0.113.10' -HttpPort 21114
```

把示例 IP 替换为真实 IP。如果公网 IP 在路由器上，只需把所选 TCP 端口映射到服务器。Windows 防火墙、上级防火墙或云安全组也需允许此端口。不要添加 80/443 映射。

```powershell
Get-Service RustDeskCompanyAPI
Invoke-RestMethod http://127.0.0.1:21114/healthz
```

再用内网和外网设备打开 `http://自己的公网IP:21114/healthz` 与管理台首页，使用 admin 登录；新用户可注册，默认没有设备权限。

## 客户端

控制端及被控端均安装 `v1.5.1-company.2` 或后续支持 HTTP 的公司版。旧 `company.1` 不支持公网 HTTP。

控制端登录／注册填写 `http://自己的公网IP:21114` 并勾选「允许此服务器使用明文 HTTP」。登录成功后只记住所选地址及端口；HTTPS 仍校验证书，所有公司请求仍不跟随重定向。

被控端在系统服务实际读取的 RustDesk2.toml 现有 `[options]` 段添加：

```toml
[options]
enterprise-server = 'http://自己的公网IP:21114'
enterprise-http-origin = 'http://自己的公网IP:21114'
enterprise-device-token = 'rd_device_该设备独立凭据'
```

两个地址必须一致（协议、主机、端口，无末尾斜线）；自定义端口须同步替换。重启被控端 RustDesk 服务，再按原流程登记设备、授权或分享。原 ID／中继地址和公钥继续使用旧值。

## 卸载及备份

备份前停止 API，复制完整 data（包括存在时的 WAL），再启动 API。使用开始菜单或 Windows 应用列表中的卸载入口，会删除本应用服务和对应 HTTP 防火墙规则、保留 data；旧 hbbs/hbbr 不受影响。手动包可运行 `windows\Uninstall-Management.ps1` 移除管理服务和规则。
