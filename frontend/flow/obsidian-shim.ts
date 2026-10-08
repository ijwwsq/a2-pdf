/*
 * Замена модуля "obsidian" для работы редактора mermaid-flow в обычном браузере.
 * Реализовано ровно то, чем пользуется редактор: DOM-хелперы Obsidian, окна,
 * контекстное меню, уведомления, иконки lucide и «хранилище», которое отдаёт
 * файлы на скачивание.
 */
import { icons } from "lucide";

/* ---------- DOM-хелперы Obsidian ---------- */

interface ElOptions {
	cls?: string | string[];
	text?: string;
	attr?: Record<string, string | number | boolean | null>;
	title?: string;
	type?: string;
	value?: string;
	placeholder?: string;
	href?: string;
	parent?: Node;
	prepend?: boolean;
}

function applyOptions(el: Element, o?: ElOptions | string): void {
	if (!o) return;
	if (typeof o === "string") { el.className = o; return; }
	if (o.cls) el.classList.add(...(Array.isArray(o.cls) ? o.cls : o.cls.split(/\s+/)).filter(Boolean));
	if (o.text !== undefined) el.textContent = o.text;
	if (o.attr) {
		for (const [k, v] of Object.entries(o.attr)) {
			if (v === null || v === false) el.removeAttribute(k);
			else el.setAttribute(k, String(v));
		}
	}
	const h = el as HTMLInputElement & HTMLAnchorElement;
	if (o.title !== undefined) el.setAttribute("title", o.title);
	if (o.type !== undefined) h.type = o.type;
	if (o.value !== undefined) h.value = o.value;
	if (o.placeholder !== undefined) h.placeholder = o.placeholder;
	if (o.href !== undefined) h.href = o.href;
}

function make<K extends keyof HTMLElementTagNameMap>(
	tag: K, o?: ElOptions | string, cb?: (el: HTMLElementTagNameMap[K]) => void,
): HTMLElementTagNameMap[K] {
	const el = document.createElement(tag);
	applyOptions(el, o);
	cb?.(el);
	return el;
}

const NodeProto = Node.prototype as any;
const ElProto = Element.prototype as any;
const HtmlProto = HTMLElement.prototype as any;

NodeProto.createEl = function (tag: any, o?: any, cb?: any) {
	const el = make(tag, o, cb);
	if (o && typeof o === "object" && o.prepend) this.insertBefore(el, this.firstChild);
	else this.appendChild(el);
	return el;
};
NodeProto.createDiv = function (o?: any, cb?: any) { return this.createEl("div", o, cb); };
NodeProto.createSpan = function (o?: any, cb?: any) { return this.createEl("span", o, cb); };
NodeProto.createSvg = function (tag: string, o?: any, cb?: any) {
	const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
	applyOptions(el, o);
	this.appendChild(el);
	cb?.(el);
	return el;
};
NodeProto.empty = function () { while (this.firstChild) this.removeChild(this.firstChild); };
NodeProto.detach = function () { this.parentNode?.removeChild(this); };
NodeProto.setText = function (t: string) { this.textContent = t; };
NodeProto.appendText = function (t: string) { this.appendChild(document.createTextNode(t)); };
ElProto.addClass = function (...c: string[]) { this.classList.add(...c); };
ElProto.addClasses = function (c: string[]) { this.classList.add(...c); };
ElProto.removeClass = function (...c: string[]) { this.classList.remove(...c); };
ElProto.removeClasses = function (c: string[]) { this.classList.remove(...c); };
ElProto.toggleClass = function (c: string | string[], on: boolean) {
	for (const x of Array.isArray(c) ? c : [c]) this.classList.toggle(x, on);
};
ElProto.hasClass = function (c: string) { return this.classList.contains(c); };
ElProto.setAttr = function (k: string, v: any) {
	if (v === null || v === false) this.removeAttribute(k); else this.setAttribute(k, String(v));
};
ElProto.setAttrs = function (o: Record<string, any>) { for (const k in o) this.setAttr(k, o[k]); };
ElProto.getText = function () { return this.textContent ?? ""; };
HtmlProto.show = function () { this.style.display = ""; this.removeAttribute("hidden"); };
HtmlProto.hide = function () { this.style.display = "none"; };
HtmlProto.toggle = function (on: boolean) { if (on) this.show(); else this.hide(); };
HtmlProto.isShown = function () { return this.style.display !== "none" && !this.hidden; };
HtmlProto.setCssStyles = function (s: Record<string, string>) { Object.assign(this.style, s); };
HtmlProto.setCssProps = function (s: Record<string, string>) {
	for (const k in s) this.style.setProperty(k, s[k] ?? "");
};
HtmlProto.onClickEvent = function (cb: (e: MouseEvent) => void) { this.addEventListener("click", cb); };

const g = globalThis as any;
g.activeDocument = document;
g.activeWindow = window;
g.createEl = (tag: any, o?: any, cb?: any) => make(tag, o, cb);
g.createDiv = (o?: any, cb?: any) => make("div", o, cb);
g.createSpan = (o?: any, cb?: any) => make("span", o, cb);
g.createFragment = (cb?: (f: DocumentFragment) => void) => {
	const f = document.createDocumentFragment(); cb?.(f); return f;
};

