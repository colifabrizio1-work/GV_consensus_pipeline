# Pipeline GV - Overview

Ultimo aggiornamento: 2026-07-01.

Questa pipeline gestisce il flusso GV per automatizzare i file consensus frames.
E' separata dalla pipeline Retail ufficiale: ha cartelle, config, script, log e
output propri. Puo' leggere dataset prodotti dalla pipeline ufficiale solo quando
serve, ma ogni dipendenza esterna deve essere dichiarata qui e nei config GV.

## Root

- Root GV: `\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus`
- Area tecnica: `{root}\00_cose_pitonose`
- Doc: `{root}\00_cose_pitonose\01_doc`
- Config: `{root}\00_cose_pitonose\02_config`
- Script: `{root}\00_cose_pitonose\03_script`
- Log: `{root}\00_cose_pitonose\04_log`
- Bat launcher: `{root}\00_cose_pitonose\05_bat`
- Input: `{root}\01_input`
- Output consensus: `{root}\02_Consensus`

## Struttura Cartelle

```text
10. Automatizzazione file consensus
|-- 00_cose_pitonose
|   |-- 01_doc
|   |   `-- overview_pipeline_GV.md
|   |-- 02_config
|   |   |-- paths.json
|   |   |-- datasets.json
|   |   `-- pipeline.json
|   |-- 03_script
|   |   |-- gv_config.py
|   |   |-- gv_samu.py
|   |   |-- update_sales_gv.py
|   |   |-- update_forecast_gv.py
|   |   `-- generate_consensus_frames_gv.py
|   |-- 04_log
|   `-- 05_bat
|       |-- Update_Forecast_GV.bat
|       `-- Update_Sales_GV.bat
|-- 01_input
|   |-- 00_Manual_input
|   |-- 01_Scarichi
|   `-- 02_Parquet
|       |-- 01_Sales
|       `-- 02_Forecast
`-- 02_Consensus
```

## Input GV

### Manual Input

- `01_Brands Defill.xlsx`
  - sheet: `DEFILL`
  - colonne rilevate: `DATEST`, `BRAND`
  - regola v0: definisce il perimetro ufficiale datest/brand della pipeline GV.
- `02_Consensus_frames_template.xlsx`
  - sheet: `Consensus Frames`
  - template base per generare un file consensus mensile con un tab per datest.

### Scarichi

- `GV_Sales_update_Eliot storico.csv`
  - separatore: `,`
  - colonne: `Client Datest`, `UPC`, `Fiscal Year`, `Fiscal Month`, `Fiscal Week`, `Hist Weekly Sales`, `Hist - Weekly Sales Act MS>0 (Total)`
  - range rilevato: settimane `202501`-`202626`
- `GV_Sales_update_Eliot.csv`
  - separatore: `,`
  - stesse colonne dello storico sales
  - range rilevato: settimane `202619`-`202626`
- `GV_Forecast_Eliot.csv`
  - separatore: `,`
  - colonne: `Client Datest`, `UPC`, `Fiscal Week`, `Forecast (no COV)`, `Forecast (with COV)`, `Forecast Approved (with COV)`
  - range rilevato: settimane `202623`-`202730`

## Perimetro Datest

Gli scarichi contengono 12 datest:

```text
026000, 026150, 026300, 028150, 028200, 028300,
032100, 032150, 032300, 033100, 033150, 033300
```

Il file manuale `01_Brands Defill.xlsx` contiene 9 datest:

```text
026000, 026150, 026300, 028150, 028200, 028300,
032100, 032150, 032300
```

Regola v0: gli script GV filtrano sui 12 datest degli scarichi sales/forecast
salvati in `business_rules.allowed_gv_datests`. Il Defill non e' la whitelist datest.

## Output Attesi

### Log

- Cartella log: `{gv.log}`
- Ogni script GV deve scrivere un log run-specific in questa cartella.
- Naming consigliato: `{script_name}_{yyyymmdd_hhmmss}.log`.

### Parquet GV

- Sales annuali: `{gv.parquet_sales}\GV_Sales_{year}.parquet`
- Forecast: `{gv.parquet_forecast}\GV_Forecast.parquet`

I parquet GV sono stato operativo della pipeline GV. I CSV in `01_Scarichi`
restano input sorgente.

