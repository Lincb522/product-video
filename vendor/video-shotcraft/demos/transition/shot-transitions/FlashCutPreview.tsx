// Product Video wrapper for the upstream FlashCut component and gallery variant.
import React from 'react';
import { AbsoluteFill, Sequence, useCurrentFrame } from 'remotion';
import { FlashCut } from '@shotcraft-lib/FlashCut';
export const FLASH_CUT_PREVIEW_DURATION = 90;
export const FlashCutPreview: React.FC = () => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{ background: frame < 45 ? '#172c27' : '#f2eee6', justifyContent: 'center', alignItems: 'center' }}>
    <div style={{ width: 980, height: 560, borderRadius: 24, background: frame < 45 ? '#e5bc75' : '#29483e', transform: `scale(${1 + Math.min(frame, 44) / 500})`, boxShadow: '0 30px 80px #0005' }} />
    <Sequence from={41} durationInFrames={10}><FlashCut duration={10} /></Sequence>
  </AbsoluteFill>;
};
