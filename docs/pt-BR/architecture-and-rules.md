# Arquitetura e regras de funcionamento

> **Aviso: dados fictícios.** Todos os endereços IP, nomes, identificadores e valores deste documento são exemplos. Os IPs usam as faixas reservadas para documentação (192.0.2.0/24, 198.51.100.0/24 e 203.0.113.0/24). Troque tudo pelos valores do seu ambiente antes de aplicar qualquer comando.

## Objetivo

Um painel HTML que mostra a saúde de cada link de internet da empresa **separadamente**: estado, latência, perda, jitter, tempo de DNS, velocidade (download e upload), quedas e trocas de link. Não depende de nenhuma ferramenta de monitoramento externa, roda em um servidor Linux interno e só é acessado pela rede interna (equipe de TI e uma TV).

## Arquitetura

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

O servidor ganha dois IPs secundários. O firewall fixa cada IP em um link por meio de regras SD-WAN manuais, então os testes de um IP sempre saem pelo link correspondente, mesmo quando o tráfego normal da rede está usando o outro. O coletor testa cada link a cada 10 s e guarda tudo em um banco SQLite. Uma API HTTP simples alimenta as duas páginas (painel e relatório).

## Ambiente de referência (exemplo)

- **Servidor:** Linux (Rocky Linux 9) em contêiner, IP principal 192.0.2.10/24, gateway 192.0.2.1, DNS interno 192.0.2.53. Python 3.9 ou superior, só biblioteca padrão.
- **Firewall:** FortiGate com FortiOS 7.4, SD-WAN com dois membros (um por link), zona INTERNET.
- **Link 1:** IP público fixo (exemplo 203.0.113.10/30, gateway 203.0.113.9), membro SD-WAN 2.
- **Link 2:** IP recebido por DHCP (exemplo 198.51.100.76) atrás de outro roteador (198.51.100.1), membro SD-WAN 3. O IP público dele pode mudar com o tempo.
- **LAN:** 192.0.2.0/24, servidor DHCP do firewall com reservas.

O coletor fica em `/opt/monitor-links`, fora das pastas de qualquer outro sistema do servidor, para que atualizações dessas aplicações não o afetem.

## Decisões de projeto

- **IPs de teste:** dois IPs livres da LAN, escolhidos fora da faixa do DHCP e reservados no firewall (exemplo: 192.0.2.12 para o Link 1 e 192.0.2.13 para o Link 2). Antes de escolher, confira sempre a lista de reservas do firewall: um ping sem resposta não prova que o IP está livre.
- **Isolamento por link:** o coletor testa cada link usando o IP de origem correspondente (`ping -I`, sockets ligados ao IP). O firewall fixa cada IP em um link.
- **Proteção contra desvio ("teste desviado"):** se o firewall mandar o teste de um link caído pelo outro, o coletor percebe pelo IP público. O Link 1 deve sair por seu IP fixo e o Link 2 não pode sair por esse IP. Em caso de desvio o link é marcado offline, e não saudável por engano.
- **Permissão de saída:** os dois IPs de teste entram em um grupo de endereços que já é origem de uma política de saída para a internet, seguindo o padrão do ambiente.
- **Velocidades contratadas:** informadas no `config.json` por link, com a indicação de que a velocidade é garantida ou não. O upload contratado é opcional.
- **Relatório com duas medidas:** "Disponível" = tempo sem estar offline. "Qualidade boa" = tempo sem estar offline nem degradado.
- **Acesso interno:** o painel e o relatório não têm login. Devem ficar atrás de um proxy reverso restrito à rede interna, com um nome no DNS interno (sem registro no DNS público).

## Regras do coletor

- **Sondas** (a cada 10 s, por link): ping a 1.1.1.1, 8.8.8.8 e 9.9.9.9 em paralelo; consulta DNS em vários servidores; IP público.
- **Estado do link:**
  - *degradado*: só se a **maioria** dos destinos alcançáveis tiver problema (perda ou latência acima do limite do link) em pelo menos 2 das 3 últimas amostras, ou se a maioria dos servidores DNS falhar;
  - *offline*: nenhum destino responde nas 3 últimas amostras, ou o teste foi desviado para outro link.
