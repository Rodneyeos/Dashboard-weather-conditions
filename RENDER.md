# Publiceren op Render met GitHub

1. Maak een **private** GitHub repository en upload de inhoud van deze map (niet het ZIP-bestand zelf). Commit nooit `.env`, API-sleutels of wachtwoorden.
2. Genereer lokaal een Fernet-sleutel: `python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` (na `pip install cryptography`).
3. Ga naar https://dashboard.render.com/ -> New -> Blueprint en verbind de repository. Render leest `render.yaml`.
4. Kies bij de eerste deployment een sterk uniek `ADMIN_PASSWORD` en de gegenereerde `FERNET_KEY` als geheime waarden. `SESSION_SECRET` wordt automatisch gegenereerd.
5. Bevestig de betaalde Starter-webservice en persistent disk (Render toont actuele kosten voor bevestiging).
6. Na de build: open de door Render toegewezen `https://<service>.onrender.com` URL, log in en voeg je AWEKAS-station toe.
7. Controleer live data, alarmen, restart en opslag. Gebruik voor evenementen aanvullende onafhankelijke alarmering.

Let op: de database staat op `/data` op de persistente disk. De disk is gekoppeld aan één service-instantie; schaal niet horizontaal met deze SQLite-opzet. Bewaar `FERNET_KEY` veilig: zonder deze sleutel zijn opgeslagen AWEKAS-credentials niet meer te ontsleutelen. De Render-URL is pas na succesvolle deployment bekend.
