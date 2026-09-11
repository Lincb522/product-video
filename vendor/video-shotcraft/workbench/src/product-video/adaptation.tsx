import React, { createContext, useContext } from 'react';
import { Sequence, staticFile, useVideoConfig } from 'remotion';

type Replacements = Record<string, string>;
type Adaptation = { text: Replacements; colors: Replacements; media: Replacements; frames: number; font: string };
const Context = createContext<Adaptation>({ text: {}, colors: {}, media: {}, frames: 150, font: '' });

export function useMotionCopy() {
  const { text } = React.use(Context);
  return <T,>(value: T): T => (typeof value === 'string' ? replaceText(value, text) : value) as T;
}

export function parseMap(value: unknown, name: string): Replacements {
  const map = typeof value === 'string' ? JSON.parse(value || '{}') : value ?? {};
  if (!map || Array.isArray(map) || typeof map !== 'object' || Object.values(map).some(v => typeof v !== 'string'))
    throw new Error(`${name} must be an object containing string values`);
  return map as Replacements;
}

export function replaceText(value: string, map: Replacements): string {
  if (Object.prototype.hasOwnProperty.call(map, value)) return map[value];
  const trimmed = value.trim();
  return Object.prototype.hasOwnProperty.call(map, trimmed) ? value.replace(trimmed, map[trimmed]) : value;
}

const replaceMedia = (value: string, map: Replacements) => {
  let result = value;
  for (const [source, target] of Object.entries(map)) {
    const resolved = staticFile(source);
    result = result.split(resolved).join(staticFile(target));
    if (result === source) result = staticFile(target);
  }
  return result;
};

// JSX adaptation changes content and presentation values while retaining each
// upstream component's frame math, geometry, easing and action choreography.
export function PvElement({ as: Tag, children, ...props }: Record<string, any>) {
  const settings = useContext(Context);
  const mapped = { ...props };
  if (typeof mapped.src === 'string') mapped.src = replaceMedia(mapped.src, settings.media);
  if (mapped.style) {
    mapped.style = Object.fromEntries(Object.entries(mapped.style).map(([key, value]) => {
      if (typeof value !== 'string') return [key, value];
      let changed = replaceMedia(value, settings.media);
      for (const [from, to] of Object.entries(settings.colors)) if (from) changed = changed.split(from).join(to);
      if (key === 'fontFamily' && settings.font) changed = settings.font;
      return [key, changed];
    }));
  }
  for (const key of ['fill', 'stroke', 'color']) {
    if (typeof mapped[key] === 'string') mapped[key] = settings.colors[mapped[key]] ?? mapped[key];
  }
  const content = React.Children.map(children, child => typeof child === 'string' ? replaceText(child, settings.text) : child);
  return React.createElement(Tag, mapped, content);
}

export function useShotcraftVideoConfig() {
  const config = useVideoConfig();
  const settings = useContext(Context);
  return { ...config, fps: 30, width: 1920, height: 1080, durationInFrames: settings.frames };
}

export function adaptMotion(Component: React.ComponentType, frames: number): React.ComponentType<Record<string, unknown>> {
  return function ProductMotion(props) {
    const value = {
      text: parseMap(props.textMap, 'Text replacements'),
      colors: parseMap(props.colorMap, 'Colour replacements'),
      media: parseMap(props.mediaMap, 'Media replacements'),
      frames,
      font: typeof props.fontFamily === 'string' ? props.fontFamily : '',
    };
    return <Context.Provider value={value}><Sequence durationInFrames={frames} layout="none"><Component /></Sequence></Context.Provider>;
  };
}
