# Critical Connection – Adminportaal

Deze release voegt gebruikersbeheer en stationsrechten toe aan de bestaande FastAPI-app.

## Upgrade op Render

Vervang in GitHub `app/main.py`, `app/index.html` en `app/static.js` met de bestanden uit dit pakket. Laat de overige bestanden ongewijzigd. Deploy de laatste commit op Render. De bestaande SQLite-database wordt uitgebreid met `users` en `user_stations`; bestaande meetgegevens blijven staan zolang dezelfde persistente disk en `DB_PATH` worden gebruikt.

## Inloggen

Bij de eerste start zonder bestaande administrator wordt automatisch een adminaccount gemaakt. Gebruikersnaam: `admin` (of `ADMIN_USERNAME` uit de Render Environment). Wachtwoord: de bestaande waarde van `ADMIN_PASSWORD`. De admin kan via het portaal nieuwe accounts met minimaal 12 tekens wachtwoord maken, rollen kiezen, accounts uitschakelen en weerstations toekennen.

Let op: wanneer een administrator al is aangemaakt, verandert het wijzigen van `ADMIN_PASSWORD` in Render zijn bestaande wachtwoord niet. Bewaar de bestaande configuratie.

## Rechten

`admin`: alle stations, beheren van stations en gebruikers. `viewer`: alleen toegewezen stations, geschiedenis, alarmen en export. Rechten worden server-side afgedwongen.

## Productie

Gebruik een persistente Render disk, `WEB_CONCURRENCY=1`, HTTPS en een sterke `SESSION_SECRET` en `FERNET_KEY`. Maak back-ups van de SQLite-database. De app bevat geen automatische e-mailalarmering, self-service wachtwoordreset, MFA of auditlog; gebruik de app daarom niet als enige veiligheidswaarschuwing bij evenementen.
