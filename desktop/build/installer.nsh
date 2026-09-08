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
;  Cuatro reglas, y cada una viene de haberla roto:
;
;  1. Sin `Abort`. Esto se inserta en `.onInit`, y ahi `Abort` cierra el
;     instalador SIN mostrar absolutamente nada: doble clic y no pasa nada, ni
;     ventana ni cartel ni error. Desde la maquina del cliente ese sintoma es
;     indistinguible de un ejecutable corrupto. Una comprobacion de
;     conveniencia no puede tener el poder de matar al instalador en silencio.
;
;  2. Sin `Var` a nivel de archivo. electron-builder compila el DESINSTALADOR
;     en una pasada aparte que incluye este mismo archivo pero NO inserta
;     `customInit`: las variables quedarian declaradas y sin usar, NSIS avisa
;     "warning 6001: Variable not referenced or never set", y electron-builder
;     trata los warnings de NSIS como errores. El build entero se cae, en el
;     ultimo paso, despues de cuatro minutos de empaquetado.
;
;  3. Los registros se guardan y se devuelven. $0-$9 y $R0-$R9 son compartidos:
;     electron-builder los usa en su propio `.onInit`, alrededor de donde se
;     inserta esto. Push al entrar, Pop al salir, y nadie se entera.
;
;  4. En instalacion silenciosa (/S) no se muestra: no hay nadie para cerrar un
;     cartel, y uno sin cerrar cuelga la instalacion para siempre. Es ademas el
;     modo en que la CI prueba el instalador.
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
  ; $0 = unidad de %TEMP%, $1 = MB libres. Prestados y devueltos.
  Push $0
  Push $1

  StrCpy $0 $TEMP 3
  ${DriveSpace} "$0" "/D=F /S=M" $1

  ; Tres condiciones para hablar, y ninguna para frenar:
  ;   - que no sea instalacion silenciosa (no hay quien lea el cartel);
  ;   - que la medicion haya dado algo (si fallo, $1 queda vacio, y comparar
  ;     eso como numero es impredecible);
  ;   - que efectivamente falte espacio.
  ${IfNot} ${Silent}
  ${AndIf} $1 != ""
  ${AndIf} $1 < ${MV_TEMP_MB_MINIMO}
    MessageBox MB_OK|MB_ICONEXCLAMATION \
      "Puede faltar espacio en el disco $0$\n$\n\
Libre: $1 MB. Conviene tener al menos ${MV_TEMP_MB_MINIMO} MB.$\n$\n\
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

  Pop $1
  Pop $0
!macroend
