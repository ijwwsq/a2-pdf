/*
 * Конструктор схем a2pdf: визуальные редакторы mermaid-flow прямо в странице.
 *
 *   A2Flow.mount(host, code, onChange) — подбирает редактор под тип схемы:
 *     блок-схема  → холст с перетаскиванием (DiagramEditorUI),
 *     sequence / mindmap / ER → свои визуальные редакторы,
 *     остальное   → null: страница показывает редактор кода.
 */
import "./obsidian-shim";
import { App, Notice } from "obsidian";
import { DiagramEditorUI } from "./vendor/editorUI";
import { AltDiagramModal } from "./vendor/altDiagrams";
import { detectDiagramType, isAltDiagramType } from "./vendor/diagramType";
import { layoutMissing, resolveOverlaps } from "./vendor/layout";
import { emptyModel } from "./vendor/model";
import { STYLE_PRESETS } from "./vendor/presets";
import { mermaidToModel } from "./vendor/parser";
import { modelToMermaid } from "./vendor/serializer";
import { startRussian } from "./ru";

startRussian();

export interface Mounted {
	kind: string;
	destroy(): void;
}

const app = new App();

function mountFlowchart(host: HTMLElement, code: string,
                        onChange: (code: string) => void): Mounted {
	const parsed = code.trim() ? mermaidToModel(code) : null;
	const model = parsed?.model ?? emptyModel("LR");
	layoutMissing(model);
	resolveOverlaps(model);
	if (parsed && parsed.warnings.length) {
		new Notice(`Схема прочитана, замечаний: ${parsed.warnings.length}`);
	}
	const emit = (m: typeof model) => onChange(modelToMermaid(m, { includePositions: true }));
	const ui = new DiagramEditorUI(app, host, model, {
		persist: emit,
		close: () => undefined,
		autoSave: true,
		saveLabel: "Применить",
		toolbarStyle: "native",
		panelStyle: "sidebar",
		autoResizeCanvas: true,
		snapSize: 0,
		defaultShape: "rect",
	});
	ui.build();
	return { kind: "flowchart", destroy: () => ui.destroy() };
}

function mountAlt(host: HTMLElement, kind: "sequence" | "mindmap" | "er", code: string,
                  onChange: (code: string) => void): Mounted {
	const modal = new AltDiagramModal(app, kind, code, async (c) => onChange(c));
	// первая отрисовка — не правка: иначе код переписывается от одного открытия
	let ready = false;
	modal.onChange = (c) => { if (ready) onChange(c); };
	host.addClass("a2-inline");
	(modal as unknown as { mountInline(h: HTMLElement): void }).mountInline(host);
	ready = true;
	return { kind, destroy: () => { modal.close(); host.empty(); host.removeClass("a2-inline"); } };
}

export function mount(host: HTMLElement, code: string,
                      onChange: (code: string) => void): Mounted | null {
	const type = detectDiagramType(code);
	if (type === "flowchart" || (type === "unknown" && !code.trim())) {
		return mountFlowchart(host, code, onChange);
	}
	if (isAltDiagramType(type)) return mountAlt(host, type, code, onChange);
	return null;
}

export { detectDiagramType };

/** Готовые стили узлов («Начало», «Решение»…) — в палитре шаблона бренда,
 *  а не в зелёно-красных цветах плагина. palette: [заливка, обводка, текст][]. */
export function setPalette(palette: [string, string, string][]): void {
	if (!palette.length) return;
	STYLE_PRESETS.forEach((preset, i) => {
		const [fill, stroke, text] = palette[i % palette.length]!;
		preset.style = { ...preset.style, fillColor: fill, strokeColor: stroke, textColor: text };
	});
}
