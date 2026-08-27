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
      {
        "t": 0.6,
        "text": "MV AutoML Studio. De una planilla a un modelo que predice, sin escribir una sola línea de código."
      },
      {
        "t": 9.1,
        "text": "Empezás trayendo los datos. Un Excel, un CSV, o directo de tu servidor."
      },
      {
        "t": 16.1,
        "text": "Soltás el archivo y listo: tres mil filas leídas."
      },
      {
        "t": 20.9,
        "text": "La plataforma sola te dice qué tiene adentro."
      },
      {
        "t": 24.9,
        "text": "Cuánto falta, qué se repite, qué columna no sirve para nada."
      },
      {
        "t": 30.2,
        "text": "Y columna por columna: los importes, los días de atraso, el canal por el que se llamó."
      },
      {
        "t": 36.9,
        "text": "Hasta las notas escritas a mano las lee y las suma al análisis."
      },
      {
        "t": 41.7,
        "text": "Acá se ve qué se mueve junto con qué. Cuanto más fuerte el color, más se acompañan."
      },
      {
        "t": 48.6,
        "text": "También te dice qué identifica a cada fila y si falta algún período."
      },
      {
        "t": 53.5,
        "text": "Ahora le decís qué querés saber, con tus palabras: si el cliente va a pagar."
      },
      {
        "t": 59.3,
        "text": "Lo entiende, encuentra la columna y arma el plan."
      },
      {
        "t": 63.6,
        "text": "Reconoce que es una pregunta de sí o no, y te dice con cuánta confianza."
      },
      {
        "t": 69.2,
        "text": "Después prepara los datos y saca lo que ya tiene la respuesta adentro."
      },
      {
        "t": 74.3,
        "text": "Entrena. Prueba familias de modelos distintas y se queda con la mejor."
      },
      {
        "t": 80.3,
        "text": "El resultado se mide sobre datos que el modelo nunca vio. Es el número que vale."
      },
      {
        "t": 86.7,
        "text": "Cuanto más cerca de uno, mejor separa a los que pagan de los que no."
      },
      {
        "t": 91.6,
        "text": "Y te explica por qué: qué pesa y para qué lado empuja."
      },
      {
        "t": 96.3,
        "text": "Hablar con la persona es lo que más pesa. Cuanto más vieja la deuda, menos se cobra."
      },
      {
        "t": 103.1,
        "text": "Todo baja a Excel, listo para usar."
      }
    ],
    "en": [
      {
        "t": 0.6,
        "text": "MV AutoML Studio. From a spreadsheet to a model that predicts, without writing a single line of code."
      },
      {
        "t": 9.1,
        "text": "You start by bringing in the data. An Excel file, a CSV, or straight from your server."
      },
      {
        "t": 16.9,
        "text": "Drop the file and that's it: three thousand rows read."
      },
      {
        "t": 21.3,
        "text": "The platform tells you on its own what's inside."
      },
      {
        "t": 25.6,
        "text": "How much is missing, what repeats, which column is of no use at all."
      },
      {
        "t": 31.1,
        "text": "And column by column: the amounts, the days overdue, the channel used to call."
      },
      {
        "t": 37.2,
        "text": "It even reads the notes typed by hand and adds them to the analysis."
      },
      {
        "t": 42.5,
        "text": "Here you see what moves together with what. The stronger the colour, the closer they move."
      },
      {
        "t": 49.8,
        "text": "It also tells you what identifies each row and whether any period is missing."
      },
      {
        "t": 55.5,
        "text": "Now you say what you want to know, in your own words: whether the customer will pay."
      },
      {
        "t": 61.5,
        "text": "It understands, finds the column and builds the plan."
      },
      {
        "t": 66.2,
        "text": "It recognises it's a yes-or-no question, and tells you how confident it is."
      },
      {
        "t": 71.9,
        "text": "Then it prepares the data and removes whatever already carries the answer inside."
      },
      {
        "t": 77.9,
        "text": "It trains. It tries different families of models and keeps the best one."
      },
      {
        "t": 84.5,
        "text": "The result is measured on data the model never saw. That's the number that counts."
      },
      {
        "t": 91.5,
        "text": "The closer to one, the better it separates those who pay from those who don't."
      },
      {
        "t": 97.1,
        "text": "And it explains why: what weighs, and which way it pushes."
      },
      {
        "t": 101.8,
        "text": "Talking to the person is what weighs the most. The older the debt, the less gets collected."
      },
      {
        "t": 109.2,
        "text": "Everything goes down to Excel, ready to use."
      }
    ],
    "pt": [
      {
        "t": 0.6,
        "text": "MV AutoML Studio. De uma planilha a um modelo que prevê, sem escrever uma única linha de código."
      },
      {
        "t": 9.3,
        "text": "Você começa trazendo os dados. Um Excel, um CSV, ou direto do seu servidor."
      },
      {
        "t": 17.6,
        "text": "Solta o arquivo e pronto: três mil linhas lidas."
      },
      {
        "t": 22.5,
        "text": "A plataforma sozinha diz o que tem lá dentro."
      },
      {
        "t": 26.9,
        "text": "Quanto falta, o que se repete, qual coluna não serve para nada."
      },
      {
        "t": 32.8,
        "text": "E coluna por coluna: os valores, os dias de atraso, o canal pelo qual se ligou."
      },
      {
        "t": 39.8,
        "text": "Até as anotações escritas à mão ela lê e soma à análise."
      },
      {
        "t": 45.0,
        "text": "Aqui se vê o que anda junto com o quê. Quanto mais forte a cor, mais se acompanham."
      },
      {
        "t": 52.4,
        "text": "Também diz o que identifica cada linha e se falta algum período."
      },
      {
        "t": 57.6,
        "text": "Agora você diz o que quer saber, com as suas palavras: se o cliente vai pagar."
      },
      {
        "t": 64.0,
        "text": "Ela entende, encontra a coluna e monta o plano."
      },
      {
        "t": 68.5,
        "text": "Reconhece que é uma pergunta de sim ou não, e diz com quanta confiança."
      },
      {
        "t": 74.5,
        "text": "Depois prepara os dados e tira o que já tem a resposta dentro."
      },
      {
        "t": 79.5,
        "text": "Treina. Testa famílias de modelos diferentes e fica com a melhor."
      },
      {
        "t": 85.7,
        "text": "O resultado é medido sobre dados que o modelo nunca viu. É o número que vale."
      },
      {
        "t": 92.6,
        "text": "Quanto mais perto de um, melhor separa quem paga de quem não paga."
      },
      {
        "t": 97.9,
        "text": "E explica por quê: o que pesa e para que lado empurra."
      },
      {
        "t": 102.9,
        "text": "Falar com a pessoa é o que mais pesa. Quanto mais velha a dívida, menos se recebe."
      },
      {
        "t": 110.4,
        "text": "Tudo baixa para Excel, pronto para usar."
      }
    ]
  },
  "tablero": {
    "es": [
      {
        "t": 0.6,
        "text": "El tablero se arma solo con cualquier dataset o consulta SQL."
      },
      {
        "t": 5.9,
        "text": "La plataforma detecta las métricas, las dimensiones y la columna de tiempo, y decide qué vale la pena mostrar."
      },
      {
        "t": 13.5,
        "text": "Cada indicador compara contra el mes anterior, contra el mismo mes del año pasado y el acumulado del año contra el anterior. En verde lo que crece, en rojo lo que cae."
      },
      {
        "t": 24.2,
        "text": "Y respeta la unidad: los montos varían en porcentaje, y lo que ya es un porcentaje varía en puntos porcentuales."
      },
      {
        "t": 31.8,
        "text": "Los filtros recalculan todo: indicadores, series, barras y tabla."
      },
      {
        "t": 37.8,
        "text": "El tablero completo se exporta a Excel o CSV con los filtros puestos, una hoja por gráfico."
      },
      {
        "t": 44.4,
        "text": "Y se le puede preguntar en castellano. Traduce la pregunta a SQL, la ejecuta de verdad sobre los datos y responde con el resultado real, no de memoria."
      }
    ],
    "en": [
      {
        "t": 0.6,
        "text": "The dashboard builds itself from any dataset or SQL query."
      },
      {
        "t": 5.8,
        "text": "The platform detects the metrics, the dimensions and the time column, and decides what is worth showing."
      },
      {
        "t": 12.8,
        "text": "Every indicator compares against the previous month, against the same month last year, and year to date against the previous one. Green when it grows, red when it falls."
      },
      {
        "t": 24.1,
        "text": "And it respects the unit: amounts vary in percent, and what already is a percentage varies in percentage points."
      },
      {
        "t": 31.8,
        "text": "Filters recalculate everything: indicators, series, bars and table."
      },
      {
        "t": 37.9,
        "text": "The whole dashboard exports to Excel or CSV with the filters applied, one sheet per chart."
      },
      {
        "t": 44.6,
        "text": "And you can ask it in plain language. It translates the question into SQL, actually runs it against the data and answers from the real result, not from memory."
      }
    ],
    "pt": [
      {
        "t": 0.6,
        "text": "O painel se monta sozinho com qualquer conjunto de dados ou consulta SQL."
      },
      {
        "t": 6.8,
        "text": "A plataforma detecta as métricas, as dimensões e a coluna de tempo, e decide o que vale a pena mostrar."
      },
      {
        "t": 14.9,
        "text": "Cada indicador compara contra o mês anterior, contra o mesmo mês do ano passado e o acumulado do ano contra o anterior. Em verde o que cresce, em vermelho o que cai."
      },
      {
        "t": 26.7,
        "text": "E respeita a unidade: os valores variam em porcentagem, e o que já é uma porcentagem varia em pontos percentuais."
      },
      {
        "t": 35.6,
        "text": "Os filtros recalculam tudo: indicadores, séries, barras e tabela."
      },
      {
        "t": 42.0,
        "text": "O painel completo é exportado para Excel ou CSV com os filtros aplicados, uma aba por gráfico."
      },
      {
        "t": 49.6,
        "text": "E dá para perguntar em linguagem comum. Traduz a pergunta para SQL, executa de verdade sobre os dados e responde com o resultado real, não de memória."
      }
    ]
  }
};
