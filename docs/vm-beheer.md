# VM-beheer spiekbriefje

*Voor de Google Cloud e2-micro die de aggregator draait. Inloggen: [console.cloud.google.com](https://console.cloud.google.com) → Compute Engine → SSH-knop bij de instance. Alles hieronder voer je op de VM uit.*

## Wat er draait

| Unit | Wat | Wanneer |
|---|---|---|
| `reisplan-aggregator.service` | pollt de feeds, schrijft snapshot naar R2, verzamelt punctualiteitsdata | continu; herstart vanzelf na crash of reboot |
| `reisplan-statisch.timer` → `.service` | dataverversing via `deploy/vernieuw.sh`: **git pull**, uv sync, feeds → filter → merge → segmenten; herstart daarna de aggregator | elke maandag ~04:30 UTC |

## Dagelijkse kost

```bash
journalctl -fu reisplan-aggregator          # live meekijken (Ctrl-C stopt alleen het kijken)
journalctl -u reisplan-aggregator -n 50     # laatste 50 regels
systemctl status reisplan-aggregator        # draait hij?
systemctl list-timers reisplan-statisch.timer   # wanneer is de volgende verversing?
```

Gezond log = een startregel met `nl=aan, fr=aan, ch=aan, be=aan` en `R2-upload: aan`, en elke minuut een `snapshot: <10000+> segmenten`-regel. Losse `WARNING … poll mislukt … backoff`-regels zijn normaal (haperende feed, herstelt zichzelf); pas verdacht als één bron het úren blijft doen.

## Ingrijpen

```bash
sudo systemctl restart reisplan-aggregator   # herstarten (bv. na .env-wijziging)
sudo systemctl stop reisplan-aggregator      # tijdelijk uit
sudo systemctl start reisplan-statisch       # dataverversing NU draaien i.p.v. maandag
                                             # (doet ook git pull + aggregator-herstart)
```

Alleen code bijwerken zonder volledige dataverversing:

```bash
cd ~/reisplan && git pull && uv sync --all-packages && sudo systemctl restart reisplan-aggregator
```

API-keys wijzigen: `nano ~/reisplan/.env`, daarna de aggregator herstarten.

## Controle op afstand (vanaf laptop/telefoon, zonder SSH)

- Kaart: https://wijnand-suijlen.github.io/reisplan/ — het paneel toont snapshot-leeftijd en per-bron-status; "snapshot > paar min oud" betekent dat de VM niet meer uploadt.
- Rauw: `curl -s https://pub-2369cd93470e40528dc3aab9ab7fd5e7.r2.dev/snapshot.json | head -c 200` — kijk naar het `t`-veld.

## Af en toe (maandelijks is zat)

```bash
df -h /                                      # schijf: 30 GB totaal
du -sh ~/reisplan/data/rt-archief            # groei van het verzamelarchief
free -h                                      # geheugen + swap
```

Het archief (observaties + snapshot-history) groeit met enkele MB's per dag; dat past jaren. Wordt de schijf ooit toch krap: oude maanden snapshot-archief zijn veilig weg te gooien (`rm -r ~/reisplan/data/rt-archief/snapshots/2026/08` bijvoorbeeld) — **`observaties.sqlite` bewaren**, dat is de punctualiteitsstatistiek voor fase 2.

Archief veiligstellen naar je laptop (vanaf de laptop, met [gcloud CLI](https://cloud.google.com/sdk); of handmatig via de SSH-browserknop downloaden):

```bash
gcloud compute scp <instance-naam>:~/reisplan/data/rt-archief/observaties.sqlite ./backup/
```

## Als het echt stuk is

1. `journalctl -u reisplan-aggregator -n 100` — de traceback staat onderaan.
2. `journalctl -u reisplan-statisch -n 100` — als de maandagverversing faalde.
3. Reboot kan altijd veilig: GCP-console → instance → Reset, of `sudo reboot`; alles start vanzelf.
4. Totaal opnieuw inrichten: repo weg­gooien en `git clone` + `.env` terugzetten + `bash deploy/setup-vm.sh` (zie `deploy/`).
