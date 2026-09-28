# Tingsted for Home Assistant

Kobler Home Assistant til [Tingsted](../README.md), den selvhostede oversikten over hva som ligger i hvilken kasse.

## Hva du får

- **Sensorer:** kasser, ting, ting totalt, steder, hyller, utlånt, utlånt over fristen (og AI-kø hvis AI er på).
- **Problem-sensor:** «Noe er ikke levert tilbake».
- **Huskeliste «Utlånt»:** alt som er lånt ut. Kryss av, så er det levert tilbake i Tingsted. Du kan også endre fristen.
- **Tjenester:**
  - `tingsted.find`: «hvor er …», gir et ferdig svar å lese opp
  - `tingsted.search`: søk etter ting, kasser og hyller
  - `tingsted.add_items`: legg ting i en kasse (`hammer x2` gir antall 2)
  - `tingsted.lend` og `tingsted.return_item`: lån ut og få tilbake
- **Assist:** «Hvor er skjøteledningen?» gir et svar som «Skjøteledning ligger i Boden H1-B3 (Verktøy).»
- **Hendelser med en gang:** med en nøkkel som har skrivetilgang, setter integrasjonen opp en webhook i Tingsted selv.
  Da fyres `tingsted_event` (alle hendelser) og for eksempel `tingsted_item_lent`, `tingsted_item_added` og
  `tingsted_box_moved` i HA, og sensorene oppdateres med en gang.

## Tingsted-kortet

Integrasjonen har med et eget dashbordkort. Du trenger ikke legge til noen ressurs, det lastes av seg selv.
Rediger et dashbord → Legg til kort → søk etter «Tingsted», eller lim inn:

```yaml
type: custom:tingsted-card
```

Kortet har søk med ferdig svar og treffliste, knappene «Lån ut» og «Levert» og «Åpne i Tingsted», utlånt med frist,
«Legg i kasse» og siste endringer (hvem gjorde hva). Valg:

```yaml
type: custom:tingsted-card
title: Boden
sections: [search, lent, add, recent]   # velg hvilke deler som vises
recent_limit: 8
config_entry_id: ...                    # bare hvis du har flere husstander
```

Uten kortet finnes også:

- **Søk** (tekstfelt) og **Søkesvar** (sensor): skriv noe i søkefeltet, så viser søkesvaret hvor det ligger. Alle treffene ligger som attributter.
- **Siste hendelse**: det siste som skjedde i Tingsted.
- **Samlet verdi**: summen av det som er registrert med verdi, i kroner.
- **Kalender**: frister for utlån og når garantier går ut.
- **Oppdater nå** (knapp).

## Installere

**HACS:** legg denne mappa i et eget GitHub-repo, og legg til repoet i HACS som «Custom repository» (type: Integration).

**Manuelt:** kopier `custom_components/tingsted` til `/config/custom_components/tingsted` og start HA på nytt.

Så: **Innstillinger → Enheter og tjenester → Legg til integrasjon → Tingsted.**

1. I Tingsted: **Mer → API og Home Assistant → Lag ny nøkkel**, velg «Hele husstanden» og «Lese og skrive».
2. I HA: skriv inn adressen til Tingsted (for eksempel `http://192.168.1.10:8096`) og nøkkelen.

Én husstand per oppføring. Har du flere husstander, legger du til integrasjonen flere ganger.

### «Hvor er …?» i Assist

Kopier `custom_sentences/nb/tingsted.yaml` til `/config/custom_sentences/nb/tingsted.yaml` og start HA på nytt.
Da forstår Assist blant annet «hvor er …», «hvor ligger …», «hvor har vi lagt …», «finn …» og «har vi …».

### Webhook

HA må kunne nås fra Tingsted på den interne adressen (Innstillinger → System → Nettverk → Home Assistant-adresse).
Webhooken tar bare imot fra lokalnettet, og hver melding er signert (HMAC-SHA256). Uten skrivetilgang, eller hvis
HA ikke har noen intern adresse, hentes data jevnlig i stedet (standard hvert 5. minutt, kan endres under Konfigurer).

## Eksempler

Varsle når noe lånes ut:

```yaml
automation:
  - alias: Tingsted utlån
    triggers:
      - trigger: event
        event_type: tingsted_item_lent
    actions:
      - action: notify.notify
        data:
          message: "{{ trigger.event.data.name }} er lånt ut til {{ trigger.event.data.lent_to }}"
```

Spør fra et skript:

```yaml
- action: tingsted.find
  data:
    query: skjøteledning
  response_variable: svar
- action: notify.notify
  data:
    message: "{{ svar.speech }}"
```
