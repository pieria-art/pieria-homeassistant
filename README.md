# Pieria for Home Assistant

Control your [Pieria](https://pieria.org) art appliance from Home Assistant: a media player per display
(so the stock media card shows the painting), playlists as sources, a quiet-mode switch, and services.

Requires a Pieria server with the public API v1 (including `/quiet`, pause/resume and `/show`) and
Home Assistant 2026.2 or newer. Local polling only, no cloud.

## Install (HACS custom repository)

1. HACS -> three-dot menu -> **Custom repositories** -> add this repository's URL, category **Integration**.
2. Install **Pieria**, restart Home Assistant.
3. **Settings -> Devices & services -> Add integration -> Pieria**. A server advertising
   `_pieria._tcp` over mDNS is discovered automatically; otherwise enter host and port.

## Create an API token

In Pieria open **Settings -> API & Integrations**, create a token, and tick **both `read` and
`control`** (control does not imply read; the integration needs both). The token is shown once. Paste
it into the config flow. If it is revoked, Home Assistant asks you for a new one (re-authentication).

## Entities

Per display (one device each, linked to the server device):

| Entity | Notes |
|---|---|
| `media_player.<display>` | playing / paused / off (display not live). Title, artist, artwork image, next / previous / play / pause, `source` = playlist (select to switch) |
| `select.<display>_render_mode` | ken-burns / static-crop / contain-matte (canvas displays only) |
| `button.<display>_show_placard` | canvas displays only |
| `binary_sensor.<display>_online` | connectivity: is the display checking in |
| `image.<display>_artwork` | the current artwork |

Per server: `switch.<server>_quiet_mode` (on = art off; attributes `source`, `until`).

Sleeping e-ink panels show as `off`; commands to a display that is not live fail with a clear
"not live" error instead of queueing.

Options: poll interval (default 10 s, minimum 5 s).

## Services

- `pieria.show_artwork` - target a Pieria media player; give `artwork_id` **or** `query` (best search hit).
- `pieria.set_quiet` - target the quiet switch; `on`, plus optional `until` (datetime) or `duration`.

## Example automations

Night playlist at sunset:

```yaml
automation:
  - alias: Pieria night playlist
    triggers:
      - trigger: sun
        event: sunset
    actions:
      - action: media_player.select_source
        target: { entity_id: media_player.living_room }
        data: { source: Night }
```

Quiet when everyone leaves:

```yaml
automation:
  - alias: Pieria quiet when away
    triggers:
      - trigger: state
        entity_id: zone.home
        to: "0"
    actions:
      - action: switch.turn_on
        target: { entity_id: switch.pieria_quiet_mode }
  - alias: Pieria on when someone is home
    triggers:
      - trigger: numeric_state
        entity_id: zone.home
        above: 0
    actions:
      - action: switch.turn_off
        target: { entity_id: switch.pieria_quiet_mode }
```

Holiday collection in December:

```yaml
automation:
  - alias: Pieria December collection
    triggers:
      - trigger: time
        at: "07:00:00"
    conditions:
      - condition: template
        value_template: "{{ now().month == 12 }}"
    actions:
      - action: media_player.select_source
        target: { entity_id: media_player.living_room }
        data: { source: Winter }
```

Show a painting on request:

```yaml
action: pieria.show_artwork
target: { entity_id: media_player.living_room }
data: { query: starry night }
```

## Development

```
python3.13 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest && .venv/bin/ruff check .
```

Licence: to be chosen by the maintainer.