### Consensus
- Commenti: la riga `40` viene riportata dalla consensus precedente agganciando i valori allo stesso `YYYYMM`, non alla posizione rolling.
- Separatore verticale continuo: current month giallo prevale su cambio anno doppio, che prevale su quarter nero; la regola vale anche sulle righe vuote.
- Proiezione mese corrente: settimane chiuse CY / stesse settimane LY applicate alle settimane aperte LY; se non esiste base LY chiusa, la ratio resta neutra e le settimane aperte vengono valorizzate come LY.

- File mensile: `{gv.consensus}\Consensus_Frames_GV_{yyyymm}.xlsx`
- Un tab per ogni datest GV nel perimetro Defill.
- Layout derivato da `02_Consensus_frames_template.xlsx`.

Output storici gia' presenti:

- `Consensus_Frames_GV_202602.xlsx`
- `Consensus_Frames_GV_202603.xlsx`

## Dipendenze Dalla Pipeline Ufficiale

Nessuna dipendenza operativa attiva nella v0.

Possibili prestiti futuri da dichiarare prima dell'uso:

- fiscal calendar ufficiale, per convertire settimane fiscali in mesi;
- anagrafica ufficiale, se servira' arricchire UPC/brand;
- eventuali dataset forecast/sales ufficiali solo per controlli, non come stato GV.

## Script Previsti

- `gv_config.py`: carica config JSON GV, risolve path simbolici e centralizza regole condivise.
- `update_sales_gv.py`: legge storico + update sales, filtra perimetro Defill e scrive parquet annuali GV.
- `update_forecast_gv.py`: legge forecast Eliot, filtra perimetro Defill e scrive parquet forecast GV.
- `generate_consensus_frames_gv.py`: legge parquet GV + template e genera workbook mensile consensus frames GV.

## Regole Di Lavoro

- Questa overview va aggiornata quando cambiano struttura, input, output, regole o dipendenze prese in prestito dalla pipeline ufficiale.
- I config in `02_config` sono la fonte per gli script GV.
- Gli script GV devono stare in `03_script`.
- I log devono stare in `04_log`.
- La pipeline GV non deve scrivere nei dataset della pipeline Retail ufficiale.
- I CSV sorgente grandi vanno letti a chunk o una sola volta, evitando scansioni ripetute non necessarie.

## Stato Attuale

### Perimetro Datest GV

I datest validi della pipeline GV sono quelli presenti negli scarichi sales e forecast, salvati in `02_config\datasets.json` come `business_rules.allowed_gv_datests`:

```text
026000, 026150, 026300, 028150, 028200, 028300, 032100, 032150, 032300, 033100, 033150, 033300
```

`01_Brands Defill.xlsx` non definisce la whitelist datest della pipeline; resta un input manuale per perimetri brand/enrichment successivi.

### Sales Storico

Ricreato il 2026-07-01 usando tutti i 12 datest GV:

- sorgente: `01_input\01_Scarichi\GV_Sales_update_Eliot storico.csv`
- script: `00_cose_pitonose\03_script\update_sales_gv.py --source historical`
- log run corretto: `00_cose_pitonose\04_log\update_sales_gv_20260701_173940.log`

Output generati:

| File | Righe | Qty totale | Datest | Data type |
| --- | ---: | ---: | ---: | --- |
| `01_input\02_Parquet\01_Sales\GV_Sales_2025.parquet` | 2,215,868 | 15,894,387 | 12 | `Sales_hist`, `Sales_minimo` |
| `01_input\02_Parquet\01_Sales\GV_Sales_2026.parquet` | 836,710 | 7,482,644 | 12 | `Sales_hist`, `Sales_minimo` |

Schema parquet sales GV:

```text
Client Datest, UPC, Fiscal Year, Fiscal Month, Fiscal Week, Qty, data_type
```

### Forecast Latest

Creato il 2026-07-01 usando tutti i 12 datest GV e solo `Forecast Approved (with COV)`.

- sorgente: `01_input\01_Scarichi\GV_Forecast_Eliot.csv`
- script: `00_cose_pitonose\03_script\update_forecast_gv.py`
- log run corretto: `00_cose_pitonose\04_log\update_forecast_gv_20260701_174045.log`
- output: `01_input\02_Parquet\02_Forecast\GV_Forecast.parquet`

Metriche output:

| File | Righe | Qty totale | Datest | Fiscal Week | Data type | Snapshot |
| --- | ---: | ---: | ---: | --- | --- | --- |
| `GV_Forecast.parquet` | 751,945 | 6,471,980 | 12 | `202623`-`202730` | `Forecast_approved` | `2026-07-01 17:40:45` |

