# Universal Room Thermostat (URT)

Custom integration YAML per Home Assistant che espone un solo termostato
virtuale per stanza e orchestra valvole, canalizzato condiviso e split del
salone. Gli attuatori fisici possono essere nascosti dalle dashboard: tutte le
impostazioni utente passano dalle entità `climate.urt_*`.

## Installazione

1. Copiare `custom_components/universal_room_thermostat` nella directory
   `custom_components` della configurazione Home Assistant.
2. Inserire la configurazione seguente in `configuration.yaml`.
3. Eseguire **Controlla configurazione** e riavviare Home Assistant.

## Configurazione per questa abitazione

```yaml
universal_room_thermostat:
  global:
    mode_entity: input_select.modalita_clima_casa
    comfort_cooling_target: 25
    maintenance_cooling_target: 28
    cooling_tolerance: 0.3
    sync_ui_climate: true
    heating_presets:
      comfort: 21
      eco: 19
      sleep: 18
      away: 16
    cooling_presets:
      comfort: 25
      eco: 27
      sleep: 26
      away: 28

  ducted_ac:
    climate_entity: climate.gateway_serranda_lora_daikin_canalizzato
    debounce: 5
    min_on_time: 300
    min_off_time: 300
    off_delay: 90
    command_interval: 15
    setpoint_high: 22
    setpoint_medium: 23
    setpoint_low: 24
    salon_boost_delta: 2
    split_heat_enabled: false

  dashboard:
    enabled: true
    title: Clima Casa
    icon: mdi:thermostat
    url_path: urt-clima-casa
    show_in_sidebar: true
    require_admin: false

  rooms:
    camera_fra:
      name: Camera Fra
      ui_climate: climate.termostato_camera_fra
      temperature_sensor: sensor.termostato_camera_fra_temperature
      heat_climate: climate.valvola_camera_fra
      presence_entity: binary_sensor.presenza_fra
      comfort_entity: binary_sensor.camera_fra_raffrescabile
      cooling_type: ducted

    camera_ale:
      name: Camera Ale
      ui_climate: climate.termostato_camera_ale
      temperature_sensor: sensor.termostato_camera_ale_temperature
      heat_climate: climate.valvola_camera_ale
      presence_entity: binary_sensor.presenza_ale
      comfort_entity: binary_sensor.camera_ale_raffrescabile
      cooling_type: ducted

    camera_padronale:
      name: Camera Padronale
      ui_climate: climate.termostato_camera_padronale
      temperature_sensor: sensor.termostato_camera_padronale_temperature
      heat_climate: climate.valvola_camera_padronale
      presence_entity: binary_sensor.presenza_massi
      comfort_entity: binary_sensor.camera_padronale_raffrescabile
      cooling_type: ducted

    salone:
      name: Salone
      temperature_sensor: sensor.hub_2_d97c_temperatura
      humidity_sensor: sensor.hub_2_d97c_umidita
      occupancy_entity: binary_sensor.casa_occupata
      heat_climates:
        - climate.valvola_salone_destra
        - climate.valvola_salone_sinistra
      cooling_type: hybrid
      split_climate: climate.condizionatore
      ducted_climate: climate.gateway_serranda_lora_daikin_canalizzato

    cucina:
      name: Cucina
      temperature_sensor: sensor.cucina_temperatura
      humidity_sensor: sensor.cucina_umidita
      heat_climate: climate.valvola_cucina

    bagno:
      name: Bagno
      temperature_sensor: sensor.valvola_bagno_local_temperature
      heat_climate: climate.valvola_bagno

    bagnetto:
      name: Bagnetto
      temperature_sensor: sensor.bagnetto_temperatura
      heat_climate: climate.valvola_bagnetto
```

## Dashboard sidebar

Quando Home Assistant carica l'integrazione, URT crea o aggiorna
automaticamente una dashboard Lovelace chiamata **Clima Casa** e la registra
nella sidebar. La pagina contiene:

- selettore modalità casa;
- termostati virtuali `climate.urt_*`;
- diagnostica canalizzato;
- richieste freddo delle camere canalizzate.

La dashboard è generata dall'integrazione, quindi non serve crearla a mano.
Per nasconderla dalla sidebar mantenendo l'integrazione attiva:

```yaml
universal_room_thermostat:
  dashboard:
    show_in_sidebar: false
```

Per disattivare del tutto la creazione della dashboard:

```yaml
universal_room_thermostat:
  dashboard:
    enabled: false
```

## Comportamento

- `estate`: valvole spente; canalizzato e split possono essere solo `OFF` o
  `COOL`.
- `inverno`: canalizzato spento; le stanze in `HEAT` comandano le rispettive
  valvole. Lo split resta spento per impostazione predefinita.
- `spento`: tutti gli attuatori sono spenti.
- `auto`: una richiesta freddo attiva rende il freddo dominante e sospende il
  riscaldamento, evitando che i sistemi combattano tra loro.

Una camera presente usa il target stanza. Una camera assente usa il target di
mantenimento e continua quindi a proteggere l'ambiente oltre 28 °C. La priorità
è valutata per livelli; il delta termico viene usato solo in caso di parità.

Il salone usa lo split da solo se è l'unica zona a chiedere freddo. Se chiedono
anche le camere, usa il canalizzato e aggiunge lo split solo quando il delta del
salone raggiunge `salon_boost_delta`.

## Entità create

- `climate.urt_camera_fra`, `climate.urt_camera_ale`,
  `climate.urt_camera_padronale`, `climate.urt_salone`,
  `climate.urt_cucina`, `climate.urt_bagno`, `climate.urt_bagnetto`;
- `sensor.urt_ducted_active_room`, `sensor.urt_ducted_max_delta`,
  `sensor.urt_ducted_requested_setpoint`;
- `binary_sensor.urt_ducted_cooling_requested` e una richiesta diagnostica per
  ogni camera canalizzata.

## Sicurezza e temporizzazioni

Il controller non invia mai `AUTO` al Daikin. Prima di avviare un sistema in
`COOL`, elimina eventuali stati `HEAT`, `AUTO` o `HEAT_COOL`. Debounce,
`min_on_time`, `min_off_time`, `off_delay` e deduplicazione dei comandi sono
configurabili in secondi.

## Test locali

La logica pura non richiede Home Assistant installato:

```bash
python3 -m unittest discover -s tests -v
```
