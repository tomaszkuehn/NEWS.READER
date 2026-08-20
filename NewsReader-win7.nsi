; NewsReader-win7.nsi — instalator News Reader dla Windows 7
; Budowany z Python 3.8 + starszymi bibliotekami (requirements-win7.txt).
; Instalacja per-user (bez UAC). Wszystkie biblioteki wbudowane w exe.
; Kompilacja: makensis.exe NewsReader-win7.nsi
;
; Instalator wykrywa wcześniejszą instalację i przeprowadza aktualizację.
; Dane użytkownika (%APPDATA%\NewsReader) są zachowywane.

!include "MUI2.nsh"
!include "InstallOptions.nsh"
!include "WinVer.nsh"

!define PRODUCT_NAME "News Reader (Win7)"
!define PRODUCT_FILE "NewsReader-win7.exe"
!define PRODUCT_VERSION "1.5.8"
!define PRODUCT_UNINSTALL "Uninstall NewsReader-win7.exe"
!define APP_REG_KEY "Software\NewsReader-win7"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\NewsReader-win7"

Name "${PRODUCT_NAME}"
OutFile "dist\NewsReader-win7-Setup.exe"
Unicode True
BrandingText "News Reader (Win7)"
SetCompressor /SOLID lzma

; Instalacja per-user — bez podnoszenia uprawnień
InstallDir "$LOCALAPPDATA\NewsReader-win7"
InstallDirRegKey HKCU "${APP_REG_KEY}" ""
RequestExecutionLevel user

; ---------- Zmienne pomocnicze ----------
Var IsUpgrade
Var InstalledVersion

; ---------- Strony ----------
!define MUI_ABORTWARNING
!define MUI_ICON "app.ico"
!define MUI_UNICON "app.ico"
!define MUI_PAGE_CUSTOMFUNCTION_SHOW WelcomeShow
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

; ---------- Wykrywanie istniejącej instalacji ----------
Function .onInit
  ; Weryfikacja wersji Windows — wymagany Windows 7 lub nowszy.
  ${IfNot} ${AtLeastWin7}
    MessageBox MB_OK|MB_ICONSTOP "Aplikacja wymaga systemu Windows 7 lub nowszego."
    Abort
  ${EndIf}

  StrCpy $IsUpgrade 0
  StrCpy $InstalledVersion ""

  ReadRegStr $InstalledVersion HKCU "${UNINST_KEY}" "DisplayVersion"

  StrCmp $InstalledVersion "" 0 have_version
    IfFileExists "$LOCALAPPDATA\NewsReader-win7\${PRODUCT_FILE}" 0 no_install
      StrCpy $InstalledVersion "nieznana"
  no_install:
  have_version:

  StrCmp $InstalledVersion "" onInit_done 0
    StrCpy $IsUpgrade 1
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON1 "Wykryto wcześniejszą instalację ${PRODUCT_NAME} (wersja $InstalledVersion).$\r$\nZaktualizować ją do wersji ${PRODUCT_VERSION}?" /SD IDYES IDYES onInit_done
    Abort
  onInit_done:
FunctionEnd

; Zatrzymuje działającą aplikację i czeka, aż plik exe zostanie
; odblokowany (pętla — system zwalnia uchwyt z opóźnieniem).
Function CloseRunningApp
  nsExec::Exec 'taskkill /IM "${PRODUCT_FILE}" /F /T'
  StrCpy $R0 0
cra_loop:
  Sleep 500
  Delete "$INSTDIR\${PRODUCT_FILE}"
  IfErrors cra_retry cra_done
cra_retry:
  IntOp $R0 $R0 + 1
  IntCmp $R0 30 cra_timeout cra_loop cra_loop
cra_timeout:
cra_done:
FunctionEnd

; tekst strony powitalnej zależny od trybu (instalacja / aktualizacja)
Function WelcomeShow
  StrCmp $IsUpgrade 1 0 wsh_done
    !insertmacro INSTALLOPTIONS_READ $0 "ioSpecial.ini" "Field 3" "Text"
    !insertmacro INSTALLOPTIONS_WRITE "ioSpecial.ini" "Field 3" "Text" "Ten kreator zaktualizuje istniejącą instalację ${PRODUCT_NAME} z wersji $InstalledVersion do wersji ${PRODUCT_VERSION}. Twoje dane (artykuły, ustawienia, identyfikator przeglądarki) zostaną zachowane."
  wsh_done:
FunctionEnd

; ---------- Sekcje ----------
Section "News Reader (Win7)" SEC_MAIN
  SectionIn RO
  SetOutPath "$INSTDIR"

  Call CloseRunningApp

  File "dist\${PRODUCT_FILE}"

  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortcut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_FILE}"
  CreateShortcut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_FILE}"

  WriteRegStr HKCU "${APP_REG_KEY}" "" "$INSTDIR"
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
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN} "News Reader (Win7) — lokalny czytnik wiadomości. Wersja budowana z Python 3.8 dla zgodności z Windows 7."
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_AUTOSTART} "Uruchamiaj aplikację automatycznie przy starcie systemu."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ---------- Odinstalowanie ----------
Section "Uninstall"
  nsExec::Exec 'taskkill /IM "${PRODUCT_FILE}" /F'

  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"
  DeleteRegKey HKCU "${APP_REG_KEY}"
  DeleteRegKey HKCU "${UNINST_KEY}"

  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"

  Delete "$INSTDIR\${PRODUCT_UNINSTALL}"
  Delete "$INSTDIR\${PRODUCT_FILE}"
  RMDir "$INSTDIR"

  ; dane użytkownika (%APPDATA%\NewsReader) są celowo zachowywane
SectionEnd