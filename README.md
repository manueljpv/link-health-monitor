# Monitor de Conectividade (link-health-monitor)

**Português** · [English](README.en.md) · [Español (Honduras)](README.es-HN.md)

Um painel que mostra, em tempo real, a saúde de **cada link de internet separadamente**: estado, latência, perda de pacotes, jitter, DNS, velocidade de download e upload, quedas e trocas de link. Roda em um servidor Linux interno, **sem depender de ferramentas de monitoramento externas** e sem instalar nenhuma biblioteca (só o Python padrão e o SQLite).

![Painel](docs/images/painel.png)

## O problema que resolve

Quando a empresa tem dois links de internet com failover, uma reclamação de lentidão muitas vezes é, na verdade, o link principal fora do ar e o tráfego rodando no reserva. Os monitores comuns testam a internet "como a rede a enxerga", então não mostram qual link está bom, qual está ruim e quando a rede trocou de um para o outro.

Este projeto testa **cada link por conta própria, o tempo todo**, mesmo quando o tráfego da rede está passando pelo outro, e guarda o histórico para você responder perguntas como "quantas vezes o link caiu neste mês?", "quanto tempo ficamos no link reserva?" e "estamos recebendo a velocidade contratada?".

## Recursos

- **Estado por link** (online, degradado, offline) com uma regra da maioria: um destino de teste fora do ar vira só um aviso e não derruba o link.
- **Latência, perda, jitter e tempo de DNS** em vários destinos e vários servidores DNS.
- **Teste de velocidade** por tempo (estável e calibrado), com o percentual da velocidade contratada, automático a cada 3 horas e sob demanda pelo botão "Medir agora".
- **Link ativo:** mostra por qual link a rede está saindo e registra cada troca.
- **Quedas e trocas de link** em uma lista colorida, com "há quanto tempo" que sobrevive a reinícios.
- **Relatório mensal:** disponibilidade, qualidade, quedas, velocidade, calendário colorido por dia, visão detalhada de cada dia, card de trocas entre links e exportação em CSV (abre direto no Excel).
- **Modo TV:** tela cheia para uma TV na sala da equipe, com ajuste de margem para TVs que cortam as bordas da imagem.
- **Responsivo:** funciona em notebook, TV e celular.
- **Sem dependências:** um único script Python, um banco SQLite e duas páginas HTML.

## Capturas de tela

Todas as imagens usam dados fictícios.

| Modo TV | Relatório do mês |
|---|---|
| ![Modo TV](docs/images/modo-tv.png) | ![Relatório do mês](docs/images/relatorio-mes.png) |

| Visão do dia | No celular |
|---|---|
| ![Visão do dia](docs/images/relatorio-dia.png) | ![Painel no celular](docs/images/painel-celular.png) |

O painel também tem tema escuro: [`docs/images/painel-escuro.png`](docs/images/painel-escuro.png).

## Como funciona

```
 Servidor Linux ─ eth0: IP principal + IP de teste A + IP de teste B
       │
       ▼
 Firewall/roteador ─ regra por origem: IP A → Link 1,  IP B → Link 2
       │                              │
     Link 1                         Link 2
```

O servidor ganha dois IPs secundários. O firewall fixa cada um em um link, então os testes de um IP saem sempre pelo link correspondente. O coletor testa cada link a cada 10 segundos (ping, DNS e IP público) e, a cada 3 horas, mede a velocidade. Um servidor HTTP embutido entrega o painel e o relatório. Se o firewall desviar um teste para o outro link, o coletor percebe pelo IP público e marca o link como offline, em vez de mostrar um falso "saudável". Detalhes em [`docs/pt-BR/architecture-and-rules.md`](docs/pt-BR/architecture-and-rules.md).

## Pré-requisitos

- Um servidor Linux com **Python 3.9 ou superior** e o comando `ping` com suporte a `-I` (pacote iputils). Testado em Rocky Linux 9 (Python 3.9) e com Python 3.13.
- **Dois IPs livres na LAN**, fora da faixa do DHCP, para serem usados como origem dos testes.
- Um **firewall ou roteador com roteamento por origem** (policy-based routing). Há um exemplo com FortiGate e SD-WAN em [`docs/pt-BR/firewall-example-fortigate.md`](docs/pt-BR/firewall-example-fortigate.md).
- Saída HTTPS liberada para os IPs de teste (os testes usam `speed.cloudflare.com`, `api.ipify.org`, `icanhazip.com`, `checkip.amazonaws.com`, além dos DNS públicos 1.1.1.1, 8.8.8.8 e 9.9.9.9).

