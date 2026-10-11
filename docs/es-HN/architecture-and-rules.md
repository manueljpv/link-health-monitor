# Arquitectura y reglas de funcionamiento

> **Aviso: datos ficticios.** Todas las direcciones IP, nombres, identificadores y valores de este documento son ejemplos. Las IP usan los rangos reservados para documentación (192.0.2.0/24, 198.51.100.0/24 y 203.0.113.0/24). Cambie todo por los valores de su entorno antes de aplicar cualquier comando.

## Objetivo

Un panel HTML que muestra la salud de cada enlace de internet de la empresa **por separado**: estado, latencia, pérdida, jitter, tiempo de DNS, velocidad (descarga y subida), caídas y cambios de enlace. No depende de ninguna herramienta de monitoreo externa, corre en un servidor Linux interno y solo se accede desde la red interna (equipo de TI y un televisor).

## Arquitectura

```
                       ┌───────────────────────────────┐
  Servidor Linux       │ eth0: IP principal            │
  (coletor + painel)   │       IP de teste A (Link 1)  │
                       │       IP de teste B (Link 2)  │
                       └──────────────┬────────────────┘
                                      │ LAN
                       ┌──────────────▼────────────────┐
  Firewall com SD-WAN  │ regra manual: IP A → Link 1   │
                       │ regra manual: IP B → Link 2   │
                       │ demais hosts: regra normal    │
                       └───────┬───────────────┬───────┘
                               │ Link 1        │ Link 2
                            Internet        Internet
```

El servidor recibe dos IP secundarias. El firewall fija cada IP a un enlace mediante reglas SD-WAN manuales, de modo que las pruebas de una IP siempre salen por el enlace correspondiente, incluso cuando el tráfico normal de la red está usando el otro. El recolector prueba cada enlace cada 10 s y guarda todo en una base de datos SQLite. Una API HTTP sencilla alimenta las dos páginas (panel e informe).

## Entorno de referencia (ejemplo)

- **Servidor:** Linux (Rocky Linux 9) en contenedor, IP principal 192.0.2.10/24, gateway 192.0.2.1, DNS interno 192.0.2.53. Python 3.9 o superior, solo biblioteca estándar.
- **Firewall:** FortiGate con FortiOS 7.4, SD-WAN con dos miembros (uno por enlace), zona INTERNET.
- **Link 1:** IP pública fija (ejemplo 203.0.113.10/30, gateway 203.0.113.9), miembro SD-WAN 2.
- **Link 2:** IP recibida por DHCP (ejemplo 198.51.100.76) detrás de otro enrutador (198.51.100.1), miembro SD-WAN 3. Su IP pública puede cambiar con el tiempo.
- **LAN:** 192.0.2.0/24, servidor DHCP del firewall con reservas.

El recolector queda en `/opt/monitor-links`, fuera de las carpetas de cualquier otro sistema del servidor, para que las actualizaciones de esas aplicaciones no lo afecten.

## Decisiones de diseño

- **IP de prueba:** dos IP libres de la LAN, elegidas fuera del rango del DHCP y reservadas en el firewall (ejemplo: 192.0.2.12 para el Link 1 y 192.0.2.13 para el Link 2). Antes de elegir, revise siempre la lista de reservas del firewall: un ping sin respuesta no prueba que la IP esté libre.
- **Aislamiento por enlace:** el recolector prueba cada enlace usando la IP de origen correspondiente (`ping -I`, sockets enlazados a la IP). El firewall fija cada IP a un enlace.
- **Protección contra desvío ("teste desviado", prueba desviada):** si el firewall envía la prueba de un enlace caído por el otro, el recolector lo detecta por la IP pública. El Link 1 debe salir por su IP fija y el Link 2 no puede salir por esa IP. En caso de desvío, el enlace se marca como fuera de línea, y no como saludable por error.
- **Permiso de salida:** las dos IP de prueba entran en un grupo de direcciones que ya es origen de una política de salida a internet, siguiendo el patrón del entorno.
- **Velocidades contratadas:** se indican en el `config.json` por enlace, junto con la indicación de si la velocidad es garantizada o no. La subida contratada es opcional.
- **Informe con dos medidas:** "Disponible" = tiempo sin estar fuera de línea. "Calidad buena" = tiempo sin estar fuera de línea ni degradado.
- **Acceso interno:** el panel y el informe no tienen inicio de sesión. Deben quedar detrás de un proxy inverso restringido a la red interna, con un nombre en el DNS interno (sin registro en el DNS público).

