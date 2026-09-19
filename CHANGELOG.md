# Changelog

## 0.4.0

- Individuelle rengøringsindstillinger pr. rum: hvert rum får nu valg for sugekraft,
  vandmængde og moppe-rute (kun dem, din model understøtter) samt antal gentagelser (1-3).
  Vælg "default" for at lade støvsugerens egen indstilling stå uændret.
- Rum-knapperne, "Clean all rooms" og `clean_rooms`-servicen bruger de enkelte rums
  indstillinger. Rum med forskellige indstillinger rengøres i grupper efter hinanden
  (støvsugeren kan kun bruge én indstilling ad gangen); næste gruppe starter, når
  støvsugeren er færdig og igen er på dock'en.
- `clean_rooms` har fået feltet `use_room_settings`, og `repeat` er nu valgfri
  (uden angivelse bruges hvert rums egen værdi).
- Intern oprydning: fælles forbindelses-hjælper til rengøring og rutiner.

## 0.3.0

- Rutiner ("routines"/scenes) fra Roborock-kontoen hentes nu med og vises som en knap
  pr. rutine, der udløser den direkte.
- Ny service, `roborock_rooms.run_routine`, til at udløse en rutine ud fra dens ID.
- Rettet: `roborock_rooms.clean_rooms`-servicen ville altid fejle med en `TypeError`,
  fordi den oprettede sin cache med den gamle `SafeFileCache`-signatur fra før 0.2.1.

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
