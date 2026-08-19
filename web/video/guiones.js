// MV AutoML Studio · Narración de los videos de la web, en los tres idiomas.
//
// Fuente única: `generar_voz.py` lee este mismo archivo para sintetizar el
// audio, así que lo que se escucha y lo que dice la web no se pueden
// desincronizar. Mismo criterio que `dashboard_estatico/guiones.js` de Kobra.
//
// Cada tramo lleva `t`: el segundo del video en el que empieza a hablar. Los
// tramos se sintetizan por separado y se montan en esa posición, así una frase
// que quede larga no corre a las demás.
//
// Es un .js y no un .json a propósito: la página se puede abrir con doble clic
// (protocolo file://), donde `fetch` de un archivo local lo bloquea CORS.
window.NARRACION = {
  "recorrido": {
    "es": [
      {"t": 0.5,  "text": "MV AutoML Studio. De cualquier dataset a un modelo validado, sin escribir una línea de código."},
      {"t": 8,    "text": "Se arrastra el archivo y la plataforma lo perfila sola: detecta el tipo de cada columna, la calidad de los datos y el texto libre, que vectoriza para que compita con el resto."},
      {"t": 20,   "text": "El mapa de correlaciones muestra de una qué variables se mueven juntas."},
      {"t": 27,   "text": "El objetivo se escribe en castellano, en tus palabras. La plataforma identifica la columna, reconoce que es una clasificación y arma el plan."},
      {"t": 38,   "text": "Antes de entrenar audita la fuga de información y descarta lo que memoriza en vez de generalizar, como el identificador de cada fila."},
      {"t": 48,   "text": "Ahora compiten los modelos: ajusta hiperparámetros, prueba familias distintas y combina las mejores."},
      {"t": 58,   "text": "El número que se reporta sale del holdout ciego, la ventana que no se tocó en ninguna decisión. Cero coma ochenta y ocho de AUC, con una degradación mínima contra la ventana de selección: el modelo se sostiene."},
      {"t": 70,   "text": "Y explica por qué: cada variable con su peso real y hacia dónde empuja. El contacto efectivo sube el pago; los días de atraso lo bajan."}
    ],
    "en": [
      {"t": 0.5,  "text": "MV AutoML Studio. From any dataset to a validated model, without writing a single line of code."},
      {"t": 8,    "text": "You drop the file and the platform profiles it on its own: it detects each column's type, the data quality, and the free text, which it vectorises so it competes with the rest."},
      {"t": 20,   "text": "The correlation map shows at a glance which variables move together."},
      {"t": 27,   "text": "You type the target in plain language. The platform finds the column, recognises it as a classification problem and builds the plan."},
      {"t": 38,   "text": "Before training it audits for leakage and drops whatever memorises instead of generalising, such as each row's identifier."},
      {"t": 48,   "text": "Then the models compete: it tunes hyperparameters, tries different families and blends the best ones."},
      {"t": 58,   "text": "The number it reports comes from the blind holdout, the window untouched by any decision. Zero point eight eight AUC, with minimal degradation against the selection window: the model holds up."},
      {"t": 70,   "text": "And it explains why: every variable with its real weight and which way it pushes. Effective contact raises payment; days overdue lower it."}
    ],
    "pt": [
      {"t": 0.5,  "text": "MV AutoML Studio. De qualquer conjunto de dados a um modelo validado, sem escrever uma linha de código."},
      {"t": 8,    "text": "Você arrasta o arquivo e a plataforma faz o perfil sozinha: detecta o tipo de cada coluna, a qualidade dos dados e o texto livre, que vetoriza para competir com o resto."},
      {"t": 20,   "text": "O mapa de correlações mostra de imediato quais variáveis andam juntas."},
      {"t": 27,   "text": "O objetivo é escrito em linguagem comum. A plataforma identifica a coluna, reconhece que é uma classificação e monta o plano."},
      {"t": 38,   "text": "Antes de treinar, audita o vazamento de informação e descarta o que memoriza em vez de generalizar, como o identificador de cada linha."},
      {"t": 48,   "text": "Então os modelos competem: ajusta hiperparâmetros, testa famílias diferentes e combina as melhores."},
      {"t": 58,   "text": "O número reportado vem do holdout cego, a janela que não foi tocada em nenhuma decisão. Zero vírgula oitenta e oito de AUC, com degradação mínima contra a janela de seleção: o modelo se sustenta."},
      {"t": 70,   "text": "E explica o porquê: cada variável com seu peso real e para onde empurra. O contato efetivo aumenta o pagamento; os dias de atraso o reduzem."}
    ]
  },
  "tablero": {
    "es": [
      {"t": 0.5,  "text": "El tablero se arma solo con cualquier dataset o consulta SQL."},
      {"t": 6,    "text": "La plataforma detecta las métricas, las dimensiones y la columna de tiempo, y decide qué vale la pena mostrar."},
      {"t": 14,   "text": "Cada indicador compara contra el mes anterior, contra el mismo mes del año pasado y el acumulado del año contra el anterior. En verde lo que crece, en rojo lo que cae."},
      {"t": 26,   "text": "Y respeta la unidad: los montos varían en porcentaje, y lo que ya es un porcentaje varía en puntos porcentuales."},
      {"t": 35,   "text": "Los filtros recalculan todo: indicadores, series, barras y tabla."},
      {"t": 43,   "text": "El tablero completo se exporta a Excel o CSV con los filtros puestos, una hoja por gráfico."},
      {"t": 52,   "text": "Y se le puede preguntar en castellano. Traduce la pregunta a SQL, la ejecuta de verdad sobre los datos y responde con el resultado real, no de memoria."}
    ],
    "en": [
      {"t": 0.5,  "text": "The dashboard builds itself from any dataset or SQL query."},
      {"t": 6,    "text": "The platform detects the metrics, the dimensions and the time column, and decides what is worth showing."},
      {"t": 14,   "text": "Every indicator compares against the previous month, against the same month last year, and year to date against the previous one. Green when it grows, red when it falls."},
      {"t": 26,   "text": "And it respects the unit: amounts vary in percent, and what already is a percentage varies in percentage points."},
      {"t": 35,   "text": "Filters recalculate everything: indicators, series, bars and table."},
      {"t": 43,   "text": "The whole dashboard exports to Excel or CSV with the filters applied, one sheet per chart."},
      {"t": 52,   "text": "And you can ask it in plain language. It translates the question into SQL, actually runs it against the data and answers from the real result, not from memory."}
    ],
    "pt": [
      {"t": 0.5,  "text": "O painel se monta sozinho com qualquer conjunto de dados ou consulta SQL."},
      {"t": 6,    "text": "A plataforma detecta as métricas, as dimensões e a coluna de tempo, e decide o que vale a pena mostrar."},
      {"t": 14,   "text": "Cada indicador compara contra o mês anterior, contra o mesmo mês do ano passado e o acumulado do ano contra o anterior. Em verde o que cresce, em vermelho o que cai."},
      {"t": 26,   "text": "E respeita a unidade: os valores variam em porcentagem, e o que já é uma porcentagem varia em pontos percentuais."},
      {"t": 35,   "text": "Os filtros recalculam tudo: indicadores, séries, barras e tabela."},
      {"t": 43,   "text": "O painel completo é exportado para Excel ou CSV com os filtros aplicados, uma aba por gráfico."},
      {"t": 52,   "text": "E dá para perguntar em linguagem comum. Traduz a pergunta para SQL, executa de verdade sobre os dados e responde com o resultado real, não de memória."}
    ]
  }
};