Schema parquet forecast GV:

```text
Client Datest, UPC, Fiscal Week, Qty, data_type, snapshot_timestamp, source_file, source_last_modified
```

Regola forecast v0:

- il parquet forecast e' una sola foto latest;
- ogni run sovrascrive `GV_Forecast.parquet`;
- non vengono storicizzate le foto passate;
- il timestamp della foto corrente e' salvato nella colonna `snapshot_timestamp`.

## Regole Operative Update

### Update Sales GV

Comando default:

```powershell
& "C:\Users\colifa\AppData\Local\Programs\Python\Python312\python.exe" -u "\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus\00_cose_pitonose\03_script\update_sales_gv.py"
```

Regola default:

- legge `01_input\01_Scarichi\GV_Sales_update_Eliot.csv`;
- identifica le ultime 5 `Fiscal Week` presenti nello scarico update dopo filtro sui 12 datest GV;
- rimuove quelle settimane in toto dai parquet annuali coinvolti per `Sales_hist` e `Sales_minimo`;
- appende le nuove righe dello scarico update per quelle settimane;
- questo gestisce anche UPC/datest comparsi o scomparsi, perche' lo scarico update possiede interamente il contenuto delle settimane sostituite.

Run reale ultimo:

- log: `00_cose_pitonose\04_log\update_sales_gv_20260701_174808.log`
- settimane sostituite: `202622, 202623, 202624, 202625, 202626`
- parquet scritto: `01_input\02_Parquet\01_Sales\GV_Sales_2026.parquet`

Modalita rebuild storico manuale:

```powershell
& "C:\Users\colifa\AppData\Local\Programs\Python\Python312\python.exe" -u "\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus\00_cose_pitonose\03_script\update_sales_gv.py" --source historical
```

### Update Forecast GV

Comando default:

```powershell
& "C:\Users\colifa\AppData\Local\Programs\Python\Python312\python.exe" -u "\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus\00_cose_pitonose\03_script\update_forecast_gv.py"
```

Regola default:

- legge `01_input\01_Scarichi\GV_Forecast_Eliot.csv`;
- tiene solo `Forecast Approved (with COV)`;
- sovrascrive `01_input\02_Parquet\02_Forecast\GV_Forecast.parquet`;
- non storicizza le foto precedenti;
- salva la foto corrente nella colonna `snapshot_timestamp`.

Run reale ultimo:

- log: `00_cose_pitonose\04_log\update_forecast_gv_20260701_174836.log`
- snapshot: `2026-07-01 17:48:36`
- righe: `751,945`
- Qty totale: `6,471,980`
- settimane forecast: `202623`-`202730`


## Launcher BAT

Cartella: `00_cose_pitonose\05_bat`

- `Update_Forecast_GV.bat`
  - lancia `03_script\update_forecast_gv.py`;
  - aggiorna `GV_Forecast.parquet` come foto latest forecast approved.
- `Update_Sales_GV.bat`
  - lancia `03_script\update_sales_gv.py`;
  - aggiorna le ultime 5 settimane sales da `GV_Sales_update_Eliot.csv`.

I `.bat` propagano l'exit code dello script Python. I log applicativi restano gestiti dagli script in `04_log`.


### BAT Launcher Unico

File:

- `00_cose_pitonose\05_bat\Run_GV_Pipeline.bat`

Menu disponibile:

- `1` aggiorna solo forecast GV;
- `2` aggiorna solo sales GV (`--source update`);
- `3` crea solo consensus GV;
- `4` aggiorna forecast, aggiorna sales e poi crea consensus GV.

Il BAT interrompe la catena se uno step restituisce errore. Gli update forecast/sales inviano S.A.M. secondo la logica degli script Python; la creazione consensus non invia mail.

## S.A.M. Mail

Gli script di update GV inviano una mail S.A.M. di stato a `fabrizio.coli@luxottica.com`.

Helper GV:

- `00_cose_pitonose\03_script\gv_samu.py`

Sorgente S.A.M. ufficiale presa in prestito dalla pipeline Retail:

- `\\luxnt\Retail\AAA_Retail\zzzz_Coli\Script\03 - py\00 - utilities\samu.py`

Regole:

- mail OK a fine run completato;
- mail ERRORE se lo script intercetta un'eccezione;
- il log del run viene allegato quando disponibile;
- destinatario per ora solo Fabrizio;
- usare `--no-mail` per dry-run o test senza invio.

## Consensus Core GV

Script:

