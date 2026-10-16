# TkinterCraft
Tkinter verzija Minecrafta uz lagane promijene za adaptaciju originalne verzije u ovom python repozitoriju

Sve je napisano samo u Pythonu i tkinteru (bez dodatnih paketa). Svijet se crta znakovima
u boji: tamno je `.`, svijetlo je `#`.

## Igra

Svijet je velik (512 x 512 blokova). Oko tebe se stalno stvaraju **lucky blokovi** (zuti `?`,
vide se i kroz maglu). Razbij ih za bodove, ali pazi, svaki skriva nesto drugo:

- bodovi (+10 do +50) ili JACKPOT (+100)
- zlatni toranj ili dijamanti koje iskopas za jos bodova
- kisa novih lucky blokova
- raketa (leti u zrak), brzina ili super skok na 20 s, teleport
- TNT koji eksplodira za 3 s (razbij ga na vrijeme za +15), kavez od kamena, ili -25 bodova

Neke stvari su **u zraku** pa do njih moras graditi:

- **nebeski lucky blokovi** (ljubicasti `?`) lebde 9-13 blokova iznad tla. Uvijek daju nesto dobro,
  a bodovi su dupli.
- **lebdeci otoci** s blagom: na vrhu je nebeski lucky blok i zlatni/dijamantni blokovi.

Najlakse se gradi prema gore: pogledaj ravno dolje i stisni desni klik ili `E`, pa se podignes
za jedan blok. Strelica u HUD-u pise i koliko je lucky blok iznad tebe.

Bodove daju i rude ispod zemlje: ugljen (+2), zlatna ruda (+10), dijamant (+25).
Runda traje 5 minuta, a onda se prikaze pobjednik i krece nova. Najbolji rezultat se pamti kao rekord.
Strelica gore lijevo pokazuje smjer i udaljenost do najblizeg lucky bloka.

## Pokretanje

```
python scripts/main.py
```

Na Linuxu je potreban tkinter paket (npr. `sudo apt install python3-tk`).

Na pocetku se otvara meni: igraj sam, napravi igru na mrezi ili se spoji na tudu.

## Multiplayer (ista mreza)

1. Jedan igrac klikne **Napravi igru na mrezi (host)**. Njegova IP adresa pise u statusnoj traci.
2. Ostali (na istom WiFi-ju / mrezi) kliknu **Osvjezi popis**, odaberu igru i **Spoji se**,
   ili upisu IP adresu hosta.
3. Svi vide jedni druge (lik s imenom iznad glave), blokove i tablicu bodova gore desno.
   Samo host moze s `R` napraviti novi svijet.

Igra koristi TCP port 25565 i UDP port 25566 (za trazenje igara). Ako vatrozid pita, dopusti
Pythonu pristup mrezi. Svi igraci moraju imati istu verziju igre.

Moze i bez menija: `python scripts/main.py --host`, `--join 192.168.1.5` ili `--solo`
(uz `--name Ime`).

## Kontrole

| Tipka | Akcija |
|---|---|
| W A S D | hodanje |
| Shift | trcanje |
| Space | skok |
| strelice | gledanje okolo |
| klik misem | zakljucaj mis i gledaj misem (Esc otkljucava) |
| lijevi klik / Q | razbij blok |
| desni klik / E | postavi blok (gledajuci dolje: podigni se za blok) |
| 1-9 / kotacic | odabir bloka |
| + / - | veci / manji render distance (16 - 128) |
| PgUp / PgDn | veca / manja rezolucija |
| R | novi random svijet |

## Datoteke

- `scripts/main.py` – prozor, meni, input, HUD i glavna petlja
- `scripts/game.py` – pravila igre: lucky blokovi, bodovi, runde, TNT
- `scripts/world.py` – generiranje velikog random svijeta (teren, rude, kamenje, drveca, lebdeci otoci)
- `scripts/render.py` – raycasting renderer koji crta svijet znakovima
- `scripts/objects.py` – tipovi blokova i igrac (fizika, kolizije, skakanje, efekti)
- `scripts/net.py` – multiplayer: server, klijent i trazenje igara na mrezi
