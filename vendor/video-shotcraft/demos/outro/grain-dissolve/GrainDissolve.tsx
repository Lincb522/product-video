// Product Video adaptation: scoped copy, media and theme; upstream motion preserved.
import { PvElement } from "@pv/adaptation";
// grain-dissolve — Grain Dissolve → Condense 文字砂化凝聚（motion-lab 定稿转原生 Remotion）
// 干净的整行字 "{ ACME. Now Live }" 先爆裂成沸腾颗粒噪点（轮廓隐约可辨、白色辉光），
// 同时出现带 45° 斜纹填充和像素方块角柄的选区框；噪点沸腾约半程后选区框消失，
// 噪点云急速凝聚成更大号的颗粒短字标（占位词 "ACME"），位移量衰减归零、辉光冲高回落，
// 凝固为清晰发光短字标。四角 HUD 括角/圆点与左右中线短划全程常驻。
// 滤镜链：feTurbulence seed 逐帧 + displacement scale 双向动画，终字同走滤镜再解除。
// 设计坐标 480×270（DesignStage 等比放大），SVG viewBox 640×360 铺满全幅。
import React, { useId } from 'react';
import { E, DesignStage, seg, useT } from '../../_fixtures/Motion';
export const GRAIN_DISSOLVE_DURATION = 60; // 2000ms @30fps
// 选区框几何（viewBox 坐标）
const BX = 128;
const BY = 148;
const BW = 384;
const BH = 62;
// 45° 斜纹：x 从 bx-bh 起每 34 一根，右下→左上
const HATCH_XS: number[] = [];
for (let x = BX - BH; x < BX + BW; x += 34)
    HATCH_XS.push(x);
// 四角像素棋盘手柄（两块 5×5 错位方块）
const Handle: React.FC<{
    x: number;
    y: number;
}> = ({ x, y }) => (<PvElement as={"g"} transform={`translate(${x - 5},${y - 5})`} fill="#cfd2d8">
    <PvElement as={"rect"} width={5} height={5}/>
    <PvElement as={"rect"} x={5} y={5} width={5} height={5}/>
  </PvElement>);
// HUD 括角 + 圆点（sx/sy 控制朝向）
const Corner: React.FC<{
    x: number;
    y: number;
    sx: number;
    sy: number;
}> = ({ x, y, sx, sy }) => (<>
    <PvElement as={"path"} d={`M${x + 14 * sx} ${y}H${x}V${y + 14 * sy}`} fill="none" stroke="#3a3a40" strokeWidth={1.5}/>
    <PvElement as={"circle"} cx={x + 34 * sx} cy={y + 28 * sy} r={1.6} fill="#8b8d94"/>
  </>);
export const GrainDissolve: React.FC = () => {
    const t = useT();
    // 滤镜/clipPath ID 按实例生成，同一 Composition 放多个实例时互不串引
    // （useId 的 «:» 在 CSS url() 里非法，清洗成纯字母数字）
    const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
    const fid = `gd-${uid}`;
    const cid = `gd-${uid}-clip`;
    const burst = seg(t, 0.13, 0.28, E.outCubic); // 干净字 → 砂化
    const cond = seg(t, 0.60, 0.71, E.inOutCubic); // 整行噪点云 → 短字标噪点云
    const lock = seg(t, 0.68, 0.90, E.outCubic); // 位移衰减凝固
    const settle = seg(t, 0.88, 1, E.outCubic); // 辉光回落
    // 白色辉光：砂化期轻微，凝聚时冲高，凝固后回落到柔光
    const glow = burst * 0.3 + cond * 0.7 - settle * 0.45;
    return (<DesignStage bg="#0a0a0c">
      <PvElement as={"svg"} viewBox="0 0 640 360" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', background: '#0a0a0c' }}>
        <PvElement as={"defs"}>
          <PvElement as={"filter"} id={fid} x="-40%" y="-150%" width="180%" height="400%">
            <PvElement as={"feTurbulence"} type="fractalNoise" baseFrequency={0.9 + burst * 0.4} numOctaves={2} seed={Math.floor(t * 46)} result="n"/>
            <PvElement as={"feDisplacementMap"} in="SourceGraphic" in2="n" scale={burst * 52 * (1 - lock)} xChannelSelector="R" yChannelSelector="G" result="d"/>
            <PvElement as={"feGaussianBlur"} in="d" stdDeviation={burst * 1.1 * (1 - lock)}/>
          </PvElement>
        </PvElement>
        {/* 四角 HUD 括角 + 圆点 + 左右中线短划（全程常驻） */}
        <PvElement as={"g"}>
          <Corner x={88} y={96} sx={1} sy={1}/>
          <Corner x={552} y={96} sx={-1} sy={1}/>
          <Corner x={88} y={264} sx={1} sy={-1}/>
          <Corner x={552} y={264} sx={-1} sy={-1}/>
          <PvElement as={"line"} x1={52} y1={180} x2={76} y2={180} stroke="#4a4a50" strokeWidth={1.5} strokeDasharray="4 3"/>
          <PvElement as={"line"} x1={564} y1={180} x2={588} y2={180} stroke="#4a4a50" strokeWidth={1.5} strokeDasharray="4 3"/>
        </PvElement>
        {/* 选区框：砂化时浮现，凝聚前撤掉 */}
        <PvElement as={"g"} opacity={burst * (1 - seg(t, 0.55, 0.64))}>
          <PvElement as={"clipPath"} id={cid}>
            <PvElement as={"rect"} x={BX} y={BY} width={BW} height={BH}/>
          </PvElement>
          <PvElement as={"g"} clipPath={`url(#${cid})`}>
            {HATCH_XS.map((x) => (<PvElement as={"line"} key={x} x1={x} y1={BY + BH} x2={x + BH} y2={BY} stroke="#2c2c31" strokeWidth={1}/>))}
          </PvElement>
          <PvElement as={"rect"} x={BX} y={BY} width={BW} height={BH} fill="none" stroke="#55565c" strokeWidth={1}/>
          <Handle x={BX} y={BY}/>
          <Handle x={BX + BW} y={BY}/>
          <Handle x={BX} y={BY + BH}/>
          <Handle x={BX + BW} y={BY + BH}/>
        </PvElement>
        {/* 文字组：整行字与终字标同走滤镜链 + 白色辉光 */}
        <PvElement as={"g"} style={{
            filter: `url(#${fid}) drop-shadow(0 0 ${4 + glow * 20}px rgba(255,255,255,${Math.max(0, glow) * 0.9}))`,
        }}>
          <PvElement as={"text"} x={320} y={191} textAnchor="middle" opacity={1 - cond} style={{
            fill: '#eceef2',
            font: "500 33px Inter,'Helvetica Neue',system-ui,sans-serif",
            letterSpacing: '2.5px',
        }}>
            {'{ ACME. Now Live }'}
          </PvElement>
          <PvElement as={"text"} x={320} y={198} textAnchor="middle" opacity={cond} style={{
            fill: '#fff',
            font: "800 54px Inter,'Helvetica Neue',system-ui,sans-serif",
            letterSpacing: '4px',
        }}>
            ACME
          </PvElement>
        </PvElement>
      </PvElement>
    </DesignStage>);
};
