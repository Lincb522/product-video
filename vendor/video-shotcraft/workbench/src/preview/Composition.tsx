// Product Video integration: modified from video-shotcraft 5e71af3; see MODIFICATIONS.md.
import React from "react";
import { AbsoluteFill, Freeze, Sequence, useCurrentFrame } from "remotion";
import type { ClipData, ProjectData } from "../types";
import { CARDS } from "../cards/registry";
import { defaultsOf } from "../cards/types";
import { Transition } from '../product-video/Transition';
import { ProductFont } from '../product-video/Font';

/** 时间重映射：clip 本地帧 → 卡片源帧（inOffset + f × speed）。
 *  卡片全部是 frame 的纯函数（tween 均 clamp），因此变速/裁入/超时长定格都安全。
 *  不变速且不裁入时直通不包 Freeze——含 Audio/Video 的卡需要原生播放（Freeze 会掐掉声音）。 */
const TimeRemap: React.FC<{
  inOffset: number;
  speed: number;
  lastFrame: number;
  children: React.ReactNode;
}> = ({ inOffset, speed, lastFrame, children }) => {
  const frame = useCurrentFrame();
  if (speed === 1 && inOffset === 0 && frame <= lastFrame) return <>{children}</>;
  return <Freeze frame={Math.min(lastFrame, Math.max(0, inOffset + frame * speed))}>{children}</Freeze>;
};

const VisualClip: React.FC<{ clip: ClipData; project: ProjectData; previous?: ClipData; transition?: boolean }> = ({ clip, project, previous, transition = true }) => {
  const frame = useCurrentFrame();
  const card = CARDS[clip.cardId];
  if (!card) throw new Error(`镜头不存在：${clip.cardId}。请重新选择镜头后导出。`);
  const Comp = card.component;
  const props: Record<string, unknown> = { ...defaultsOf(card), ...clip.props };
  if (card.durationProp) props[card.durationProp] = Math.max(1, Math.round(clip.inOffset + clip.duration * clip.speed));
  const width = card.width ?? 1920, height = card.height ?? 1080;
  const scale = Math.min(project.width / width, project.height / height);
  const content = <AbsoluteFill style={{ opacity: clip.opacity, width, height, transformOrigin: '0 0',
    transform: `translate(${clip.x + (project.width-width*scale)/2}px, ${clip.y + (project.height-height*scale)/2}px) scale(${clip.scale*scale})` }}>
    {card.kind === 'video' ? <Comp {...props} inOffset={clip.inOffset} speed={clip.speed} /> :
      <TimeRemap inOffset={clip.inOffset} speed={clip.speed} lastFrame={card.durationProp ? Math.max(card.durationInFrames-1, Number(props[card.durationProp])-1) : card.durationInFrames-1}><Comp {...props} /></TimeRemap>}
  </AbsoluteFill>;
  const spec = clip.transition;
  if (!transition || !previous || !spec || spec.kind === 'cut' || spec.duration <= 0 || frame >= spec.duration) return content;
  return <Transition kind={spec.kind} progress={frame / Math.max(1, spec.duration-1)} width={project.width} height={project.height}
    before={<Freeze frame={previous.duration-1}><VisualClip clip={previous} project={project} transition={false} /></Freeze>}>{content}</Transition>;
};

export const MainComposition: React.FC<{ project: ProjectData }> = ({ project }) => (
  <AbsoluteFill style={{ background: project.background ?? '#0e0e10' }}>
    {project.fontFile && <ProductFont file={project.fontFile} />}
    {[...project.tracks].reverse().map(track => !track.hidden && track.clips.map(clip => {
      const card = CARDS[clip.cardId];
      if (!card) throw new Error(`镜头不存在：${clip.cardId}。请重新选择镜头后导出。`);
      const Comp = card.component;
      const previous = track.clips.find(other => other.id !== clip.id && other.start + other.duration === clip.start);
      return <Sequence key={clip.id} from={clip.start} durationInFrames={Math.max(1, Math.round(clip.duration))}>
        {card.kind === 'audio' ? <Comp {...defaultsOf(card)} {...clip.props} inOffset={clip.inOffset} speed={clip.speed} /> :
          <VisualClip clip={clip} project={project} previous={previous} />}
      </Sequence>;
    }))}
  </AbsoluteFill>
);
