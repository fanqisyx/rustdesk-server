Unicode true
RequestExecutionLevel admin
SetCompressor /SOLID lzma
CRCCheck force
!include MUI2.nsh
!include LogicLib.nsh
!include FileFunc.nsh
!include nsDialogs.nsh
!include x64.nsh

!define APP_NAME "RustDesk 公司管理服务端"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\RustDeskCompanyServer"
Name "${APP_NAME} ${RELEASE_TAG}"
OutFile "${SETUP_OUT}"
InstallDir "$PROGRAMFILES64\RustDesk Company Server"
ShowInstDetails show
ShowUninstDetails show
VIProductVersion "${VERSION_NUM}"
VIAddVersionKey ProductName "RustDesk Company Server"
VIAddVersionKey ProductVersion "${RELEASE_TAG}"
VIAddVersionKey FileDescription "RustDesk company management setup"
VIAddVersionKey FileVersion "${VERSION_NUM}"
VIAddVersionKey LegalCopyright "AGPL-3.0 See bundled source and licenses"

Var PublicIP
Var AdminPassword
Var PasswordConfirmation
Var IpInput
Var PasswordInput
Var ConfirmationInput

!define MUI_WELCOMEPAGE_TITLE "安装公司账号与设备管理服务"
!define MUI_WELCOMEPAGE_TEXT "本安装程序增加账号管理 API 和 HTTPS 服务。$\r$\n$\r$\n现有 hbbs.exe、hbbr.exe 继续使用原端口和密钥。请先备份旧配置，并确认公网 TCP 80 和 443 可访问本机。$\r$\n$\r$\n不需要另装 Python 或 Docker。"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${PAYLOAD_DIR}\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
Page custom AccountPage AccountPageLeave
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "管理服务安装完成"
!define MUI_FINISHPAGE_TEXT "管理服务已安装。公网证书签发可能需要等待，请先从外网检查 HTTPS 再迁移客户端。$\r$\n$\r$\n打开管理台后以 admin 登录。先用两台电脑完成登记、授权和远控试点。"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\RustDesk-Windows-Server-Manual-zh-CN.pdf"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "打开中文安装与使用说明书"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE SimpChinese

Function ClearCredentials
  System::Call 'kernel32::SetEnvironmentVariableW(w "RDM_BOOTSTRAP_PASSWORD", p 0)'
  StrCpy $AdminPassword ""
  StrCpy $PasswordConfirmation ""
FunctionEnd

Function .onInit
  SetRegView 64
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "本安装包仅支持 Windows x64。" /SD IDOK
    SetErrorLevel 2
    Quit
  ${EndIf}
  ${If} ${Silent}
    ReadEnvStr $PublicIP "RDM_INSTALL_PUBLIC_IP"
    ReadEnvStr $AdminPassword "RDM_BOOTSTRAP_PASSWORD"
    StrCpy $PasswordConfirmation $AdminPassword
    Call ValidateAccount
  ${EndIf}
FunctionEnd

Function .onGUIEnd
  Call ClearCredentials
FunctionEnd

Function AccountPage
  !insertmacro MUI_HEADER_TEXT "管理服务配置" "填写服务器公网 IPv4 和初始管理员密码"
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 12u "固定公网 IPv4 不含 http、https 或端口号"
  Pop $0
  ${NSD_CreateText} 0 14u 100% 14u "$PublicIP"
  Pop $IpInput
  ${NSD_CreateLabel} 0 34u 100% 12u "管理员账号为 admin 密码至少 12 个字符"
  Pop $0
  ${NSD_CreatePassword} 0 48u 100% 14u "$AdminPassword"
  Pop $PasswordInput
  ${NSD_CreateLabel} 0 68u 100% 12u "再次输入管理员密码"
  Pop $0
  ${NSD_CreatePassword} 0 82u 100% 14u "$PasswordConfirmation"
  Pop $ConfirmationInput
  ${NSD_CreateLabel} 0 104u 100% 30u "请使用空安装目录。已有账号管理服务或端口占用时会停止安装，不会关闭旧 hbbs/hbbr。密码不会写入命令行或配置文件。"
  Pop $0
  nsDialogs::Show
FunctionEnd

Function AccountPageLeave
  ${NSD_GetText} $IpInput $PublicIP
  ${NSD_GetText} $PasswordInput $AdminPassword
  ${NSD_GetText} $ConfirmationInput $PasswordConfirmation
  Call ValidateAccount
FunctionEnd

