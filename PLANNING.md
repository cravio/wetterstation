# Wetterstation – Planung & Roadmap

## Status: v2.0.0

Modulare Architektur, 127 Tests, Systemd-Service, FIFO-Fernsteuerung. Stabil im Betrieb auf Raspberry Pi 5.

---

## Erledigte Meilensteine

### v2.0.0 – TDD-Refactoring (März 2026)
- [x] 820-Zeilen-Monolith in 8 Module aufgeteilt
- [x] Thread-safe State Machine mit Event Queue
- [x] DisplayBackend Protocol + Simulator für Tests
- [x] Alle SPI-Operationen nur im Main Thread
- [x] Pi 5 SPI-Fix: Triple-Show mit 3ms Gaps
- [x] Interruptible Animationen via `threading.Event`
- [x] 4-Button-Steuerung (A/B/X/Y) mit Double-Click
- [x] Terminal- und FIFO-Input
- [x] Systemd-Service + täglicher Autostart
- [x] Autostart mit konfigurierbaren Zyklen (statt Dauerbetrieb)
- [x] 127 Unit-Tests (pytest)
- [x] README + anonymisierte Config

---

## Bekannte Einschränkungen

| Thema | Details |
|-------|---------|
| Zeitzone | Hardcodiert `Europe/Zurich` in `weather.py` |
| Fehleranzeige | Keine visuelle Anzeige bei API-Fehler (zeigt letzte bekannte Daten) |
| Übergänge | Kein Fade-Out/Fade-In zwischen Animationen |
| Persistenz | Kein gespeicherter Zustand zwischen Neustarts |
| Nur heute | Zeigt nur Wetter für den aktuellen Tag |

---

## Test-Coverage

| Modul | Coverage | Bemerkung |
|-------|----------|-----------|
| `config.py` | 100% | |
| `renderer.py` | 100% | |
| `weather.py` | 100% | |
| `state.py` | 98% | 2 Edge-Case-Zeilen |
| `simulator.py` | 93% | |
| `animations.py` | 84% | Interrupt-Pfade teilweise ungetestet |
| `__main__.py` | 0% | Integration/Threading – schwer zu testen |
| `display.py` | 0% | Hardware-abhängig |
| `input.py` | 0% | Threading, GPIO, FIFO |

**Priorität**: `animations.py` auf >90% bringen, Integration-Tests für `input.py` dispatch-Logik.

---

## Offene Aufgaben

### Kurz (Quick Wins)
- [ ] `animations.py` Coverage auf >90% (Interrupt-Edge-Cases testen)
- [ ] `dispatch_command()` Unit-Tests (ist pure Funktion, leicht testbar)
- [ ] Stale-Indikator testen (rotes Pixel wenn API-Daten veraltet)

### Mittel
- [ ] **Telegram Bot**: Nachrichten ans Display senden, Status abfragen (python-telegram-bot)
- [ ] **Email (IMAP)**: Betreff/Body als Scrolltext ans Display (z.B. Gmail per IMAP-Polling)
- [ ] Fehler-Animation: Blinkendes Icon wenn API seit >1h nicht erreichbar
- [ ] Konfigurierbare Zeitzone (statt hardcodiert)
- [ ] `config.json` Validierung mit klaren Fehlermeldungen
- [ ] Logging-Level per Config steuerbar (DEBUG/INFO/WARNING)

### Langfristig (Nice to Have)
- [ ] Mehrtages-Vorhersage (z.B. morgen/übermorgen als Scrolltext)
- [ ] Mehrere Standorte (durchblätterbar per Button)
- [ ] Fade-Übergänge zwischen Animationen
- [ ] Helligkeitsanpassung nach Uhrzeit (nachts dunkler)
- [ ] Web-Interface für Konfiguration (statt JSON-Datei editieren)
- [ ] OTA-Updates (git pull + systemctl restart per Knopfdruck)

---

## Architektur-Notizen

### Thread-Modell
```
ButtonHandler (GPIO-Thread)  ──┐
TerminalInput (stdin-Thread) ──┤
FifoInput (FIFO-Thread)      ──┼──► Event Queue ──► StateMachine ──► Display
AutostartScheduler (Thread)  ──┤                    (Main Thread)
WeatherFetcher (Thread)      ──┘
```

**Regel**: Nur der Main Thread darf `display.show()` aufrufen. Alle anderen Threads pushen Events.

### SPI-Stabilität (Pi 5)
- `paced_xfer`: Minimum 1ms zwischen SPI-Transfers
- `stable_show`: 3× senden mit je 3ms Pause
- `hat_reset`: clear + show + 10ms settle

### State Machine
```
IDLE ──START──► RUNNING ──CYCLE_COMPLETE──► IDLE (wenn Zyklen = 0)
  │                │
  ├──GREETING──► GREETING ──COMPLETE──► IDLE
  │                │
  └──INFO──────► INFO ──COMPLETE──► IDLE
```

---

## Gelöste Probleme (Referenz)

| Problem | Ursache | Lösung | Commit |
|---------|---------|--------|--------|
| Display-Flicker | Mehrere Python-Prozesse auf SPI-Bus | Crontab entfernt, Systemd only | `9a73379` |
| Halber Screen | Pi 5 SPI-Timing zu schnell | Triple-Show mit 3ms Gaps | `9a73379` |
| Commands reagieren nicht | Interrupt-Event nicht verbunden | `StateMachine(interrupt=event)` | `954ddea` |
| Greeting/Info starten nicht | `interrupt.clear()` vor `process_events()` | Clear nach Processing | `80c9376` |
| Greeting überschreibt Info | COMPLETE auch bei Interrupt gesendet | Nur bei echtem Abschluss senden | `98bd552` |
| Autostart läuft endlos | `_cycles_remaining = CONTINUOUS` | Zyklen aus Config lesen | `2aede1b` |
