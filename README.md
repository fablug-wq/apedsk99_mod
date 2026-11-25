# APEDSK99 mod – stampante virtuale PIO

Modifica di [APEDSK99](https://github.com/jambuur/APEDSK99) di Jochen Buur, il controller dischi su Arduino per il TI-99/4A.

Aggiunge una seconda DSR, **APEDSKPR**, che emula una stampante `PIO`: quello che il TI stampa finisce in un file di testo sulla SD, e alla chiusura il file viene inviato al server FTP già configurato per APEDSK99.

## Contenuto

| Percorso | Cosa contiene |
|---|---|
| `SD/APEDSK99.DSR` | DSR originale v12s |
| `SD/APEDSKPR.DSR` | nuova DSR con PIO |
| `TI/APEDSK99.a99` | sorgente della DSR originale |
| `TI/APEDSKPR.a99` | sorgente della nuova DSR |
| `Arduino/APEDSK99_012s/` | sketch Arduino, con i comandi PIO aggiunti |

Il primo commit contiene i file originali senza modifiche, quindi `git diff` dal primo commit mostra esattamente cosa è cambiato.

## La DSR APEDSKPR

Per far posto al PIO, la DSR tiene solo le CALL essenziali:

- **mantenute:** `LDSK`, `MDSK`, `ADSR`, `CDIR`, `SMAP`, `LDIR` (oltre a `CALL FILES`)
- **tolte:** `PDSK`, `UDSK`, `NDSK`, `RDSK`, `FGET`, `FPUT`, `AHLP`, `ACHR`, `ARST`, `TIME`, `ACFG`

Per le CALL tolte basta tornare un momento alla DSR standard.

## Installazione

1. Copia `SD/APEDSKPR.DSR` nella radice della SD, accanto ad `APEDSK99.DSR`.
2. Carica sull'Arduino Uno lo sketch in `Arduino/APEDSK99_012s` (servono le librerie del progetto originale). Lo stesso firmware funziona con entrambe le DSR.

## Uso

```
CALL ADSR("APEDSKPR")     poi FCTN-QUIT
```

```
OPEN #1:"PIO"
PRINT #1:"CIAO DAL TI-99"
CLOSE #1
```

Va bene anche `LIST "PIO"`, e qualunque programma che stampi su `PIO`.

- Durante la stampa l'output va in `/PRINT.TXT` sulla SD, con un CR/LF a fine riga.
- Al `CLOSE` il file viene inviato via FTP come `PRINT-AAMMGG-HHMM.TXT`, con l'ora presa dall'NTP; senza NTP il nome è `PRINT.TXT`. Il TI resta fermo qualche secondo durante l'invio.
- Se l'FTP non risponde, il `CLOSE` dà I/O error 6 e il file resta sulla SD. Il prossimo `OPEN` lo sovrascrive.

Per tornare alla DSR standard:

```
CALL ADSR("APEDSK99")     poi FCTN-QUIT
```

**Attenzione:** il cambio di DSR riavvia l'Arduino, e le mappature fatte con `MDSK` tornano a `_APEDSK1/2/3.DSK`. La configurazione di rete (IP, FTP, NTP) resta invece in EEPROM.

## Come funziona

La DSR aggiunge `PIO` alla catena dei dispositivi, dopo `DSK3`. Per ogni carattere da stampare scrive il carattere nel buffer `CALLBF` (>5FC8) e un codice comando in `ACOMND` (>5FE8). L'Arduino ferma il TI, esegue il comando e lo rilascia, come per le altre CALL di APEDSK99.

| Codice | Comando |
|---|---|
| >40 | OPEN: crea `/PRINT.TXT`; se il PAB non indica la lunghezza del record, la DSR imposta 80 |
| >41 | un carattere (in `CALLBF`) |
| >42 | fine record: CR/LF |
| >43 | CLOSE: chiude il file e lo invia via FTP |

Gli errori dell'Arduino arrivano al TI tramite `CALLST` e diventano errore 6 nel PAB; gli opcode non supportati danno errore 3.

## Compilazione

- **DSR:** `xas99.py -R -b TI/APEDSKPR.a99 -o APEDSKPR.bin` ([xdt99](https://github.com/endlos99/xdt99)), poi riempire con zeri fino a 8192 byte. Riassemblato allo stesso modo, il sorgente originale è identico byte per byte ad `APEDSK99.DSR`.
- **Sketch:** Arduino IDE, scheda Uno. Usa circa il 94% della flash.

## Crediti

APEDSK99 è opera di Jochen Buur ([github.com/jambuur/APEDSK99](https://github.com/jambuur/APEDSK99)), distribuito come freeware senza restrizioni. Il codice del controller deriva dal disassemblato commentato di Thierry Nouspikel.