/* ---------- иконки ---------- */

const pascal = (name: string) =>
	name.split("-").map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join("");

export function setIcon(el: HTMLElement, name: string): void {
	el.empty();
	const node = (icons as Record<string, any>)[pascal(name)];
	const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
	for (const [k, v] of Object.entries({
		xmlns: "http://www.w3.org/2000/svg", width: "24", height: "24",
		viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
		"stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round",
		class: `svg-icon lucide-${name}`,
	})) svg.setAttribute(k, v);
	// lucide отдаёт иконку как [тег, атрибуты][] — в разных версиях с обёрткой
	const parts: [string, Record<string, string>][] =
		Array.isArray(node) ? (node[0] === "svg" ? node[2] : node) : [];
	for (const [tag, attrs] of parts ?? []) {
		const child = document.createElementNS("http://www.w3.org/2000/svg", tag);
		for (const [k, v] of Object.entries(attrs)) child.setAttribute(k, String(v));
		svg.appendChild(child);
	}
	el.appendChild(svg);
}

/* ---------- уведомления ---------- */

export class Notice {
	noticeEl: HTMLElement;
	constructor(message: string | DocumentFragment, timeout = 4000) {
		let box = document.querySelector<HTMLElement>(".notice-container");
		if (!box) box = document.body.createDiv({ cls: "notice-container" });
		this.noticeEl = box.createDiv({ cls: "notice" });
		if (typeof message === "string") this.noticeEl.setText(message);
		else this.noticeEl.appendChild(message);
		this.noticeEl.addEventListener("click", () => this.hide());
		if (timeout) setTimeout(() => this.hide(), timeout);
	}
	setMessage(m: string): this { this.noticeEl.setText(m); return this; }
	hide(): void { this.noticeEl.detach(); }
}

/* ---------- «хранилище»: файлы уходят на скачивание ---------- */

