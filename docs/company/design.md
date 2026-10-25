# 公司管理服务的边界与兼容性

管理 API 现在由 fanqisyx/rustdesk-server 维护，首版从客户端 v1.5.1-company.1 的已验证 management 实现原样引入；来源与兼容版本见 management/CLIENT_COMPATIBILITY.json。客户端仓库旧副本用于历史兼容，不在两处独立演进新 API。

管理进程处理账号、资产树、分组授权、单台分享、审计、一次性连接票据。原有 hbbs/hbbr 负责 ID 注册、穿透和中继，保持原路径。两套数据库独立：ID 注册不等于资产归属，不自动从 db_v2.sqlite3 导入授权。

公司版控制端申请绑定 challenge 的短时票据，再由新版被控端用逐台凭据向 API 核验；通过后继续原有密码／人工确认。公司账号令牌不传入 hbbs/hbbr。保持其协议不变，便于现有服务器增配和分批迁移。

新成员默认无权限。内部／外部分组支持后代继承，允许授权取并集；分享仅涉及单台设备，不能超过分享者当前直接权限，也不能经收到的分享链放大授权。目录与连接核验同时读取当前权限。已有会话不即时强制断开。

Windows 新增 rustdesk-management.exe、Caddy 与 WinSW 模板。安装脚本只操作 RustDeskCompanyAPI、RustDeskCompanyHTTPS 和对应防火墙规则；使用独立配置与数据目录，遇到端口或服务冲突报错，不停止未知服务。

固定公网 IPv4 配置显式请求 Let's Encrypt shortlived profile 并自动续期，API 只监听回环，不放宽客户端证书校验。签发和外网可达性必须在真实服务器验收。

已有文件只变更 README.md（公司版入口）和 .gitignore（排除构建产物及缓存）。Rust 源码、Cargo 依赖、共享子模块、旧 docker-compose.yml 及旧构建流水线均保持原值。新实现集中在 management、tools、docs/company 和独立公司版工作流。
