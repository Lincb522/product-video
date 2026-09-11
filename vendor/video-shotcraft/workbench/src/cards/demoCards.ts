// Product Video integration: modified from video-shotcraft 5e71af3; see MODIFICATIONS.md.
import type { CardDef } from "./types";
import { DEMO_MODULES } from "./demo-index";
import { DEMO_CATEGORIES, DEMO_META } from "./demoMeta";
import { adaptMotion } from '../product-video/adaptation';

/** All upstream motions retain their choreography and expose scoped content overrides. */
export const DEMO_CARDS: CardDef[] = DEMO_MODULES.map((m) => {
  const meta = DEMO_META[m.stem];
  return {
    id: `demo:${m.stem}`,
    name: meta?.name ?? m.stem,
    category: meta?.category ?? "动效库",
    durationInFrames: Math.max(2, Math.round(m.duration)),
    component: adaptMotion(m.component, Math.max(2, Math.round(m.duration))),
    schema: [
      { type: 'mapping', key: 'textMap', label: '画面文案', default: {}, kind: 'text', suggestions: meta?.content?.text },
      { type: 'mapping', key: 'mediaMap', label: '画面素材', default: {}, kind: 'media', suggestions: meta?.content?.media },
      { type: 'mapping', key: 'colorMap', label: '画面配色', default: {}, kind: 'color', suggestions: meta?.content?.colors },
      { type: 'text', key: 'fontFamily', label: '产品字体', default: '' },
    ],
    accent: "#c58a2a",
    preview: meta?.preview ? `cardpreviews/${meta.preview}` : undefined,
    summary: meta?.summary,
  };
});

export { DEMO_CATEGORIES };
