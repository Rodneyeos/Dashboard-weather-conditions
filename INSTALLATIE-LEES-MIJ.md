# Critical Connections — complete dashboard update

Deze ZIP combineert het adminportaal, gebruikersgebonden windmeters, totaaloverzicht, keuzemenu km/h–m/s–knopen–mph, rapportage met Nederlandse datum/tijd, windrichtingkompas en het aangeleverde Critical Connections-logo.

## BESTAANDE WINDMETERS BEHOUDEN

**Verwijder of reset de database NIET.** De windmeters, API-sleutels, gebruikers, toewijzingen en historie staan in SQLite, standaard `/data/weather.sqlite3`. De nieuwe applicatie gebruikt dezelfde tabellen en database.

1. Maak vóór de update een back-up van de bestaande database, bij voorkeur inclusief WAL-bestanden of met SQLite `.backup`.
2. Controleer in Render > Disks dat de bestaande persistent disk nog gekoppeld is aan `/data`.
3. Controleer in Render > Environment dat `DB_PATH=/data/weather.sqlite3`, `FERNET_KEY`, `SESSION_SECRET` en `ADMIN_PASSWORD` ongewijzigd blijven. **Wijzig FERNET_KEY NIET**, anders zijn opgeslagen AWEKAS-sleutels niet meer te ontsleutelen.
4. Upload de inhoud van deze `awekas-dashboard/` naar je bestaande GitHub repository en commit. Verwijder in GitHub geen overige eigen bestanden.
5. Render deployt opnieuw. Controleer login, totaaloverzicht, eenheid, kompas, rapportage en adminportaal.

**Let op:** Bij een nieuw Render-service of een andere disk is de bestaande SQLite database niet automatisch aanwezig. Deze update bevat geen live database of persoonlijke sleutels. Een deploy op dezelfde service met dezelfde persistente disk behoudt de records.

Het ZIP-bestand is syntax-gecontroleerd maar niet getest tegen je live Render-server of live AWEKAS-account.
