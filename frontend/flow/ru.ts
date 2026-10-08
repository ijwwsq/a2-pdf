/*
 * Русский интерфейс редактора mermaid-flow без правки его исходников:
 * наблюдатель подменяет надписи, подсказки и плейсхолдеры по словарю.
 * Холст со схемой и поля ввода не трогаем — там текст пользователя.
 */

const RU: Record<string, string> = {
	// тулбар и режимы
	"Add": "Добавить", "Add shape": "Добавить фигуру", "Direction": "Направление",
	"Select direction": "Направление схемы", "Theme": "Тема",
	"Left to right": "Слева направо", "Right to left": "Справа налево",
	"Top to bottom": "Сверху вниз", "Bottom to top": "Снизу вверх",
	"Select / move (S)": "Выбор и перемещение (S)", "Connect nodes (C)": "Соединить узлы (C)",
	"Connect nodes mode": "Режим соединения узлов", "Undo": "Отменить", "Redo": "Повторить",
	"Redo (alt)": "Повторить (альт.)", "Auto-layout": "Авторасстановка",
	"Lock layout": "Закрепить раскладку", "Layout locked": "Раскладка закреплена",
	"Layout is locked. Unlock it to change layout.":
		"Раскладка закреплена. Открепите, чтобы её менять.",
	"Layout presets": "Готовые раскладки", "Clean up layout": "Навести порядок",
	"Zoom to fit all nodes": "Показать всю схему", "Reset zoom to 100%": "Масштаб 100%",
	"Toggle code view": "Показать код", "Open code view": "Открыть код",
	"Delete selected": "Удалить выбранное", "Delete selected (Del)": "Удалить выбранное (Del)",
	"Export diagram": "Выгрузить схему", "Export": "Выгрузить", "Export as PNG…": "PNG…",
	"Export as SVG…": "SVG…", "Copy PNG to clipboard": "Скопировать PNG",
	"Copy code to clipboard": "Скопировать код", "Copy diagram code to clipboard": "Скопировать код схемы",
	"Keyboard Shortcuts & Help": "Клавиши и подсказки", "Find nodes…": "Найти узел…",
	"Close find bar": "Закрыть поиск", "Component library": "Библиотека компонентов",
	"Group selected into subgraph": "Объединить выбранное в группу",
	"Collapse properties panel": "Свернуть панель", "Expand properties panel": "Развернуть панель",
	"Save": "Сохранить", "Discard": "Отменить правки", "Close": "Закрыть", "Cancel": "Отмена",
	"Open": "Открыть", "Copy": "Копировать", "Delete": "Удалить", "Duplicate": "Дублировать",
	// фигуры
	"Rectangle": "Прямоугольник", "Rounded": "Скруглённый", "Stadium": "Капсула",
	"Subroutine": "Подпроцесс", "Cylinder / database": "Цилиндр / база данных",
	"Circle": "Круг", "Double circle": "Двойной круг", "Asymmetric": "Флажок",
	"Decision": "Решение", "Hexagon": "Шестиугольник", "Parallelogram": "Параллелограмм",
	"Parallelogram (alt)": "Параллелограмм (обратный)", "Trapezoid": "Трапеция",
	"Trapezoid (alt)": "Трапеция (обратная)", "Process": "Процесс", "Data / IO": "Данные / ввод-вывод",
	"Start": "Начало", "End": "Конец", "Step": "Шаг", "Idea": "Идея",
	// связи
	"Arrow": "Стрелка", "Arrow →": "Стрелка →", "Open line": "Линия", "Open line —": "Линия —",
	"Dotted": "Пунктир", "Dotted -→": "Пунктир -→", "Thick": "Жирная", "Thick ⇒": "Жирная ⇒",
	"Bidirectional": "В обе стороны", "Bidirectional ↔": "В обе стороны ↔",
	"Invisible": "Невидимая", "Animated": "Анимированная", "Dependency": "Зависимость",
	"Reverse direction": "Развернуть направление", "Delete edge": "Удалить связь",
	// панель свойств
	"Properties": "Свойства", "Select a node or edge to edit it.": "Выберите узел или связь.",
	"Click a shape in the toolbar to add a node.": "Фигура из тулбара добавляет узел.",
	"Drag a node to move it; drag a blue edge dot to connect.":
		"Узел перетаскивается; связь тянется от синей точки на краю.",
	"Shift-click or drag a box to select several nodes.":
		"Shift-клик или рамка выделяют несколько узлов.",
	"Right-click a node or edge for more actions.":
		"Правый клик по узлу или связи — остальные действия.",
	"Diagram": "Схема", "Background": "Фон", "Transparent": "Прозрачный",
	"Diagram background color": "Цвет фона схемы", "Nothing selected.": "Ничего не выбрано.",
	"Node": "Узел", "Edge": "Связь", "Label": "Подпись", "Node label": "Подпись узла",
	"Shape": "Фигура", "Size": "Размер", "Auto size": "Авторазмер", "Node width": "Ширина узла",
	"Node height": "Высота узла", "Text & style": "Текст и стиль", "Preset style": "Готовый стиль",
	"Style as": "Оформить как", "Quick add": "Быстро добавить", "Line & label style": "Линия и подпись",
	"Fill color": "Заливка", "Border color": "Обводка", "Text color": "Цвет текста",
	"Line color": "Цвет линии", "Label color": "Цвет подписи", "Line width (px)": "Толщина линии (px)",
	"Label size (px)": "Размер подписи (px)", "Font size (px)": "Размер шрифта (px)",
	"Font family": "Шрифт", "Link": "Ссылка", "Type": "Тип", "Content": "Содержимое",
	"Style changes apply to all selected nodes.": "Стиль меняется у всех выбранных узлов.",
	"Reset style": "Сбросить стиль", "Reset style for all": "Сбросить стиль у всех",
	"Classes": "Классы", "Edit class": "Изменить класс", "New class name": "Имя нового класса",
	"Create class and assign to this node": "Создать класс и назначить узлу",
	"Class fill": "Заливка класса", "Class border": "Обводка класса", "Class text": "Текст класса",
	"No classes yet — add one to create a reusable style shared by several nodes.":
		"Классов пока нет — класс задаёт общий стиль для нескольких узлов.",
	"Subgraph": "Группа", "Parent subgraph": "Родительская группа", "Title": "Заголовок",
	"Ungroup": "Разгруппировать", "Ungroup (keep nodes)": "Разгруппировать (узлы оставить)",
	"Drag the title bar to move the whole group. Assign more nodes from each node's panel.":
		"Тащите заголовок, чтобы сдвинуть всю группу. Узлы добавляются из их панелей.",
	"Lock position": "Закрепить положение", "Bring to front": "На передний план",
	"Send to back": "На задний план", "Muted": "Приглушённый", "Emphasis": "Акцент",
	"Default": "Обычный", "Normal": "Обычная", "Compact": "Плотно", "Spacious": "Свободно",
	"Yes": "Да", "No": "Нет", "Yes path": "Ветка «да»", "No path": "Ветка «нет»",
	// контекстное меню
	"Add node here": "Добавить узел здесь", "Select all (Ctrl+A)": "Выделить всё (Ctrl+A)",
	"Select all nodes": "Выделить все узлы", "Connect from here": "Соединить отсюда",
	"Add step after": "Добавить следующий шаг", "Add parallel sibling": "Добавить параллельный шаг",
	"Add Yes/No branch": "Добавить ветвление да/нет", "Group into new subgraph": "Объединить в группу",
	"Save selection as component…": "Сохранить выделенное как компонент…",
	"Rename / edit label": "Переименовать", "Delete node": "Удалить узел",
	"Duplicate selected node": "Дублировать узел", "Copy selected node(s)": "Копировать узлы",
	"Paste copied node(s)": "Вставить узлы", "Step after": "Следующий шаг",
	"Parallel sibling": "Параллельный шаг", "Sibling": "Соседний", "Child label": "Подпись дочернего",
	"Align left edges": "Выровнять по левому краю", "Align right edges": "Выровнять по правому краю",
	"Align top edges": "Выровнять по верху", "Align bottom edges": "Выровнять по низу",
	"Centre horizontally": "Центр по горизонтали", "Centre vertically": "Центр по вертикали",
	"Distribute horizontally": "Распределить по горизонтали",
	"Distribute vertically": "Распределить по вертикали",
	"Select at least 3 nodes to distribute.": "Для распределения выберите хотя бы 3 узла.",
	"Select one or more nodes (Shift-click or drag a box), then group.":
		"Выберите узлы (Shift-клик или рамкой), затем объедините.",
	"Flow — Left to right": "Поток — слева направо", "Flow — Top to bottom": "Поток — сверху вниз",
	"Tree": "Дерево", "Tree — Horizontal": "Дерево — горизонтально", "Tree — Vertical": "Дерево — вертикально",
	// библиотека компонентов
	"No saved components yet": "Сохранённых компонентов нет", "Component name": "Имя компонента",
	"Untitled component": "Компонент без имени",
	"Component library is not available.": "Библиотека компонентов недоступна.",
	"Select one or more nodes to save as a component.": "Выберите узлы, чтобы сохранить компонент.",
	"Could not build component from selection.": "Из выделенного компонент не собрать.",
	// код
	"Mermaid code": "Код mermaid", "Edit Mermaid diagram code": "Код схемы",
	"Apply to diagram": "Применить к схеме", "Apply code changes to diagram": "Применить код к схеме",
	"Toggle auto-apply for code changes": "Применять код сразу",
	"Invalid Mermaid code. Check the error below.": "Ошибка в коде — подробности ниже.",
	"Unknown parsing error": "Неизвестная ошибка разбора", "Unknown error": "Неизвестная ошибка",
	"Diagram imported.": "Схема загружена.", "Could not import: invalid Mermaid syntax.":
		"Не загрузилось: ошибка в синтаксисе mermaid.",
	// выгрузка
	"Filename": "Имя файла", "Save to folder": "Папка", "Scale": "Масштаб",
	"Transparent background": "Прозрачный фон", "Diagram code copied to clipboard": "Код схемы скопирован",
	"PNG copied to clipboard": "PNG скопирован", "Failed to copy code": "Не удалось скопировать код",
	"Could not export: SVG not available": "Не выгрузилось: нет SVG",
	"Failed to load SVG": "Не удалось загрузить SVG", "Failed to render PNG": "Не удалось собрать PNG",
	"Canvas context unavailable": "Холст недоступен",
	// клавиши
	"Pan canvas": "Двигать холст", "Deselect / cancel connect mode": "Снять выделение / выйти из соединения",
	"Arrow keys": "Стрелки", "Delete / Backspace": "Delete / Backspace", "Escape": "Esc",
	// sequence, mindmap, ER
	"Sequence diagram editor": "Редактор последовательности", "Mindmap editor": "Редактор карты мыслей",
	"Entity-relationship editor": "Редактор сущностей", "Participants": "Участники",
	"Messages": "Сообщения", "Add participant": "Добавить участника", "Add message": "Добавить сообщение",
	"Participant id": "Имя участника", "Message text": "Текст сообщения",
	"Add at least two participants first.": "Сначала добавьте хотя бы двух участников.",
	"Add child": "Добавить ветку", "Add child to root": "Добавить ветку к корню",
	"Entities": "Сущности", "Relations": "Связи", "Add entity": "Добавить сущность",
	"Entity name": "Имя сущности", "Attribute name": "Имя атрибута",
	"Link first two entities": "Связать первые две сущности",
	// старт
	"Get started": "С чего начать", "Start your diagram": "Начните схему",
	"Nothing here is visually editable": "Эту схему можно править только кодом",
	"✓ Auto-saving enabled": "✓ Изменения применяются сразу",
	"Shape & size": "Фигура и размер", "(none)": "(нет)",
	"[[Note]] or https://…": "https://…",
};

