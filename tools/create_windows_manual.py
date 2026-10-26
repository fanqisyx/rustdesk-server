"""Generate the Chinese server deployment manual with embedded Windows fonts."""
import argparse
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak,
                               Table, TableStyle, KeepTogether)

ROOT = Path(__file__).resolve().parents[1]
TAG = (ROOT / "COMPANY_RELEASE").read_text().strip()
pdfmetrics.registerFont(TTFont("CN", "C:/Windows/Fonts/msyh.ttc"))
pdfmetrics.registerFont(TTFont("CNBold", "C:/Windows/Fonts/msyhbd.ttc"))
pdfmetrics.registerFontFamily("CN", normal="CN", bold="CNBold", italic="CN", boldItalic="CNBold")

styles = {
    "title": ParagraphStyle("Title", fontName="CNBold", fontSize=23, leading=32, spaceAfter=14),
    "sub": ParagraphStyle("Subtitle", fontName="CN", fontSize=10.5, leading=17, spaceAfter=12, textColor=colors.HexColor("#444444")),
    "h1": ParagraphStyle("Heading", fontName="CNBold", fontSize=16, leading=23, spaceAfter=12, keepWithNext=True),
    "h2": ParagraphStyle("Subheading", fontName="CNBold", fontSize=12, leading=19, spaceBefore=10, spaceAfter=6, keepWithNext=True),
    "body": ParagraphStyle("Body", fontName="CN", fontSize=10.5, leading=17, spaceAfter=7, wordWrap="CJK"),
    "small": ParagraphStyle("Small", fontName="CN", fontSize=9, leading=14, spaceAfter=6, wordWrap="CJK"),
    "code": ParagraphStyle("Code", fontName="CN", fontSize=9, leading=14, leftIndent=10, rightIndent=5, spaceAfter=7),
    "cell": ParagraphStyle("Cell", fontName="CN", fontSize=9.5, leading=15, wordWrap="CJK"),
}
story = []


def text(value, kind="body"):
    story.append(Paragraph(value, styles[kind]))


def code(lines):
    paragraphs = [Paragraph(escape(line).replace(" ", "&#160;"), styles["code"]) for line in lines]
    story.append(KeepTogether(paragraphs))


def heading(value):
    text(value, "h2")


def table(headers, rows, widths):
    content = [[Paragraph(f"<b>{escape(h)}</b>", styles["cell"]) for h in headers]]
    content.extend([[Paragraph(escape(str(cell)), styles["cell"]) for cell in row] for row in rows])
    item = Table(content, colWidths=widths, repeatRows=1, hAlign="LEFT")
    item.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9EDF2")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9D9D9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([item, Spacer(1, 9)])


def page(title):
    story.append(PageBreak())
    text(title, "h1")


