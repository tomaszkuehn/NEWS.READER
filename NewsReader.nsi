; NewsReader.nsi — instalator News Reader (Windows 7 / 10 / 11)
; Instalacja per-user (bez UAC, działa na kontach bez uprawnień admina).
; Wszystkie biblioteki aplikacji są wbudowane w NewsReader.exe (PyInstaller onefile).
; Kompilacja (przenośny NSIS): makensis.exe NewsReader.nsi

!include "MUI2.nsh"

!define PRODUCT_NAME "News Reader"
!define PRODUCT_FILE "NewsReader.exe"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_UNINSTALL "Uninstall NewsReader.exe"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\NewsReader"

Name "${PRODUCT_NAME}"
OutFile "dist\NewsReader-Setup.exe"
Unicode True
BrandingText "News Reader"
SetCompressor /SOLID lzma

; Instalacja per-user — bez podnoszenia uprawnień
InstallDir "$LOCALAPPDATA\NewsReader"
InstallDirRegKey HKCU "Software\NewsReader" ""
RequestExecutionLevel user

; ---------- Strony ----------
!define MUI_ABORTWARNING
!define MUI_ICON "app.ico"
!define MUI_UNICON "app.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${PRODUCT_FILE}"
!define MUI_FINISHPAGE_RUN_TEXT "Uruchom ${PRODUCT_NAME}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Polish"
!insertmacro MUI_LANGUAGE "English"

; ---------- Sekcje ----------
Section "News Reader" SEC_MAIN
  SectionIn RO
  SetOutPath "$INSTDIR"
  File "dist\${PRODUCT_FILE}"

  ; skróty
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortcut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_FILE}"
  CreateShortcut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_FILE}"

  ; wpis instalacji w rejestrze (Add/Remove Programs)
  WriteRegStr HKCU "Software\${PRODUCT_NAME}" "" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${PRODUCT_FILE}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${PRODUCT_NAME}"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\${PRODUCT_UNINSTALL}"'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1

  WriteUninstaller "$INSTDIR\${PRODUCT_UNINSTALL}"
SectionEnd

Section "Uruchom przy starcie systemu" SEC_AUTOSTART
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}" '"$INSTDIR\${PRODUCT_FILE}"'
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN} "News Reader — lokalny czytnik wiadomości (serwer + tray). Zawiera wszystkie potrzebne biblioteki."
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_AUTOSTART} "Uruchamiaj aplikację automatycznie przy starcie systemu."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ---------- Odinstalowanie ----------
Section "Uninstall"
  ; zatrzymaj działającą aplikację
  nsExec::Exec 'taskkill /IM "${PRODUCT_FILE}" /F'

  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"
  DeleteRegKey HKCU "Software\${PRODUCT_NAME}"
  DeleteRegKey HKCU "${UNINST_KEY}"

  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"

  Delete "$INSTDIR\${PRODUCT_UNINSTALL}"
  Delete "$INSTDIR\${PRODUCT_FILE}"
  RMDir "$INSTDIR"

  ; dane użytkownika (%APPDATA%\NewsReader) są celowo zachowywane
SectionEnd
