# AWEKAS Weather Control (Ubuntu VPS)

FastAPI + SQLite + Docker Compose. Meerdere AWEKAS-stations, historische wind-/regenmetingen, drempelalarmen, CSV-export en admin-login.

## Installeren (Ubuntu 22.04 / 24.04)

1. Installeer Docker Engine en Docker Compose plugin via de officiële Docker Ubuntu-instructies.
2. Pak de ZIP uit op de VPS, bijvoorbeeld in `/opt/awekas-dashboard`.
3. Maak het configuratiebestand:

```bash
cp .env.example .env
python3 - <<'PY'
import secrets
from cryptography.fernet import Fernet
print('SESSION_SECRET='+secrets.token_hex(32))
print('FERNET_KEY='+Fernet.generate_key().decode())
PY
```

Voor de generator is lokaal `python3 -m pip install cryptography` nodig; je kunt de sleutels ook in een tijdelijke Docker Python-container genereren. Zet de drie vereiste waarden in `.env`. Gebruik een sterk, uniek `ADMIN_PASSWORD` en bewaar `.env` buiten versiebeheer.

4. Start:

```bash
chmod 600 .env
docker compose up -d --build
docker compose logs -f dashboard
```

5. De webapp luistert **alleen op 127.0.0.1:8000**. Publiceer via een reverse proxy met HTTPS (bijvoorbeeld Caddy of Nginx) en een eigen domein. Voor Caddy:

```caddyfile
weer.example.nl {
  reverse_proxy 127.0.0.1:8000
}
```

6. Open `https://weer.example.nl`, log in en voeg je AWEKAS-station toe via de beheerpagina. De API-sleutel wordt versleuteld opgeslagen en nooit naar de browser teruggestuurd.

## AWEKAS

De API wordt via `https://api.awekas.at/current.php?key=...&lng=nl` opgevraagd. `POLL_SECONDS=60` betekent 60 aanvragen per uur per station (onder de gedocumenteerde limiet van 240). Er is per station een **eigen API-sleutel** nodig en AWEKAS Plus kan vereist zijn.

Een gedeelde sleutel moet je bij AWEKAS vernieuwen. De eerder in de chat gedeelde sleutel is **niet** in de bestanden opgenomen.

## Alarmen

- Windstoot >= ingestelde km/u
- Regenintensiteit >= ingestelde mm/u
- Alarmen openen/sluiten automatisch bij een **verse** meting (<10 minuten oud).
- Stale/ontbrekende data wordt apart gemeld, maar is geen drempelalarm.
- De alarmen zijn **dashboard- en databasealarmen**; er worden nog geen e-mails, sms'jes of pushmeldingen verstuurd.

## Back-up / productie

Back-up de Docker-volume `weather_data` (SQLite inclusief WAL, bij voorkeur via SQLite backup API of bij gestopte container) en de `.env`/Fernet-sleutel apart en veilig. De encryptiesleutel is nodig om de opgeslagen AWEKAS-sleutels te ontsleutelen.

Deze versie heeft één adminaccount, geen rollen/groepen. Gebruik HTTPS en een firewall; zet poort 8000 niet publiek open. Voor bedrijfskritische event-veiligheid: test alarmen, sensorkwaliteit, datavertraging en fallbackprocedures voordat je operationeel op het systeem vertrouwt.