Function ValidateAccount
  StrLen $0 $AdminPassword
  ${If} $0 < 12
    Goto invalid_password
  ${EndIf}
  ${If} $0 > 128
    Goto invalid_password
  ${EndIf}
  ${If} $AdminPassword != $PasswordConfirmation
    Goto invalid_password
  ${EndIf}
  StrLen $R0 $PublicIP
  StrCpy $R1 0
  StrCpy $R2 0
  StrCpy $R3 0
  StrCpy $R4 0
  StrCpy $R5 ""
  ip_loop:
    ${If} $R1 >= $R0
      Goto ip_done
    ${EndIf}
    StrCpy $R6 $PublicIP 1 $R1
    ${If} $R6 == "."
      ${If} $R3 == 0
        Goto invalid_ip
      ${EndIf}
      IntOp $R4 $R4 + 1
      ${If} $R4 > 3
        Goto invalid_ip
      ${EndIf}
      StrCpy $R5 "$R5$R2."
      StrCpy $R2 0
      StrCpy $R3 0
    ${Else}
      StrCpy $R7 0
      ${For} $R8 0 9
        ${If} $R6 == $R8
          StrCpy $R7 1
          ${Break}
        ${EndIf}
      ${Next}
      ${If} $R7 == 0
        Goto invalid_ip
      ${EndIf}
      IntOp $R2 $R2 * 10
      IntOp $R2 $R2 + $R8
      IntOp $R3 $R3 + 1
      ${If} $R2 > 255
      ${OrIf} $R3 > 3
        Goto invalid_ip
      ${EndIf}
    ${EndIf}
    IntOp $R1 $R1 + 1
    Goto ip_loop
  ip_done:
    ${If} $R4 != 3
    ${OrIf} $R3 == 0
      Goto invalid_ip
    ${EndIf}
    StrCpy $PublicIP "$R5$R2"
    Return
  invalid_ip:
    MessageBox MB_ICONSTOP "请输入完整的公网 IPv4 地址，例如 203.0.113.10。示例地址须替换。" /SD IDOK
    SetErrorLevel 2
    Abort
  invalid_password:
    MessageBox MB_ICONSTOP "密码需为 12 至 128 个字符，且两次输入一致。" /SD IDOK
    SetErrorLevel 2
    Abort
FunctionEnd

Section "安装管理服务"
  Call ValidateAccount
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /oname=Preflight-Setup.ps1 "${PAYLOAD_DIR}\windows\Preflight-Setup.ps1"
  nsExec::ExecToLog '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Preflight-Setup.ps1" -InstallRoot "$INSTDIR"'
  Pop $0
  ${If} $0 != 0
    Call ClearCredentials
    MessageBox MB_ICONSTOP "安装前检查未通过。请查看详细信息中的端口、现有服务或目录提示。现有服务未被停止。" /SD IDOK
    SetErrorLevel 20
    Abort
  ${EndIf}
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD_DIR}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayVersion" "${RELEASE_TAG}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "Publisher" "fanqisyx"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoRepair" 1
  StrCpy $1 $AdminPassword
  System::Call 'kernel32::SetEnvironmentVariableW(w "RDM_BOOTSTRAP_PASSWORD", w r1)i.r2'
  StrCpy $1 ""
  ${If} $2 == 0
    Call ClearCredentials
    MessageBox MB_ICONSTOP "无法初始化管理员密码，安装已停止。" /SD IDOK
    SetErrorLevel 3
    Abort
  ${EndIf}
  nsExec::ExecToLog '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\windows\Install-Management.ps1" -PublicIp "$PublicIP"'
  Pop $0
  Call ClearCredentials
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "安装未完成。请查看详细信息；如需清理，可从 Windows 应用列表卸载本管理扩展。数据库会保留。" /SD IDOK
    SetErrorLevel 3
    Abort
  ${EndIf}
  SetShellVarContext all
  CreateDirectory "$SMPROGRAMS\RustDesk Company Server"
  CreateShortCut "$SMPROGRAMS\RustDesk Company Server\中文说明书.lnk" "$INSTDIR\RustDesk-Windows-Server-Manual-zh-CN.pdf"
  CreateShortCut "$SMPROGRAMS\RustDesk Company Server\卸载管理扩展.lnk" "$INSTDIR\Uninstall.exe"
  WriteINIStr "$SMPROGRAMS\RustDesk Company Server\管理台.url" "InternetShortcut" "URL" "https://$PublicIP"
  SetErrorLevel 0
SectionEnd

Function un.onInit
  SetRegView 64
  ReadRegStr $0 HKLM "${UNINSTALL_KEY}" "InstallLocation"
  ${If} $0 != $INSTDIR
    MessageBox MB_ICONSTOP "卸载程序不在登记的安装目录内，已停止操作。" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
FunctionEnd

Section Uninstall
  nsExec::ExecToLog '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\windows\Uninstall-Management.ps1"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "无法安全移除服务。请查看详情，文件和数据均已保留。" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  SetShellVarContext all
  Delete "$SMPROGRAMS\RustDesk Company Server\中文说明书.lnk"
  Delete "$SMPROGRAMS\RustDesk Company Server\卸载管理扩展.lnk"
  Delete "$SMPROGRAMS\RustDesk Company Server\管理台.url"
  RMDir "$SMPROGRAMS\RustDesk Company Server"
  !include "${DELETE_INCLUDE}"
  Delete "$INSTDIR\Uninstall.exe"
  DeleteRegKey HKLM "${UNINSTALL_KEY}"
  RMDir "$INSTDIR"
  SetErrorLevel 0
SectionEnd