## Reglas del recolector

- **Sondas** (cada 10 s, por enlace): ping a 1.1.1.1, 8.8.8.8 y 9.9.9.9 en paralelo; consulta DNS en varios servidores; IP pública.
- **Estado del enlace:**
  - *degradado*: solo si la **mayoría** de los destinos alcanzables tiene problema (pérdida o latencia por encima del límite del enlace) en al menos 2 de las 3 últimas muestras, o si la mayoría de los servidores DNS falla;
  - *fuera de línea*: ningún destino responde en las 3 últimas muestras, o la prueba fue desviada hacia otro enlace.
- **Avisos:** un destino de ping o servidor DNS aislado que esté caído se convierte solo en un *aviso* ("destino X indisponível", "DNS X sem resposta"), con histéresis de 3 muestras para entrar y salir. No pesa en el estado del enlace y aparece en la lista de eventos.
- **Servidores DNS:** Cloudflare y Google en todos los enlaces, más servidores adicionales por enlace (`dns_extra`), por ejemplo los DNS del proveedor o el enrutador de enfrente.
- **IP pública:** intenta api.ipify.org, luego icanhazip.com, luego checkip.amazonaws.com.
- **"Hace cuánto tiempo" y "sin caídas desde hace X"** provienen del historial grabado (tabla de eventos), por lo que no se reinician cuando el recolector se reinicia.
- **Prueba de velocidad** (speed.cloudflare.com), por **tiempo**: descarga 10 s y subida 8 s, varias conexiones en paralelo (predeterminado 4; ajustable por enlace), 2 s iniciales descartados para que el enlace se acelere. Cada conexión pide bloques de 25 MB (descarga) o 5 MB y 3 MB (subida) en secuencia; si un tamaño es rechazado con HTTP 403, intenta tamaños menores. La prueba falla si al menos la mitad de las conexiones da error, y el último valor válido se conserva con su hora. Un enlace fuera de línea no se prueba. Las pruebas corren una a la vez y la recolección de latencia se pausa durante ellas (cerca de 30 s). Frecuencia automática: cada 180 min.
- **Medir ahora** (`Medir agora` en la interfaz): botón en cada tarjeta (`POST /api/medir?link=NOME`). El bloqueo entre mediciones del mismo enlace se configura en `medir_agora_intervalo_s` (predeterminado 300 s). Se rechaza si el enlace está fuera de línea o ya hay una medición en la cola.
- **Porcentaje de lo contratado:** campo `contratado` por enlace (`{"down": 300, "up": null, "garantido": true}`). Límites del enlace con velocidad garantizada: verde desde 80%, amarillo de 50% a 80%, rojo por debajo. Para un enlace no garantizado: 60% y 30%.
- **Modo TV** (`/?tv=1`): panel en pantalla completa, reloj, curva de latencia de la última hora y eventos de hoy, con recarga cada 30 min. El parámetro `&margem=N` reduce el panel en N% de cada lado, para televisores que cortan los bordes de la imagen. El botón "Sair do modo TV" (salir del modo TV) aparece al mover el mouse o al tocar la pantalla y desaparece después de 5 s.
- **Cloudflare y HTTP 403:** Cloudflare rechaza algunos tamaños de descarga (por ejemplo 15 MB; 1, 5, 10 y 25 MB funcionan). La regla no está documentada, por eso el recolector tiene tamaños de reserva. El monitor depende de Cloudflare para velocidad, DNS y ping; un problema ahí aparece como aviso y no tumba el estado del enlace, gracias a la regla de mayoría.

