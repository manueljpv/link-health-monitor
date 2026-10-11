# Roadmap

**Português** · [English](ROADMAP.en.md) · [Español (Honduras)](ROADMAP.es-HN.md)

Este documento mostra para onde o projeto pode ir e o que aprendemos até aqui. Nada abaixo é promessa de data: são intenções, em ordem aproximada de prioridade. Sugestões são bem-vindas por *issue*.

## Curto prazo

- **Alertas por mensagem (Telegram).** Avisar quando um link cair, voltar ou quando a rede trocar de link, com limite para não repetir a mesma mensagem.
- **Rótulos de data no gráfico de latência de 7 dias.** Hoje o eixo mostra só a hora (HH:MM) e, em períodos longos, fica difícil saber de que dia é cada ponto.
- **Contagem do upload na confirmação.** Medir o upload pelo que o servidor de teste confirmou ter recebido, e não pelo que foi enviado, para evitar números otimistas.
- **Usuário de serviço dedicado.** Rodar o coletor com um usuário sem privilégios, em vez de root, mantendo só o necessário para os testes por IP de origem.
- **Testes automatizados** para a lógica de estado (regra da maioria, histerese dos avisos, detecção de "teste desviado"), usando dados de exemplo.

## Médio prazo

- **Interface em vários idiomas.** Hoje a documentação é trilíngue, mas os textos do painel estão em português. Mover os textos para um arquivo de idiomas.
- **Publicação atrás de proxy reverso com nome interno**, restrita a endereços privados, e um exemplo de configuração na documentação.
- **Mais de dois links.** Generalizar a configuração para N links.
- **Exportações extras:** relatório mensal em PDF e métricas em formato compatível com Prometheus.
- **Instalador simples** (script que cria pastas, serviços e valida a instalação).

## Longo prazo

- **Autenticação opcional** no painel e no botão "Medir agora".
- **Exemplos de firewall** para outros fabricantes e para Linux (nftables/iproute2).
- **Pacote para distribuição** (RPM/DEB) e imagem de contêiner.
- **Comparação entre períodos** (mês contra mês) e metas de disponibilidade no relatório.

## Lições aprendidas

1. **Teste cada link separadamente.** Medir "a internet" a partir da rede só mostra o link que está em uso. Para saber a saúde dos dois, cada teste precisa sair de propósito por um link, com roteamento por origem no firewall.
2. **Desconfie de um teste que saiu pelo caminho errado.** Se o firewall desvia o teste, o link "morto" parece saudável. Comparar o IP público de cada teste com o esperado evita esse falso positivo.
3. **Um destino fora do ar não é um link fora do ar.** A regra da maioria e os avisos com histerese de três amostras reduziram muito os falsos alarmes.
4. **Teste de velocidade por tempo, e não por tamanho fixo.** Arquivos pequenos não enchem links rápidos, e servidores de teste recusam alguns tamanhos. Medir por tempo, com vários tamanhos de reserva, deu resultados estáveis.
5. **Guarde o que importa para sempre e o resto por pouco tempo.** Amostras brutas crescem rápido; quedas, trocas e velocidades são poucas e valiosas. Um resumo diário permanente deixou o relatório mensal barato.
6. **Simples ajuda a operar.** Python padrão, SQLite e duas páginas HTML significam nenhuma dependência para atualizar e uma reversão que cabe em dois comandos.
7. **Cuidado com o que o navegador mostra.** O relógio e o fuso do computador que abre o painel mudam os horários exibidos. Em TVs, o *overscan* corta as bordas: o modo TV ganhou margem ajustável.
8. **Painel sem login pede rede restrita.** Por isso a recomendação de proxy reverso interno e de nunca expor o painel à internet.
9. **Documente enquanto faz.** A documentação de reversão, escrita junto com cada mudança, foi o que tornou as atualizações seguras.
