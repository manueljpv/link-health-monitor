#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Manuel Pérez
"""Monitor de saúde de links de internet (dois ou mais links testados em paralelo) v4.6. Só biblioteca padrão. Linux."""
import datetime, json, os, re, socket, sqlite3, ssl, struct, subprocess, sys, threading, time, random
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(BASE, sys.argv[1] if len(sys.argv) > 1 else "config.json")))
DB = os.path.join(BASE, "monitor.db")
lock = threading.Lock()
STATE = {}      # estado atual por link
ACTIVE = {"link": None, "ip": None}

def db():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("pragma journal_mode=wal")
    return c

def init_db():
    c = db()
    c.executescript("""
    create table if not exists samples(ts int, link text, loss real, rtt real, jitter real, dns real, pub text);
    create index if not exists i_s on samples(link, ts);
    create table if not exists events(ts int, link text, kind text, detail text);
    create table if not exists speed(ts int, link text, down real, up real);
    create table if not exists daily(day text, link text, mon_s int, online_s int, degr_s int, off_s int, quedas int, failovers int,
      n int, rtt_avg real, rtt_p95 real, rtt_max real, loss_avg real, jitter_avg real, dns_avg real,
      n_speed int, down_min real, down_avg real, down_max real, up_min real, up_avg real, up_max real,
      primary key(day, link));
    """)
    try: c.execute("alter table samples add column state text")      # estado do link em cada amostra (para o relatório)
    except sqlite3.OperationalError: pass
    # meta: guarda o instante em que o monitor começou a coletar (base para o tempo em cada link ativo)
    c.execute("create table if not exists meta(k text primary key, v text)")
    if not c.execute("select 1 from meta where k='inicio'").fetchone():
        r = c.execute("select min(ts) from samples").fetchone()[0]
        c.execute("insert into meta values('inicio', ?)", (str(int(r or time.time())),))
    c.commit(); c.close()

def event(link, kind, detail):
    c = db(); c.execute("insert into events values(?,?,?,?)", (int(time.time()), link, kind, detail)); c.commit(); c.close()

# ---------- sondas ----------
def ping(src, dst, n=3):
    try:
        out = subprocess.run(["ping", "-n", "-c", str(n), "-i", "0.3", "-W", "1", "-I", src, dst],
                             capture_output=True, text=True, timeout=n * 2 + 3).stdout
    except Exception:
        return 100.0, None, None
    m = re.search(r"([\d.]+)% packet loss", out)
    loss = float(m.group(1)) if m else 100.0
    r = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", out)
    if r and loss < 100:
        return loss, float(r.group(2)), float(r.group(4))
    return loss, None, None

def dns_time(src, server, name):
    q = struct.pack(">HHHHHH", random.randint(0, 65535), 0x0100, 1, 0, 0, 0)
    for p in name.split("."):
        q += bytes([len(p)]) + p.encode()
    q += b"\x00" + struct.pack(">HH", 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2); s.bind((src, 0))
    try:
        t = time.time(); s.sendto(q, (server, 53)); s.recv(512)
        return (time.time() - t) * 1000
    except Exception:
        return None
    finally:
        s.close()

def https_conn(host, src=None, timeout=8):
    sock = socket.create_connection((host, 443), timeout, source_address=(src, 0) if src else None)
    return ssl.create_default_context().wrap_socket(sock, server_hostname=host)

