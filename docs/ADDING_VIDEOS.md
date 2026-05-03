# Как добавить новые видео

Пайплайн **идемпотентен** — повторный запуск пропускает уже обработанное. Можно добавлять видео порциями.

## Сценарий 1: Новые видео в существующем плейлисте

YouTube-канал плейлиста добавил новые выпуски — нужно подтянуть их.

```bash
# 1. Удалить кэш плейлиста, чтобы он перечитался
rm data/all_videos.json

# 2. Запустить с начала — пропустит уже скачанные .vtt и обработанные video_id
python scripts/1_download_subs.py
python scripts/2_parse_vtt.py
python scripts/3_extract_events.py 6 15
# … запустить субагентов …
python scripts/_apply_extracted_events.py
python scripts/4_geocode.py
python scripts/4b_geocode_retry.py
python scripts/5_export_geojson.py
```

## Сценарий 2: Другой плейлист

```bash
# Указать другой плейлист через env var
export DP_PLAYLIST="https://www.youtube.com/playlist?list=PLxxxxx"

# Перезаписать all_videos.json
rm data/all_videos.json

# Дальше — обычный пайплайн (см. сценарий 1)
```

## Сценарий 3: Список конкретных видео

Например, добавить 10 конкретных видео не из плейлиста.

1. Открыть `data/all_videos.json` и руками добавить записи:
   ```json
   {
     "video_id": "dQw4w9WgXcQ",
     "title": "...",
     "upload_date": "",
     "duration_sec": 213,
     "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
   }
   ```
2. Запустить с шага 1 — обнаружит новые `video_id` и обработает их.

## Сценарий 4: Перепроверить конкретные видео

Например, выяснилось что Haiku-агент пропустил события в каком-то выпуске.

```bash
# 1. Удалить эти video_id из processed_videos.txt
# (открыть файл, удалить строки)

# 2. Перезапустить шаги 3-5 — возьмёт эти видео в новый раунд
python scripts/3_extract_events.py 1 5  # 1 агент на 5 видео
# … запустить агента …
python scripts/_apply_extracted_events.py
python scripts/5_export_geojson.py
```

⚠️ **Дубли по `(video_id, timecode)`** автоматически отбрасываются. Если хочется заменить старые события новыми — сначала почистить CSV руками.

## Сценарий 5: Резкое расширение качества

Если хочется поднять покрытие геокодинга с 79% до 95%:

1. **Yandex Geocoder API** ($, регистрация на developer.tech.yandex.ru):
   ```python
   # Заменить geocode() в scripts/4_geocode.py:
   url = f"https://geocode-maps.yandex.ru/1.x/?apikey={API_KEY}&geocode={addr}&format=json&lang=ru_RU"
   ```
   Скорость — 25 req/sec вместо 1, точность — выше для русских адресов.

2. **Перезапуск только для непокрытых:**
   ```bash
   # Очистить только неудачные кеш-записи
   python -c "
   import json
   c = json.load(open('data/geocode_cache.json', encoding='utf-8'))
   c = {k: v for k, v in c.items() if v.get('lat')}
   json.dump(c, open('data/geocode_cache.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
   "
   python scripts/4_geocode.py
   ```

## Идемпотентность: что хранится

| Файл | Что отслеживает |
|---|---|
| `subs/*.ru.vtt` | Какие .vtt уже скачаны (>100 байт = OK) |
| `transcripts/*.txt` | Какие транскрипты распарсены |
| `data/processed_videos.txt` | Какие video_id обработаны субагентами |
| `data/geocode_cache.json` | Какие адреса искались (с координатами или без) |

Удаление любого из этих маркеров заставит соответствующий шаг переделать работу.
