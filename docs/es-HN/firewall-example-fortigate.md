# Ejemplo de firewall: FortiGate con SD-WAN

> **Aviso: datos ficticios.** Todas las direcciones IP, nombres, identificadores y valores de este documento son ejemplos. Las IP usan los rangos reservados para documentación (192.0.2.0/24, 198.51.100.0/24 y 203.0.113.0/24). Cambie todo por los valores de su entorno antes de aplicar cualquier comando.

Este documento muestra una forma de preparar el firewall. Lo que importa es el resultado: cada IP de prueba del servidor debe salir siempre por un enlace específico. Cualquier firewall o enrutador con enrutamiento por origen (policy-based routing) logra lo mismo.

Valores de ejemplo; ajuste nombres e IDs a su entorno.

**Lo que se hizo:**

1. **Reservas DHCP** en el servidor DHCP de la LAN, una para cada IP de prueba (direcciones MAC ficticias, por ejemplo 02:00:00:00:00:12 y 02:00:00:00:00:13). Sirven solo para que el DHCP nunca entregue esas IP.
2. **Objetos de dirección:** `MON-LINK1` (192.0.2.12/32) y `MON-LINK2` (192.0.2.13/32).
3. **Reglas SD-WAN manuales** (por ejemplo, IDs 10 y 11): `MON-LINK1` en modo manual en el miembro del Link 1 y `MON-LINK2` en el miembro del Link 2, **antes** de la regla general de mejor calidad.
4. **Permiso de salida:** los dos objetos entran en el grupo de direcciones `ALLOWED-HOSTS`, origen de la política de salida `ALLOW-HOSTS`.

Verificación: `diagnose sys sdwan service4` debe listar las reglas manuales antes de la regla general, cada una con un único miembro activo.

**Cómo revertir** (en el orden 4, 3, 2, 1; un objeto en uso por una regla o grupo no puede borrarse):

```
# 4. Retirar só os dois membros do grupo (o grupo é de outros equipamentos e não deve ser apagado)
config firewall addrgrp
    edit "ALLOWED-HOSTS"
        unselect member "MON-LINK1" "MON-LINK2"
    next
end

# 3 e 2. Regras SD-WAN e objetos (só depois do passo 4)
config system sdwan
    config service
        delete 10
        delete 11
    end
end
config firewall address
    delete "MON-LINK1"
    delete "MON-LINK2"
end

# 1. Reservas DHCP (só depois que o monitor deixar de usar esses IPs; use os seus IDs)
config system dhcp server
    edit <id-do-servidor-dhcp>
        config reserved-address
            delete <id-reserva-1>
            delete <id-reserva-2>
        end
    next
end
```

Verificar después: `diagnose sys sdwan service4` debe mostrar solo la regla general; `show firewall addrgrp ALLOWED-HOSTS | grep MON-` no debe devolver nada.

Los cambios solo afectan el tráfico de las dos IP de prueba. El resto de la red no se toca, ni en la creación ni en la reversión.