- **Avisos:** um destino de ping ou servidor DNS isolado fora do ar vira só um *aviso* ("destino X indisponível", "DNS X sem resposta"), com histerese de 3 amostras para entrar e sair. Não pesa contra o estado do link e aparece na lista de eventos.
- **Servidores DNS:** Cloudflare e Google em todos os links, mais servidores extras por link (`dns_extra`), por exemplo os DNS do provedor ou o roteador da frente.
- **IP público:** tenta api.ipify.org, depois icanhazip.com, depois checkip.amazonaws.com.
- **"Há quanto tempo" e "sem quedas há X"** vêm do histórico gravado (tabela de eventos), então não zeram quando o coletor reinicia.
- **Teste de velocidade** (speed.cloudflare.com), por **tempo**: download 10 s e upload 8 s, várias conexões em paralelo (padrão 4; ajustável por link), 2 s iniciais descartados para o link acelerar. Cada conexão pede blocos de 25 MB (download) ou 5 MB e 3 MB (upload) em sequência; se um tamanho for recusado com HTTP 403, tenta tamanhos menores. O teste falha se pelo menos metade das conexões der erro, e o último valor válido é mantido com o horário. Link offline não é testado. Os testes rodam um de cada vez e a coleta de latência pausa durante eles (cerca de 30 s). Frequência automática: a cada 180 min.
- **Medir agora:** botão em cada card (`POST /api/medir?link=NOME`). Trava entre medições do mesmo link configurável em `medir_agora_intervalo_s` (padrão 300 s). Recusa se o link estiver offline ou já houver medição na fila.
- **Percentual do contratado:** campo `contratado` por link (`{"down": 300, "up": null, "garantido": true}`). Limites do link com velocidade garantida: verde a partir de 80%, amarelo de 50% a 80%, vermelho abaixo. Para link não garantido: 60% e 30%.
- **Modo TV** (`/?tv=1`): painel em tela cheia, relógio, curva de latência da última hora e eventos de hoje, com recarga a cada 30 min. O parâmetro `&margem=N` reduz o painel em N% de cada lado, para TVs que cortam as bordas da imagem. O botão "Sair do modo TV" aparece com o mouse ou o toque e some depois de 5 s.
- **Cloudflare e HTTP 403:** o Cloudflare recusa alguns tamanhos de download (por exemplo 15 MB; 1, 5, 10 e 25 MB funcionam). A regra não é documentada, por isso o coletor tem tamanhos de reserva. O monitor depende do Cloudflare para velocidade, DNS e ping; um problema lá aparece como aviso e não derruba o estado do link, por causa da regra da maioria.

## Retenção de dados e relatório

- **30 dias** (`retencao_dias`): amostras detalhadas (a tabela grande) e avisos.
- **Sem limite:** quedas, trocas de link, testes de velocidade e o **resumo diário** por link (tempo online, degradado e offline, quedas, trocas, latência média, p95 e máxima, perda, jitter, DNS, velocidade mínima, média e máxima).
- **Relatório mensal** (`/relatorio`): disponibilidade, qualidade, quedas, latência, perda, velocidade com o percentual do contratado, calendário colorido por dia e tabela diária, mais o card de **trocas entre links** (quantidade por sentido, tempo e percentual de cada link como ativo, maior permanência e lista das trocas). Exportação em CSV (`/api/relatorio.csv?mes=AAAA-MM`), com ponto e vírgula, vírgula decimal e BOM para abrir direto no Excel em português.
- **Visão do dia:** clicar em um dia do calendário abre o resumo, a curva de latência, os eventos, os testes de velocidade e as trocas daquele dia. O endereço guarda o dia (`/relatorio#AAAA-MM-DD`). Para dias com mais de 30 dias a curva de latência não existe mais, mas o resumo, os eventos e os testes continuam.
- **Cálculo:** o tempo monitorado soma os intervalos entre amostras, ignorando lacunas maiores que `max(30, 3 × intervalo)` segundos (coletor parado ou reiniciando). Os dias seguem o fuso do servidor.

## Calibração do teste de velocidade

- O primeiro método (volume fixo de dados) variava até 2× entre medições consecutivas do mesmo link (por exemplo, 100% e 50% do contratado em 5 minutos).
- O teste por tempo, com várias conexões e descarte do início, ficou estável: cinco medições seguidas no link rápido variaram cerca de 5% no download, ficando entre 80% e 90% do valor de uma ferramenta de referência medida em um PC.
- O **upload** varia mais, porque os bytes são contados quando enviados e não quando confirmados, o que pode superestimar um pouco. Contar na confirmação é um refinamento possível (veja o roteiro de melhorias).
- Um link sem velocidade garantida varia naturalmente entre medições, e isso é esperado.
- Cada teste consome algumas centenas de MB no link mais rápido. Considere isso se algum link tiver franquia de dados.

## Pontos de atenção

- A regra SD-WAN geral usa "melhor qualidade por latência" com uma tolerância. Uma oscilação de latência no link principal pode mandar a rede para o outro sem que o principal tenha caído. O histórico de trocas do monitor mostra com que frequência isso acontece. Essa regra não é alterada pelo projeto.
- Ao rodar como serviço, a mensagem inicial "Dashboard em http://..." não aparece no `journalctl` (saída em buffer). Para confirmar que está no ar, use `ss -ltnp | grep 8080`.
- Depois de reiniciar o serviço, o selo "LINK ATIVO" leva cerca de 40 s para aparecer (o coletor confirma o link em uso após duas leituras iguais).
- O botão "Medir agora", o relatório e o CSV não têm login. A trava entre medições limita o abuso, mas o acesso deve ser restrito à rede interna.
- O relatório de um mês só tem dados a partir do dia em que o monitor começou, e os percentuais consideram só o tempo monitorado.
- O exemplo roda o coletor como root. Avalie um usuário dedicado e um firewall no próprio servidor.
- Os horários do painel usam o relógio do navegador. Em um computador de TV, confira data, hora e fuso.