// строки с числами и именами внутри
const PATTERNS: [RegExp, string][] = [
	[/^(\d+) nodes · (\d+) edges$/, "Узлов: $1 · связей: $2"],
	[/^(\d+) nodes selected$/, "Выбрано узлов: $1"],
	[/^(\d+) node\(s\) copied$/, "Скопировано узлов: $1"],
	[/^id: (.+) · (\d+) nodes$/, "id: $1 · узлов: $2"],
	[/^Applied with (\d+) warning\(s\)\.$/, "Применено, замечаний: $1"],
	[/^Imported with (\d+) warning\(s\)\.$/, "Загружено, замечаний: $1"],
	[/^Spacing: (.+)$/, "Плотность: $1"],
	[/^Export as (PNG|SVG)$/, "Выгрузка в $1"],
	[/^(PNG|SVG) saved to (.+)$/, "$1 скачан"],
	[/^Auto-apply: (.*)$/, "Применять сразу: $1"],
	[/^ ?Syntax Error: (.*)$/, " Ошибка синтаксиса: $1"],
	[/^Export failed: (.*)$/, "Выгрузка не удалась: $1"],
	[/^Failed to copy PNG: (.*)$/, "Не удалось скопировать PNG: $1"],
	[/^Saved, but Mermaid reports a syntax error: (.*)$/, "Сохранено, но в коде ошибка: $1"],
	[/^Inserted “(.+)”$/, "Вставлен «$1»"],
	[/^Removed “(.+)”$/, "Удалён «$1»"],
	[/^Saved “(.+)” to the component library\.$/, "«$1» сохранён в библиотеку"],
	[/^Insert: (.+)$/, "Вставить: $1"],
	[/^Delete “(.+)”$/, "Удалить «$1»"],
];

