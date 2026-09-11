import type { CSSProperties, ReactNode } from 'react';
import { AbsoluteFill } from 'remotion';

export const TRANSITIONS = ['cut', 'fade', 'slide-left', 'slide-right', 'slide-up', 'wipe-left', 'wipe-right', 'zoom', 'blur', 'focus-dissolve', 'depth-slide', 'mask-up', 'iris', 'split-reveal', 'glass-sweep'] as const;
export type TransitionKind = typeof TRANSITIONS[number];

export function transitionStyles(kind: TransitionKind, progress: number, width: number, height: number): [CSSProperties, CSSProperties] {
  const t = Math.min(1, Math.max(0, progress));
  const p = t ** 3 * (10 + t * (-15 + 6 * t));
  const outgoing: CSSProperties = {}, incoming: CSSProperties = {};
  if (kind === 'cut' || p === 1) return [{ opacity: 0 }, {}];
  if (p === 0) return [{}, { opacity: 0 }];
  const fade = () => { incoming.opacity = p; };
  if (kind === 'fade') fade();
  else if (kind === 'slide-up') {
    outgoing.transform = `translateY(${-height * p}px)`;
    incoming.transform = `translateY(${height * (1-p)}px)`;
  } else if (kind.startsWith('slide-')) {
    const sign = kind === 'slide-left' ? -1 : 1;
    outgoing.transform = `translateX(${sign * width * p}px)`;
    incoming.transform = `translateX(${sign * width * (p-1)}px)`;
  } else if (kind === 'wipe-left' || kind === 'wipe-right' || kind === 'mask-up' || kind === 'glass-sweep') {
    const direction = kind === 'wipe-left' ? 'to left' : kind === 'mask-up' ? 'to top' : 'to right';
    incoming.maskImage = `linear-gradient(${direction}, black ${p*105-5}%, transparent ${p*105}%)`;
    if (kind === 'mask-up') incoming.transform = `translateY(${height*.055*(1-p)}px)`;
  } else if (kind === 'iris') {
    incoming.clipPath = `inset(${(1-p)*50}% round ${width*.04*(1-p)}px)`;
    incoming.transform = `scale(${1+.025*(1-p)})`;
  } else if (kind === 'split-reveal') {
    outgoing.opacity = 0;
    incoming.transform = `scale(${1+.025*(1-p)})`;
  } else if (kind === 'zoom') {
    outgoing.transform = `scale(${1+.055*p})`;
    incoming.transform = `scale(${.945+.055*p})`; fade();
  } else if (kind === 'blur') {
    outgoing.filter = incoming.filter = `blur(${Math.sin(Math.PI*p)*width/180}px)`; fade();
  } else if (kind === 'focus-dissolve') {
    outgoing.transform = `scale(${1-.018*p})`;
    outgoing.filter = `blur(${width*.006*p**1.5}px)`;
    incoming.transform = `scale(${1+.038*(1-p)})`;
    incoming.filter = `blur(${width*.005*(1-p)**1.5}px)`; fade();
  } else if (kind === 'depth-slide') {
    outgoing.transform = `translateX(${-width*.045*p}px) scale(${1-.07*p})`;
    outgoing.filter = `blur(${width*.002*p}px)`;
    incoming.transform = `translate(${width*.12*(1-p)}px, ${height*.018*(1-p)}px) scale(${1+.04*(1-p)})`; fade();
  } else throw new Error(`Unsupported transition: ${kind}`);
  return [outgoing, incoming];
}

export function Transition({ kind, progress, width, height, before, children }: { kind: TransitionKind; progress: number; width: number; height: number; before: ReactNode; children: ReactNode }) {
  const [outgoing, incoming] = transitionStyles(kind, progress, width, height);
  const t = Math.min(1, Math.max(0, progress));
  const p = t ** 3 * (10+t*(-15+6*t));
  return <AbsoluteFill style={{ overflow: 'hidden' }}>
    <AbsoluteFill style={outgoing}>{before}</AbsoluteFill>
    <AbsoluteFill style={incoming}>{children}</AbsoluteFill>
    {kind === 'split-reveal' && p < 1 && <>
      <AbsoluteFill style={{ clipPath: 'inset(0 50% 0 0)', transform: `translateX(${-width*.5*p}px)` }}>{before}</AbsoluteFill>
      <AbsoluteFill style={{ clipPath: 'inset(0 0 0 50%)', transform: `translateX(${width*.5*p}px)` }}>{before}</AbsoluteFill>
    </>}
    {kind === 'glass-sweep' && p > 0 && p < 1 && <AbsoluteFill style={{ background: `linear-gradient(to right, transparent ${p*100-4}%, rgba(255,255,255,${.16*Math.sin(Math.PI*p)}) ${p*100}%, transparent ${p*100+4}%)` }} />}
  </AbsoluteFill>;
}