- `00_cose_pitonose\03_script\generate_consensus_frames_gv.py`

Output:

- `02_Consensus\Consensus_Frames_GV_{yyyymm}.xlsx`

Comando usato per il run reale corretto:

```powershell
& "C:\Users\colifa\AppData\Local\Programs\Python\Python312\python.exe" -u "\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus\00_cose_pitonose\03_script\generate_consensus_frames_gv.py" --yyyymm 202607
```

Run reale 202607:

- output: `02_Consensus\Consensus_Frames_GV_202607.xlsx`
- log: `00_cose_pitonose\04_log\generate_consensus_frames_gv_20260701_182509.log`
- fogli: 12, uno per ogni datest GV
- UPC senza match anagrafica sales: `0` righe, `0` UPC uniche
- UPC senza match anagrafica forecast: `0` righe, `0` UPC uniche
- sales accessori esclusi: `12,797` righe
- sales wearables esclusi: `16,309` righe
- sales Defill esclusi: `134,818` righe
- sales finali dopo filtri: `2,888,726` righe
- forecast accessori esclusi: `2,684` righe
- forecast wearables esclusi: `11,501` righe
- forecast Defill esclusi: `0` righe
- forecast finali dopo filtri: `737,826` righe

Regole principali:

- salva solo nella cartella GV `02_Consensus`;
- legge il template `01_input\00_Manual_input\02_Consensus_frames_template.xlsx`;
- ripete solo il foglio template `Consensus Frames`, una volta per datest;
- non crea split, normalizzazioni o tab ausiliari;
- ogni foglio contiene solo i dati del suo datest;
- arricchisce `UPC` con `Brand` e `Product Type` da `Anagrafica_Base.parquet` ufficiale;
- se una UPC non trova match anagrafica, viene segnalata nel log e in CSV diagnostico in `04_log`; in assenza di match non viene scartata automaticamente;
- scarta gli accessori con `Product Type = Accessories`;
- scarta i wearables usando `brand_wearables.xlsx` ufficiale;
- poi esclude le righe `Client Datest + Brand` presenti nel Defill;
- mappa `Fiscal Week` forecast a `Year_month` usando `Fiscal Calendar.xlsx` ufficiale;
- colonne `B:N`: finestra rolling di 13 fiscal month da `yyyymm - 6` a `yyyymm + 6`;
- `B:N` mantengono stile, righe separatrici e formato del template;
- i placeholder `LLLY`, `LLY`, `LY`, `CY` sono sostituiti con gli anni reali rispetto al target `yyyymm`;
- se `--yyyymm` non viene passato, lo script usa il mese fiscale corrente da Fiscal Calendar.

Dipendenze prese in prestito dalla pipeline ufficiale:

- `Fiscal Calendar.xlsx`, per mappare settimane/mese e default del mese corrente;
- `Anagrafica_Base.parquet`, per arricchire UPC con Brand/Product Type;
- `brand_wearables.xlsx`, per escludere i brand wearable.

## Storico Sales 2023-2024

Sorgente aggiunta:

- `01_input\01_Scarichi\storici sales\GV_Sales_update_Eliot storico 2024-2023.csv`
- separatore: `;`
- anni: `2023`, `2024`

Comando usato:

```powershell
& "C:\Users\colifa\AppData\Local\Programs\Python\Python312\python.exe" -u "\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus\00_cose_pitonose\03_script\update_sales_gv.py" --source custom --source-path "\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus\01_input\01_Scarichi\storici sales\GV_Sales_update_Eliot storico 2024-2023.csv" --no-mail
```

Run reale corretto:

- log: `00_cose_pitonose\04_log\update_sales_gv_20260701_191044.log`
- sorgente letta: `1,812,486` righe
- righe intermedie long: `3,437,565`
- righe con UPC vuota/non valida scartate: `10`

Output:

| File | Righe | Qty totale | Datest | Fiscal Week | Note |
| --- | ---: | ---: | ---: | --- | --- |
| `01_input\02_Parquet\01_Sales\GV_Sales_2023.parquet` | 1,339,276 | 7,911,628 | 9 | `202301`-`202352` | Nel file 2023 non ci sono righe utili per i datest `033100`, `033150`, `033300`. |
| `01_input\02_Parquet\01_Sales\GV_Sales_2024.parquet` | 2,098,289 | 13,786,643 | 12 | `202401`-`202452` | Tutti i 12 datest GV presenti. |

Il consensus `202607` e' stato rigenerato dopo il caricamento storico:

