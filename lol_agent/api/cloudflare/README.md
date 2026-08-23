# Cloudflare Tunnel — Darmowy dostęp zdalny

Dzięki Cloudflare Tunnel apka na telefonie może połączyć się z PC nawet poza domem.
Bez płatnego serwera, bez otwierania portów routera.

## Instalacja (jednorazowa)

### Krok 1 — Zainstaluj cloudflared
```powershell
winget install Cloudflare.cloudflared
```

### Krok 2 — Zaloguj się do Cloudflare
```powershell
cloudflared tunnel login
```
Otworzy przeglądarkę — zaloguj się na konto Cloudflare (darmowe).

### Krok 3 — Utwórz tunel
```powershell
cloudflared tunnel create shortsyt
```
Zapisz UUID tunelu który pojawi się w output.

### Krok 4 — Utwórz konfigurację
Skopiuj `config.yml.example` do `~/.cloudflared/config.yml` i uzupełnij UUID:

```yaml
tunnel: TWOJ-UUID-TUNELU
credentials-file: C:\Users\mz100\.cloudflared\TWOJ-UUID.json

ingress:
  - hostname: shortsyt.twoja-domena.com
    service: http://localhost:8765
  - service: http_status:404
```

### Krok 5 — Bez własnej domeny (darmowy subdomain)
```powershell
# Uruchom jednorazowo — daje losowy URL *.trycloudflare.com
cloudflared tunnel --url http://localhost:8765
```
URL pojawi się w konsoli — wklej go w apce (Settings → Server URL).

> **Uwaga**: Darmowy URL zmienia się przy każdym uruchomieniu.
> Jeśli chcesz stały URL — zarejestruj darmową domenę na Cloudflare.

## Codzienne użycie

1. Uruchom `start_server.bat` — automatycznie startuje FastAPI + Cloudflare Tunnel
2. W apce: Settings → wklej URL z konsoli (jeśli używasz darmowego tunnelu)
3. Gotowe!

## Bezpieczeństwo

- Komunikacja przez HTTPS (Cloudflare szyfruje automatycznie)
- JWT token chroni wszystkie endpointy API
- Hasło zmień w `.env` (klucz `API_PASSWORD`)
