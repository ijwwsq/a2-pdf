# mermaid-flow в a2pdf

`vendor/` — исходники [obsidian-mermaid-flow](https://github.com/thansheer/obsidian-mermaid-flow)
(коммит `2c33686`, 2026-09-26), лицензия GPL-3.0-or-later — см. `vendor/LICENSE`.
Используется во внутреннем инструменте и не распространяется; при выдаче
сервиса наружу весь код подпадает под GPL.

Убрано: `main.ts`, `editorExtension.ts`, `feedback/`, `kofi.ts` — интеграция с Obsidian.

Изменено (помечено `a2pdf:`):

- `altDiagrams/editor.ts` — колбэк `onChange` для живого превью, цвета холста из токенов бренда;
- `themePalette.ts`, `canvas.ts` — обводка узлов цветом бренда вместо лилового;
- `textMetrics.ts` — ширина подписей меряется шрифтом бренда;
- `propertiesPanel.ts` — класс у кнопки выбора заметки, чтобы спрятать;
- `toolbar.ts` — класс у выбора темы, чтобы спрятать его: цвета задаёт брендбук.

Русский интерфейс — `ru.ts`: словарь, без правки исходников плагина.

Модуль `obsidian` подменяется `obsidian-shim.ts` (см. `build.mjs`).
Сборка: `npm ci && npm run build` → `a2pdf/static/flow/flow.js` и `flow.css`.
