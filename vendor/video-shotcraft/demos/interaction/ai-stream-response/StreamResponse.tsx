// Product Video adaptation: scoped copy, media and theme; upstream motion preserved.
import { PvElement } from "@pv/adaptation";
import React from 'react';
import { AbsoluteFill, Easing, Img, interpolate, useCurrentFrame, } from 'remotion';
import backplate from './agent-stream.jpg';
const ROW_CUES = [42, 53, 63, 72, 80, 87, 93];
const ROWS = [
    ['Indexed the workspace', '128 files'],
    ['Mapped the authentication flow', '12 modules'],
    ['Checked recent error traces', 'No blockers'],
    ['Matched API contracts to handlers', '24 routes'],
    ['Verified permission boundaries', '6 roles'],
    ['Cross-checked release notes', '3 changes'],
    ['Prepared an implementation plan', 'Ready'],
] as const;
const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
const ease = Easing.bezier(0.2, 0.75, 0.25, 1);
const CheckIcon: React.FC<{
    progress: number;
}> = ({ progress }) => {
    const ringOpacity = interpolate(progress, [0, 0.45, 0.75], [0.36, 1, 0], clamp);
    const checkOpacity = interpolate(progress, [0.62, 1], [0, 1], clamp);
    const checkScale = interpolate(progress, [0.62, 1], [0.72, 1], { ...clamp, easing: ease });
    return (<PvElement as={"div"} style={{ position: 'relative', width: 27, height: 27, flex: '0 0 auto' }}>
      <PvElement as={"div"} style={{
            position: 'absolute', inset: 2, borderRadius: 99,
            border: '2px solid rgba(183, 190, 199, .6)',
            borderTopColor: '#d4ff77', opacity: ringOpacity,
            transform: `rotate(${progress * 100}deg)`,
        }}/>
      <PvElement as={"div"} style={{
            position: 'absolute', inset: 1, borderRadius: 99,
            background: '#b8f36a', opacity: checkOpacity,
            transform: `scale(${checkScale})`,
            display: 'grid', placeItems: 'center',
            boxShadow: '0 0 16px rgba(184,243,106,.18)',
        }}>
        <PvElement as={"svg"} width="16" height="16" viewBox="0 0 16 16" fill="none">
          <PvElement as={"path"} d="M3.4 8.3 6.6 11l6-6" stroke="#15200d" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round"/>
        </PvElement>
      </PvElement>
    </PvElement>);
};
const EvidenceRow: React.FC<{
    cue: number;
    title: string;
    meta: string;
    index: number;
}> = ({ cue, title, meta, index }) => {
    const frame = useCurrentFrame();
    const body = interpolate(frame, [cue, cue + 12], [0, 1], { ...clamp, easing: ease });
    const status = interpolate(frame, [cue + 3, cue + 11], [0, 1], { ...clamp, easing: ease });
    return (<PvElement as={"div"} style={{
            position: 'absolute', left: 0, right: 0, top: index * 68,
            height: 58, borderRadius: 13,
            border: '1px solid rgba(255,255,255,.065)',
            background: 'rgba(255,255,255,.025)',
            display: 'flex', alignItems: 'center', padding: '0 20px', gap: 15,
            opacity: body,
            transform: `translateY(${18 * (1 - body)}px)`,
            filter: `blur(${6 * (1 - body)}px)`,
        }}>
      <CheckIcon progress={status}/>
      <PvElement as={"div"} style={{ fontSize: 21, color: '#e8eaed', letterSpacing: '-0.015em', flex: 1 }}>{title}</PvElement>
      <PvElement as={"div"} style={{ fontSize: 16, color: status > 0.78 ? '#a9c77f' : '#777f89', fontVariantNumeric: 'tabular-nums' }}>{meta}</PvElement>
    </PvElement>);
};
export const StreamResponse: React.FC = () => {
    const frame = useCurrentFrame();
    const panelIn = interpolate(frame, [0, 16], [0, 1], { ...clamp, easing: ease });
    const summary = interpolate(frame, [18, 30], [0, 1], { ...clamp, easing: ease });
    const camera = interpolate(frame, [0, 100], [1.04, 1], { ...clamp, easing: ease });
    const pulse = interpolate(frame, [110, 115, 120], [0.25, 0.55, 0.25], clamp);
    const complete = interpolate(frame, [110, 120], [0, 1], { ...clamp, easing: ease });
    return (<PvElement as={AbsoluteFill} style={{ background: '#07090a', fontFamily: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', overflow: 'hidden' }}>
      <PvElement as={AbsoluteFill} style={{ transform: `scale(${camera})` }}>
        <PvElement as={Img} src={backplate} style={{ width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(.58) saturate(.76) blur(1px)', opacity: .7 }}/>
        <PvElement as={AbsoluteFill} style={{ background: 'radial-gradient(circle at 50% 44%, rgba(6,9,10,.08) 10%, rgba(4,6,7,.72) 92%)' }}/>
      </PvElement>

      <PvElement as={"div"} style={{
            position: 'absolute', left: 344, top: 72, width: 1232, height: 936,
            borderRadius: 29, overflow: 'hidden',
            background: 'linear-gradient(145deg, rgba(25,29,32,.985), rgba(12,15,17,.99))',
            border: `1px solid rgba(184,243,106,${pulse})`,
            boxShadow: '0 46px 100px rgba(0,0,0,.58), inset 0 1px 0 rgba(255,255,255,.06)',
            opacity: panelIn,
            transform: `translateY(${12 * (1 - panelIn)}px) scale(${.985 + .015 * panelIn})`,
        }}>
        <PvElement as={"div"} style={{ height: 76, display: 'flex', alignItems: 'center', padding: '0 34px', borderBottom: '1px solid rgba(255,255,255,.065)' }}>
          <PvElement as={"div"} style={{ width: 29, height: 29, borderRadius: 9, background: '#e9edf0', color: '#15191b', display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: 17 }}>A</PvElement>
          <PvElement as={"div"} style={{ marginLeft: 13, fontSize: 22, fontWeight: 590, color: '#f1f3f4' }}>Ask Atlas</PvElement>
          <PvElement as={"div"} style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 9, color: '#7d858e', fontSize: 15 }}>
            <PvElement as={"span"} style={{ width: 7, height: 7, background: '#b8f36a', borderRadius: 99 }}/> Workspace agent
          </PvElement>
        </PvElement>

        <PvElement as={"div"} style={{ padding: '28px 38px 34px' }}>
          <PvElement as={"div"} style={{ height: 48, borderRadius: 12, background: 'rgba(255,255,255,.048)', display: 'flex', alignItems: 'center', padding: '0 18px', color: '#b9bec4', fontSize: 18 }}>
            Review this codebase and identify the safest implementation path
          </PvElement>

          <PvElement as={"div"} style={{ height: 119, marginTop: 21, borderBottom: '1px solid rgba(255,255,255,.07)', overflow: 'hidden', position: 'relative' }}>
            <PvElement as={"div"} style={{ position: 'absolute', inset: 0, opacity: summary, transform: `translateY(${10 * (1 - summary)}px)`, clipPath: `inset(0 ${100 * (1 - summary)}% 0 0)` }}>
              <PvElement as={"div"} style={{ color: '#838b94', fontSize: 15, textTransform: 'uppercase', letterSpacing: '.12em', marginBottom: 10 }}>Result summary</PvElement>
              <PvElement as={"div"} style={{ color: '#f3f4f5', fontSize: 26, fontWeight: 510, lineHeight: 1.35, letterSpacing: '-.022em' }}>
                The codebase is ready for a focused, low-risk implementation.
              </PvElement>
            </PvElement>
          </PvElement>

          <PvElement as={"div"} style={{ position: 'relative', height: 466, marginTop: 17 }}>
            {ROWS.map(([title, meta], index) => <EvidenceRow key={title} cue={ROW_CUES[index]} title={title} meta={meta} index={index}/>)}
          </PvElement>

          <PvElement as={"div"} style={{ height: 60, marginTop: 2, borderTop: '1px solid rgba(255,255,255,.07)', display: 'flex', alignItems: 'flex-end' }}>
            <PvElement as={"div"} style={{ display: 'flex', alignItems: 'center', gap: 11, opacity: complete, transform: `translateY(${5 * (1 - complete)}px)` }}>
              <PvElement as={"div"} style={{ width: 24, height: 24, borderRadius: 99, background: '#b8f36a', display: 'grid', placeItems: 'center' }}>
                <PvElement as={"svg"} width="14" height="14" viewBox="0 0 16 16" fill="none"><PvElement as={"path"} d="M3.4 8.3 6.6 11l6-6" stroke="#15200d" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></PvElement>
              </PvElement>
              <PvElement as={"span"} style={{ color: '#dce7d0', fontSize: 17, fontWeight: 560 }}>Analysis complete</PvElement>
              <PvElement as={"span"} style={{ color: '#69717a', fontSize: 15 }}>7 checks finished · ready to build</PvElement>
            </PvElement>
          </PvElement>
        </PvElement>
      </PvElement>
    </PvElement>);
};
