/**
 * Squarified treemap — Bruls/Huijsen/van Wijk algorithm.
 *
 * Given a rectangle and a list of positive weights, produces a layout where
 * each cell's area is proportional to its weight and the aspect ratios are
 * close to 1. Weights must be sorted descending before calling.
 */

export interface TreemapInput {
  key: string;
  /** Positive weight (e.g. portfolio market value). */
  value: number;
}

export interface TreemapCell {
  key: string;
  value: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

const aspectScore = (sumValue: number, max: number, min: number, side: number) => {
  const w2 = side * side;
  const s2 = sumValue * sumValue;
  return Math.max((w2 * max) / s2, s2 / (w2 * min));
};

export function squarify(
  items: TreemapInput[],
  width: number,
  height: number,
): TreemapCell[] {
  const total = items.reduce((sum, it) => sum + it.value, 0);
  if (total <= 0 || width <= 0 || height <= 0 || items.length === 0) return [];

  // Scale weights so their sum equals the rectangle area.
  const scale = (width * height) / total;
  const scaled = items.map((it) => ({ ...it, area: it.value * scale }));

  const cells: TreemapCell[] = [];

  function layoutRow(row: typeof scaled, rect: Rect, side: number): Rect {
    const sum = row.reduce((s, it) => s + it.area, 0);
    if (sum === 0) return rect;
    const isHorizontal = side === rect.height;
    const rowThickness = sum / side;
    let offset = isHorizontal ? rect.y : rect.x;
    for (const item of row) {
      const length = item.area / rowThickness;
      cells.push({
        key: item.key,
        value: item.value,
        x: isHorizontal ? rect.x : offset,
        y: isHorizontal ? offset : rect.y,
        width: isHorizontal ? rowThickness : length,
        height: isHorizontal ? length : rowThickness,
      });
      offset += length;
    }
    return isHorizontal
      ? {
          x: rect.x + rowThickness,
          y: rect.y,
          width: rect.width - rowThickness,
          height: rect.height,
        }
      : {
          x: rect.x,
          y: rect.y + rowThickness,
          width: rect.width,
          height: rect.height - rowThickness,
        };
  }

  function place(remaining: typeof scaled, rect: Rect): void {
    if (remaining.length === 0 || rect.width <= 0 || rect.height <= 0) return;
    const side = Math.min(rect.width, rect.height);

    const row: typeof scaled = [];
    let i = 0;
    while (i < remaining.length) {
      const candidate = [...row, remaining[i]!];
      const sum = candidate.reduce((s, it) => s + it.area, 0);
      const max = Math.max(...candidate.map((it) => it.area));
      const min = Math.min(...candidate.map((it) => it.area));
      const newScore = aspectScore(sum, max, min, side);

      if (row.length === 0) {
        row.push(remaining[i]!);
        i += 1;
        continue;
      }

      const prevSum = row.reduce((s, it) => s + it.area, 0);
      const prevMax = Math.max(...row.map((it) => it.area));
      const prevMin = Math.min(...row.map((it) => it.area));
      const prevScore = aspectScore(prevSum, prevMax, prevMin, side);

      if (newScore <= prevScore) {
        row.push(remaining[i]!);
        i += 1;
      } else {
        break;
      }
    }

    const newRect = layoutRow(row, rect, side);
    place(remaining.slice(i), newRect);
  }

  place(scaled, { x: 0, y: 0, width, height });
  return cells;
}