- output: `02_Consensus\Consensus_Frames_GV_202607.xlsx`
- log: `00_cose_pitonose\04_log\generate_consensus_frames_gv_20260701_191245.log`
- match anagrafica sales: `0` missing UPC dopo la pulizia UPC vuote
- match anagrafica forecast: `0` missing UPC
### Correzioni Layout Consensus

- Titolo foglio datest: Consensus Frames GV - <datest> (wearable and defill excluded).
- Righe 2 e 3 nascoste in ogni foglio consensus.
- Righe 15 e 16: i testi `LY`, `LLY`, `CY` vengono sostituiti con gli anni reali, esempio `Sales 2025 vs sales 2024` e `Sales 2026 vs sales 2025` per il consensus 202607.
- Formula riga 16 sul mese corrente: la cella del mese corrente copia la formula della colonna precedente. Esempio consensus 202607: H16 usa la stessa formula di G16.
- Riga bucket anni: i mesi nello stesso anno del target sono `CY`, il mese target e' `CM`, i mesi in anni successivi diventano `CY+1`, `CY+2`, ecc.
- Separatore anno fiscale: quando dentro B:N cambia l'anno fiscale, lo script applica un bordo verticale sinistro `double` dalla riga 4 alla riga 40 sulla prima colonna del nuovo anno. Esempio 202607: separatore tra M=202612 e N=202701; 202608: separatore tra L=202612 e M=202701.
- Colori header mesi riga 4: seguono sempre il trimestre fiscale per numero mese, quindi gen-feb-mar stesso colore, apr-mag-giu stesso colore, lug-ago-set stesso colore, ott-nov-dic stesso colore, indipendentemente dalla posizione rolling della colonna.


### Regole Forecast e Minimo Consensus

Per il consensus rolling 202607, con G=mese precedente, H=mese corrente, I:N=futuro:

- righe 21-23: B:F vuote;
- G21 = G16, G22 = G8, G23 = G22-G19;
- H21 = `IFERROR(SUM(F8:H8)/SUM(F7:H7)-1,"")`;
- I21:N21 = H21;
- H22:N22 = riga 7 * (1 + riga 21);
- H28 = proiezione Sales_minimo del mese corrente con la stessa logica usata per H8 sulle sales totali;
- I28:N28 vuote;
- righe 35-38: B:F vuote;
- G35/H35 = riga 33, G36/H36 = riga 28, G37/H37 = forecast del mese corrispondente, G38/H38 = riga 36 - riga 37;
- I35:M35 = valore della riga 35 dell'ultima consensus disponibile, agganciato per `YYYYMM` rolling; G35, H35 e N35 mantengono le proprie regole;
- I36:N36 = riga 22 * (1 + riga 35);
- I37:N37 = forecast del mese corrispondente;
- I38:N38 = `IFERROR(riga36-riga37,"")`.

### Regola Sales CY Corrente e Futuro

Nel consensus, per i mesi futuri rispetto al mese corrente consensus, le righe Sales CY e Weekly Sales CY restano vuote. Non vengono scritti zero perche' nel futuro non possono esserci vendite actual.

Le righe 21-23 restano vuote per i mesi precedenti al mese target. Esempio consensus 202607: colonne B:G vuote sulle righe 21, 22 e 23.

Riga 21 Forecast Sales Tot %:

- colonna del mese target: `=IFERROR(SUM(F8:H8)/SUM(F7:H7)-1,"")` per consensus 202607;
- colonne successive al mese target: copiano la percentuale del mese target, esempio `I21:N21 = H21`.

Riga 22 Forecast Sales Tot pcs:

- colonne dal mese target in avanti: `riga 7 * (1 + riga 21)`, esempio `H22 = H7*(1+H21)` e `I22 = I7*(1+I21)`.

Per il mese corrente, Sales CY non e' piu' il solo actual MTD: viene proiettato a fine mese con questa logica:

- settimane chiuse CY = settimane del mese corrente che hanno sales nel parquet;
- rapporto = somma settimane chiuse CY / somma delle stesse posizioni settimana LY;
- proiezione settimane aperte = rapporto * somma settimane aperte LY;
- Sales CY mese corrente = somma settimane chiuse CY + proiezione settimane aperte;
- Weekly Sales CY mese corrente = Sales CY proiettato / numero settimane fiscali del mese corrente.

Se non ci sono ancora settimane chiuse CY nel mese corrente, la proiezione resta `0`.

