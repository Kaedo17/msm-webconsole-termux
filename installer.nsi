; Minecraft Web Manager Installer
; Requires NSIS 3.0+ (https://nsis.sourceforge.io/)
;
; Build with:  makensis installer.nsi
; Or:          python build_exe.py --installer

!define PRODUCT_NAME "Minecraft Web Manager"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "Kemji"
!define PRODUCT_WEB_SITE "https://github.com/Kaedo17/msm-webconsole-termux"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\MinecraftWebManager.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

; Modern UI
!include "MUI2.nsh"

; MUI Settings
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Wizard\win.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Header\win.bmp"

; Welcome page
!insertmacro MUI_PAGE_WELCOME
; License page
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
; Components page
!insertmacro MUI_PAGE_COMPONENTS
; Directory page
!insertmacro MUI_PAGE_DIRECTORY
; Instfiles page
!insertmacro MUI_PAGE_INSTFILES
; Finish page
!define MUI_FINISHPAGE_RUN "$INSTDIR\MinecraftWebManager.exe"
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES

; Language
!insertmacro MUI_LANGUAGE "English"

; Installer info
Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "MinecraftWebManager_Setup_${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES64\MinecraftWebManager"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show
RequestExecutionLevel admin

; Check if already installed (for updates)
Section "CheckPreviousInstall"
  ReadRegStr $R0 HKLM "${PRODUCT_UNINST_KEY}" "UninstallString"
  StrCmp $R0 "" done

  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
    "${PRODUCT_NAME} is already installed. $\n$\nClick OK to update to ${PRODUCT_VERSION}." \
    IDOK uninst
  Abort

  uninst:
    ; Temporarily move data directory aside to preserve it
    IfFileExists "$INSTDIR\data" 0 no_data
      Rename "$INSTDIR\data" "$TEMP\MWM-data-backup"
    no_data:
    ; Run the old uninstaller silently
    ExecWait '"$R0" /S _?=$INSTDIR'
    IfErrors no_remove
    RMDir /r "$INSTDIR"
  no_remove:
done:
SectionEnd

; Main application files
Section "Application Files" SEC_APP
  SectionIn RO
  SetOutPath "$INSTDIR"
  SetOverwrite on

  ; Copy all files from the build dist folder
  File /r "dist\MinecraftWebManager\*.*"

  ; First, restore data backup from update (if any) — do this BEFORE
  ; creating new data directories, so Rename doesn't fail.
  IfFileExists "$TEMP\MWM-data-backup" 0 no_restore
    DetailPrint "Restoring server data from backup..."
    Rename "$TEMP\MWM-data-backup" "$INSTDIR\data"
    Goto after_dirs
  no_restore:
    ; No backup to restore — create fresh data directories
    CreateDirectory "$INSTDIR\data"
    CreateDirectory "$INSTDIR\data\servers"
    CreateDirectory "$INSTDIR\data\jdk"
  after_dirs:

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\Minecraft Web Manager"
  CreateShortCut "$SMPROGRAMS\Minecraft Web Manager\Minecraft Web Manager.lnk" \
    "$INSTDIR\MinecraftWebManager.exe" "" "$INSTDIR\MinecraftWebManager.exe" 0
  CreateShortCut "$SMPROGRAMS\Minecraft Web Manager\Uninstall.lnk" \
    "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\Minecraft Web Manager.lnk" \
    "$INSTDIR\MinecraftWebManager.exe" "" "$INSTDIR\MinecraftWebManager.exe" 0

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Register in Add/Remove Programs
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\MinecraftWebManager.exe"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoRepair" 1
SectionEnd

; Optional: Desktop shortcut
Section /o "Desktop Shortcut" SEC_DESKTOP
  SetOutPath "$INSTDIR"
  CreateShortCut "$DESKTOP\Minecraft Web Manager.lnk" \
    "$INSTDIR\MinecraftWebManager.exe" "" "$INSTDIR\MinecraftWebManager.exe" 0
SectionEnd

; Optional: Quick Launch shortcut
Section /o "Quick Launch Shortcut" SEC_QUICKLAUNCH
  SetOutPath "$INSTDIR"
  CreateShortCut "$QUICKLAUNCH\Minecraft Web Manager.lnk" \
    "$INSTDIR\MinecraftWebManager.exe" "" "$INSTDIR\MinecraftWebManager.exe" 0
SectionEnd

; Descriptions
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_APP} "Core application files (required)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} "Create a shortcut on your desktop"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_QUICKLAUNCH} "Add to Quick Launch toolbar"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; Uninstaller
Section "Uninstall"
  ; Remove shortcuts
  RMDir /r "$SMPROGRAMS\Minecraft Web Manager"
  Delete "$DESKTOP\Minecraft Web Manager.lnk"
  Delete "$QUICKLAUNCH\Minecraft Web Manager.lnk"

  ; Remove installed files (keep data directory for safety)
  Delete "$INSTDIR\*.*"
  RMDir /r "$INSTDIR\_internal"

  ; Remove uninstaller
  Delete "$INSTDIR\uninstall.exe"

  ; Remove directory if empty (data stays if user has servers)
  RMDir "$INSTDIR"

  ; Remove registry keys
  DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
  DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
SectionEnd
