# a2pdf — фирменные PDF из markdown, Word и Notion

Сервис и CLI, которые превращают `.md`, `.docx`, вставленный markdown или
ссылку на страницу Notion в PDF в оформлении A2DATA: обложка, колонтитулы
с нумерацией страниц, диаграммы mermaid в фирменной палитре, встроенные
шрифты Inter и JetBrains Mono.

```
a2pdf/
  a2pdf/
    core.py          вёрстка и сборка PDF
    docx_reader.py   чтение .docx
    html_reader.py   HTML в блоки документа
    notion.py        импорт страниц Notion
    fetch.py         загрузка обычных страниц и raw markdown
    web.py           HTTP-сервис (FastAPI)
    static/          веб-форма
    assets/          шрифты и mermaid
  Dockerfile
  docker-compose.yml
  md-to-pdf.cmd      перетащи файл на этот значок (Windows)
  requirements.txt
```

## Поднять сервис

```bash
docker compose up -d --build
```

Открыть http://localhost:8000 — форма загрузки. Проверка живости:
`GET /healthz`, описание API: `/api`.

Образ самодостаточный: внутри chromium, шрифты и mermaid, в интернет
на старте сервис не ходит.

### Переменные окружения

| Переменная | По умолчанию | Что делает |
|---|---|---|
| `A2PDF_WORKERS` | 2 | сколько документов собирается одновременно |
| `A2PDF_TIMEOUT` | 120 | предел на один документ, секунд |
| `A2PDF_MAX_UPLOAD` | 20971520 | максимальный размер загрузки, байт |
| `A2PDF_CHROME` | автопоиск | путь к chromium или chrome |
| `A2PDF_ASSETS` | `a2pdf/assets` | где лежат шрифты и mermaid |
| `A2PDF_TMP`, `A2PDF_OUT` | системный temp | рабочие каталоги |
| `NOTION_TOKEN` | — | токен интеграции Notion для закрытых страниц |

Один воркер держит один процесс chromium, поэтому память растёт линейно:
на 2 воркера достаточно 1 ГБ. Ставьте `A2PDF_WORKERS` по числу ядер, а перед
сервисом — обычный reverse proxy с ограничением размера тела запроса.

## Как пользоваться

**Через браузер.** Три вкладки: перетащить файл, вставить markdown текстом
или дать ссылку. При необходимости раскрыть «Настройки обложки» и нажать
«Собрать PDF».

**Через API.**

```bash
curl -X POST http://localhost:8000/convert -F "file=@doc.md" -F "kicker=Коммерческое предложение" -F "index=01" -F "meta=Клиент=ООО Пример;Срок=10 недель" -o doc.pdf
```

Источник задаётся одним из полей: `file`, `text` или `url`.

```bash
curl -X POST http://localhost:8000/convert -F "url=https://www.notion.so/..." -o doc.pdf
```

Остальные поля необязательные и перекрывают front matter: `title`, `subtitle`,
`kicker`, `index`, `header`, `footer`, `confidential`, `meta`
(строки `Ключ=Значение` через перевод строки или `;`), `style=light|dark`,
`photo` (файл), `cover=0`, `numbered=0`.

### Ссылки

Notion читается через его API — подходят адреса `notion.so`, `notion.site`
и `app.notion.com`. Страница должна быть открыта по ссылке: Share → General
access → **Anyone on the web with link**. Для закрытых страниц заведите internal
integration, передайте сервису `NOTION_TOKEN` и добавьте интеграцию к странице
через Share.

Обычные страницы и ссылки на `.md` берутся простым HTTP-запросом. Браузер при
этом не запускается вообще, поэтому страницы, где текст подгружают скрипты,
прочитать нельзя — такие проще сохранить в файл и загрузить им.

**Локально, без сервиса.**

```bash
pip install -r requirements.txt
```

```bash
python -m a2pdf документ.md -o готовый.pdf --kicker "Отчёт" --confidential
```

На Windows можно просто перетащить файлы на `md-to-pdf.cmd`.

**Как библиотека.**

```python
import a2pdf, pathlib

a2pdf.build_any(pathlib.Path("документ.docx"), pathlib.Path("out.pdf"),
                overrides={"kicker": "Отчёт", "meta": {"Автор": "Егор"}})
```

## Что понимает конвертер

Из markdown: заголовки, абзацы, списки, таблицы, код, цитаты (рисуются
янтарной выноской), картинки, блоки ` ```mermaid `.

Из docx: заголовки, жирный и курсив, списки, таблицы, цитаты, картинки.
Оформление Word игнорируется — документ пересобирается по брендбуку.

Из Notion: заголовки, абзацы, списки, чек-листы, цитаты и колауты, код,
таблицы, разделители, картинки и вложенные блоки.

Из веб-страницы: то же, что из HTML, — заголовки, текст, списки и таблицы.

### Обложка

По умолчанию синяя. `style: light` даёт светлый вариант, `photo` кладёт
снимок фоном: он обесцвечивается и уходит под синий слой — получается дуотон
в фирменном цвете.

Front matter в начале md задаёт обложку:

```markdown
---
title: Rate Limiter
subtitle: Ограничение частоты запросов
kicker: Тестовое задание
index: "01"
confidential: Не для кандидатов
header: Тестовое задание · Rate Limiter
footer: Python Backend Developer · a2data.ai
cover: true
numbered: true
mermaid: true
style: dark
photo: cover.jpg
meta:
  Роль: Python Backend
  Таймбокс: 4 часа
---
```

Маркеры внутри текста:

- `<!--PART:Часть 2|Заголовок-->` — разделитель между частями документа;
- `<!--CAP:подпись под схемой-->` — подпись к диаграмме;
- `<!--NUMBERING:off-->` — выключить нумерацию разделов с этого места.

## Как это устроено

Markdown, docx, Notion или веб-страница разбираются в единый список блоков;
блоки превращаются в HTML со стилями брендбука, headless chromium печатает его
в PDF, PyMuPDF склеивает обложку с телом и штампует колонтитулы с номерами
страниц. Браузер используется только для печати.

Палитра и шрифты берутся из брендбука: navy `#0B2660`, blue `#1FA8FC`,
amber `#FF9F1C`, Inter + JetBrains Mono.
