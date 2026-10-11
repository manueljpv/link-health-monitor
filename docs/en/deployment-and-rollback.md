# Deployment, update, and rollback

> **Notice: fictitious data.** All IP addresses, names, identifiers, and values in this document are examples. The IPs use the ranges reserved for documentation (192.0.2.0/24, 198.51.100.0/24, and 203.0.113.0/24). Replace everything with the values from your environment before running any command.

## Step-by-step installation

Prerequisite: prepare the firewall with two free test IPs and the source-based routing rules (see `firewall-example-fortigate.md`).

1. On the server, create the folder and copy the files (as root, from the repository folder):

   ```
   mkdir -p /opt/monitor-links
   cp src/collector.py src/dashboard.html src/relatorio.html /opt/monitor-links/
   cp config/config.example.json /opt/monitor-links/config.json
   ```

2. Edit `/opt/monitor-links/config.json`: organization name, link names, `ip_origem` (the test IPs), `ip_publico_esperado` for the fixed-IP link (and `ip_publico_proibido` on the other), warning thresholds, contracted speeds, and the provider's extra DNS servers.
3. Copy the systemd units, adjust the IPs, prefix, and interface in `monitor-links-ips.service`, and enable both services:

   ```
   cp deploy/*.service /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now monitor-links-ips.service
   systemctl enable --now monitor-links.service
   ```

4. Confirm the IPs and the port and open the dashboard in the browser:

   ```
   ip -4 -brief addr show eth0
   ss -ltnp | grep 8080
   ```

   Dashboard at `http://SERVER-IP:8080`, TV mode at `/?tv=1`, and report at `/relatorio`.
5. Run the validation (section below).
6. Restrict access to the internal network (see the points of attention in `architecture-and-rules.md`).

## What the installation does on the server, update, and rollback

**What was done:**

1. **Service `monitor-links-ips.service`:** on every boot it adds the two test IPs to the network interface as secondary IPs. The main IP and the server's normal traffic do not change. It uses a systemd service, rather than the system's network configuration, so that the hypervisor or the network manager does not undo the IPs.
2. **Collector** in `/opt/monitor-links` (`collector.py`, `dashboard.html`, `relatorio.html`, `config.json`) and service `monitor-links.service`: starts after the IP service and restarts by itself on failure. It listens on `0.0.0.0:8080`.

**Update** (as root, inside `/opt/monitor-links`):

```
ls -l <package>.tar.gz
tar xzf <package>.tar.gz --strip-components=1
chown -R root:root /opt/monitor-links
systemctl restart monitor-links      # only if collector.py or config.json changed
```

Update packages **do not include `config.json`**, because it holds the local settings (extra DNS servers, contracted speeds). `dashboard.html` and `relatorio.html` are read from disk on every access: replacing those files does not require a restart. The collector updates the database by itself, without erasing the history.

**Roll back the collector** (as root):

```
systemctl disable --now monitor-links
rm /etc/systemd/system/monitor-links.service
systemctl daemon-reload
rm -rf /opt/monitor-links
ss -ltnp | grep 8080          # should return nothing
```

Warning: deleting `/opt/monitor-links` also deletes the history (`monitor.db`, which includes the monthly summaries) and `config.json`. First, copy them:

```
cp /opt/monitor-links/monitor.db /root/monitor-links-backup.db
cp /opt/monitor-links/config.json /root/monitor-links-config-backup.json
```

Recommendation: copy `monitor.db` from time to time, because it becomes the only long-term record of link quality.

**Roll back the test IPs** (as root):

```
systemctl disable --now monitor-links-ips.service
rm /etc/systemd/system/monitor-links-ips.service
systemctl daemon-reload
ip -4 -brief addr show eth0      # should show only the main IP
```

## Validation

From the server, using each test IP as the source:

```
curl --interface 192.0.2.12 -s https://api.ipify.org     # should show Link 1's public IP
curl --interface 192.0.2.13 -s https://api.ipify.org     # should show Link 2's public IP
ping -I 192.0.2.12 -c 3 1.1.1.1
ping -I 192.0.2.13 -c 3 1.1.1.1
```

The two links must go out through **different** public IPs. Then, `ss -ltnp | grep 8080` shows the dashboard is up and the home page should show both links online, with DNS responding on all servers.
