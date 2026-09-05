# Roborock Rooms – Home Assistant integration

En custom Home Assistant-integration (installeres via [HACS](https://hacs.xyz)) der henter
rum/segment-ID'er fra din Roborock-konto og gør dem tilgængelige som entities i Home
Assistant – uden at du selv skal slå segment-ID'er op og skrive dem ind i automatiseringer.

For hver Roborock-støvsuger på kontoen oprettes:

- **En sensor pr. rum**, hvis state er rummets segment-ID (det tal, Roborocks cloud-API
  bruger til at identificere rummet), fx `sensor.stuen_koekken` → state `14`.
- **En knap pr. rum** ("Clean <rum>"), der starter en rengøring af netop det rum.
- En service, **`roborock_rooms.clean_rooms`**, til at rengøre flere rum på én gang.

## Installation

### Via HACS (custom repository)

1. HACS → tre prikker øverst til højre → **Custom repositories**.
2. Tilføj `https://github.com/PeterNielsenDev/-Roborock-rum-ID-er` som kategori **Integration**.
3. Find "Roborock Rooms" i HACS og installer den.
4. Genstart Home Assistant.
5. **Indstillinger → Enheder og tjenester → Tilføj integration** → søg efter "Roborock Rooms".

### Manuelt

Kopiér mappen `custom_components/roborock_rooms` ind i din Home Assistant-installations
`config/custom_components/` mappe, genstart, og tilføj integrationen som ovenfor.

## Login

Under opsætningen bliver du bedt om din Roborock-kontos email. Du kan enten:

- indtaste din adgangskode, eller
- lade adgangskoden stå tom, hvorefter du modtager en engangskode på email, som du
  efterfølgende indtaster.

Login gemmes i Home Assistants config entry og bruges automatisk fremover.

## Brug af `clean_rooms`-servicen

```yaml
service: roborock_rooms.clean_rooms
data:
  duid: "abc123..."        # se attributten "duid" på en af rum-sensorerne
  segments: [2, 5]         # segment-ID'erne for de rum, der skal rengøres
  repeat: 1                # valgfri, 1-3
```

`duid` og segment-ID'erne kan aflæses direkte fra rum-sensorernes state og attributter i
**Udviklerværktøjer → Tilstande**.

## Begrænsninger

- Kun understøttet på V1-robotstøvsugere (dvs. ikke Qrevo/Q10-serien, der bruger en
  anden protokol).
- Rum-opdagelse kan ikke køre, mens støvsugeren er i gang med at gøre rent – integrationen
  springer da over og prøver igen ved næste opdatering (hvert 30. minut).
- Kontoens liste over enheder (`home_data`) er rate-limited af Roborocks cloud-API
  (ca. 5 opslag/time) og caches derfor lokalt; selve rum-/segment-data hentes altid
  live fra støvsugeren, så nye eller omdøbte rum dukker op med det samme.

Bygget på [python-roborock](https://github.com/python-roborock/python-roborock).
