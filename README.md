# Pieria for Home Assistant

Control your [Pieria](https://pieria.org) art appliance from Home Assistant: a media player per display
(so the stock media card shows the painting), playlists as sources, quiet-mode controls, and services.

Requires a Pieria server with the public API v1 and Home Assistant 2026.2 or newer. Local polling,
no cloud. Optional features (pause, quiet, show) are detected from the server's `/info`
`api_features`; entities and services for a feature the server does not advertise are not created.

## Install (HACS custom repository)

1. HACS -> three-dot menu -> **Custom repositories** -> add this repository's URL, category **Integration**.
2. Install **Pieria**, restart Home Assistant.
3. **Settings -> Devices & services -> Add integration -> Pieria**. A server advertising
   `_pieria._tcp` over mDNS is discovered automatically; otherwise enter host and port.

## Create an API token

In Pieria open **Settings -> API & Integrations**, create a token, and tick **both `read` and
`control`** (control does not imply read; the integration needs both; the config flow reports
`missing_scope` if either is absent). The token is shown once. Paste
it into the config flow. If it is revoked, Home Assistant asks you for a new one (re-authentication).

## Entities

Per display (one device each, linked to the server device):

| Entity | Notes |
|---|---|
| `media_player.<display>` | playing / paused / off (display not live). Title, artist, artwork image, play / pause, next / previous (not on e-ink or frame displays), `source` = playlist (select to switch) |
| `select.<display>_render_mode` | ken-burns / static-crop / contain-matte (canvas displays only) |
| `button.<display>_show_placard` | canvas displays only |
| `binary_sensor.<display>_online` | connectivity: is the display checking in |
| `image.<display>_artwork` | the current artwork |

Per server (when the server advertises `quiet`):

| Entity | Notes |
|---|---|
| `select.<server>_quiet_mode` | `auto` (follow the quiet-hours schedule) / `on` (quiet now) / `off` (awake now). `on` and `off` end at the next schedule boundary |
| `switch.<server>_quiet_mode` | on = art off right now, whatever the cause. Attributes `mode`, `source` (`schedule` / `manual` / `none`), `until`. Turn on forces quiet; turn off forces awake when a schedule is making it quiet, otherwise clears the override (`auto`) |

Device names come from each display's name. After a command the state is shown optimistically until
the server's `updated_at` for that display advances (or about 10 s pass), and a refresh is requested.

Sleeping e-ink panels show as `off`; commands to a display that is not live fail with a clear
"not live" error instead of queueing.

Options: poll interval (default 10 s, minimum 5 s).

## Services

- `pieria.show_artwork` - target a Pieria media player; give `artwork_id` **or** `query` (best search hit).
- `pieria.set_quiet` - target the quiet switch; `mode` (`on` / `off` / `auto`), plus optional `until` (datetime) or `duration` (ignored for `auto`).

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
      - action: select.select_option
        target: { entity_id: select.pieria_quiet_mode }
        data: { option: "on" }
  - alias: Pieria back to schedule when someone is home
    triggers:
      - trigger: numeric_state
        entity_id: zone.home
        above: 0
    actions:
      - action: select.select_option
        target: { entity_id: select.pieria_quiet_mode }
        data: { option: auto }
```

Stay awake for two hours tonight, regardless of the schedule:

```yaml
action: pieria.set_quiet
target: { entity_id: switch.pieria_quiet_mode }
data: { mode: "off", duration: { hours: 2 } }
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
