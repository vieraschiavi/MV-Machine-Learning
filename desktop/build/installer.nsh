; ---------------------------------------------------------------------------
;  MV AutoML Studio - comprobacion previa de espacio
;
;  NSIS descomprime su paquete interno (app-64.7z) en %TEMP% y RECIEN DESPUES
;  lo copia al destino: pide el espacio dos veces, y la primera siempre en el
;  disco del sistema, aunque el usuario elija instalar en otro.
;
;  Cuando ahi no entra, la instalacion muere a mitad de la barra con
;  "Extrayendo: error escribiendo al archivo ...\app-64.7z", un mensaje que no
;  menciona el espacio ni dice que hacer. Esto lo comprueba antes de empezar y
;  nombra las tres salidas.
;
;  Todo en ASCII: NSIS compila con la pagina de codigos del sistema y un acento
;  sale como basura en la pantalla del cliente.
; ---------------------------------------------------------------------------

!include "FileFunc.nsh"
!include "LogicLib.nsh"

; Espacio necesario en el disco de %TEMP%, en MB: el paquete comprimido que se
; extrae ahi (~370 MB) mas margen para que el sistema siga funcionando. El
; destino necesita ~1400 MB mas, pero ese disco lo elige el usuario.
!define MV_TEMP_MB_MINIMO 900

!macro customInit
  StrCpy $R0 $TEMP 3
  ${DriveSpace} "$R0" "/D=F /S=M" $R1

  ; Si la medicion falla, $R1 queda vacio: no se bloquea la instalacion por no
  ; haber podido medir.
  ${If} $R1 != ""
  ${AndIf} $R1 < ${MV_TEMP_MB_MINIMO}
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
      "Falta espacio en el disco $R0$\n$\n\
Libre: $R1 MB. Hacen falta al menos ${MV_TEMP_MB_MINIMO} MB.$\n$\n\
El instalador descomprime en la carpeta temporal de ESE disco antes de copiar \
los archivos, asi que necesita lugar ahi aunque elijas instalar en otro disco.$\n$\n\
Tres salidas:$\n\
  1. Liberar espacio y volver a intentar.$\n\
  2. Cancelar y usar Instalar-en-otro-disco.bat, que mueve la carpeta temporal \
al disco que le digas.$\n\
  3. Cancelar y usar la version portable (.zip), que no instala nada: se \
descomprime donde quieras y se ejecuta.$\n$\n\
Continuar igual de todos modos?" \
      IDOK mv_continuar
    Abort
    mv_continuar:
  ${EndIf}
!macroend
