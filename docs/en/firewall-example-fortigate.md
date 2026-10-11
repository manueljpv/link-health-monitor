# Firewall example: FortiGate with SD-WAN

> **Notice: fictitious data.** All IP addresses, names, identifiers, and values in this document are examples. The IPs use the ranges reserved for documentation (192.0.2.0/24, 198.51.100.0/24, and 203.0.113.0/24). Replace everything with the values from your environment before running any command.

This document shows one way to prepare the firewall. What matters is the result: each of the server's test IPs must always go out through a specific link. Any firewall or router with source-based routing (policy-based routing) can achieve the same.

Example values; adjust names and IDs to your environment.

**What was done:**

1. **DHCP reservations** on the LAN's DHCP server, one for each test IP (fictitious MAC addresses, for example 02:00:00:00:00:12 and 02:00:00:00:00:13). They only exist so that DHCP never hands out these IPs.
2. **Address objects:** `MON-LINK1` (192.0.2.12/32) and `MON-LINK2` (192.0.2.13/32).
3. **Manual SD-WAN rules** (for example, IDs 10 and 11): `MON-LINK1` in manual mode on Link 1's member and `MON-LINK2` on Link 2's member, **before** the general best-quality rule.
4. **Outbound permission:** both objects are added to the `ALLOWED-HOSTS` address group, the source of the `ALLOW-HOSTS` outbound policy.

Verification: `diagnose sys sdwan service4` should list the manual rules before the general rule, each with a single active member.

**How to roll back** (in the order 4, 3, 2, 1; an object in use by a rule or group cannot be deleted):

```
# 4. Remove only the two members from the group (the group belongs to other devices and must not be deleted)
config firewall addrgrp
    edit "ALLOWED-HOSTS"
        unselect member "MON-LINK1" "MON-LINK2"
    next
end

# 3 and 2. SD-WAN rules and objects (only after step 4)
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

# 1. DHCP reservations (only after the monitor stops using these IPs; use your own IDs)
config system dhcp server
    edit <dhcp-server-id>
        config reserved-address
            delete <reservation-id-1>
            delete <reservation-id-2>
        end
    next
end
```

Check afterwards: `diagnose sys sdwan service4` should show only the general rule; `show firewall addrgrp ALLOWED-HOSTS | grep MON-` should return nothing.

The changes only affect the traffic of the two test IPs. The rest of the network is not touched, neither on creation nor on rollback.
