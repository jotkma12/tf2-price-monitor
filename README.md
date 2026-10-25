# TF2 Price Monitor

Monitor personal de precios para Team Fortress 2 con:
- Página estática (GitHub Pages) con tabla, filtros e historial gráfico.
- GitHub Actions programado cada 12 horas.
- Supabase para guardar artículos e historial.
- Notificaciones de cambios por Telegram.
- Adaptador de proveedor preparado para una API autorizada.

## Estado importante

Este proyecto está listo como base funcional, pero **no incluye una integración inventada con PriceScout.tf**. Antes de activar consultas automáticas, confirma con el proveedor el endpoint, autenticación, límites y si devuelve precios de venta y buy orders. El monitor no hace scraping de Mannco.Store ni automatiza compras.

Hasta configurar `PRICE_API_URL` y el formato de respuesta documentado por el proveedor, el workflow se ejecuta en modo seguro y no registra precios falsos.

## 1. Crear servicios

1. Crea un repositorio GitHub llamado `tf2-price-monitor`.
2. Crea un proyecto Supabase: https://supabase.com/
3. Crea un bot con `@BotFather` en Telegram y consigue el token. Envía un mensaje al bot y consulta `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` para obtener tu `chat_id`.
4. Solicita al proveedor autorizado su endpoint/API key y confirma el esquema de respuesta.

## 2. Configurar Supabase

En SQL Editor ejecuta `supabase/schema.sql`.

La web usa la clave `anon`/publishable, con políticas RLS de solo lectura. El monitor usa la clave `service_role` únicamente en GitHub Actions; jamás la publiques en la web.

## 3. Configurar GitHub Secrets

En `Settings → Secrets and variables → Actions → New repository secret`, agrega:

- `SUPABASE_URL`: URL del proyecto Supabase.
- `SUPABASE_SERVICE_ROLE_KEY`: clave `service_role` de Supabase (solo en Actions).
- `TELEGRAM_BOT_TOKEN`: token del bot (opcional).
- `TELEGRAM_CHAT_ID`: tu chat ID (opcional).
- `PRICE_API_URL`: endpoint oficial/autorizado del proveedor (cuando lo tengas).
- `PRICE_API_KEY`: clave de la API del proveedor (cuando la tengas).

No añadas secretos al repositorio, a archivos HTML ni a `web/config.js`.

## 4. Configurar el proveedor

Edita `tracker.py` solo cuando tengas la documentación real del proveedor. El adaptador espera una respuesta JSON con una lista de observaciones. El formato esperado es:

```json
{
  "items": [
    {
      "item_name": "Mann Co. Supply Crate Key",
      "source": "provider-name",
      "price": 1.23,
      "currency": "USD",
      "item_url": "https://example.com/item",
      "kind": "sell"
    }
  ]
}
```

Este es un contrato de entrada para adaptar el proveedor, **no** una afirmación sobre el formato de PriceScout.tf. Si la API devuelve otro esquema, ajusta `normalize_provider_payload()` a la documentación oficial. La API debe permitir el uso previsto y el endpoint debe ser de lectura.

## 5. Publicar GitHub Pages

El repositorio incluye `.github/workflows/pages.yml`, que publica la carpeta `web/` mediante GitHub Actions.

1. En GitHub, abre `Settings → Pages`.
2. En **Build and deployment → Source**, selecciona **GitHub Actions**.
3. Guarda. Al subir cambios a `main`, el sitio se desplegará automáticamente.
4. En `web/config.js`, establece `SUPABASE_URL` y `SUPABASE_ANON_KEY` (solo clave pública anon/publishable). La clave pública se puede exponer con RLS correctamente configurado; nunca uses `service_role`.

## 6. Ejecutar

- Automático: GitHub Actions cada 12 horas (UTC).
- Manual: `Actions → TF2 Price Monitor → Run workflow`.
- Ver logs: pestaña `Actions`.
- La programación puede retrasarse por GitHub. No es un reloj exacto.

## 7. Costes y límites

Los planes gratuitos están sujetos a cuotas, políticas y cambios de proveedor. GitHub Actions puede tener límites y los servicios externos pueden pausarse o requerir pago. No se puede garantizar coste cero en cualquier circunstancia; configura límites y alertas de facturación.

## Seguridad y privacidad

- No uses scraping ni automatización de compras.
- No compartas tokens ni claves privadas.
- RLS limita el acceso de la web a las tablas expuestas.
- El monitor solo envía alertas por Telegram si se configuraron ambos secretos.
