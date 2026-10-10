# Critical Connections – ESP32 PoE + RS485 windmeter

## Werking

Deze release voegt een **tweede databron** toe naast AWEKAS. Bestaande stations, historie en gebruikersrechten blijven in dezelfde SQLite-database staan. De database wordt uitsluitend uitgebreid met `stations.source` en `esp_devices`.

1. Maak een database-back-up van de persistente Render-disk `/data` en bewaar de bestaande `FERNET_KEY`.
2. Deploy deze release naar dezelfde Render-service en dezelfde persistente disk.
3. Log in als admin, open **ESP32 PoE / RS485 windmeter toevoegen**, geef de locatie op en sla op.
4. Bewaar het nieuwe station-ID en de **eenmalig getoonde** device-token. Zet ze in de ESP32-firmware.
5. Wijs het station via het bestaande adminportaal toe aan de gewenste gebruikers.

## ESP32 POST protocol

`POST https://JOUW-RENDER-URL/api/esp/ingest/STATION_ID`

Headers:

- `Authorization: Bearer JOUW_DEVICE_TOKEN`
- `Content-Type: application/json`

Body (alleen `wind` is verplicht):

```json
{"wind": 18.5, "gust": 27.2, "direction": 225, "rainrate": 0}
```

**Eenheden:** `wind` en `gust` altijd in **km/h**; `direction` in meteorologische graden 0=N, 90=O, 180=Z, 270=W; `rainrate` in mm/uur. Het dashboard converteert km/h naar de door de gebruiker gekozen eenheid. De server zet de ontvangsttijd op de meting, zodat de ESP32 geen realtimeklok nodig heeft. Stuur bij voorkeur elke 30–60 seconden een meting. `gust` is optioneel, maar windstootalarmen werken alleen als de sensor windstoten aanlevert.

**Let op:** een RS485-windsensor geeft vaak alleen windsnelheid. Een kompas heeft een **aparte windrichtingssensor** of gecombineerde sensor nodig. Zonder richting blijft het kompas leeg. De registeradressen, Modbus slave-ID, baudrate, pariteit, schaalfactor en pinnen zijn **sensor- en ESP32-bordspecifiek**. Stel deze vast aan de hand van de datasheets voordat firmware geschreven of aangesloten wordt.

## Netwerk en beveiliging

- Gebruik een ESP32 PoE-bord met werkende Ethernet-ondersteuning en een **geschikte RS485-transceiver** (bij voorkeur galvanisch geïsoleerd).
- Verbind RS485 A/B en referentie volgens de sensorhandleiding; voed de sensor volgens diens specificaties. **Sluit nooit 12/24 V direct aan op ESP32 GPIO.**
- Gebruik HTTPS en **controleer het servercertificaat** in de ESP32-firmware; schakel TLS-validatie niet uit.
- Sla device-tokens niet in GitHub op. Eén token per ESP32; een gestolen token kan via `/api/esp/stations/{id}/rotate` ongeldig worden gemaakt (admin-login + CSRF).
- Voor productie is een vaste device-interval en eventueel rate limiting aan de edge aanbevolen.
- Render moet een persistente disk voor SQLite hebben, anders kunnen stations en historie bij een herstart verdwijnen.

## Handmatige test met curl

```bash
curl --fail-with-body -X POST 'https://JOUW-RENDER-URL/api/esp/ingest/123' \
  -H 'Authorization: Bearer JOUW_DEVICE_TOKEN' \
  -H 'Content-Type: application/json' \
  --data '{"wind":18.5,"gust":27.2,"direction":225}'
```

Verwacht: `{"ok":true,"received_at":...}`. Daarna verschijnt de meting in het totaaloverzicht, de grafiek en CSV-export. Test eerst met een nieuw ESP32-station en laat de bestaande AWEKAS-stations ongemoeid.
