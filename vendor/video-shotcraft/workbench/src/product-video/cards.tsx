import React from 'react';
import { AbsoluteFill, Audio, staticFile } from 'remotion';
import {editorialCard} from './Editorial';
import type { CardDef } from '../cards/types';

const Caption: React.FC<Record<string, unknown>> = ({ text = '', color = '#ffffff', background = '#15191d', fontFamily = 'sans-serif', fontSize = 36 }) => (
  <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', padding: '0 96px 42px', pointerEvents: 'none' }}>
    <div style={{ maxWidth: 1660, padding: '10px 24px', borderRadius: 12, textAlign: 'center', whiteSpace: 'pre-wrap', fontSize: Number(fontSize), lineHeight: 1.35, color: String(color), background: String(background), fontFamily: String(fontFamily) }}>{String(text)}</div>
  </AbsoluteFill>
);

const Narration: React.FC<Record<string, unknown>> = ({ file = '', volume = 1, inOffset = 0, speed = 1 }) => file ? (
  <Audio src={staticFile(String(file))} volume={Number(volume)} trimBefore={Math.round(Number(inOffset))} playbackRate={Number(speed)} />
) : null;

export const PRODUCT_CARDS: CardDef[] = [
  editorialCard,
  { id: 'pv-caption', name: '旁白字幕', category: '字幕', durationInFrames: 90, component: Caption, schema: [
    { type: 'textarea', key: 'text', label: '字幕', default: '' },
    { type: 'color', key: 'color', label: '文字颜色', default: '#ffffff' },
    { type: 'color', key: 'background', label: '字幕底色', default: '#15191d' },
    { type: 'number', key: 'fontSize', label: '字号', default: 36, min: 20, max: 80 },
    { type: 'text', key: 'fontFamily', label: '字体', default: 'sans-serif' },
  ] },
  { id: 'pv-narration', name: '语音旁白', category: '音频', kind: 'audio', timing: 'realtime', durationInFrames: 150, component: Narration, schema: [
    { type: 'text', key: 'file', label: '音频文件', default: '' },
    { type: 'slider', key: 'volume', label: '音量', default: 1, min: 0, max: 2, step: .01 },
  ] },
];
