# Monitor de Conectividad (link-health-monitor)

[Português](README.md) · [English](README.en.md) · **Español (Honduras)**

Un panel que muestra, en tiempo real, la salud de **cada enlace de internet por separado**: estado, latencia, pérdida de paquetes, jitter, DNS, velocidad de descarga y de subida, caídas y cambios de enlace. Corre en un servidor Linux interno, **sin depender de herramientas de monitoreo externas** y sin instalar ninguna biblioteca (solo Python estándar y SQLite).

![Painel](docs/images/painel.png)

## El problema que resuelve

Cuando la empresa tiene dos enlaces de internet con failover, una queja de lentitud muchas veces es, en realidad, el enlace principal caído y el tráfico corriendo por el de respaldo. Los monitores comunes prueban internet "como la red la ve", así que no muestran cuál enlace está bien, cuál está mal ni cuándo la red cambió de uno a otro.

Este proyecto prueba **cada enlace por su cuenta, todo el tiempo**, incluso cuando el tráfico de la red está pasando por el otro, y guarda el historial para que usted pueda responder preguntas como "¿cuántas veces se cayó el enlace este mes?", "¿cuánto tiempo estuvimos en el enlace de respaldo?" y "¿estamos recibiendo la velocidad contratada?".

## Características

- **Estado por enlace** (en línea, degradado, fuera de línea) con una regla de mayoría: un destino de prueba caído se convierte solo en un aviso y no tumba el enlace.
- **Latencia, pérdida, jitter y tiempo de DNS** en varios destinos y varios servidores DNS.
- **Prueba de velocidad** por tiempo (estable y calibrada), con el porcentaje de la velocidad contratada, automática cada 3 horas y bajo demanda mediante el botón "Medir ahora" (`Medir agora` en la interfaz).
- **Enlace activo:** muestra por cuál enlace está saliendo la red y registra cada cambio.
- **Caídas y cambios de enlace** en una lista de colores, con "hace cuánto tiempo" que sobrevive a los reinicios.
- **Informe mensual:** disponibilidad, calidad, caídas, velocidad, calendario coloreado por día, vista detallada de cada día, tarjeta de cambios entre enlaces y exportación a CSV (se abre directamente en Excel).
- **Modo TV:** pantalla completa para un televisor en la sala del equipo, con ajuste de margen para televisores que cortan los bordes de la imagen.
- **Adaptable (responsivo):** funciona en laptop, TV y celular.
- **Sin dependencias:** un único script Python, una base de datos SQLite y dos páginas HTML.

## Capturas de pantalla

Todas las imágenes usan datos ficticios.

| Modo TV | Informe del mes |
|---|---|
| ![Modo TV](docs/images/modo-tv.png) | ![Relatório do mês](docs/images/relatorio-mes.png) |

| Vista del día | En el celular |
|---|---|
| ![Visão do dia](docs/images/relatorio-dia.png) | ![Painel no celular](docs/images/painel-celular.png) |

El panel también tiene tema oscuro: [`docs/images/painel-escuro.png`](docs/images/painel-escuro.png).

## Cómo funciona

```
 Servidor Linux ─ eth0: IP principal + IP de teste A + IP de teste B
       │
       ▼
 Firewall/roteador ─ regra por origem: IP A → Link 1,  IP B → Link 2
       │                              │
     Link 1                         Link 2
```

El servidor recibe dos IP secundarias. El firewall fija cada una a un enlace, de modo que las pruebas de una IP salen siempre por el enlace correspondiente. El recolector prueba cada enlace cada 10 segundos (ping, DNS e IP pública) y, cada 3 horas, mide la velocidad. Un servidor HTTP integrado entrega el panel y el informe. Si el firewall desvía una prueba hacia el otro enlace, el recolector lo detecta por la IP pública y marca el enlace como fuera de línea, en lugar de mostrar un falso "saludable". Detalles en [`docs/es-HN/architecture-and-rules.md`](docs/es-HN/architecture-and-rules.md).

## Requisitos previos

- Un servidor Linux con **Python 3.9 o superior** y el comando `ping` con soporte para `-I` (paquete iputils). Probado en Rocky Linux 9 (Python 3.9) y con Python 3.13.
- **Dos IP libres en la LAN**, fuera del rango del DHCP, para usarlas como origen de las pruebas.
- Un **firewall o enrutador con enrutamiento por origen** (policy-based routing). Hay un ejemplo con FortiGate y SD-WAN en [`docs/es-HN/firewall-example-fortigate.md`](docs/es-HN/firewall-example-fortigate.md).
- Salida HTTPS habilitada para las IP de prueba (las pruebas usan `speed.cloudflare.com`, `api.ipify.org`, `icanhazip.com`, `checkip.amazonaws.com`, además de los DNS públicos 1.1.1.1, 8.8.8.8 y 9.9.9.9).

## Instalación rápida

