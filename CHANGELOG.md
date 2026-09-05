# Changelog

## 0.2.2

- Rettet fejlende CI-validering: manifest-nøgler sorteret korrekt til hassfest,
  repo-beskrivelse og topics tilføjet, og et brand-ikon oprettet under
  `custom_components/roborock_rooms/brand/` (krævet af HACS). Ingen
  funktionelle ændringer.

## 0.2.1

- Rettet: cache-filen for konto-data blev læst og skrevet synkront direkte i
  event loopet, hvilket udløste Home Assistants "Detected blocking call"
  advarsel ved opsætning/opdatering. Al fil-I/O køres nu i en executor-tråd.

## 0.2.0

- Ny "Clean all rooms"-knap pr. støvsuger.
- `clean_rooms`-servicen bruger nu en device-selector i stedet for en rå `duid`-tekststreng.
- Reauth-flow: Home Assistant beder automatisk om login igen, hvis det gemte token bliver afvist.
- Options flow til at konfigurere opdateringsintervallet (standard 30 minutter).
- Reparations-advarsel, hvis rum-opdagelse fejler gentagne gange for en støvsuger.
- Understøtter "Download diagnostics" (kontodata og token maskeres automatisk).

## 0.1.0

- Første udgave: login-flow, rum-sensorer (state = segment-ID), rum-knapper og
  `roborock_rooms.clean_rooms`-servicen.
