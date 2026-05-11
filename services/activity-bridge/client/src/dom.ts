export function mustGet<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing element ${selector}`);
  return element;
}

export function setText(selector: string, text: string) {
  mustGet<HTMLElement>(selector).textContent = text;
}
