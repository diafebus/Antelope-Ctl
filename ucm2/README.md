# Orion Studio Synergy Core UCM2 profile

This directory contains an ALSA UCM2 profile for the Antelope Orion Studio
Synergy Core (`USB VID 23e5`, `PID a221`, ALSA card name commonly `III`).

The profile describes the class-compliant audio function:

- 24-channel, 24-bit playback at the rates advertised by the device;
- 24-channel, 24-bit capture;
- a `HiFi` verb with stereo convenience devices for every adjacent pair;
- a `Direct` verb with the complete 24-channel playback and capture streams.

The stereo names are deliberately generic (`USB playback 1-2`, `USB capture
1-2`, and so on). They are USB stream lanes, not guaranteed physical
connectors: the Orion's routing, gain, monitoring, and mixer controls are on
its vendor HID interface and remain the responsibility of `antelope-ctl` or
the WebUI. The USB Audio control interface exposes no standard mixer controls
that UCM2 can configure.

## Install

The stock `USB-Audio.conf` supplied by `alsa-ucm-conf` has a per-USB-ID
extension point. Install the files below into the system UCM2 directory (on
the usual Fedora/Debian layouts this is `/usr/share/alsa/ucm2`):

```sh
sudo install -d /usr/share/alsa/ucm2/USB-Audio/Antelope \
               /usr/share/alsa/ucm2/USB-Audio/conf.d
sudo install -m 0644 \
  ucm2/USB-Audio/Antelope/OrionStudio-III.conf \
  ucm2/USB-Audio/Antelope/OrionStudio-III-HiFi.conf \
  /usr/share/alsa/ucm2/USB-Audio/Antelope/
sudo install -m 0644 ucm2/USB-Audio/conf.d/23e5-a221.conf \
  /usr/share/alsa/ucm2/USB-Audio/conf.d/
```

The `23e5-a221.conf` drop-in selects the profile from the generic USB-Audio
configuration. It avoids matching the device's topology-dependent long card
name and does not change the generic configuration for other USB cards.

## Check the loaded profile

After reconnecting the device or restarting the audio session, inspect the
verbs and devices with:

```sh
alsaucm -n -b - <<'EOF'
open hw:III
list _verbs
set _verb HiFi
list _devices
EOF
```

For the full raw stream, select the `Direct` verb. The current repository
does not include a system-wide installer because UCM2 paths are owned by the
distribution package manager.