def http_get(host, path, src=None, limit=None, timeout=8):
    s = https_conn(host, src, timeout)
    s.sendall(f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: monitor\r\nConnection: close\r\n\r\n".encode())
    data = b""; t0 = time.time()
    while True:
        b = s.recv(65536)
        if not b: break
        data += b
        if limit and len(data) > limit: break
    s.close()
    return data, time.time() - t0

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IP_PROVEDORES = [("api.ipify.org", "/"), ("icanhazip.com", "/"), ("checkip.amazonaws.com", "/")]

def public_ip(src=None):
    """Tenta cada provedor em ordem; o primeiro que responder vale. Só None se TODOS falharem."""
    for host, path in [tuple(p) for p in CFG.get("provedores_ip", IP_PROVEDORES)]:
        try:
            d, _ = http_get(host, path, src)
            m = IP_RE.search(d.split(b"\r\n\r\n", 1)[1].decode(errors="ignore"))
            if m: return m.group(0)
        except Exception:
            pass
    return None

def mediana(v):
    v = sorted(v)
    if not v: return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

SPEED_LOCK = threading.Lock()   # um teste por vez (os dois links não competem entre si)

def testando():
    """True enquanto QUALQUER link faz teste de velocidade: o teste satura o servidor e o firewall e distorce a medição dos dois links."""
    return any(s.get("speedtest") for s in STATE.values())

def _erro_txt(e):
    if isinstance(e, socket.timeout) or isinstance(e, TimeoutError): return "tempo esgotado"
    if isinstance(e, ConnectionRefusedError): return "conexão recusada"
    if isinstance(e, ssl.SSLError): return "falha TLS"
    if isinstance(e, socket.gaierror): return "falha de DNS"
    return type(e).__name__

def _status(b):
    m = re.match(rb"HTTP/\d\.\d (\d{3})", b)
    return int(m.group(1)) if m else 0

BUCKETS = 4   # janelas de 0,25 s para somar os bytes

def _w_down(host, src, size, t0, dur, out, errs):
    """Baixa blocos de 'size' bytes, um após o outro, até acabar o tempo; soma os bytes por janela de 0,25 s."""
    buf = bytearray(262144); deadline = t0 + dur
    req = f"GET /__down?bytes={size} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: monitor\r\n\r\n".encode()
    while time.time() < deadline:
        s = None
        try:
            s = https_conn(host, src, 15)
            s.sendall(req)
            hdr = b""; started = False
            while time.time() < deadline:
                n = s.recv_into(buf)
                if not n: break
                if not started:
                    hdr += bytes(buf[:n]); k = hdr.find(b"\r\n\r\n")
                    if k < 0: continue
                    code = _status(hdr)
                    if code != 200:
                        errs.append(f"servidor recusou (HTTP {code})"); return
                    started = True; n = len(hdr) - k - 4
                i = int((time.time() - t0) * BUCKETS)
                if 0 <= i < dur * BUCKETS: out[i] = out.get(i, 0) + n
        except Exception as e:
            errs.append(_erro_txt(e)); return
        finally:
            if s:
                try: s.close()
                except Exception: pass

def _w_up(host, src, size, t0, dur, out, errs):
    """Envia blocos de 'size' bytes, um após o outro, até acabar o tempo; soma os bytes enviados por janela de 0,25 s."""
    deadline = t0 + dur; chunk = os.urandom(65536)
    head = (f"POST /__up HTTP/1.1\r\nHost: {host}\r\nContent-Length: {size}\r\n"
            f"Content-Type: application/octet-stream\r\nConnection: close\r\n\r\n").encode()
    while time.time() < deadline:
        s = None
        try:
            s = https_conn(host, src, 15)
            s.sendall(head); left = size; completo = True
            while left > 0:
                if time.time() >= deadline: completo = False; break
                k = min(len(chunk), left)
                s.sendall(chunk[:k]); left -= k
                i = int((time.time() - t0) * BUCKETS)
                if 0 <= i < dur * BUCKETS: out[i] = out.get(i, 0) + k
            if completo:
                r = s.recv(1024)                 # a resposta só vem depois de o servidor receber tudo
                code = _status(r)
                if code != 200:
                    errs.append(f"servidor recusou (HTTP {code})"); return
        except Exception as e:
            errs.append(_erro_txt(e)); return
        finally:
            if s:
                try: s.close()
                except Exception: pass

def _medir(worker, host, src, n, size, dur, aquecimento):
    """(Mbps, motivo_da_falha). Velocidade = média dos bytes depois do período de aquecimento (descarta a fase de aceleração do TCP)."""
    t0 = time.time() + 0.3
    outs = [{} for _ in range(n)]; errs = []
    ths = [threading.Thread(target=worker, args=(host, src, size, t0, dur, outs[i], errs), daemon=True) for i in range(n)]
    for t in ths: t.start()
    for t in ths: t.join(timeout=dur + 20)
    total = sum(v for o in outs for k, v in o.items() if k >= aquecimento * BUCKETS)
    if errs and len(errs) * 2 >= n:          # metade ou mais das conexões falhou: o teste não vale
        return None, max(set(errs), key=errs.count)
    if total <= 0:
        return None, (max(set(errs), key=errs.count) if errs else "nenhum dado recebido")
    return total * 8 / (dur - aquecimento) / 1e6, None

def _tamanhos(principal, reserva):
    return [principal] + [t for t in reserva if t < principal]

def speedtest(link):
    """Várias conexões em paralelo (como o Fast.com), por TEMPO fixo: mais estável que baixar um volume fixo.
    O tamanho (MB) é o de cada bloco pedido. Se um tamanho for recusado, tenta os tamanhos de reserva (menores)."""
    src = link["ip_origem"]; host = "speed.cloudflare.com"
    n = max(1, int(link.get("velocidade_conexoes", 4)))
    aq = CFG.get("velocidade_aquecimento_s", 2)
    dd, du = CFG.get("velocidade_duracao_down_s", 10), CFG.get("velocidade_duracao_up_s", 8)
    reserva = CFG.get("velocidade_tamanhos_reserva_mb", [10, 5])
    out = {"down": None, "up": None, "down_erro": None, "up_erro": None}
    for mb in _tamanhos(link.get("velocidade_download_mb", 25), reserva):
        try: out["down"], out["down_erro"] = _medir(_w_down, host, src, n, int(mb * 1_000_000), dd, aq)
        except Exception as e: out["down_erro"] = _erro_txt(e)
        if out["down"] is not None: break
    time.sleep(2)
    for mb in _tamanhos(link.get("velocidade_upload_mb", 5), [3, 1]):
        try: out["up"], out["up_erro"] = _medir(_w_up, host, src, n, int(mb * 1_000_000), du, aq)
        except Exception as e: out["up_erro"] = _erro_txt(e)
        if out["up"] is not None: break
    return out

# ---------- ciclo por link ----------
def dns_lista(link):
    d = CFG.get("dns") or {"nome": CFG.get("alvo_dns", {}).get("nome", "www.google.com"),
                           "servidores": [{"rotulo": "Cloudflare", "servidor": CFG.get("alvo_dns", {}).get("servidor", "1.1.1.1")}]}
    return d["nome"], list(d["servidores"]) + list(link.get("dns_extra") or [])

def since_persistido(nome, estado):
    """Reiniciar o coletor não pode zerar o 'há quanto tempo': usa o último evento de estado gravado."""
    c = db()
    r = c.execute("select ts, kind from events where link=? and kind in ('online','degradado','offline') order by ts desc limit 1", (nome,)).fetchone()
    c.close()
    return r[0] if r and r[1] == estado else int(time.time())

def avisos_update(st, nome, ativos):
    """ativos: {chave: texto}. Histerese de 3 amostras para entrar e para sair (evita ruído de uma amostra só)."""
    sc = st.setdefault("av_score", {}); on = st.setdefault("av_on", {})
    for k in list(sc):
        if k not in ativos:
            sc[k] -= 1
            if sc[k] <= 0:
                sc.pop(k)
                if k in on: event(nome, "aviso", on.pop(k) + " — normalizado")
    for k, t in ativos.items():
        sc[k] = min(3, sc.get(k, 0) + 1)
        if sc[k] >= 3 and k not in on:
            on[k] = t; event(nome, "aviso", t)
        elif k in on:
            on[k] = t
    return list(on.values())

def cycle(link):
    nome, src = link["nome"], link["ip_origem"]
    st = STATE[nome]
    em_teste = testando()   # durante o teste de velocidade a latência sobe de propósito: não conta
    alvos = CFG["alvos_ping"]
    dnome, dsrv = dns_lista(link)
    with ThreadPoolExecutor(max_workers=len(alvos) + len(dsrv)) as ex:
        fp = [ex.submit(ping, src, a) for a in alvos]
        fd = [ex.submit(dns_time, src, s["servidor"], dnome) for s in dsrv]
        res = [f.result() for f in fp]
        dres = [f.result() for f in fd]
    if em_teste or testando():
        return
    # --- por destino ---
    det = [{"alvo": a, "loss": r[0], "rtt": r[1], "jitter": r[2]} for a, r in zip(alvos, res)]
    alcancaveis = [d for d in det if d["loss"] < 100]
    ativos = {}
    for d in det:
        if d["loss"] >= 100 and alcancaveis:        # só é "destino indisponível" se os outros respondem
            ativos["p" + d["alvo"]] = f"destino {d['alvo']} indisponível"
    dns_det = [{"rotulo": s["rotulo"], "servidor": s["servidor"], "ms": ms} for s, ms in zip(dsrv, dres)]
    dns_falhas = [x for x in dns_det if x["ms"] is None]
    if alcancaveis:
        for x in dns_falhas:
            ativos["d" + x["servidor"]] = f"DNS {x['rotulo']} ({x['servidor']}) sem resposta"
    # --- agregados (um destino fora do ar não pesa) ---
    loss = sum(d["loss"] for d in alcancaveis) / len(alcancaveis) if alcancaveis else 100.0
    rtt = mediana([d["rtt"] for d in alcancaveis if d["rtt"] is not None])
    jitter = mediana([d["jitter"] for d in alcancaveis if d["jitter"] is not None])
    dns = mediana([x["ms"] for x in dns_det if x["ms"] is not None])
    pub = st.get("pub")
    if time.time() - st.get("pub_ts", 0) > 20:
        pub = public_ip(src) if alcancaveis else None
        st["pub_ts"] = time.time()
    # Se o firewall desviar o teste para outro link, o IP público denuncia: o link testado NÃO está respondendo.
    exp = link.get("ip_publico_esperado")
    proib = link.get("ip_publico_proibido") or []
    desviado = bool(pub and ((exp and pub != exp) or pub in proib))
    if desviado:
        loss, rtt, jitter, dns, alcancaveis, dns_det = 100.0, None, None, None, [], []
        ativos = {}
    # --- problema nesta amostra? maioria dos destinos alcançáveis com problema ---
    razoes = []
    if alcancaveis:
        mal_perda = [d for d in alcancaveis if d["loss"] >= link["perda_aviso_pct"]]
        mal_rtt = [d for d in alcancaveis if d["rtt"] and d["rtt"] > link["rtt_aviso_ms"]]
        if len(mal_perda) * 2 > len(alcancaveis): razoes.append(f"perda {loss:.0f}% na maioria dos destinos")
        if len(mal_rtt) * 2 > len(alcancaveis): razoes.append(f"latência {rtt:.0f} ms na maioria dos destinos")
        if dns_det and len(dns_falhas) * 2 > len(dns_det): razoes.append("DNS falhando")
    st["recent"].append((bool(alcancaveis), bool(razoes), "; ".join(razoes))); st["recent"] = st["recent"][-3:]
    rec = st["recent"]
    if len(rec) >= 3 and not any(r[0] for r in rec):
        new, why = "offline", "sem resposta de nenhum destino de ping"
    elif sum(1 for r in rec if r[1]) * 2 > len(rec):
        new, why = "degradado", next(r[2] for r in reversed(rec) if r[1])
    else:
        new, why = "online", ""
    if desviado:
        new, why = "offline", f"teste desviado para outro link (IP público {pub}); este link não está respondendo"
    st.update(loss=loss, rtt=rtt, jitter=jitter, dns=dns, dns_det=dns_det, det=det, pub=pub, ts=int(time.time()))
    if new != st.get("state"):
        if st.get("state") is not None:
            event(nome, new, why or "normalizado")
            st["since"] = int(time.time())
        else:   # primeira leitura após (re)início: recupera desde quando o link está neste estado
            st["since"] = since_persistido(nome, new)
        st["state"], st["why"] = new, why
    else:
        st["why"] = why
    c = db(); c.execute("insert into samples(ts,link,loss,rtt,jitter,dns,pub,state) values(?,?,?,?,?,?,?,?)",
                        (int(time.time()), nome, loss, rtt, jitter, dns, pub, st["state"])); c.commit(); c.close()
    st["avisos"] = avisos_update(st, nome, ativos)

def loop_link(link):
    while True:
        t = time.time()
        try: cycle(link)
        except Exception as e: print("erro", link["nome"], e, file=sys.stderr)
        time.sleep(max(1, CFG["intervalo_s"] - (time.time() - t)))

def loop_active():
    """Descobre por qual link o tráfego 'normal' (sem origem forçada) está saindo."""
    cand, n = None, 0
    while True:
        ip = public_ip()
        names = [n_ for n_, s in STATE.items() if ip and s.get("pub") == ip]
        cur = names[0] if names else ("desconhecido" if ip else "sem internet")
        if cur == ACTIVE["link"]:
            cand, n = None, 0
        else:
            n = n + 1 if cur == cand else 1      # só confirma a troca após 2 leituras iguais seguidas
            cand = cur
            if n >= 2:
                if ACTIVE["link"] is not None:   # na partida só registra o estado, sem gerar evento
                    event(cur, "failover", f"tráfego da rede passou de {ACTIVE['link']} para {cur}")
                ACTIVE.update(link=cur, ip=ip)
                cand, n = None, 0
        time.sleep(20)

def carregar_ultimo_speed(link):
    """Após reiniciar, mostra a última medição boa em vez de '—' até o próximo teste."""
    sp = {"down": None, "up": None, "ts": None, "down_ts": None, "up_ts": None, "falha": None}
    c = db()
    for col in ("down", "up"):
        r = c.execute(f"select ts,{col} from speed where link=? and {col} is not null order by ts desc limit 1", (link["nome"],)).fetchone()
        if r: sp[col], sp[col + "_ts"] = r[1], r[0]; sp["ts"] = max(sp["ts"] or 0, r[0])
    c.close()
    STATE[link["nome"]]["speed"] = sp

def loop_speed(link):
    """Mede a velocidade a cada teste_velocidade_min minutos ou quando alguém pede 'medir agora'."""
    nome = link["nome"]; st = STATE[nome]
    go = st["go"] = threading.Event()
    go.wait(15)
    while True:
        go.clear()
        if st.get("state") == "offline":         # não adianta testar velocidade de link fora do ar
            st["speed"]["falha"] = "link offline — teste não executado"
            st["pedido"] = False
            go.wait(120); continue
        with SPEED_LOCK:
            st["speedtest"] = True
            try:
                r = speedtest(link)
            except Exception as e:
                r = {"down": None, "up": None, "down_erro": _erro_txt(e), "up_erro": _erro_txt(e)}
            finally:
                time.sleep(5)            # deixa as filas do link esvaziarem antes de voltar a medir latência
                st["speedtest"] = False
        now = int(time.time()); sp = st["speed"]; falhas = []
        for col in ("down", "up"):
            if r[col] is not None: sp[col], sp[col + "_ts"] = r[col], now
            else: falhas.append(("download" if col == "down" else "upload") + ": " + (r[col + "_erro"] or "falhou"))
        sp["falha"] = "; ".join(falhas) or None
        if r["down"] is not None or r["up"] is not None:
            sp["ts"] = now
            c = db(); c.execute("insert into speed values(?,?,?,?)", (now, nome, r["down"], r["up"])); c.commit(); c.close()
        sp["ts_tentativa"] = now
        st["pedido"] = False
        go.wait(CFG["teste_velocidade_min"] * 60)

def pedir_medicao(nome):
    """'Medir agora'. Devolve (http_status, mensagem). Trava contra cliques repetidos: a medição satura o link por ~1 min."""
    st = STATE.get(nome)
    if not st or "go" not in st: return 404, "link desconhecido"
    if st.get("state") == "offline": return 409, "link offline: nada para medir"
    if st.get("speedtest") or st.get("pedido"): return 409, "já existe uma medição em andamento ou na fila"
    espera = int(st["speed"].get("ts_tentativa", 0) + CFG.get("medir_agora_intervalo_s", 300) - time.time())
    if espera > 0: return 429, f"aguarde {espera} s para medir de novo"
    st["pedido"] = True; st["go"].set()
    return 202, "medição solicitada"

def loop_purge():
    while True:
        lim = int(time.time()) - CFG["retencao_dias"] * 86400
        c = db()
        # Só as amostras (a tabela grande) e os avisos expiram. Quedas, trocas de link e testes de velocidade
        # são poucos e ficam para sempre: é o que permite abrir qualquer dia antigo no relatório.
        c.execute("delete from samples where ts<?", (lim,))
        c.execute("delete from events where ts<? and kind='aviso'", (lim,))
        c.commit(); c.close(); time.sleep(3600)

# ---------- resumo diário (histórico de longo prazo) ----------
def _dia_range(day):
    d = datetime.date.fromisoformat(day)
    return int(time.mktime(d.timetuple())), int(time.mktime((d + datetime.timedelta(days=1)).timetuple()))

def _media(v): return sum(v) / len(v) if v else None

def resumo_dia(day):
    """Calcula e grava (substitui) o resumo de um dia para cada link. Tempo em cada estado = soma dos intervalos entre amostras
    (lacunas maiores que 3 intervalos, como coletor parado, não contam como tempo monitorado)."""
    a, b = _dia_range(day); cap = max(30, CFG["intervalo_s"] * 3); c = db()
    for l in CFG["links"]:
        nome = l["nome"]
        rows = c.execute("select ts,loss,rtt,jitter,dns,state from samples where link=? and ts>=? and ts<? order by ts", (nome, a, b)).fetchall()
        if not rows: continue
        secs = {"online": 0, "degradado": 0, "offline": 0}; rtts, losses, jits, dnss = [], [], [], []
        for i, r in enumerate(rows):
            nxt = rows[i + 1][0] if i + 1 < len(rows) else r[0] + CFG["intervalo_s"]
            st = r[5] or ("offline" if r[1] >= 100 else "online")
            secs[st] += min(nxt - r[0], cap)
            if st != "offline":
                losses.append(r[1])
                if r[2] is not None: rtts.append(r[2])
                if r[3] is not None: jits.append(r[3])
                if r[4] is not None: dnss.append(r[4])
        rtts.sort()
        p95 = rtts[min(len(rtts) - 1, int(len(rtts) * 0.95))] if rtts else None
        q = c.execute("select count(*) from events where link=? and kind='offline' and ts>=? and ts<?", (nome, a, b)).fetchone()[0]
        f = c.execute("select count(*) from events where link=? and kind='failover' and ts>=? and ts<?", (nome, a, b)).fetchone()[0]
        sp = c.execute("select down,up from speed where link=? and ts>=? and ts<?", (nome, a, b)).fetchall()
        dn = [x[0] for x in sp if x[0] is not None]; up = [x[1] for x in sp if x[1] is not None]
        c.execute("insert or replace into daily values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (day, nome, sum(secs.values()), secs["online"], secs["degradado"], secs["offline"], q, f, len(losses),
                   _media(rtts), p95, rtts[-1] if rtts else None, _media(losses), _media(jits), _media(dnss), len(sp),
                   min(dn) if dn else None, _media(dn), max(dn) if dn else None, min(up) if up else None, _media(up), max(up) if up else None))
    c.commit(); c.close()

