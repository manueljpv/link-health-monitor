# Implantação, atualização e reversão

> **Aviso: dados fictícios.** Todos os endereços IP, nomes, identificadores e valores deste documento são exemplos. Os IPs usam as faixas reservadas para documentação (192.0.2.0/24, 198.51.100.0/24 e 203.0.113.0/24). Troque tudo pelos valores do seu ambiente antes de aplicar qualquer comando.

## Instalação passo a passo

Pré-requisito: preparar o firewall com dois IPs de teste livres e as regras de roteamento por origem (veja `firewall-example-fortigate.md`).

1. No servidor, crie a pasta e copie os arquivos (como root, a partir da pasta do repositório):

   ```
   mkdir -p /opt/monitor-links
   cp src/collector.py src/dashboard.html src/relatorio.html /opt/monitor-links/
   cp config/config.example.json /opt/monitor-links/config.json
   ```

2. Edite `/opt/monitor-links/config.json`: nome da organização, nomes dos links, `ip_origem` (os IPs de teste), `ip_publico_esperado` do link de IP fixo (e `ip_publico_proibido` no outro), limites de aviso, velocidades contratadas e DNS extras do provedor.
3. Copie as unidades systemd, ajuste os IPs, o prefixo e a interface em `monitor-links-ips.service` e ative os dois serviços:

   ```
   cp deploy/*.service /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now monitor-links-ips.service
   systemctl enable --now monitor-links.service
   ```

4. Confirme os IPs e a porta e abra o painel no navegador:

   ```
   ip -4 -brief addr show eth0
   ss -ltnp | grep 8080
   ```

   Painel em `http://IP-DO-SERVIDOR:8080`, modo TV em `/?tv=1` e relatório em `/relatorio`.
5. Faça a validação (seção abaixo).
6. Restrinja o acesso à rede interna (veja os pontos de atenção em `architecture-and-rules.md`).

## O que a instalação faz no servidor, atualização e reversão

**O que foi feito:**

1. **Serviço `monitor-links-ips.service`:** a cada boot adiciona os dois IPs de teste à interface de rede como IPs secundários. O IP principal e o tráfego normal do servidor não mudam. Usa um serviço systemd, e não a configuração de rede do sistema, para que o hipervisor ou o gerenciador de rede não desfaça os IPs.
2. **Coletor** em `/opt/monitor-links` (`collector.py`, `dashboard.html`, `relatorio.html`, `config.json`) e serviço `monitor-links.service`: inicia depois do serviço de IPs e reinicia sozinho em caso de falha. Escuta em `0.0.0.0:8080`.

**Atualizar** (como root, dentro de `/opt/monitor-links`):

```
ls -l <pacote>.tar.gz
tar xzf <pacote>.tar.gz --strip-components=1
chown -R root:root /opt/monitor-links
systemctl restart monitor-links      # só se collector.py ou config.json mudou
```

Os pacotes de atualização **não incluem o `config.json`**, porque ele guarda os ajustes locais (DNS extras, velocidades contratadas). `dashboard.html` e `relatorio.html` são lidos do disco a cada acesso: trocar esses arquivos não exige reiniciar. O coletor atualiza o banco sozinho, sem apagar o histórico.

**Reverter o coletor** (como root):

```
systemctl disable --now monitor-links
rm /etc/systemd/system/monitor-links.service
systemctl daemon-reload
rm -rf /opt/monitor-links
ss -ltnp | grep 8080          # não deve devolver nada
```

Atenção: apagar `/opt/monitor-links` apaga também o histórico (`monitor.db`, que inclui os resumos mensais) e o `config.json`. Antes, copie:

```
cp /opt/monitor-links/monitor.db /root/monitor-links-backup.db
cp /opt/monitor-links/config.json /root/monitor-links-config-backup.json
```

Recomendação: copiar o `monitor.db` de tempos em tempos, porque ele passa a ser o único registro de longo prazo da qualidade dos links.

**Reverter os IPs de teste** (como root):

```
systemctl disable --now monitor-links-ips.service
rm /etc/systemd/system/monitor-links-ips.service
systemctl daemon-reload
ip -4 -brief addr show eth0      # deve mostrar só o IP principal
```

## Validação

Do servidor, usando cada IP de teste como origem:

```
curl --interface 192.0.2.12 -s https://api.ipify.org     # deve mostrar o IP público do Link 1
curl --interface 192.0.2.13 -s https://api.ipify.org     # deve mostrar o IP público do Link 2
ping -I 192.0.2.12 -c 3 1.1.1.1
ping -I 192.0.2.13 -c 3 1.1.1.1
```

Os dois links devem sair por IPs públicos **diferentes**. Depois, `ss -ltnp | grep 8080` mostra o painel no ar e a página inicial deve mostrar os dois links online, com DNS respondendo em todos os servidores.