def footer(canvas, document):
    width, height = A4
    canvas.setFont("CN", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(48, height - 29, "RustDesk 公司管理服务端")
    canvas.drawRightString(width - 48, height - 29, TAG)
    canvas.drawString(48, 27, "编制日期 2026年10月26日")
    canvas.drawRightString(width - 48, 27, f"第 {document.page} 页")


def build(destination):
    text("Windows 服务器安装与使用说明", "title")
    text(f"RustDesk 公司管理服务端 {TAG}<br/>适用于 Windows 10 x64 和已有 hbbs.exe、hbbr.exe 的固定公网 IP 服务器", "sub")
    text("本说明帮助公司管理员增加账号、设备分组、访问权限和单台电脑分享。保留当前中继服务，在同一台电脑上增加管理 API 与 HTTPS。先完成两台电脑试点，再批量纳管。")
    heading("一 先分清服务器包与客户端包")
    table(["使用位置", "需要的程序", "作用"], [
        ("公司中心服务器", "本版 Setup.exe", "安装管理 API、HTTPS 和开机自启服务"),
        ("公司中心服务器", "现有 hbbs.exe 和 hbbr.exe", "继续负责 ID、穿透和中继，保留原配置与密钥"),
        ("员工电脑及被控电脑", "客户端 v1.5.1-company.1", "登录公司账号、显示授权目录及执行远控"),
    ], [105, 170, 224])
    text("服务器安装包不必安装到每台员工电脑。服务器也不必为了提供账号管理而运行远控客户端。", "small")
    heading("二 安装前准备")
    text("准备管理员权限、固定公网 IPv4，以及能从外网访问本机的 TCP 80 和 443。若公网 IP 在路由器上，将这两个端口映射到服务器。管理 API 的 21114 只监听本机回环，不映射公网。")
    text("备份旧服务启动方式、配置和 id_ed25519 密钥文件。不要重新生成密钥，不要把新管理包覆盖到旧 hbbs/hbbr 目录。运行中的旧 SQLite 数据库需用在线备份，或在维护窗口停旧服务后复制完整数据目录。")
    heading("三 获取安装文件")
    text('从自己的服务端仓库下载 Setup.exe 和 SHA256SUMS：<br/><link href="https://github.com/fanqisyx/rustdesk-server/releases" color="#175A96">https://github.com/fanqisyx/rustdesk-server/releases</link>')
    text("本版内置运行时、Caddy 和服务工具，无需额外安装 Python 或 Docker。安装前对照 SHA256SUMS 核验文件。当前为预发布版，未完成公司环境双机远控验收。", "small")

    page("安装向导与首次登录")
    heading("一 双击 Setup.exe")
    text("在公司服务器双击安装程序，允许管理员权限，阅读许可后选择空安装目录。默认目录为 C:\\Program Files\\RustDesk Company Server。程序不会覆盖非空目录，也不会关闭现有的端口占用服务。")
    heading("二 填写管理服务配置")
    text("填写实际固定公网 IPv4，不加 http、https 或端口。管理员账号固定为 admin；输入至少 12 个字符的密码并再次确认。密码通过临时进程环境传给初始化命令，不写入命令行、注册表或配置文件。")
    text("点击安装后，会创建 RustDeskCompanyAPI 与 RustDeskCompanyHTTPS 两个自动启动服务，并为 Caddy 增加 TCP 80/443 防火墙规则。现有 hbbs/hbbr 继续运行。")
    heading("三 确认服务运行")
    text("可从 Windows 服务管理器查看这两个服务，或在 PowerShell 执行：")
    code(["Get-Service RustDeskCompanyAPI, RustDeskCompanyHTTPS", "Invoke-RestMethod http://127.0.0.1:21114/healthz"])
    text("服务显示 Running、本地健康检查成功，均不代表公网证书已经签发。先用外网设备打开 https://实际公网IP/healthz，确认 HTTPS 证书有效、可信且匹配 IP。内网员工电脑也需能访问同一个 HTTPS 地址。")
    heading("四 登录管理台")
    text("打开 https://实际公网IP，以 admin 和安装时的密码登录。开始菜单提供管理台和说明书入口。Let's Encrypt 的 IP 证书约六天有效，Caddy 自动续期；服务器需持续运行、保留 data/caddy，并保持验证端口可达。")
    text("若安装提示端口或服务冲突，查看详细信息后处理对应配置，不停止未知服务。若已有 IIS 或 HTTPS 代理，可按仓库的手动部署说明复用代理。", "small")

    page("先纳管一台被控电脑")
    heading("一 准备两台电脑")
    text("保留旧客户端安装包和配置，先准备一台控制电脑、一台被控电脑。两端安装公司版 Flutter 原生客户端 v1.5.1-company.1；使用原 ID 服务器、中继地址和公钥。不要使用 Sciter 版。")
    text('客户端来源：<link href="https://github.com/fanqisyx/rustdesk/releases/tag/v1.5.1-company.1" color="#175A96">fanqisyx/rustdesk 的 v1.5.1-company.1 Release</link>。')
    heading("二 先创建账号与资产分组")
    text("控制端公司账号服务填写 https://实际公网IP，注册并登录。注册只创建普通成员，初始没有设备权限。管理员也可在网页创建账号。")
    text("管理员在分组页建立内部资产和外部客户设备树，例如 内部资产 / 上海 / 办公室，或 外部客户 / 客户A / 门店。设备只归属一个分组。")
    heading("三 登记设备并保存独立凭据")
    text("在管理台设备目录登记被控电脑升级后实际显示的 RustDesk ID，并填写名称、资产编号、责任人和地点。保存仅显示一次的设备凭据；遗失时轮换，不把管理员登录令牌当成设备凭据。")
    heading("四 配置被控端服务")
    text("在被控电脑系统服务实际读取的 RustDesk2.toml 现有 [options] 段中增加以下键，不能重复创建同名段。服务账户与普通操作员可能读取不同配置路径，修改后重启该电脑的 RustDesk 服务。")
    code(["[options]", "enterprise-server = 'https://实际公网IP'", "enterprise-device-token = 'rd_device_该设备独立凭据'"])
    text("管理员给测试账号授予相应分组权限；控制端刷新设备组后连接，原设备密码或人工确认继续保留。旧客户端或无票据连接会被受管端拒绝。不要通过唯一远程入口盲目升级，先保留现场或其他维护方式。", "small")

    page("分配权限与分享电脑")
    heading("一 按员工和分组授权")
    text("在访问授权页选择员工、分组、操作权限和可选到期时间。授权覆盖后代分组，多条允许取并集。管理员拥有全局权限；新注册不会自动获得设备归属。")
    table(["权限", "含义"], [
        ("view", "查看设备目录，不代表远程画面只读"),
        ("connect", "远程桌面会话"), ("file_transfer", "文件传输会话"),
        ("terminal", "终端会话"), ("tunnel", "隧道和 RDP 会话"),
        ("camera", "摄像头会话"), ("share", "允许按已有直接权限分享单台设备"),
    ], [115, 384])
    heading("二 分享单台电脑")
    text("管理员或有 share 权限的成员，在设备菜单选择分享远程电脑，填写同一管理服务上的接收账号，选择操作权限和有效期。普通成员还必须直接拥有准备转授的操作权限。")
    text("接收者刷新设备目录，只看到被分享的单台电脑及其分组路径，不获得同组其他设备权限。收到的分享不能继续转发。接收者仍需满足设备密码或人工确认。")
    heading("三 收回权限")
    text("分享者可撤销，接收者可退出，管理员可管理所有分享。分享到期、分享者停用或上游权限收回后，后续连接会重新检查；已有独立授权仍可能保留访问。设备移组或停用会清理相关分享。")
    text("撤权不会立刻断开已经建立的远控会话。浏览器管理台支持账号与资产管理，但 RustDesk Web 远控引擎暂不支持本版票据。", "small")

    page("备份 更新与卸载")
    heading("一 需要保留的内容")
    text("默认安装目录下 data/management.sqlite3 保存账号、资产和授权，data/caddy 保存证书状态，data/logs 保存日志。旧 hbbs/hbbr 的数据库、密钥和配置在原目录，单独备份。")
    heading("二 管理服务备份")
    text("先停止两个新增服务，再复制整个 data 目录到受控备份位置，保留存在时的 WAL 文件。不要只复制仍在运行的 SQLite 主库。完成后依次启动 API 与 HTTPS。")
    code(["Stop-Service RustDeskCompanyHTTPS", "Stop-Service RustDeskCompanyAPI", "# 复制完整 data 目录到公司备份位置", "Start-Service RustDeskCompanyAPI", "Start-Service RustDeskCompanyHTTPS"])
    heading("三 更新与恢复")
    text("更新前核对兼容版本并先试点。向导要求空目录：先备份旧 data 并卸载旧管理扩展，再用 Setup 在空目录新装。随后停止两个新服务，将旧 data 完整恢复到新安装目录，再依次启动 API 和 HTTPS。恢复后使用旧账号密码，向导中新建的初始账号会被备份库覆盖。")
    text("不要合并两套数据库或用空库覆盖生产数据。schema v2 回退旧程序须恢复升级前备份。")
    text("若之前仅使用 ZIP 方式安装，可在原目录运行 windows/Uninstall-Management.ps1 移除新增服务，再保留 data 和备份资料。不要把两个管理扩展同时运行。")
    heading("四 卸载管理扩展")
    text("在 Windows 应用列表找到 RustDesk 公司管理服务端，或从开始菜单运行卸载管理扩展。卸载会核对服务归属，移除本扩展的服务、对应防火墙规则及发布程序文件，保留 data。未随包提供的其他文件不会被递归删除。")
    text("停止或卸载管理服务后，已纳管电脑会拒绝新的公司连接。原 hbbs/hbbr 不被卸载；若要恢复旧客户端连接，还需按计划恢复对应旧程序与配置，并明确设备暂时退出集中授权。", "small")

    page("故障排查与验收")
    table(["现象", "先检查什么"], [
        ("提示目录非空", "另选专用空目录，避免覆盖旧服务和数据；已有管理扩展先备份再卸载"),
        ("80 443 或 21114 被占用", "按提示的端口和进程 ID 找到用途，复用已有代理或调整方案，不关闭未知服务"),
        ("服务运行但 HTTPS 失败", "检查 data/logs、路由器映射、运营商入站限制、出站 HTTPS 和系统时间"),
        ("外网能访问 内网不能", "检查路由器 NAT 回流和内网路由，确保客户端能访问同一 HTTPS 管理地址"),
        ("登录后没有设备", "新账号默认无权限；管理员登记设备、授权或分享后刷新设备组"),
        ("设备可见但不能连接", "检查双方公司版客户端、服务实际读取的配置、逐台凭据、连接权限和设备密码"),
        ("旧控制端被拒绝", "受管端的预期行为；控制端也要升级并登录同一公司管理服务"),
        ("Windows 提示未知发布者", "当前安装包未做代码签名，先核对来源及 SHA256，再按公司管理策略允许运行"),
    ], [135, 364])
    heading("正式批量使用前的检查")
    for item in [
        "[ ] 外网与内网均可打开有效 HTTPS 管理台，重启后服务自动恢复。",
        "[ ] 新账号默认无权限，授权账号可连接，越权输入 ID 和旧客户端被拒绝。",
        "[ ] 分享只授予指定电脑，撤销后新连接被拒绝，其他独立授权符合预期。",
        "[ ] 文件 终端 隧道 摄像头等按实际授予权限隔离，密码及人工确认正常。",
        "[ ] 已完成完整 data 备份与恢复演练，确认日志和证书续期可持续运行。",
    ]:
        text(item, "small")
    text('完整源代码与发布校验：<link href="https://github.com/fanqisyx/rustdesk-server" color="#175A96">github.com/fanqisyx/rustdesk-server</link>。本说明不代表已在公司真实公网环境完成安装和双机验收。', "small")
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=48, rightMargin=48,
        topMargin=55, bottomMargin=45, title="RustDesk Windows 服务器安装与使用说明", author="fanqisyx")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/pdf/RustDesk-Windows-Server-Manual-zh-CN.pdf")
    build(parser.parse_args().output)