def loop_resumo():
    """Na partida completa os dias que ainda não têm resumo; depois, de hora em hora, refaz hoje e ontem.
    Dias antigos não são refeitos: os dados detalhados deles podem já ter sido apagados (retenção de 30 dias)."""
    primeira = True
    while True:
        try:
            c = db()
            com_dados = {r[0] for r in c.execute("select distinct date(ts,'unixepoch','localtime') from samples")}
            prontos = {r[0] for r in c.execute("select distinct day from daily")}
            c.close()
            hoje = datetime.date.today()
            dias = {hoje.isoformat(), (hoje - datetime.timedelta(days=1)).isoformat()}
            if primeira: dias |= (com_dados - prontos)
            for d in sorted(dias & (com_dados | {hoje.isoformat()})): resumo_dia(d)
        except Exception as e:
            print("erro resumo", e, file=sys.stderr)
        primeira = False
        time.sleep(3600)

def _mes_range(mes):
    d = datetime.date.fromisoformat(mes + "-01")
    prox = (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return int(time.mktime(d.timetuple())), int(time.mktime(prox.timetuple()))

def trocas_info(a, b):
    """Qual link carregou o tráfego da rede entre os instantes a e b, a partir dos eventos de troca (failover).
    Devolve tempo ativo por link, trocas por sentido, maior permanência e a lista das trocas."""
    nomes = [l["nome"] for l in CFG["links"]]
    agora = int(time.time()); fim = min(b, agora)
    c = db()
    ev = c.execute("select ts,link,detail from events where kind='failover' order by ts").fetchall()
    r = c.execute("select v from meta where k='inicio'").fetchone()
    c.close()
    ini = max(a, int(r[0]) if r else a)
    vazio = {"total_s": 0, "n": 0, "links": {n: {"ativo_s": 0, "pct": None, "vezes": 0, "maior_s": 0} for n in nomes},
             "outros_s": 0, "direcoes": [], "lista": []}
    if fim <= ini: return vazio

    def de_para(e):
        m = re.search(r"passou de (.+) para (.+)$", e[2] or "")
        return (m.group(1), m.group(2)) if m else (None, e[1])
    antes = [e for e in ev if e[0] < ini]
    if antes: atual = de_para(antes[-1])[1]
    else:
        depois = [e for e in ev if e[0] >= ini]
        atual = de_para(depois[0])[0] if depois else ACTIVE.get("link")
    t, segs, trocas = ini, [], []
    for e in ev:
        if e[0] < ini or e[0] >= fim: continue
        de, para = de_para(e)
        segs.append((atual, t, e[0]))
        trocas.append({"ts": e[0], "de": de or atual, "para": para})
        atual, t = para, e[0]
    segs.append((atual, t, fim))
    for i, x in enumerate(trocas):
        x["dur_s"] = (trocas[i + 1]["ts"] if i + 1 < len(trocas) else fim) - x["ts"]
        x["em_curso"] = i == len(trocas) - 1 and fim >= agora
    total = fim - ini
    res = {"total_s": total, "n": len(trocas), "ini": ini, "fim": fim,
           "links": {n: {"ativo_s": 0, "pct": None, "vezes": 0, "maior_s": 0} for n in nomes}, "outros_s": 0}
    for lk, t0, t1 in segs:
        if lk in res["links"]:
            L = res["links"][lk]; L["ativo_s"] += t1 - t0; L["maior_s"] = max(L["maior_s"], t1 - t0)
        else: res["outros_s"] += t1 - t0
    for n in nomes: res["links"][n]["pct"] = res["links"][n]["ativo_s"] * 100 / total
    for x in trocas:
        if x["para"] in res["links"]: res["links"][x["para"]]["vezes"] += 1
    res["direcoes"] = [{"de": d, "para": p, "n": sum(1 for x in trocas if x["de"] == d and x["para"] == p)}
                       for d in nomes for p in nomes if d != p]
    res["lista"] = trocas[::-1][:200]
    return res

def api_relatorio(mes):
    c = db()
    meses = [r[0] for r in c.execute("select distinct substr(day,1,7) m from daily order by m desc")]
    if not mes or mes not in meses: mes = meses[0] if meses else datetime.date.today().strftime("%Y-%m")
    cols = ["day", "mon_s", "online_s", "degr_s", "off_s", "quedas", "failovers", "n", "rtt_avg", "rtt_p95", "rtt_max", "loss_avg", "jitter_avg",
            "dns_avg", "n_speed", "down_min", "down_avg", "down_max", "up_min", "up_avg", "up_max"]
    out = {"mes": mes, "meses": meses, "links": {}}
    for l in CFG["links"]:
        rows = c.execute(f"select {','.join(cols)} from daily where link=? and day like ? order by day", (l["nome"], mes + "-%")).fetchall()
        dias = [dict(zip(cols, r)) for r in rows]
        mon = sum(d["mon_s"] for d in dias)
        def pond(k, w):
            v = [(d[k], d[w]) for d in dias if d[k] is not None and d[w]]
            t = sum(x[1] for x in v)
            return sum(x[0] * x[1] for x in v) / t if t else None
        def lim(k, fn):
            v = [d[k] for d in dias if d[k] is not None]
            return fn(v) if v else None
        res = {"mon_s": mon, "online_s": sum(d["online_s"] for d in dias), "degr_s": sum(d["degr_s"] for d in dias), "off_s": sum(d["off_s"] for d in dias),
               "quedas": sum(d["quedas"] for d in dias), "failovers": sum(d["failovers"] for d in dias),
               "rtt_avg": pond("rtt_avg", "n"), "rtt_p95": lim("rtt_p95", max), "loss_avg": pond("loss_avg", "n"),
               "n_speed": sum(d["n_speed"] for d in dias), "down_avg": pond("down_avg", "n_speed"), "down_min": lim("down_min", min), "down_max": lim("down_max", max),
               "up_avg": pond("up_avg", "n_speed"), "up_min": lim("up_min", min), "up_max": lim("up_max", max)}
        out["links"][l["nome"]] = {"contratado": l.get("contratado"), "dias": dias, "resumo": res}
    c.close()
    out["trocas"] = trocas_info(*_mes_range(mes))
    return out

DAILY_COLS = ["day", "mon_s", "online_s", "degr_s", "off_s", "quedas", "failovers", "n", "rtt_avg", "rtt_p95", "rtt_max", "loss_avg", "jitter_avg",
              "dns_avg", "n_speed", "down_min", "down_avg", "down_max", "up_min", "up_avg", "up_max"]

def api_dia(dia):
    """Tudo o que aconteceu em um dia: resumo por link, curva de latência, eventos, testes de velocidade e trocas de link."""
    d = datetime.date.fromisoformat(dia)
    a, b = _dia_range(dia)
    if d == datetime.date.today():
        try: resumo_dia(dia)                      # hoje: o resumo guardado pode ter até 1 h de atraso
        except Exception as e: print("erro resumo", e, file=sys.stderr)
    bucket = 300
    c = db(); out = {"dia": dia, "links": {}}
    for l in CFG["links"]:
        r = c.execute(f"select {','.join(DAILY_COLS)} from daily where link=? and day=?", (l["nome"], dia)).fetchone()
        serie = c.execute("select ts/?*? b, avg(rtt), avg(loss), max(loss) from samples where link=? and ts>=? and ts<? group by b order by b",
                          (bucket, bucket, l["nome"], a, b)).fetchall()
        out["links"][l["nome"]] = {"contratado": l.get("contratado"), "resumo": dict(zip(DAILY_COLS, r)) if r else None, "serie": serie}
    out["bucket"] = bucket; out["a"], out["b"] = a, b
    out["eventos"] = c.execute("select ts,link,kind,detail from events where ts>=? and ts<? order by ts desc", (a, b)).fetchall()
    out["velocidade"] = c.execute("select ts,link,down,up from speed where ts>=? and ts<? order by ts desc", (a, b)).fetchall()
    out["anterior"] = (c.execute("select max(day) from daily where day<?", (dia,)).fetchone() or [None])[0]
    out["proximo"] = (c.execute("select min(day) from daily where day>?", (dia,)).fetchone() or [None])[0]
    c.close()
    out["trocas"] = trocas_info(a, b)
    return out

def csv_relatorio(mes):
    r = api_relatorio(mes)
    f = lambda v, d=1: "" if v is None else f"{v:.{d}f}".replace(".", ",")
    head = ["Data", "Link", "Monitorado (h)", "Disponível (%)", "Qualidade boa (%)", "Minutos offline", "Minutos degradado", "Quedas", "Vezes que assumiu o tráfego",
            "Latência média (ms)", "Latência p95 (ms)", "Latência máx (ms)", "Perda média (%)", "Jitter médio (ms)", "DNS médio (ms)", "Testes de velocidade",
            "Download mín (Mbps)", "Download médio (Mbps)", "Download máx (Mbps)", "Upload mín (Mbps)", "Upload médio (Mbps)", "Upload máx (Mbps)"]
    lines = [";".join(head)]
    for nome, L in r["links"].items():
        for d in L["dias"]:
            m = d["mon_s"] or 1
            lines.append(";".join([d["day"], nome, f(d["mon_s"] / 3600), f((d["online_s"] + d["degr_s"]) * 100 / m, 2), f(d["online_s"] * 100 / m, 2),
                                   f(d["off_s"] / 60), f(d["degr_s"] / 60), str(d["quedas"]), str(d["failovers"]), f(d["rtt_avg"]), f(d["rtt_p95"]), f(d["rtt_max"]),
                                   f(d["loss_avg"], 2), f(d["jitter_avg"]), f(d["dns_avg"]), str(d["n_speed"]), f(d["down_min"], 0), f(d["down_avg"], 0),
                                   f(d["down_max"], 0), f(d["up_min"], 0), f(d["up_avg"], 0), f(d["up_max"], 0)]))
    return "\r\n".join(lines) + "\r\n", r["mes"]

# ---------- API ----------
def api_status():
    out = {"agora": int(time.time()), "ativo": ACTIVE, "links": []}
    pubs = [s.get("pub") for s in STATE.values() if s.get("pub")]
    for l in CFG["links"]:
        s = STATE[l["nome"]]
        d = {k: s.get(k) for k in ("state", "why", "since", "loss", "rtt", "jitter", "dns", "dns_det", "det", "avisos", "pub", "speed", "ts")}
        d["nome"] = l["nome"]
        c = db()
        q = c.execute("select max(ts) from events where link=? and kind='offline'", (l["nome"],)).fetchone()
        m = c.execute("select min(ts) from samples where link=?", (l["nome"],)).fetchone()
        c.close()
        d["ultima_queda"], d["monitorado_desde"] = q[0], m[0]
        d["contratado"] = l.get("contratado")
        d["medindo"] = bool(s.get("speedtest")); d["na_fila"] = bool(s.get("pedido")) and not s.get("speedtest")
        d["medir_intervalo_s"] = CFG.get("medir_agora_intervalo_s", 300)
        d["medir_libera_em"] = int((s.get("speed") or {}).get("ts_tentativa", 0) + CFG.get("medir_agora_intervalo_s", 300))
        d["isolamento_ok"] = not (s.get("pub") and pubs.count(s["pub"]) > 1)
        out["links"].append(d)
    return out

def api_history(hours, hoje=False):
    hours = max(1, min(hours, 24 * CFG["retencao_dias"]))
    bucket = max(CFG["intervalo_s"], int(hours * 3600 / 240))
    since = int(time.time()) - hours * 3600
    # hoje=True (modo TV): os eventos vão da meia-noite de hoje (hora do servidor) até agora; as curvas continuam nas últimas 'hours' h
    since_ev = _dia_range(datetime.date.today().isoformat())[0] if hoje else since
    c = db(); res = {"bucket": bucket, "links": {}}
    for l in CFG["links"]:
        rows = c.execute("select ts/?*? b, avg(rtt), avg(loss), avg(jitter), max(loss) from samples where link=? and ts>=? group by b order by b",
                         (bucket, bucket, l["nome"], since)).fetchall()
        res["links"][l["nome"]] = rows
    res["events"] = c.execute("select ts,link,kind,detail from events where ts>=? order by ts desc limit 100", (since_ev,)).fetchall()
    res["speed"] = c.execute("select ts,link,down,up from speed where ts>=? order by ts", (since,)).fetchall()
    c.close()
    return res

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/status": body, ct = json.dumps(api_status()), "application/json"
        elif u.path == "/api/history":
            q = parse_qs(u.query)
            body, ct = json.dumps(api_history(int(q.get("h", ["6"])[0]), q.get("hoje", ["0"])[0] == "1")), "application/json"
        elif u.path == "/api/info": body, ct = json.dumps({"organizacao": CFG.get("organizacao", "")}), "application/json"
        elif u.path == "/api/dia":
            try: body, ct = json.dumps(api_dia(parse_qs(u.query).get("dia", [""])[0])), "application/json"
            except ValueError: self.send_error(400); return
        elif u.path == "/api/relatorio":
            body, ct = json.dumps(api_relatorio(parse_qs(u.query).get("mes", [""])[0])), "application/json"
        elif u.path == "/api/relatorio.csv":
            txt, mes = csv_relatorio(parse_qs(u.query).get("mes", [""])[0])
            b = ("\ufeff" + txt).encode("utf-8")      # BOM: o Excel em português abre com acentos certos
            self.send_response(200); self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="conectividade-{mes}.csv"')
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        elif u.path == "/relatorio":
            body, ct = open(os.path.join(BASE, "relatorio.html"), encoding="utf-8").read(), "text/html; charset=utf-8"
        elif u.path in ("/", "/index.html"):
            body, ct = open(os.path.join(BASE, "dashboard.html"), encoding="utf-8").read(), "text/html; charset=utf-8"
        else:
            self.send_error(404); return
        b = body.encode()
        self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)

def _json(self, code, obj):
    b = json.dumps(obj).encode()
    self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
    self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
H._json = _json

def _post(self):
    u = urlparse(self.path)
    if u.path != "/api/medir": self.send_error(404); return
    code, msg = pedir_medicao(parse_qs(u.query).get("link", [""])[0])
    self._json(code, {"ok": code == 202, "msg": msg})
H.do_POST = _post

if __name__ == "__main__":
    init_db()
    for l in CFG["links"]:
        STATE[l["nome"]] = {"recent": []}
        carregar_ultimo_speed(l)
        for f in (loop_link, loop_speed):
            threading.Thread(target=f, args=(l,), daemon=True).start()
    threading.Thread(target=loop_active, daemon=True).start()
    threading.Thread(target=loop_purge, daemon=True).start()
    threading.Thread(target=loop_resumo, daemon=True).start()
    print(f"Dashboard em http://{CFG.get('bind', '0.0.0.0')}:{CFG['porta_http']}")
    ThreadingHTTPServer((CFG.get("bind", "0.0.0.0"), CFG["porta_http"]), H).serve_forever()
