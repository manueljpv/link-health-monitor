# Exemplo de firewall: FortiGate com SD-WAN

> **Aviso: dados fictícios.** Todos os endereços IP, nomes, identificadores e valores deste documento são exemplos. Os IPs usam as faixas reservadas para documentação (192.0.2.0/24, 198.51.100.0/24 e 203.0.113.0/24). Troque tudo pelos valores do seu ambiente antes de aplicar qualquer comando.

Este documento mostra uma forma de preparar o firewall. O que importa é o resultado: cada IP de teste do servidor precisa sair sempre por um link específico. Qualquer firewall ou roteador com roteamento por origem (policy-based routing) consegue o mesmo.

Valores de exemplo; ajuste nomes e IDs ao seu ambiente.

**O que foi feito:**

1. **Reservas DHCP** no servidor DHCP da LAN, uma para cada IP de teste (endereços MAC fictícios, por exemplo 02:00:00:00:00:12 e 02:00:00:00:00:13). Servem só para o DHCP nunca entregar esses IPs.
2. **Objetos de endereço:** `MON-LINK1` (192.0.2.12/32) e `MON-LINK2` (192.0.2.13/32).
3. **Regras SD-WAN manuais** (por exemplo, IDs 10 e 11): `MON-LINK1` em modo manual no membro do Link 1 e `MON-LINK2` no membro do Link 2, **antes** da regra geral de melhor qualidade.
4. **Permissão de saída:** os dois objetos entram no grupo de endereços `ALLOWED-HOSTS`, origem da política de saída `ALLOW-HOSTS`.

Verificação: `diagnose sys sdwan service4` deve listar as regras manuais antes da regra geral, cada uma com um único membro ativo.

**Como reverter** (na ordem 4, 3, 2, 1; um objeto em uso por regra ou grupo não pode ser apagado):

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

Conferir depois: `diagnose sys sdwan service4` deve mostrar só a regra geral; `show firewall addrgrp ALLOWED-HOSTS | grep MON-` não deve devolver nada.

As alterações só afetam o tráfego dos dois IPs de teste. O restante da rede não é tocado, nem na criação nem na reversão.
