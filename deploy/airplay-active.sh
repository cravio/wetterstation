#!/bin/sh
# Called by shairport-sync sessioncontrol hooks.
# The flag file signals "AirPlay is streaming" to wetterstation.
# Lives in /run/shairport-sync/ (RuntimeDirectory): systemd removes it
# when shairport-sync stops or crashes, so it can never go stale.
FLAG=/run/shairport-sync/active
case "$1" in
  on)  touch "$FLAG" ;;
  off) rm -f "$FLAG" ;;
esac