## Retención de datos e informe

- **30 días** (`retencao_dias`): muestras detalladas (la tabla grande) y avisos.
- **Sin límite:** caídas, cambios de enlace, pruebas de velocidad y el **resumen diario** por enlace (tiempo en línea, degradado y fuera de línea, caídas, cambios, latencia promedio, p95 y máxima, pérdida, jitter, DNS, velocidad mínima, promedio y máxima).
- **Informe mensual** (`/relatorio`): disponibilidad, calidad, caídas, latencia, pérdida, velocidad con el porcentaje de lo contratado, calendario coloreado por día y tabla diaria, además de la tarjeta de **cambios entre enlaces** (cantidad por sentido, tiempo y porcentaje de cada enlace como activo, mayor permanencia y lista de los cambios). Exportación a CSV (`/api/relatorio.csv?mes=AAAA-MM`), con punto y coma, coma decimal y BOM para abrir directamente en Excel en portugués.
- **Vista del día:** al hacer clic en un día del calendario se abre el resumen, la curva de latencia, los eventos, las pruebas de velocidad y los cambios de ese día. La dirección guarda el día (`/relatorio#AAAA-MM-DD`). Para días con más de 30 días de antigüedad la curva de latencia ya no existe, pero el resumen, los eventos y las pruebas continúan.
- **Cálculo:** el tiempo monitoreado suma los intervalos entre muestras, ignorando lagunas mayores que `max(30, 3 × intervalo)` segundos (recolector detenido o reiniciándose). Los días siguen la zona horaria del servidor.

## Calibración de la prueba de velocidad

- El primer método (volumen fijo de datos) variaba hasta 2× entre mediciones consecutivas del mismo enlace (por ejemplo, 100% y 50% de lo contratado en 5 minutos).
- La prueba por tiempo, con varias conexiones y descarte del inicio, quedó estable: cinco mediciones seguidas en el enlace rápido variaron cerca de 5% en la descarga, quedando entre 80% y 90% del valor de una herramienta de referencia medida en una PC.
- La **subida** varía más, porque los bytes se cuentan cuando se envían y no cuando se confirman, lo que puede sobrestimar un poco. Contar en la confirmación es un refinamiento posible (vea la hoja de ruta de mejoras).
- Un enlace sin velocidad garantizada varía naturalmente entre mediciones, y eso es lo esperado.
- Cada prueba consume unos cientos de MB en el enlace más rápido. Tenga esto en cuenta si algún enlace tiene límite de datos.

## Puntos de atención

- La regla SD-WAN general usa "mejor calidad por latencia" con una tolerancia. Una oscilación de latencia en el enlace principal puede mandar la red al otro sin que el principal se haya caído. El historial de cambios del monitor muestra con qué frecuencia ocurre esto. Esta regla no es modificada por el proyecto.
- Al correr como servicio, el mensaje inicial "Dashboard em http://..." no aparece en el `journalctl` (salida con búfer). Para confirmar que está en línea, use `ss -ltnp | grep 8080`.
- Después de reiniciar el servicio, el distintivo "LINK ATIVO" tarda cerca de 40 s en aparecer (el recolector confirma el enlace en uso después de dos lecturas iguales).
- El botón "Medir ahora" (`Medir agora`), el informe y el CSV no tienen inicio de sesión. El bloqueo entre mediciones limita el abuso, pero el acceso debe restringirse a la red interna.
- El informe de un mes solo tiene datos desde el día en que el monitor comenzó, y los porcentajes consideran solo el tiempo monitoreado.
- El ejemplo corre el recolector como root. Evalúe un usuario dedicado y un firewall en el propio servidor.
- Las horas del panel usan el reloj del navegador. En una computadora de TV, revise la fecha, la hora y la zona horaria.
