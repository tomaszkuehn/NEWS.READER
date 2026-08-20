; NewsReader.nsi — instalator News Reader (Windows 7 / 10 / 11)
; Instalacja per-user (bez UAC, działa na kontach bez uprawnień admina).
; Wszystkie biblioteki aplikacji są wbudowane w NewsReader.exe (PyInstaller onefile).
; Kompilacja (przenośny NSIS): makensis.exe NewsReader.nsi
;
; Instalator wykrywa wcześniejszą instalację (klucz rejestru + plik aplikacji)
; i wtedy przeprowadza AKTUALIZACJĘ (upgrade): zatrzymuje działającą aplikację,
; nadpisuje pliki i odświeża wersję w rejestrze. Dane użytkownika
; (%APPDATA%\NewsReader) są celowo zachowywane — także przy odinstalowaniu.

!include "MUI2.nsh"
!include "InstallOptions.nsh"

!define PRODUCT_NAME "News Reader"
!define PRODUCT_FILE "NewsReader.exe"
!define PRODUCT_VERSION "1.5.8"
!define PRODUCT_UNINSTALL "Uninstall NewsReader.exe"
!define APP_REG_KEY "Software\NewsReader"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\NewsReader"

Name "${PRODUCT_NAME}"
OutFile "dist\NewsReader-Setup.exe"
Unicode True
BrandingText "News Reader"
SetCompressor /SOLID lzma

; Instalacja per-user — bez podnoszenia uprawnień
InstallDir "$LOCALAPPDATA\NewsReader"
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
  StrCpy $IsUpgrade 0
  StrCpy $InstalledVersion ""

  ; 1) wersja z klucza odinstalowania (Add/Remove Programs)
  ReadRegStr $InstalledVersion HKCU "${UNINST_KEY}" "DisplayVersion"

  ; 2) brak wpisu, ale plik aplikacji istnieje — mimo to upgrade (naprawa)
  StrCmp $InstalledVersion "" 0 have_version
    IfFileExists "$LOCALAPPDATA\NewsReader\${PRODUCT_FILE}" 0 no_install
      StrCpy $InstalledVersion "nieznana"
  no_install:
  have_version:

  ; 3) jeśli wykryto — zapytaj o zgodę na aktualizację
  StrCmp $InstalledVersion "" onInit_done 0
    StrCpy $IsUpgrade 1
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON1 "Wykryto wcześniejszą instalację ${PRODUCT_NAME} (wersja $InstalledVersion).$\r$\nZaktualizować ją do wersji ${PRODUCT_VERSION}?" /SD IDYES IDYES onInit_done
    Abort
  onInit_done:
FunctionEnd

; tekst strony powitalnej zależny od trybu (instalacja / aktualizacja)
Function WelcomeShow
  StrCmp $IsUpgrade 1 0 wsh_done
    !insertmacro INSTALLOPTIONS_READ $0 "ioSpecial.ini" "Field 3" "Text"
    !insertmacro INSTALLOPTIONS_WRITE "ioSpecial.ini" "Field 3" "Text" "Ten kreator zaktualizuje istniejącą instalację ${PRODUCT_NAME} z wersji $InstalledVersion do wersji ${PRODUCT_VERSION}. Twoje dane (artykuły, ustawienia, identyfikator przeglądarki) zostaną zachowane."
  wsh_done:
FunctionEnd

; ---------- Sekcje ----------
Section "News Reader" SEC_MAIN
  SectionIn RO
  SetOutPath "$INSTDIR"

  ; przy aktualizacji zatrzymaj działającą aplikację — działający exe jest
  ; zablokowany przez Windows i nie dałby się nadpisać
  nsExec::Exec 'taskkill /IM "${PRODUCT_FILE}" /F'

  File "dist\${PRODUCT_FILE}"

  ; skróty (nadpisywane przy aktualizacji)
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortcut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_FILE}"
  CreateShortcut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_FILE}"

  ; wpis instalacji w rejestrze (Add/Remove Programs)
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
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN} "News Reader — lokalny czytnik wiadomości (serwer + tray). Zawiera wszystkie potrzebne biblioteki."
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_AUTOSTART} "Uruchamiaj aplikację automatycznie przy starcie systemu."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ---------- Odinstalowanie ----------
Section "Uninstall"
  ; zatrzymaj działającą aplikację
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
