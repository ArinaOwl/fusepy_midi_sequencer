# fusepy_midi_sequencer

Файловая система — MIDI-секвенсер. 

При монтировании передается аргумент — путь к MIDI-файлу, который разбирается на треки и/или каналы (в зависимости от значения поля format в заголовке `MThd`): каждый трек представляется подкаталогом и MIDI-файлом в каталоге `tracks`. Каждый канал представляется отдельным MIDI-файлом в каталоге соответствующей дорожки. У генерируемых MIDI-файлов `format=0`. Генерируемые MIDI-файлы и содержащие их каталоги доступны на чтение. Также в корне файловой системы представлен файл `HEADER`, содержащий информацию из `MThd` (формат и количество треков).

Пример `HEADER.txt`:
```        
format: 1 
ntrks: 2
```
---
Примеры организации:
- `format=0`
    ```
    HEADER
    track/
        channel0.mid
        channel1.mid
        channel2.mid
    ```
            
- `format=1`
    ```
    HEADER
    tracks/
        track0.mid
        track1.mid
        track2.mid
    ```
            
- `format=2`
    ```
    HEADER
    tracks/
        track0/
            channel0.mid
            channel1.mid
            channel2.mid
        track0.mid
        track1/
            channel0.mid
        track1.mid
    ```

