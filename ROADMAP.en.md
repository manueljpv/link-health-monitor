# Roadmap

[Português](ROADMAP.md) · **English** · [Español (Honduras)](ROADMAP.es-HN.md)

This document shows where the project may go and what we have learned so far. Nothing below is a promise of a date: these are intentions, in rough order of priority. Suggestions are welcome through an issue.

## Short term

- **Message alerts (Telegram).** Notify when a link goes down, comes back, or when the network switches links, with a limit so the same message is not repeated.
- **Date labels on the 7-day latency chart.** Today the axis shows only the time (HH:MM), so over long periods it is hard to tell which day a point belongs to.
- **Upload counted at confirmation.** Measure upload by what the test server confirmed it received, not by what was sent, to avoid optimistic numbers.
- **Dedicated service user.** Run the collector as an unprivileged user instead of root, keeping only what is needed for source-IP tests.
- **Automated tests** for the state logic (majority rule, warning hysteresis, "diverted test" detection) using sample data.

## Medium term

- **Multi-language interface.** The documentation is trilingual, but the dashboard text is in Portuguese. Move the strings to a language file.
- **Publishing behind a reverse proxy with an internal name**, restricted to private addresses, with a configuration example in the docs.
- **More than two links.** Generalize the configuration to N links.
- **Extra exports:** monthly report as PDF and metrics in a Prometheus-compatible format.
- **Simple installer** (a script that creates folders and services and validates the setup).

## Long term

- **Optional authentication** for the dashboard and the "Measure now" button.
- **Firewall examples** for other vendors and for Linux (nftables/iproute2).
- **Distribution packages** (RPM/DEB) and a container image.
- **Period comparison** (month over month) and availability targets in the report.

## Lessons learned

1. **Test each link separately.** Measuring "the internet" from inside the network only shows the link in use. To know the health of both, each test must deliberately leave through one link, using source-based routing on the firewall.
2. **Distrust a test that took the wrong path.** If the firewall diverts the test, the "dead" link looks healthy. Comparing each test's public IP with the expected one prevents that false positive.
3. **A target being down is not a link being down.** The majority rule and warnings with three-sample hysteresis greatly reduced false alarms.
4. **Time-based speed tests, not fixed-size ones.** Small files do not fill fast links, and test servers refuse some sizes. Measuring by time, with several fallback sizes, gave stable results.
5. **Keep what matters forever and the rest briefly.** Raw samples grow fast; outages, switches and speeds are few and valuable. A permanent daily summary made the monthly report cheap.
6. **Simple is easier to operate.** Standard Python, SQLite and two HTML pages mean no dependencies to update and a rollback that fits in two commands.
7. **Mind what the browser shows.** The clock and time zone of the computer that opens the dashboard change the displayed times. On TVs, overscan crops the edges: TV mode gained an adjustable margin.
8. **A dashboard without login needs a restricted network.** Hence the recommendation of an internal reverse proxy and never exposing the dashboard to the internet.
9. **Document as you go.** The rollback documentation, written together with each change, is what made updates safe.
