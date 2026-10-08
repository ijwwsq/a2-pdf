// Правки уже нарисованной схемы — общие для документа и конструктора.
// series — цвета серий бренда, source — исходник, ушедший в mermaid.
function a2pdfFix(svg, source, series) {
  // sankey не принимает кириллицу: сервер подменил её метками lbl0q…,
  // словарь лежит в комментарии — возвращаем настоящие подписи
  const mark = /^%% a2pdf-labels (.*)$/m.exec(source || '');
  if (mark) {
    let names = {};
    try { names = JSON.parse(mark[1]); } catch (e) {}
    for (const text of svg.querySelectorAll('text, tspan')) {
      if (text.children.length) continue;
      text.textContent = text.textContent.replace(/lbl\d+q/g, m => names[m] || m);
    }
  }
  // иконки architecture залиты штатным синим mermaid — красим основным цветом
  if (series && series.length &&
      svg.getAttribute('aria-roledescription') === 'architecture') {
    // цвет иконки задан в style, а не атрибутом
    for (const el of svg.querySelectorAll('rect[style*="087ebf" i]')) {
      el.style.fill = series[0];
    }
  }
  // sankey красит узлы своей палитрой d3 — меняем её на цвета бренда,
  // вместе с градиентами связей, которые повторяют цвета узлов
  if (series && series.length &&
      svg.getAttribute('aria-roledescription') === 'sankey') {
    const swap = new Map();
    const pick = (c) => {
      if (!c || c === 'none') return c;
      if (!swap.has(c)) swap.set(c, series[swap.size % series.length]);
      return swap.get(c);
    };
    for (const rect of svg.querySelectorAll('.node rect, rect.node, g.nodes rect')) {
      rect.setAttribute('fill', pick(rect.getAttribute('fill')));
    }
    for (const stop of svg.querySelectorAll('stop')) {
      const c = stop.getAttribute('stop-color');
      if (swap.has(c)) stop.setAttribute('stop-color', swap.get(c));
    }
    for (const path of svg.querySelectorAll('path')) {
      const c = path.getAttribute('stroke');
      if (swap.has(c)) path.setAttribute('stroke', swap.get(c));
    }
  }
}