El paso a paso completo está en [`docs/es-HN/deployment-and-rollback.md`](docs/es-HN/deployment-and-rollback.md). Resumen, como root, desde la carpeta del repositorio:

```bash
mkdir -p /opt/monitor-links
cp src/collector.py src/dashboard.html src/relatorio.html /opt/monitor-links/
cp config/config.example.json /opt/monitor-links/config.json
# edite /opt/monitor-links/config.json (nomes, IPs de origem, IP público, velocidades)

cp deploy/*.service /etc/systemd/system/
# edite monitor-links-ips.service (IPs de teste, prefixo e interface)
systemctl daemon-reload
systemctl enable --now monitor-links-ips.service monitor-links.service
```

Abra `http://IP-DO-SERVIDOR:8080`. El modo TV está en `/?tv=1` (agregue `&margem=5` si el televisor corta los bordes) y el informe en `/relatorio`.

## Cómo validar

```bash
curl --interface 192.0.2.12 -s https://api.ipify.org    # IP público do Link 1
curl --interface 192.0.2.13 -s https://api.ipify.org    # IP público do Link 2
ss -ltnp | grep 8080                                     # painel no ar
```

Los dos enlaces deben salir por IP públicas **distintas** (cambie las IP de ejemplo por las suyas). En el panel, los dos enlaces deben aparecer en línea, con el DNS respondiendo y, después de la primera medición, con la velocidad.

## Problemas comunes

- **Los dos enlaces muestran la misma IP pública, o un enlace aparece fuera de línea aunque internet funciona.** El firewall está desviando la prueba hacia el otro enlace ("teste desviado", prueba desviada). Verifique que cada IP de prueba tenga una regla de enrutamiento por origen y que la política de salida permita esas IP.
- **El panel se queda en "aguardando" o muestra un error de dirección.** Las IP de prueba no existen en la interfaz. Revise `ip -4 -brief addr` y el servicio `monitor-links-ips.service`.
- **"Falha de DNS" o "HTTP 403" en la prueba de velocidad.** El servidor de prueba rechaza algunos tamaños de archivo. El recolector ya intenta tamaños menores (`velocidade_tamanhos_reserva_mb`), pero verifique la salida HTTPS de las IP de prueba.
- **La velocidad medida es menor que la contratada.** Aumente `velocidade_conexoes` del enlace (más conexiones en paralelo) y compare con una herramienta de referencia. Los enlaces sin velocidad garantizada varían de forma natural.
- **"Medir agora" responde "aguarde".** Es el bloqueo entre mediciones (`medir_agora_intervalo_s`, valor predeterminado 300 s).
- **Las horas del panel están incorrectas.** El panel usa el reloj del navegador. Revise la fecha, la hora y la zona horaria de la computadora que lo abre.
- **El modo TV corta los bordes.** Normalmente es el *overscan* del televisor: elija "Somente varredura" (Just Scan) en el formato de la imagen o use `/?tv=1&margem=5`.
- **El distintivo "LINK ATIVO" tarda al reiniciar.** Tarda cerca de 40 s: el recolector confirma el enlace en uso después de dos lecturas iguales.

## Seguridad

El panel, el botón "Medir ahora" (`Medir agora`), el informe y el CSV **no tienen inicio de sesión**. Mantenga el acceso restringido a la red interna, de preferencia detrás de un proxy inverso que solo acepte direcciones privadas, con un nombre en el DNS interno (sin registro en el DNS público). Las pruebas de velocidad consumen unos cientos de MB por medición: tenga esto en cuenta si algún enlace tiene límite de datos.

## Aviso: datos ficticios

Todas las direcciones IP, nombres, identificadores y valores de este repositorio y de las imágenes son **ficticios**. Las IP usan los rangos reservados para documentación (192.0.2.0/24, 198.51.100.0/24 y 203.0.113.0/24) y "Sua Empresa" es un nombre de ejemplo. Cambie todo por los valores de su entorno. No publique su `config.json` ni su `monitor.db`: están en el `.gitignore` por ese motivo.

## Documentación

- [Arquitectura y reglas de funcionamiento](docs/es-HN/architecture-and-rules.md)
- [Implementación, actualización y reversión](docs/es-HN/deployment-and-rollback.md)
- [Ejemplo de firewall: FortiGate con SD-WAN](docs/es-HN/firewall-example-fortigate.md)
- [Historial de versiones](CHANGELOG.md)

## Cómo contribuir

Las contribuciones son bienvenidas. Abra un *issue* para reportar un problema o sugerir una mejora (indique su firewall, la distribución de Linux y la versión de Python, sin pegar IP ni nombres reales). Para cambiar el código, haga un *fork*, cree una rama y abra un *pull request* explicando qué cambió y cómo lo probó. El código es Python estándar y las páginas son HTML con JavaScript puro, sin paso de compilación.

## Licencia

Distribuido bajo la **GNU General Public License v3.0** (GPL-3.0). Vea el archivo [LICENSE](LICENSE).
Copyright (C) 2026 Manuel Pérez.
