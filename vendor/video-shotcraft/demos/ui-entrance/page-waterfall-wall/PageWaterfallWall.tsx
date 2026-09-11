// Product Video adaptation: scoped copy, media and theme; upstream motion preserved.
import { PvElement, useShotcraftVideoConfig as useVideoConfig } from "@pv/adaptation";
import React from 'react';
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from 'remotion';
import { VerticalTicker, TickerColumn } from './VerticalTicker';
const BG = '#101014';
const shot = (file: string) => (<PvElement as={"div"} style={{
        borderRadius: 16,
        overflow: 'hidden',
        boxShadow: '0 12px 40px rgba(0,0,0,0.45)',
        background: '#fff',
    }}>
    <PvElement as={Img} src={staticFile(`textures/live/${file}`)} style={{ width: '100%', display: 'block' }}/>
  </PvElement>);
// 3 列差速反向（配方卡参数：loop 12/9/14s，中列反向）
export const buildColumns = (loops: [
    number,
    number,
    number
]): TickerColumn[] => [
    {
        items: ['card1.png', 'card2.png', 'card3.png', 'card10.png'].map(shot),
        durationInSeconds: loops[0],
        direction: -1,
    },
    {
        items: ['card4.png', 'card5.png', 'card6.png', 'projects-empty.png'].map(shot),
        durationInSeconds: loops[1],
        direction: 1,
    },
    {
        items: ['card7.png', 'card8.png', 'card9.png', 'float-search.png'].map(shot),
        durationInSeconds: loops[2],
        direction: -1,
    },
];
export const PageWaterfallWall: React.FC = () => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();
    // 镜头缓推寄生在外层，墙自身循环、镜头单向
    const push = interpolate(frame, [0, durationInFrames], [1, 1.06]);
    return (<PvElement as={AbsoluteFill} style={{ backgroundColor: BG }}>
      <PvElement as={AbsoluteFill} style={{ transform: `scale(${push})` }}>
        <VerticalTicker columns={buildColumns([12, 9, 14])} backgroundColor={BG} columnWidth={560} gap={30}/>
      </PvElement>
    </PvElement>);
};
// 接缝自检用：短 loop（3s=90f）、无镜头推，f0 与 f90 应逐像素一致
export const SeamTest: React.FC = () => (<PvElement as={AbsoluteFill} style={{ backgroundColor: BG }}>
    <VerticalTicker columns={buildColumns([3, 3, 3])} backgroundColor={BG} columnWidth={560} gap={30}/>
  </PvElement>);
