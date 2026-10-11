# Implementación, actualización y reversión

> **Aviso: datos ficticios.** Todas las direcciones IP, nombres, identificadores y valores de este documento son ejemplos. Las IP usan los rangos reservados para documentación (192.0.2.0/24, 198.51.100.0/24 y 203.0.113.0/24). Cambie todo por los valores de su entorno antes de aplicar cualquier comando.

## Instalación paso a paso

Requisito previo: preparar el firewall con dos IP de prueba libres y las reglas de enrutamiento por origen (vea `firewall-example-fortigate.md`).

1. En el servidor, cree la carpeta y copie los archivos (como root, desde la carpeta del repositorio):

   ```
   mkdir -p /opt/monitor-links
   cp src/collector.py src/dashboard.html src/relatorio.html /opt/monitor-links/
   cp config/config.example.json /opt/monitor-links/config.json
   ```

2. Edite `/opt/monitor-links/config.json`: nombre de la organización, nombres de los enlaces, `ip_origem` (las IP de prueba), `ip_publico_esperado` del enlace de IP fija (y `ip_publico_proibido` en el otro), límites de aviso, velocidades contratadas y DNS adicionales del proveedor.
3. Copie las unidades systemd, ajuste las IP, el prefijo y la interfaz en `monitor-links-ips.service` y active los dos servicios:

   ```
   cp deploy/*.service /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now monitor-links-ips.service
   systemctl enable --now monitor-links.service
   ```

4. Confirme las IP y el puerto y abra el panel en el navegador:

   ```
   ip -4 -brief addr show eth0
   ss -ltnp | grep 8080
   ```

   Panel en `http://IP-DO-SERVIDOR:8080`, modo TV en `/?tv=1` e informe en `/relatorio`.
5. Haga la validación (sección siguiente).
6. Restrinja el acceso a la red interna (vea los puntos de atención en `architecture-and-rules.md`).

## Qué hace la instalación en el servidor, actualización y reversión

**Lo que se hizo:**

1. **Servicio `monitor-links-ips.service`:** en cada arranque agrega las dos IP de prueba a la interfaz de red como IP secundarias. La IP principal y el tráfico normal del servidor no cambian. Se usa un servicio systemd, y no la configuración de red del sistema, para que el hipervisor o el administrador de red no deshaga las IP.
2. **Recolector** en `/opt/monitor-links` (`collector.py`, `dashboard.html`, `relatorio.html`, `config.json`) y servicio `monitor-links.service`: inicia después del servicio de IP y se reinicia solo en caso de falla. Escucha en `0.0.0.0:8080`.

**Actualizar** (como root, dentro de `/opt/monitor-links`):

```
ls -l <pacote>.tar.gz
tar xzf <pacote>.tar.gz --strip-components=1
chown -R root:root /opt/monitor-links
systemctl restart monitor-links      # só se collector.py ou config.json mudou
```

Los paquetes de actualización **no incluyen el `config.json`**, porque este guarda los ajustes locales (DNS adicionales, velocidades contratadas). `dashboard.html` y `relatorio.html` se leen del disco en cada acceso: cambiar esos archivos no requiere reiniciar. El recolector actualiza la base de datos por sí solo, sin borrar el historial.

**Revertir el recolector** (como root):

```
systemctl disable --now monitor-links
rm /etc/systemd/system/monitor-links.service
systemctl daemon-reload
rm -rf /opt/monitor-links
ss -ltnp | grep 8080          # não deve devolver nada
```

Atención: borrar `/opt/monitor-links` también borra el historial (`monitor.db`, que incluye los resúmenes mensuales) y el `config.json`. Antes, copie:

```
cp /opt/monitor-links/monitor.db /root/monitor-links-backup.db
cp /opt/monitor-links/config.json /root/monitor-links-config-backup.json
```

Recomendación: copiar el `monitor.db` de vez en cuando, porque pasa a ser el único registro de largo plazo de la calidad de los enlaces.

**Revertir las IP de prueba** (como root):

```
systemctl disable --now monitor-links-ips.service
rm /etc/systemd/system/monitor-links-ips.service
systemctl daemon-reload
ip -4 -brief addr show eth0      # deve mostrar só o IP principal
```

## Validación

Desde el servidor, usando cada IP de prueba como origen:

```
curl --interface 192.0.2.12 -s https://api.ipify.org     # deve mostrar o IP público do Link 1
curl --interface 192.0.2.13 -s https://api.ipify.org     # deve mostrar o IP público do Link 2
ping -I 192.0.2.12 -c 3 1.1.1.1
ping -I 192.0.2.13 -c 3 1.1.1.1
```

Los dos enlaces deben salir por IP públicas **distintas**. Después, `ss -ltnp | grep 8080` muestra el panel en línea y la página de inicio debe mostrar los dos enlaces en línea, con el DNS respondiendo en todos los servidores.
