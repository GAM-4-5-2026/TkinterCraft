# TkinterCraft
Tkinter verzija Minecrafta uz lagane promijene za adaptaciju originalne verzije u ovom python repozitoriju

Sve je napisano samo u Pythonu i tkinteru (bez dodatnih paketa). Svijet se crta znakovima
u boji: tamno je `.`, svijetlo je `#`.

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
3. Svi vide jedni druge (lik s imenom iznad glave), a razbijeni i postavljeni blokovi
   vide se kod svih. Samo host moze s `R` napraviti novi svijet.

Igra koristi TCP port 25565 i UDP port 25566 (za trazenje igara). Ako vatrozid pita, dopusti
Pythonu pristup mrezi.

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
| desni klik / E | postavi blok |
| 1-9 / kotacic | odabir bloka |
| + / - | veca / manja rezolucija |
| R | novi random svijet |

## Datoteke

- `scripts/main.py` – prozor, input i glavna petlja
- `scripts/world.py` – generiranje random svijeta (teren, kamenje, drveca)
- `scripts/render.py` – raycasting renderer koji crta svijet znakovima
- `scripts/objects.py` – tipovi blokova i igrac (fizika, kolizije, skakanje)
- `scripts/net.py` – multiplayer: server, klijent i trazenje igara na mrezi