function download(path: string, data: string | ArrayBuffer): void {
	const name = path.split("/").pop() || "diagram";
	const type = name.endsWith(".svg") ? "image/svg+xml"
		: name.endsWith(".png") ? "image/png" : "text/plain";
	const url = URL.createObjectURL(new Blob([data], { type }));
	const a = document.createElement("a");
	a.href = url; a.download = name;
	document.body.appendChild(a); a.click(); a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export class TFile { path = ""; basename = ""; extension = ""; }

export class App {
	vault = {
		getAbstractFileByPath: (_p: string) => null,
		createFolder: async (_p: string) => undefined,
		create: async (p: string, d: string) => download(p, d),
		createBinary: async (p: string, d: ArrayBuffer) => download(p, d),
		getFiles: () => [] as TFile[],
		getMarkdownFiles: () => [] as TFile[],
	};
	workspace = {
		getActiveFile: () => null,
		openLinkText: async () => undefined,
	};
	metadataCache = { getFirstLinkpathDest: () => null };
}

export const normalizePath = (p: string) =>
	p.replace(/\\/g, "/").replace(/\/+/g, "/").replace(/^\/|\/$/g, "");

/* ---------- окна ---------- */

export class Modal {
	app: App;
	containerEl: HTMLElement;
	modalEl: HTMLElement;
	titleEl: HTMLElement;
	contentEl: HTMLElement;
	scope = { register: () => undefined };
	private keyHandler = (e: KeyboardEvent) => { if (e.key === "Escape") this.close(); };
	private inline: HTMLElement | null = null;

	constructor(app: App) {
		this.app = app;
		this.containerEl = createDiv({ cls: "modal-container" });
		this.containerEl.createDiv({ cls: "modal-bg" })
			.addEventListener("click", () => this.close());
		this.modalEl = this.containerEl.createDiv({ cls: "modal" });
		const close = this.modalEl.createDiv({ cls: "modal-close-button" });
		setIcon(close, "x");
		close.addEventListener("click", () => this.close());
		this.titleEl = this.modalEl.createDiv({ cls: "modal-title" });
		this.contentEl = this.modalEl.createDiv({ cls: "modal-content" });
	}

	setTitle(t: string): this { this.titleEl.setText(t); return this; }

	open(): void {
		document.body.appendChild(this.containerEl);
		document.addEventListener("keydown", this.keyHandler);
		this.onOpen();
	}

	/** Не окном, а прямо в странице: так встраиваются редакторы схем. */
	mountInline(host: HTMLElement): void {
		this.inline = host;
		host.empty();
		this.modalEl = host;
		this.titleEl = createDiv();
		this.contentEl = host;
		this.onOpen();
	}

	close(): void {
		if (this.inline) { this.onClose(); return; }
		document.removeEventListener("keydown", this.keyHandler);
		this.onClose();
		this.containerEl.detach();
	}

	onOpen(): void {}
	onClose(): void {}
}

export class FuzzySuggestModal<T> extends Modal {
	setPlaceholder(_p: string): void {}
	getItems(): T[] { return []; }
	getItemText(_i: T): string { return ""; }
	onChooseItem(_i: T, _e: Event): void {}
}

/* ---------- контекстное меню ---------- */

class MenuItem {
	el: HTMLElement;
	private handler: ((e: MouseEvent | KeyboardEvent) => void) | null = null;
	constructor(private menu: Menu) {
		this.el = createDiv({ cls: "menu-item" });
		this.el.createDiv({ cls: "menu-item-icon" });
		this.el.createDiv({ cls: "menu-item-title" });
		this.el.addEventListener("click", (e) => {
			if (this.el.hasClass("is-disabled")) return;
			this.menu.hide();
			this.handler?.(e);
		});
	}
	setTitle(t: string | DocumentFragment): this {
		const title = this.el.querySelector<HTMLElement>(".menu-item-title")!;
		title.empty();
		if (typeof t === "string") title.setText(t); else title.appendChild(t);
		return this;
	}
	setIcon(name: string | null): this {
		const icon = this.el.querySelector<HTMLElement>(".menu-item-icon")!;
		if (name) setIcon(icon, name); else icon.empty();
		return this;
	}
	setChecked(on: boolean | null): this { this.el.toggleClass("mod-checked", !!on); return this; }
	setDisabled(on: boolean): this { this.el.toggleClass("is-disabled", on); return this; }
	setWarning(on: boolean): this { this.el.toggleClass("mod-warning", on); return this; }
	setSection(_s: string): this { return this; }
	setIsLabel(on: boolean): this { this.el.toggleClass("is-label", on); return this; }
	onClick(cb: (e: MouseEvent | KeyboardEvent) => void): this { this.handler = cb; return this; }
}

export class Menu {
	dom: HTMLElement;
	private hideCbs: (() => void)[] = [];
	private outside = (e: Event) => {
		if (!this.dom.contains(e.target as Node)) this.hide();
	};
	private esc = (e: KeyboardEvent) => { if (e.key === "Escape") this.hide(); };

	constructor() { this.dom = createDiv({ cls: "menu" }); }

	addItem(cb: (item: MenuItem) => unknown): this {
		const item = new MenuItem(this);
		cb(item);
		this.dom.appendChild(item.el);
		return this;
	}
	addSeparator(): this { this.dom.createDiv({ cls: "menu-separator" }); return this; }
	addClass(c: string): this { this.dom.addClass(c); return this; }
	setNoIcon(): this { return this; }
	setUseNativeMenu(_n: boolean): this { return this; }
	onHide(cb: () => void): void { this.hideCbs.push(cb); }

	showAtPosition(p: { x: number; y: number }): this {
		document.querySelectorAll(".menu").forEach((m) => m.remove());
		document.body.appendChild(this.dom);
		const r = this.dom.getBoundingClientRect();
		this.dom.style.left = Math.min(p.x, window.innerWidth - r.width - 8) + "px";
		this.dom.style.top = Math.min(p.y, window.innerHeight - r.height - 8) + "px";
		setTimeout(() => {
			document.addEventListener("mousedown", this.outside, true);
			document.addEventListener("keydown", this.esc, true);
		});
		return this;
	}
	showAtMouseEvent(e: MouseEvent): this {
		e.preventDefault();
		return this.showAtPosition({ x: e.clientX, y: e.clientY });
	}
	hide(): this {
		document.removeEventListener("mousedown", this.outside, true);
		document.removeEventListener("keydown", this.esc, true);
		this.dom.detach();
		this.hideCbs.forEach((cb) => cb());
		return this;
	}
	close(): void { this.hide(); }
}

/* ---------- настройки: только для окна AI, которое здесь не открывается ---------- */

export class Setting {
	settingEl: HTMLElement;
	constructor(container: HTMLElement) { this.settingEl = container.createDiv({ cls: "setting-item" }); }
	setName(_n: string): this { return this; }
	setDesc(_d: string): this { return this; }
	setHeading(): this { return this; }
	setClass(c: string): this { this.settingEl.addClass(c); return this; }
	addText(_cb: unknown): this { return this; }
	addTextArea(_cb: unknown): this { return this; }
	addToggle(_cb: unknown): this { return this; }
	addDropdown(_cb: unknown): this { return this; }
	addButton(_cb: unknown): this { return this; }
	addSlider(_cb: unknown): this { return this; }
}

/* ---------- прочее ---------- */

export async function loadMermaid(): Promise<unknown> { return (window as any).mermaid; }

export async function requestUrl(req: { url: string; method?: string; headers?: Record<string, string>; body?: string }) {
	const res = await fetch(req.url, { method: req.method, headers: req.headers, body: req.body });
	const text = await res.text();
	let json: unknown = null;
	try { json = JSON.parse(text); } catch { /* не json */ }
	return { status: res.status, text, json };
}

export class Plugin {}
export class PluginSettingTab {}
export class ItemView {}
export class WorkspaceLeaf {}
export class MarkdownView {}
export class Editor {}
export class Component {}
export const Platform = { isMobile: false, isDesktop: true };
