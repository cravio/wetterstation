#!/bin/bash
# ============================================================
# AirPlay 2 Receiver "wohnzimmer airplay" + Visualizer-Audio-Tap
# fuer die Wetterstation (Raspberry Pi Zero 2 W, USB-DAC)
#
# Aufruf auf dem Pi, aus dem wetterstation-Verzeichnis:
#   ./deploy/setup_airplay.sh ["receiver name"]
#
# Hinweis Zero 2 W: der shairport-sync-Build dauert 30-60 Min
# (make -j2 wegen 512 MB RAM). Vorher pruefen, ob das apt-Paket
# schon AirPlay 2 kann: `apt show shairport-sync`, dann
# `shairport-sync -V` (muss "AirPlay2" enthalten). nqptp gibt es
# in bookworm NICHT als Paket und muss immer aus Source gebaut werden.
# ============================================================
set -e

DEVICE_NAME="${1:-wohnzimmer airplay}"
DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "=== AirPlay-Setup: $DEVICE_NAME ==="

# --- Build-Dependencies ---
echo "[1/7] Build-Dependencies installieren..."
sudo apt-get update
sudo apt-get install -y \
  build-essential git autoconf automake libtool \
  libpopt-dev libconfig-dev libasound2-dev libavahi-client-dev \
  libssl-dev libsoxr-dev libplist-dev libsodium-dev \
  libavutil-dev libavcodec-dev libavformat-dev \
  uuid-dev libgcrypt-dev xxd libplist-utils \
  avahi-daemon alsa-utils \
  python3-numpy python3-alsaaudio

# --- NQPTP (AirPlay-2-Timing) ---
echo "[2/7] NQPTP bauen..."
cd /tmp
rm -rf nqptp
git clone https://github.com/mikebrady/nqptp.git
cd nqptp
autoreconf -i -f
./configure --with-systemd-startup
make -j2
sudo make install
sudo systemctl daemon-reload
sudo systemctl enable --now nqptp

# --- Shairport-sync (AirPlay 2) ---
echo "[3/7] shairport-sync bauen (dauert auf dem Zero 2 W 30-60 Min)..."
cd /tmp
rm -rf shairport-sync
git clone https://github.com/mikebrady/shairport-sync.git
cd shairport-sync
autoreconf -i -f
./configure --sysconfdir=/etc \
  --with-alsa --with-avahi --with-ssl=openssl \
  --with-soxr --with-metadata --with-airplay-2 --with-systemd
make -j2
sudo make install
sudo useradd -r -s /usr/sbin/nologin -G audio shairport-sync 2>/dev/null || true

# --- ALSA: Loopback + USB-DAC ---
echo "[4/7] ALSA konfigurieren..."
sudo install -m 644 "$DEPLOY_DIR/snd-aloop-modules-load.conf" /etc/modules-load.d/snd-aloop.conf
sudo install -m 644 "$DEPLOY_DIR/snd-aloop-modprobe.conf" /etc/modprobe.d/snd-aloop.conf
sudo modprobe snd-aloop index=7 pcm_substreams=1 || true

# USB-DAC-Kartennamen erkennen (erste Karte, die nicht Loopback/vc4/Headphones ist)
DAC_CARD=$(aplay -l | awk -F'[][ :]+' '/^card/ {print $3}' \
  | grep -viE 'loopback|vc4|hdmi|headphones' | head -1)
if [ -z "$DAC_CARD" ]; then
  echo "WARNUNG: Kein USB-DAC gefunden (aplay -l pruefen)."
  echo "         /etc/asound.conf wird mit Platzhalter installiert –"
  echo "         @DAC_CARD@ manuell ersetzen, sobald der DAC steckt."
  DAC_CARD="@DAC_CARD@"
else
  echo "USB-DAC erkannt: card \"$DAC_CARD\""
fi
sed "s/@DAC_CARD@/$DAC_CARD/g" "$DEPLOY_DIR/asound.conf" | sudo tee /etc/asound.conf > /dev/null

# --- Hooks + shairport-Konfiguration ---
echo "[5/7] shairport-sync konfigurieren..."
sudo install -m 755 "$DEPLOY_DIR/airplay-active.sh" /usr/local/bin/airplay-active.sh
sed "s/wohnzimmer airplay/$DEVICE_NAME/" "$DEPLOY_DIR/shairport-sync.conf" | sudo tee /etc/shairport-sync.conf > /dev/null

# Systemd drop-in: RuntimeDirectory raeumt das Flag-File auf
sudo mkdir -p /etc/systemd/system/shairport-sync.service.d
sudo install -m 644 "$DEPLOY_DIR/shairport-sync-wetterstation.conf" \
  /etc/systemd/system/shairport-sync.service.d/wetterstation.conf

sudo systemctl daemon-reload
sudo systemctl enable --now shairport-sync

# --- wetterstation: audio-Gruppe fuer Loopback-Capture ---
echo "[6/7] wetterstation.service anpassen..."
if [ -f /etc/systemd/system/wetterstation.service ]; then
  if ! grep -q "SupplementaryGroups=audio" /etc/systemd/system/wetterstation.service; then
    sudo sed -i '/^\[Service\]/a SupplementaryGroups=audio' /etc/systemd/system/wetterstation.service
    sudo systemctl daemon-reload
    sudo systemctl restart wetterstation || true
  fi
else
  echo "Hinweis: /etc/systemd/system/wetterstation.service nicht gefunden –"
  echo "         SupplementaryGroups=audio manuell ergaenzen."
fi

# --- Verifikation ---
echo "[7/7] Fertig. Verifikationsschritte:"
echo ""
echo "  1. Ton-Kette:      speaker-test -D airplay_out -c2 -twav -l1"
echo "  2. Loopback-Tap:   arecord -D hw:Loopback,1,0 -f S16_LE -r 44100 -c 2 -d 3 /dev/null -vv"
echo "  3. Vom iPhone auf \"$DEVICE_NAME\" streamen"
echo "  4. Flag-File:      cat /run/shairport-sync/active (existiert waehrend Stream)"
echo "  5. Visualizer:     laeuft automatisch, wenn wetterstation idle ist"
echo ""
