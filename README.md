# remote-tunerr

Ansible playbook that turns a Raspberry Pi into a remote HDHomeRun gateway. The tuner sits at a site with a good antenna; the media server reaches it over Tailscale.

Needs only an Ethernet jack with internet at the remote site. No port forwarding, no access to the host network's router.

## why

The antenna at my media server's location can't receive channels at longer wavelenghts. An unused antenna was available at another site with less space restrictions. This  stack puts the tuner there and makes it look local to the media server.

Same setup would work for any number of sites, allowing local channels from several places on a single media server.

## how it works

The HDHomeRun plugs into the Pi's USB NIC and gets its IP from the Pi. The Pi joins your tailnet over the site's internet and advertises the tuner's subnet as a route. The media server, also on the tailnet, reaches the tuner by IP.

### network

The uplink is the onboard RJ45 port (eth0). The USB NIC to the tuner is renamed to tunerlan0, because eth0 on a Pi is also USB and the order isn't stable. The HDHomeRun gets 10.77.0.101 from a DHCP reservation. 10.77.0.0/24 is advertised to the tailnet.

All values are in group_vars/all.yml. Change them per site so the networks don't overlap.

### repo layout

```
├── ansible.cfg
├── benchmarks                  # Holds benchmark results
├── benchmark.yml               # Run benchmark script playbook
├── grafana                     # Custom monitoring dashboard
├── group_vars                  # Set private HDHomeRun network; must not overlap
├── host_vars                   # Set usb adapter and HDHomeRun MAC addresses
├── inventory.ini               # Set remote hostname
├── roles
│   ├── base                    # Configure avahi, unattended upgrades, and reboots
│   ├── benchmark
│   │   └── defaults            # Set the path for server benchmark container temp files
│   ├── dnsmasq                 # Configure dnsmasq to handle DHCP on tuner network
│   ├── iperf3                  # Install iperf3 on Pi, only running or used during benchmarking
│   ├── network                 # Configure network for both interfaces, rename
│   ├── node_exporter           # Configure stats from both the Pi and the tuner as text
│   └── tailscale               # Configure and authenticate to tailscale network
└── site.yml                    # Main setup playbook               
```

## testing and monitoring

the benchmark playbook will create start the iperf3 server on the Pi, and create a temporary container on the media server. We run a latency test, bandwidth test, and then incremental stream tests. To simulate load it starts one stream to the media server, analyzes the output for loss, waits 60 seconds, then starts two concurrent streams. This goes on until we tests all tuners being in use at the same time. Finnaly the iperf3 server is stopped and the temporary container and files are removed from the media server. You can view results in benchmarks/ and see live stats using the dashboard

<p align="center">
  <img src=".images/grafana_during_benchmark.png" alt="Grafana dashboard during a benchmark run">
</p>

## setup

### hardware

| Part | Used here |
|---|---|
|Control PC | with ansible-core; community.general and ansible.posix |
| Raspberry Pi | I'm using a 3B with PI OS Lite |
| Second NIC | USB to Ethernet adapter (any; mine is a TP-Link using cdc_ncm) |
| Tuner | HDHomeRun (Testing with a FLEX QUATRO, not 4K) |
| Power | 2.5 A supply. A weaker one caused under-voltage and throttling under load |
| Antenna | Whatever picks up what you need |


### steps

1. Flash Raspberry Pi OS Lite with hostname, user and SSH key set. Boot it on your LAN and  ssh `<user>@<hostname>.local` once to accept the host key
2. Fill out `host_vars/tuner_pi.yml` using the example
3. Set the host in `inventory.ini`.
4. First run (the Pi isn't on Tailscale yet): `ansible-playbook site.yml -K -e ansible_host=<hostname>.local -e tailscale_authkey=<your key>` The Pi will reboot
5. On tailscale admin console: approve the route, disable key expiry
6. On your media server tailscale config, accept-routes
7. Add `10.77.0.101` to Plex (or whatever else) manually as discover will not work over tailscale

Finally: `ansible-playbook site.yml -K`
If the Pi is logged out of Tailscale, the play stops and asks for `-e tailscale_authkey=`

### updates

- Unattended upgrades from Debian and Debian-Security
- Reboots at 04:00 if an update requires it, and every Tuesday at 03:30.
- Tailscale updates itself
- The tuner will not be updated

## TODO

- Benchmarking
- `roles/network` removes the NetworkManager profile `Wired connection 2` by name.
- Clear error for a missing `host_vars` file
- Wifi backup uplink?
- Set SSH to only over tailscale and with SSH keys only incase the remote site is not as secure
- Can I get tuner updates?