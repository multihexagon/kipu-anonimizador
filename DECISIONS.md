# DECISIONS

## 1. Qué consideramos PII

- **Identificadores directos de personas naturales:** nombre completo y sus variantes (nombre + primer apellido, nombres de pila, en MAYÚSCULAS sin tildes, con `_`, `.` o `-` como en `extracto_manuela_castano.pdf`), primer nombre o apodo cuando la persona ya está en el hilo o registro, correo (incluido el dictado: "juan arroba gmail punto com"), celular, cédula (con y sin puntos), dirección, fecha de nacimiento, placa, pasaporte y usuario interno (`fernanda.vargas` en `pqrs.agente`).
- **Dónde los buscamos:** texto de chats, autor, nombres de adjuntos, título, cuerpo, front matter, comentarios y `<meta>` de HTML, metadatos de PDF, nombres de archivo y **todas** las columnas de texto de las tablas (incluidos `notas`, `descripcion`, `respuesta` y `reporta_a`, que trae el nombre del jefe).
- **Cuasi-identificadores:** ocupación + barrio + año de vinculación. En las tablas, la ocupación pasa a sector ("periodista" → "profesional de medios") y el barrio cambia por otro de la misma ciudad. En el texto, cuando aparece la ocupación de un cliente del contexto, se generaliza junto con su barrio (→ ciudad) y su año (→ "hace unos años").

## 2. Qué conservamos a propósito y por qué

- **Organizaciones, lugares, marcas y figuras públicas** (Bancolombia, Nequi, Superfinanciera, Kipu Pay, Kipi, Plaza Botero, Shakira...): no son personas naturales y son señal útil para entrenar. Se declaran en `entities.json` con `kept: true`. Las frases se conservan completas ("Plaza Botero"), nunca la palabra suelta, porque un apellido que también es lugar sigue siendo apellido cuando nombra a una persona.
- **Llaves y datos de negocio:** `cliente_id`, `tx_id`, radicados, montos, fechas de transacción, canal, estado y ciudad. Así las uniones entre tablas siguen funcionando.
- **El texto no personal, byte a byte:** reemplazamos por spans y nunca reescribimos con un modelo, para conservar el parecido con la salida ideal y no inventar datos.

## 3. Decisiones de diseño (y alternativa descartada)

| Decisión | Descartada | Por qué |
| --- | --- | --- |
| Seudónimo = HMAC(clave secreta, llave de la persona), congelado en disco | Azar con mapa guardado | Con la misma clave, dos corridas, e incluso un disco vacío, dan el mismo `entities.json` byte a byte (verificado). Un nombre ya asignado nunca se reasigna. |
| Llave = id del maestro (`CL-`, `KP-`, uid) | Agrupar por nombre | Los homónimos (10 nombres repetidos en `clientes.csv`) reciben seudónimos distintos. |
| Reglas + registro de personas desde las tablas | LLM de punta a punta | Es determinista, rápido (~28 s el corpus completo) y no reescribe ni inventa datos. 0 tokens de LLM. |
| El seudónimo copia la forma de la mención | Un único nombre fijo | "MANUELA CASTANO" → "SOFIA ZAMBRANO"; `manuela_castano` → `sofia_zambrano`; "Manuela" → "Sofía". Mantiene la utilidad y el formato. |
| Seudónimos que nunca coinciden con valores reales | Solo evitar repetidos | Un nombre falso igual al de otra persona real se contaría como fuga. |
| EC2 + Docker con CloudFormation, autodespliegue desde git | Railway, Render, Lambda | Railway tenía pausados los registros y una caída de builds ese día. Lambda tiene un tope de 15 min por corrida. EC2 no se duerme y conserva el disco. |
| `/anonymize` usa el mismo registro que `/run` | Recalcular por llamada | Una persona ya vista recibe en vivo el mismo seudónimo que en `output/`. |

## 4. Costo

- **Tokens de LLM:** 0. El pipeline no usa modelos.
- **Tiempo:** ~28 s para regenerar el corpus completo (2.999 mensajes, 34 documentos, 7.823 filas), incluidas unas 210 llamadas al API de fuentes con límite de ~9 req/s. `/anonymize` responde en ~0,1 s un lote de prueba.
- **Infraestructura:** una EC2 t3.micro dentro del free tier (`infra/ec2.yaml`).

## 5. Cómo medimos

- Validador oficial (`validar.mjs`) sobre la muestra y sobre el corpus real: OK.
- Tests de la muestra: 13/13. Tests públicos: 5/5 (`scripts/eval_tests.py`, un evaluador local aproximado).
- Barrido de fugas: se busca cada nombre, correo y celular real de las tablas en toda la salida.
- Estabilidad: dos corridas con distinto `PYTHONHASHSEED` y una con el disco vacío producen el mismo `entities.json`.

## 6. Limitaciones conocidas

- Una persona que no está en las tablas se detecta por una lista de nombres de pila o por una presentación explícita ("soy...", "me llamo..."). Un nombre poco común sin esas pistas puede escaparse.
- Dos personas nuevas con el mismo nombre y sin otro identificador quedan fusionadas en `/anonymize`.
- No hay OCR de imágenes dentro de los PDF.