## Instalação rápida

O passo a passo completo está em [`docs/pt-BR/deployment-and-rollback.md`](docs/pt-BR/deployment-and-rollback.md). Resumo, como root, a partir da pasta do repositório:

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

Abra `http://IP-DO-SERVIDOR:8080`. O modo TV fica em `/?tv=1` (acrescente `&margem=5` se a TV cortar as bordas) e o relatório em `/relatorio`.

## Como validar

```bash
curl --interface 192.0.2.12 -s https://api.ipify.org    # IP público do Link 1
curl --interface 192.0.2.13 -s https://api.ipify.org    # IP público do Link 2
ss -ltnp | grep 8080                                     # painel no ar
```

Os dois links devem sair por IPs públicos **diferentes** (troque os IPs de exemplo pelos seus). No painel, os dois links devem aparecer online, com DNS respondendo e, depois da primeira medição, com a velocidade.

## Problemas comuns

- **Os dois links mostram o mesmo IP público, ou um link aparece offline mesmo com a internet funcionando.** O firewall está desviando o teste para o outro link ("teste desviado"). Confira se cada IP de teste tem uma regra de roteamento por origem e se a política de saída libera esses IPs.
- **O painel fica em "aguardando" ou dá erro de endereço.** Os IPs de teste não existem na interface. Confira `ip -4 -brief addr` e o serviço `monitor-links-ips.service`.
- **"Falha de DNS" ou "HTTP 403" no teste de velocidade.** O servidor de teste recusa alguns tamanhos de arquivo. O coletor já tenta tamanhos menores (`velocidade_tamanhos_reserva_mb`), mas confira a saída HTTPS dos IPs de teste.
- **A velocidade medida é menor que a contratada.** Aumente `velocidade_conexoes` do link (mais conexões em paralelo) e compare com uma ferramenta de referência. Links sem velocidade garantida variam naturalmente.
- **"Medir agora" responde "aguarde".** É a trava entre medições (`medir_agora_intervalo_s`, padrão 300 s).
- **Os horários do painel estão errados.** O painel usa o relógio do navegador. Confira data, hora e fuso do computador que o abre.
- **O modo TV corta as bordas.** Normalmente é o *overscan* da TV: escolha "Somente varredura" (Just Scan) no formato da imagem ou use `/?tv=1&margem=5`.
- **O selo "LINK ATIVO" demora ao reiniciar.** Leva cerca de 40 s: o coletor confirma o link em uso depois de duas leituras iguais.

## Segurança

O painel, o botão "Medir agora", o relatório e o CSV **não têm login**. Mantenha o acesso restrito à rede interna, de preferência atrás de um proxy reverso que só aceite endereços privados, com um nome no DNS interno (sem registro no DNS público). Os testes de velocidade consomem algumas centenas de MB por medição: considere isso se algum link tiver franquia de dados.

## Aviso: dados fictícios

Todos os endereços IP, nomes, identificadores e valores deste repositório e das imagens são **fictícios**. Os IPs usam as faixas reservadas para documentação (192.0.2.0/24, 198.51.100.0/24 e 203.0.113.0/24) e "Sua Empresa" é um nome de exemplo. Troque tudo pelos valores do seu ambiente. Não publique o seu `config.json` nem o seu `monitor.db`: eles estão no `.gitignore` por esse motivo.

## Documentação

- [Arquitetura e regras de funcionamento](docs/pt-BR/architecture-and-rules.md)
- [Implantação, atualização e reversão](docs/pt-BR/deployment-and-rollback.md)
- [Exemplo de firewall: FortiGate com SD-WAN](docs/pt-BR/firewall-example-fortigate.md)
- [Histórico de versões](CHANGELOG.md)

## Como contribuir

Contribuições são bem-vindas. Abra uma *issue* para relatar um problema ou sugerir uma melhoria (diga o seu firewall, a distribuição Linux e a versão do Python, sem colar IPs ou nomes reais). Para mudar o código, faça um *fork*, crie uma branch e abra um *pull request* explicando o que mudou e como testou. O código é Python padrão e as páginas são HTML com JavaScript puro, sem etapa de build.

## Licença

Distribuído sob a **GNU General Public License v3.0** (GPL-3.0). Veja o arquivo [LICENSE](LICENSE).
Copyright (C) 2026 Manuel Pérez.
