# RagPilot — Resumen del proyecto

> **English:** [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)

Construí RagPilot para responder una pregunta de forma honesta: **¿la
recuperación realmente le gana a meter todo el documento en el prompt de un
LLM?**

Es una demo en dos partes: un backend FastAPI que ingiere documentos, los
trocea y los embeddea en pgvector; y un workspace React donde corrés dos
pipelines sobre la misma pregunta — **RAG** (recuperar los chunks relevantes y
generar) vs **full-doc** (generar con todo el corpus metido en un solo prompt,
el baseline ingenuo que RAG reemplaza). Y después hice que el dashboard mostrara
ese tradeoff en vivo, con los datos reales del usuario.

---

## Por qué lo construí (y por qué RAG importa)

La mayoría de las preguntas que una empresa realmente le hace a un LLM no son
sobre lo que el modelo ya sabe. Son sobre sus propios datos: documentación de
producto, tickets de soporte, política interna, changelogs. Un modelo entrenado
hace meses no tiene ese conocimiento, adivina cuando no lo tiene y cobra tokens
mientras adivina.

Me encontré una y otra vez con los mismos tres problemas cuando alguien quería
meter un LLM en operaciones diarias o en un chatbot:

1. **Conocimiento congelado.** El modelo sabe lo que se entrenó, no lo que la
   empresa publicó la semana pasada. Cada respuesta sobre datos actuales,
   privados o cambiantes es un volado.
2. **El workaround caro.** El arreglo ingenuo es pegar todo en el prompt.
   Funciona hasta que el set de documentos crece — entonces cada request quema
   un prompt gigante, tarda más, y aun así responde desde la primera sección
   que parece relevante.
3. **Sin prueba.** No se puede distinguir qué afirmación salió de tus datos y
   cuál fue inventada por el modelo para sonar útil.

RAG es el enfoque que concluí que tiene sentido: recuperar solo las partes de
tus propios documentos relevantes a la pregunta, y dejar que el modelo responda
a partir de exactamente esa evidencia. El conocimiento queda en tus documentos
— los actualizás y las respuestas se actualizan con ellos, sin reentrenar, sin
fine-tuning. Y como la respuesta se construye sobre evidencia recuperada, puede
apuntar de vuelta a su fuente.

Quería que el proyecto lo demostrara, no que lo afirmara. Por eso el contraste
está diseñado, pero los números son reales:

- El corpus contiene preguntas con **dos respuestas plausibles** escondidas en
  secciones distintas (p. ej. "Which version is more recent by date, v2.4 or
  v2.8?" — la lista de versiones no es cronológica).
- Las preguntas están escritas para que la recuperación alcance el matiz
  correcto leyendo una fracción del documento. El baseline full-doc lo ve todo
  y puede generalizar o elegir mal, pero ese resultado varía según el modelo y
  la corrida — el contraste siempre medible es el de coste y latencia.
- Ambas ramas de cada comparación se persisten y se agregan, y las dos
  pipelines comparten el mismo modelo, así la demo aísla la **recuperación**,
  no el modelo.

---

## Arquitectura

Dividí el proyecto en tres piezas: un cliente React delgado, un único
orquestador FastAPI y Supabase para storage y analítica. Decidí desde temprano
que solo el backend hablaría con los servicios de IA y la base de datos; el
browser solo presenta archivos, comparaciones y resultados.

**Cliente (React).** El workspace hace tres cosas: loguea al usuario con
Supabase Auth, envía los documentos seleccionados al backend y renderiza cada
comparación junto con el dashboard en vivo. Nunca guarda más que el token de
auth del usuario y la URL del backend.

**Backend (FastAPI).** Cada request llega con un JWT que `auth.py` valida del
lado del servidor; de ahí el trabajo se divide por responsabilidad:

- **Ingesta** (`documents.py`) recibe el upload multipart, aplica el
  presupuesto de 24 KB, extrae y trocea el texto, lo embeddea, y guarda los
  vectores de chunks más el archivo crudo en Storage.
- **La comparación** (`compare.py`) corre ambas pipelines sobre la misma
  pregunta y persiste el resultado — RAG recupera los chunks con mejor match y
  responde a partir de ellos, mientras el baseline full-doc junta todo el
  corpus seleccionado y lo mete en un solo prompt. Dos llamadas al LLM, mismo
  modelo.
- **El dashboard** (`metrics.py`) lee las filas persistidas y las agrega en
  los KPIs en vivo, las queries recientes y el historial de comparaciones.
- **Plomería compartida** (`rag_service.py`, `embeddings.py`) sostiene la
  pipeline retrieve → prompt → generate que ambas ramas reutilizan, más la
  normalización de vectores antes de la búsqueda de similitud.

**Capa de datos (Supabase).** Tres piezas guardan estado: un bucket privado de
Storage con una carpeta por usuario para los archivos originales; Postgres con
pgvector guardando los embeddings de chunks, buscados a través de la función
`match_documents`; y las tablas de analítica (`comparisons`, `queries`) que
alimentan el dashboard.

El flujo es unidireccional: upload → trocear → embeber; luego pregunta →
respuesta RAG o completa → persistir → agregar.

### El baseline honesto

Decidí que la comparación solo tiene sentido si la variable es la recuperación.
Por eso `/v1/compare` hace dos llamadas al LLM por pregunta, ambas con el mismo
modelo de Groq (`openai/gpt-oss-120b`), y la única diferencia es cómo llega el
contexto al modelo. RAG recupera los chunks con mejor match (5 por defecto), y
sus tokens escalan con la recuperación; el baseline full-doc mete todo el corpus
seleccionado textual en el prompt, y sus tokens escalan con el tamaño del
corpus. RAG falla cuando la recuperación no encuentra el chunk correcto; el
baseline falla generalizando a partir de una sección irrelevante. Esos son los
modos de falla detrás del diseño; lo que el dashboard hace visible y medible es
el coste, la latencia y el groundedness.

### Pipeline de ingesta

1. Upload (multipart) → extraer texto (PDF, TXT, MD, JSON, CSV)
2. Chunking de tamaño fijo (1.000 caracteres, overlap de 150, ajuste a límites
   de oración/párrafo)
3. Embeber con `gemini-embedding-001` (1536 dims, normalizados)
4. Guardar en `document_chunks` con índice HNSW de coseno
5. `match_documents` (función SQL, otorgada solo a `service_role`) recupera el
   top-k por similitud de coseno, acotado por `user_id`

---

## Decisiones que defendería

### Mismo modelo en ambas ramas
Una comparación honesta necesita sacar el modelo de la ecuación. Groq
`openai/gpt-oss-120b` impulsa ambas pipelines, y el resultado aísla la
recuperación.

### Presupuesto de tokens: 24.000 caracteres (~6K tokens) por documento y por corpus
Lo aprendí a las malas: el baseline full-doc mete *todo el corpus seleccionado*
en un solo prompt, y Groq limita a 8.000 tokens por minuto — un corpus de más de
~6K tokens se trunca o falla. Apliqué el límite en tres lugares: al subir
(`documents.py`), antes de cualquier llamada al LLM (`compare.py` falla rápido
con `422`) y defensivamente dentro de `run_stuffed` (`rag_service.py`). El
corpus demo — ~20.8 KB, 30 chunks — entra de sobra.

### Groundedness que no cuesta una fortuna
Etiqueto las respuestas `High` / `Medium` / `Low` según la similitud de
recuperación contra umbrales configurables (`0.72`/`0.48`). Solo la banda media
ambigua corre un juez LLM corto, así que la mayoría de las respuestas se
etiquetan gratis.

### Postura de seguridad
- El browser **nunca** tiene la key de service-role; solo el JWT de Supabase
  Auth del usuario, que el backend valida del lado del servidor.
- Los vectores/embeddings solo los escribe el backend con service-role. RLS es
  defensa en profundidad: los inserts en `document_chunks` validan que el
  `user_id` del chunk matchea el documento dueño
  (`004_chunk_ownership_rls.sql`).
- Storage es un bucket privado, una carpeta por usuario; borrar elimina chunks,
  objetos de storage y la fila del documento.

### Contrato camelCase
La API habla camelCase (`storagePath`, `documentIds`) vía alias de Pydantic para
que `app/schemas.py` espeje `src/lib/types.ts` uno a uno y el frontend nunca
traduzca nombres de campos.

### Las métricas dicen la verdad
Decidí que los badges de "cambio" del dashboard solo se renderizan cuando existe
una ventana previa real (`change: null` oculta el badge). Un historial vacío no
muestra **ningún 0% falso**.

---

## Probalo vos mismo

```powershell
# Backend — abrí una terminal en el repo del backend (RagBackendProject)
.\.venv\Scripts\python.exe -m scripts.create_bucket
.\.venv\Scripts\python.exe -m scripts.seed <user_email>        # métricas de ejemplo
.\.venv\Scripts\python.exe -m scripts.seed_corpus <user_email> # el corpus de 30 chunks
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# Frontend — abrí una segunda terminal en el repo hermano (RAGProject)
pnpm install
pnpm run dev
```

Logueate, seleccioná el documento sembrado y probá las tres preguntas ambiguas
en el chat. Mirá tokens/latencia/contexto/groundedness de RAG vs full-doc en
las tarjetas de respuesta, y el refresco del dashboard tras cada comparación.

Instrucciones completas de setup: `README.es.md` (backend) y
`../RAGProject/README.md` (frontend).

---

## Qué hizo falta para que sea honesto

No quería entregar un proyecto que solo funcione en el camino de la demo. Escribí
47 tests unitarios cubriendo auth, manejo de documentos, chunking, el
presupuesto del compare y el filtrado por documentos, la pipeline de
rag_service, groundedness y ambos endpoints de métricas — todos mockeando el
cliente de Supabase, así la suite corre sin ninguna API key live. El frontend
compila con type checking estricto y pasa ESLint. Y recorrí el codebase más de
una vez para eliminar código muerto y una dependencia de gráficos sobrante,
porque nada envejece a un proyecto más rápido que imports muertos que nadie
entiende.