function translate(text: string): string | null {
	const core = text.trim();
	if (!core) return null;
	const hit = RU[core];
	if (hit !== undefined) return text.replace(core, hit);
	for (const [re, to] of PATTERNS) {
		if (re.test(core)) return text.replace(core, core.replace(re, to));
	}
	return null;
}

// холст со схемой и поля ввода — текст пользователя, их не переводим
const USER = ".mermaid-flow-svg, .mermaid-flow-alt-svg, textarea, input, [contenteditable]";
const ATTRS = ["title", "aria-label", "placeholder"];

function walk(root: Node): void {
	if (root.nodeType === Node.TEXT_NODE) {
		const parent = root.parentElement;
		if (!parent || parent.closest(USER)) return;
		const t = translate(root.nodeValue ?? "");
		if (t !== null && t !== root.nodeValue) root.nodeValue = t;
		return;
	}
	if (!(root instanceof Element) || root.closest(".mermaid-flow-svg, .mermaid-flow-alt-svg")) return;
	for (const el of [root, ...root.querySelectorAll<Element>("*")]) {
		for (const a of ATTRS) {
			const v = el.getAttribute(a);
			if (!v) continue;
			const t = translate(v);
			if (t !== null && t !== v) el.setAttribute(a, t);
		}
		if (el.closest(USER)) continue;
		for (const child of el.childNodes) {
			if (child.nodeType === Node.TEXT_NODE) walk(child);
		}
	}
}

export function startRussian(root: Node = document.body): void {
	walk(root);
	new MutationObserver((records) => {
		for (const r of records) {
			if (r.type === "characterData") walk(r.target);
			else if (r.type === "attributes") walk(r.target);
			else r.addedNodes.forEach(walk);
		}
	}).observe(root, { subtree: true, childList: true, characterData: true,
		attributes: true, attributeFilter: ATTRS });
}
