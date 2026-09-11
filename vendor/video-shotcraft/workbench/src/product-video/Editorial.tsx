// Product Video content layouts, using adapted Shotcraft motion primitives.
import React from 'react';
import {AbsoluteFill, Freeze, Img, staticFile, useVideoConfig} from 'remotion';
import type {CardDef} from '../cards/types';
import {MotionPicture, FeatureOverview, CardFan, ThemeWipe, type Screen} from './EditorialMotion';

type Props={items?:Screen[];layout?:string;motion?:string;headline?:string;eyebrow?:string;notes?:string[];
  productName?:string;section?:string;logo?:string;duration?:number;focus_at?:number[];slices?:number[];
  background?:string;surface?:string;foreground?:string;accent?:string;reducedMotion?:boolean};
const Scene:React.FC<Props>=(p)=>{
  const {fps}=useVideoConfig(),duration=(p.duration??180)*30/fps,items=p.items??[],layout=p.layout??'full';
  const side=layout==='side'||layout==='fan',box:[number,number,number,number]=side?[600,200,1235,650]:[80,250,1760,650];
  return <AbsoluteFill style={{background:p.background??'#171515',color:p.foreground??'#f2e9df',fontFamily:'ProductVideoFont, sans-serif',overflow:'hidden',
    '--pv-accent':p.accent??'#e7a878','--pv-surface':p.surface??'#282220'} as React.CSSProperties}>
    <div style={{position:'absolute',left:88,right:88,top:32,display:'flex',alignItems:'center',gap:14,fontSize:22}}>
      {p.logo&&<Img src={staticFile(p.logo)} style={{width:28,height:28,objectFit:'contain'}}/>}<span style={{fontWeight:650}}>{p.productName}</span><span style={{opacity:.65}}>{p.section}</span>{!side&&p.eyebrow&&<span style={{marginLeft:'auto',color:'var(--pv-accent)'}}>{p.eyebrow}</span>}
    </div>
    <div style={{position:'absolute',left:88,top:side?185:90,width:side?455:1744,zIndex:3}}>
      {side&&p.eyebrow&&<div style={{fontSize:22,marginBottom:22,color:'var(--pv-accent)'}}>{p.eyebrow}</div>}
      <div style={{fontSize:side?54:50,fontWeight:650,lineHeight:1.22,whiteSpace:'pre-line',overflowWrap:'anywhere'}}>{p.headline}</div>
      <div style={{marginTop:22,display:side?'block':'flex',gap:32,flexWrap:'wrap',fontSize:side?25:23,lineHeight:1.4,opacity:.72}}>{p.notes?.map((note,i)=><div key={i} style={{marginBottom:side?18:0,flexShrink:0}}>{note}</div>)}</div>
    </div>
    {!items.length?<div style={{position:'absolute',left:88,top:400,opacity:.65,fontSize:30}}>为内容镜头绑定产品截图</div>:
      layout==='overview'||layout==='portal'?<FeatureOverview tiles={items} focusAt={p.focus_at} duration={duration} portal={layout==='portal'}/>:
      layout==='fan'?<CardFan tiles={items}/>:
      layout==='pair'&&p.motion==='comparison-wipe'?<ThemeWipe first={items[0]} second={items[1]} box={box} duration={duration}/>:
      layout==='pair'?<>{items.map((image,i)=><React.Fragment key={i}><MotionPicture image={image} box={[80+i*890,255,870,605]} motion={p.motion} duration={duration}/><div style={{position:'absolute',left:80+i*890,top:883,width:870,textAlign:'center',fontSize:24,opacity:.7}}>{image.label}</div></React.Fragment>)}</>:
      <MotionPicture image={p.motion==='card-flip'?items[1]:items[0]} before={items[0]} box={box} motion={p.motion} duration={duration} tiles={items} slices={p.slices}/>}
    <div style={{position:'absolute',bottom:115,left:88,right:88,height:1,background:'currentColor',opacity:.15}}/>
  </AbsoluteFill>;
};
const Editorial:React.FC<Record<string,unknown>>=(raw)=>{
  const p=raw as Props,{fps}=useVideoConfig();
  return p.reducedMotion?<Freeze frame={Math.max(p.duration??180,6*fps)}><Scene {...p}/></Freeze>:<Scene {...p}/>;
};
export const editorialCard:CardDef={id:'pv-editorial',name:'内容镜头',category:'产品编排',component:Editorial,durationInFrames:180,durationProp:'duration',timing:'realtime',schema:[
  {type:'text',key:'headline',label:'标题',default:''},
  {type:'text',key:'eyebrow',label:'短标签',default:''},
  {type:'color',key:'background',label:'背景',default:'#171515'},
  {type:'color',key:'surface',label:'面板',default:'#282220'},
  {type:'color',key:'foreground',label:'正文',default:'#f2e9df'},
  {type:'color',key:'accent',label:'强调色',default:'#e7a878'},
]};
