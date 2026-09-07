; ---------------------------------------------------------------------------
;  MV AutoML Studio - aviso de espacio, que NUNCA impide instalar
;
;  NSIS descomprime su paquete interno (app-64.7z) en %TEMP% y RECIEN DESPUES
;  lo copia al destino: pide el espacio dos veces, y la primera siempre en el
;  disco del sistema, aunque el usuario elija instalar en otro. Cuando ahi no
;  entra, la instalacion muere a mitad de la barra con "Extrayendo: error
;  escribiendo al archivo ...\app-64.7z", que no menciona el espacio.
;
;  Este aviso corre antes de extraer y nombra las salidas. Es SOLO un aviso.
;
;  Por que solo un aviso, y esto importa mas que la comprobacion misma:
;
;  1. Esto se inserta en `.onInit`. Ahi `Abort` cierra el instalador SIN
;     mostrar absolutamente nada: el usuario hace doble clic y no pasa nada,
;     ni ventana ni cartel ni error. Un sintoma imposible de diagnosticar
;     desde la maquina del cliente. Una comprobacion de conveniencia no puede
;     tener el poder de matar al instalador en silencio, asi que no hay Abort.
;
;  2. Las variables son propias (`Var`), no $R0/$R1. Los registros $R0-$R9 los
;     usa electron-builder en su propio `.onInit`, alrededor de donde se
;     inserta esto; pisarlos deja el arranque en un estado indefinido.
;
;  3. En instalacion silenciosa (/S) no se muestra: no hay nadie para leer un
;     cartel, y un MessageBox sin nadie que lo cierre cuelga la instalacion
;     para siempre. Es ademas el modo en que la CI prueba el instalador.
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

Var mvUnidadTemp
Var mvLibreMB

!macro customInit
  StrCpy $mvUnidadTemp $TEMP 3
  ${DriveSpace} "$mvUnidadTemp" "/D=F /S=M" $mvLibreMB

  ; Tres condiciones para hablar, y ninguna para frenar:
  ;   - que no sea instalacion silenciosa (no hay quien lea el cartel);
  ;   - que la medicion haya dado algo (si fallo, $mvLibreMB queda vacio, y
  ;     comparar eso como numero es impredecible);
  ;   - que efectivamente falte espacio.
  ${IfNot} ${Silent}
  ${AndIf} $mvLibreMB != ""
  ${AndIf} $mvLibreMB < ${MV_TEMP_MB_MINIMO}
    MessageBox MB_OK|MB_ICONEXCLAMATION \
      "Puede faltar espacio en el disco $mvUnidadTemp$\n$\n\
Libre: $mvLibreMB MB. Conviene tener al menos ${MV_TEMP_MB_MINIMO} MB.$\n$\n\
El instalador descomprime en la carpeta temporal de ESE disco antes de copiar \
los archivos, asi que necesita lugar ahi aunque elijas instalar en otro disco.$\n$\n\
Si seguis y no alcanza, va a fallar con un error que menciona app-64.7z. \
Tres salidas:$\n\
  1. Liberar espacio y volver a intentar.$\n\
  2. Instalar-en-otro-disco.bat, que mueve la carpeta temporal al disco que \
le digas.$\n\
  3. La version portable (.zip), que no instala nada: se descomprime donde \
quieras y se ejecuta.$\n$\n\
Aceptar para seguir igual."
  ${EndIf}
!macroend
