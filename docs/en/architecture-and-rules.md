# Architecture and operating rules

> **Notice: fictitious data.** All IP addresses, names, identifiers, and values in this document are examples. The IPs use the ranges reserved for documentation (192.0.2.0/24, 198.51.100.0/24, and 203.0.113.0/24). Replace everything with the values from your environment before running any command.

## Purpose

An HTML dashboard that shows the health of each of the company's internet links **separately**: status, latency, loss, jitter, DNS time, speed (download and upload), outages, and link switches. It does not depend on any external monitoring tool, runs on an internal Linux server, and is only accessed from the internal network (the IT team and a TV).

## Architecture

```
                       ┌───────────────────────────────┐
  Linux server         │ eth0: main IP                 │
  (collector +         │       test IP A (Link 1)      │
  dashboard)           │       test IP B (Link 2)      │
                       └──────────────┬────────────────┘
                                      │ LAN
                       ┌──────────────▼────────────────┐
  Firewall with SD-WAN │ manual rule: IP A → Link 1    │
                       │ manual rule: IP B → Link 2    │
                       │ other hosts: normal rule      │
                       └───────┬───────────────┬───────┘
                               │ Link 1        │ Link 2
                            Internet        Internet
```

The server gets two secondary IPs. The firewall pins each IP to a link through manual SD-WAN rules, so tests from one IP always go out through the corresponding link, even when normal network traffic is using the other one. The collector tests each link every 10 s and stores everything in a SQLite database. A simple HTTP API feeds the two pages (dashboard and report).

## Reference environment (example)

- **Server:** Linux (Rocky Linux 9) in a container, main IP 192.0.2.10/24, gateway 192.0.2.1, internal DNS 192.0.2.53. Python 3.9 or later, standard library only.
- **Firewall:** FortiGate running FortiOS 7.4, SD-WAN with two members (one per link), zone INTERNET.
- **Link 1:** fixed public IP (example 203.0.113.10/30, gateway 203.0.113.9), SD-WAN member 2.
- **Link 2:** IP received by DHCP (example 198.51.100.76) behind another router (198.51.100.1), SD-WAN member 3. Its public IP may change over time.
- **LAN:** 192.0.2.0/24, firewall DHCP server with reservations.

The collector lives in `/opt/monitor-links`, outside the folders of any other system on the server, so updates to those applications do not affect it.

## Design decisions

- **Test IPs:** two free LAN IPs, chosen outside the DHCP range and reserved on the firewall (example: 192.0.2.12 for Link 1 and 192.0.2.13 for Link 2). Before choosing, always check the firewall's reservation list: a ping with no reply does not prove the IP is free.
- **Per-link isolation:** the collector tests each link using the corresponding source IP (`ping -I`, sockets bound to the IP). The firewall pins each IP to a link.
- **Protection against diversion ("diverted test"):** if the firewall sends the test of a downed link through the other one, the collector notices from the public IP. Link 1 must go out through its fixed IP and Link 2 must not go out through that IP. In case of diversion the link is marked offline, not mistakenly healthy.
- **Outbound permission:** the two test IPs are added to an address group that is already the source of an outbound internet policy, following the environment's existing pattern.
- **Contracted speeds:** set per link in `config.json`, indicating whether the speed is guaranteed or not. The contracted upload is optional.
- **Report with two measures:** "Available" = time not offline. "Good quality" = time neither offline nor degraded.
- **Internal access:** the dashboard and the report have no login. They should sit behind a reverse proxy restricted to the internal network, with a name in the internal DNS (no record in public DNS).

## Collector rules

