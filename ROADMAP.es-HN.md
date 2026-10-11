# Hoja de ruta

[Português](ROADMAP.md) · [English](ROADMAP.en.md) · **Español (Honduras)**

Este documento muestra hacia dónde puede ir el proyecto y lo que hemos aprendido hasta ahora. Nada de lo siguiente es una promesa de fecha: son intenciones, en orden aproximado de prioridad. Las sugerencias son bienvenidas mediante un *issue*.

## Corto plazo

- **Alertas por mensaje (Telegram).** Avisar cuando un enlace se caiga, regrese o cuando la red cambie de enlace, con un límite para no repetir el mismo mensaje.
- **Etiquetas de fecha en el gráfico de latencia de 7 días.** Hoy el eje muestra solo la hora (HH:MM) y, en períodos largos, es difícil saber a qué día pertenece cada punto.
- **Conteo de la subida en la confirmación.** Medir la subida por lo que el servidor de prueba confirmó haber recibido, y no por lo que se envió, para evitar cifras optimistas.
- **Usuario de servicio dedicado.** Ejecutar el recolector con un usuario sin privilegios en lugar de root, conservando solo lo necesario para las pruebas por IP de origen.
- **Pruebas automatizadas** para la lógica de estado (regla de la mayoría, histéresis de los avisos, detección de "prueba desviada") usando datos de ejemplo.

## Mediano plazo

- **Interfaz en varios idiomas.** La documentación ya es trilingüe, pero los textos del panel están en portugués. Mover los textos a un archivo de idiomas.
- **Publicación detrás de un proxy inverso con nombre interno**, restringida a direcciones privadas, con un ejemplo de configuración en la documentación.
- **Más de dos enlaces.** Generalizar la configuración a N enlaces.
- **Exportaciones adicionales:** reporte mensual en PDF y métricas en un formato compatible con Prometheus.
- **Instalador sencillo** (un script que cree carpetas y servicios y valide la instalación).

## Largo plazo

- **Autenticación opcional** en el panel y en el botón "Medir ahora".
- **Ejemplos de firewall** para otros fabricantes y para Linux (nftables/iproute2).
- **Paquetes de distribución** (RPM/DEB) e imagen de contenedor.
- **Comparación entre períodos** (mes contra mes) y metas de disponibilidad en el reporte.

## Lecciones aprendidas

1. **Pruebe cada enlace por separado.** Medir "el internet" desde la red solo muestra el enlace en uso. Para conocer la salud de ambos, cada prueba debe salir a propósito por un enlace, con enrutamiento por origen en el firewall.
2. **Desconfíe de una prueba que salió por el camino equivocado.** Si el firewall desvía la prueba, el enlace "caído" parece sano. Comparar la IP pública de cada prueba con la esperada evita ese falso positivo.
3. **Un destino caído no es un enlace caído.** La regla de la mayoría y los avisos con histéresis de tres muestras redujeron mucho las falsas alarmas.
4. **Prueba de velocidad por tiempo, no por tamaño fijo.** Los archivos pequeños no llenan enlaces rápidos, y los servidores de prueba rechazan algunos tamaños. Medir por tiempo, con varios tamaños de respaldo, dio resultados estables.
5. **Guarde lo importante para siempre y el resto por poco tiempo.** Las muestras crudas crecen rápido; las caídas, los cambios y las velocidades son pocos y valiosos. Un resumen diario permanente hizo barato el reporte mensual.
6. **Lo sencillo es más fácil de operar.** Python estándar, SQLite y dos páginas HTML significan cero dependencias que actualizar y una reversión que cabe en dos comandos.
7. **Cuidado con lo que muestra el navegador.** El reloj y la zona horaria de la computadora que abre el panel cambian las horas mostradas. En las TV, el *overscan* recorta los bordes: el modo TV ganó un margen ajustable.
8. **Un panel sin inicio de sesión requiere una red restringida.** De ahí la recomendación de un proxy inverso interno y de nunca exponer el panel a internet.
9. **Documente mientras trabaja.** La documentación de reversión, escrita junto con cada cambio, fue lo que hizo seguras las actualizaciones.