- **Probes** (every 10 s, per link): ping to 1.1.1.1, 8.8.8.8, and 9.9.9.9 in parallel; DNS queries to several servers; public IP.
- **Link status:**
  - *degraded*: only if the **majority** of reachable targets have a problem (loss or latency above the link's threshold) in at least 2 of the last 3 samples, or if the majority of DNS servers fail;
  - *offline*: no target responds in the last 3 samples, or the test was diverted to another link.
- **Warnings:** a single ping target or DNS server being down becomes just a *warning* ("target X unavailable", "DNS X not responding"), with a 3-sample hysteresis to enter and leave. It does not count against the link status and appears in the event list.
- **DNS servers:** Cloudflare and Google on all links, plus extra servers per link (`dns_extra`), for example the provider's DNS or the upstream router.
- **Public IP:** tries api.ipify.org, then icanhazip.com, then checkip.amazonaws.com.
- **"How long ago" and "no outages for X"** come from the recorded history (events table), so they do not reset when the collector restarts.
- **Speed test** (speed.cloudflare.com), **time-based**: download 10 s and upload 8 s, several parallel connections (default 4; adjustable per link), the first 2 s discarded so the link can ramp up. Each connection requests blocks of 25 MB (download) or 5 MB and 3 MB (upload) in sequence; if a size is refused with HTTP 403, it tries smaller sizes. The test fails if at least half of the connections error out, and the last valid value is kept along with its timestamp. An offline link is not tested. Tests run one at a time and latency collection pauses during them (about 30 s). Automatic frequency: every 180 min.
- **Measure now:** a button on each card (`POST /api/medir?link=NAME`; "Measure now" is `Medir agora` in the UI). Lock between measurements of the same link, configurable in `medir_agora_intervalo_s` (default 300 s). It refuses if the link is offline or a measurement is already queued.
- **Percentage of contracted:** `contratado` field per link (`{"down": 300, "up": null, "garantido": true}`). Thresholds for a link with guaranteed speed: green from 80%, yellow from 50% to 80%, red below. For a non-guaranteed link: 60% and 30%.
- **TV mode** (`/?tv=1`): full-screen dashboard, clock, latency curve for the last hour, and today's events, reloading every 30 min. The `&margem=N` parameter shrinks the dashboard by N% on each side, for TVs that crop the edges of the image. The "Exit TV mode" button (`Sair do modo TV` in the UI) appears with the mouse or touch and disappears after 5 s.
- **Cloudflare and HTTP 403:** Cloudflare refuses some download sizes (for example 15 MB; 1, 5, 10, and 25 MB work). The rule is undocumented, which is why the collector has fallback sizes. The monitor depends on Cloudflare for speed, DNS, and ping; a problem there shows up as a warning and does not take down the link status, thanks to the majority rule.

## Data retention and report

- **30 days** (`retencao_dias`): detailed samples (the large table) and warnings.
- **No limit:** outages, link switches, speed tests, and the per-link **daily summary** (online, degraded, and offline time, outages, switches, average, p95, and maximum latency, loss, jitter, DNS, minimum, average, and maximum speed).
- **Monthly report** (`/relatorio`): availability, quality, outages, latency, loss, speed with the percentage of contracted, a per-day color-coded calendar and a daily table, plus the **switches between links** card (count per direction, time and percentage of each link as active, longest stay, and list of switches). CSV export (`/api/relatorio.csv?mes=AAAA-MM`), with semicolons, decimal commas, and a BOM so it opens directly in Excel in Portuguese.
- **Day view:** clicking a day on the calendar opens that day's summary, latency curve, events, speed tests, and switches. The address keeps the day (`/relatorio#AAAA-MM-DD`). For days older than 30 days the latency curve no longer exists, but the summary, events, and tests remain.
- **Calculation:** monitored time adds up the intervals between samples, ignoring gaps longer than `max(30, 3 × interval)` seconds (collector stopped or restarting). Days follow the server's time zone.

## Speed test calibration

- The first method (fixed data volume) varied up to 2× between consecutive measurements of the same link (for example, 100% and 50% of the contracted speed within 5 minutes).
- The time-based test, with several connections and the start discarded, became stable: five consecutive measurements on the fast link varied about 5% in download, landing between 80% and 90% of the value from a reference tool measured on a PC.
- **Upload** varies more, because bytes are counted when sent and not when acknowledged, which can overestimate slightly. Counting on acknowledgment is a possible refinement (see the improvement roadmap).
- A link without guaranteed speed naturally varies between measurements, and this is expected.
- Each test consumes a few hundred MB on the fastest link. Take that into account if any link has a data cap.

## Points of attention

- The general SD-WAN rule uses "best quality by latency" with a tolerance. A latency fluctuation on the primary link can send the network to the other one without the primary having gone down. The monitor's switch history shows how often this happens. This rule is not changed by the project.
- When running as a service, the initial "Dashboard em http://..." message does not appear in `journalctl` (buffered output). To confirm it is up, use `ss -ltnp | grep 8080`.
- After restarting the service, the "ACTIVE LINK" badge takes about 40 s to appear (the collector confirms the link in use after two identical readings).
- The "Measure now" button, the report, and the CSV have no login. The lock between measurements limits abuse, but access must be restricted to the internal network.
- A month's report only has data from the day the monitor started, and percentages consider only the monitored time.
- The example runs the collector as root. Consider a dedicated user and a firewall on the server itself.
- The dashboard times use the browser's clock. On a TV computer, check the date, time, and time zone.
