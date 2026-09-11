// Product Video adaptation of Shotcraft motion primitives; see MODIFICATIONS.md.
import React from 'react';
import {Img, staticFile, useCurrentFrame, useVideoConfig, Easing, interpolate} from 'remotion';
import {E, seg} from '../../demosrc/_fixtures/Motion';

export type Screen = {file: string; width: number; height: number; label?: string};
const useFrame30 = () => { const f=useCurrentFrame(); return f*30/useVideoConfig().fps; };
type Box = [number, number, number, number];
const clamp = {extrapolateLeft:'clamp' as const, extrapolateRight:'clamp' as const};
const tween = (f:number,a:number,b:number,ease=E.outCubic) => interpolate(f,[a,b],[0,1],{...clamp,easing:ease});
const mix = (a:number,b:number,t:number) => a+(b-a)*t;
const shadow = '0 22px 48px #0005, 0 0 0 1px #ffffff18';
function fit(image:Screen,box:Box):Box {
  const r=Math.min(box[2]/image.width,box[3]/image.height),w=image.width*r,h=image.height*r;
  return [box[0]+(box[2]-w)/2,box[1]+(box[3]-h)/2,w,h];
}
const Photo = ({image,style={}}:{image:Screen;style?:React.CSSProperties}) => <Img src={staticFile(image.file)} style={{width:'100%',height:'100%',objectFit:'contain',display:'block',...style}}/>;

// Shotcraft row-embed: preserve the 12f flight, 16 degree leveling,
// four-frame press recovery and five-frame seam spread; rebind to native pixels.
function Slices({image,w,h,vertical=false,cuts=[0,1/3,2/3,1]}:{image:Screen;w:number;h:number;vertical?:boolean;cuts?:number[]}) {
  const f=useFrame30();
  const boundaries=cuts;
  return <>{boundaries.slice(0,-1).map((a,i)=>{
    const b=boundaries[i+1],cue=12+i*9,land=cue+12;
    const t=tween(f,cue,land,Easing.bezier(.3,0,.25,1));
    const air=1-t,press=f<land?1.06-.065*t:mix(.995,1,tween(f,land,land+4,E.outQuad));
    const x=vertical?a*w:0,y=vertical?0:a*h,sw=vertical?(b-a)*w:w,sh=vertical?h:(b-a)*h;
    const seam=tween(f,land,land+5,E.outCubic),op=f<land?0:1-tween(f,land+2,land+8);
    return <div key={i} style={{position:'absolute',left:x,top:y,width:sw,height:sh,opacity:tween(f,cue,cue+3),
      transform:`perspective(900px) translate${vertical?'X':'Y'}(${(vertical?(i-1)*95:-60)*air}px) rotateX(${16*air}deg) scale(${press})`,
      transformOrigin:'50% 50%',overflow:'hidden'}}>
      <Img src={staticFile(image.file)} style={{position:'absolute',left:-x,top:-y,width:w,height:h}}/>
      <div style={{position:'absolute',bottom:0,left:sw*(1-seam)/2,width:sw*seam,height:2,background:'var(--pv-accent)',opacity:op}}/>
    </div>;
  })}</>;
}

export function MotionPicture({image,box,motion='',duration,before,tiles,slices,shadowed=true}:{image:Screen;box:Box;motion?:string;duration:number;before?:Screen;tiles?:Screen[];slices?:number[];shadowed?:boolean}) {
  const f=useFrame30(),[x,y,w,h]=fit(image,box);
  const end=Math.max(45,Math.min(duration-28,150));
  const arrive=tween(f,0,48,Easing.bezier(.33,0,.15,1));
  let transform='',filter:string|undefined,clipPath:string|undefined,opacity=1;
  if(motion==='camera-tour') {
    const push=tween(f,12,65,Easing.bezier(.33,0,.15,1)),pan=tween(f,65,Math.max(95,end));
    const room=Math.max(0,Math.min(36,(box[2]-w)/2-12));
    transform=`translate(${mix(room,-room,pan)}px, 0px) scale(${.88+push*.12})`;
  } else if(motion==='focus-pull') {
    transform=`scale(${mix(1.08,1,tween(f,0,36))})`;filter=`blur(${12*(1-tween(f,0,32))}px)`;
  } else if(motion==='orbit-level') {
    transform=`perspective(1800px) translateY(${32*(1-arrive)}px) rotateX(${14*(1-arrive)}deg) rotateY(${-16*(1-arrive)}deg) scale(${mix(.89,1,arrive)})`;
  } else if(motion==='mask-reveal') {
    clipPath=`inset(0 ${(1-tween(f,4,42,Easing.bezier(.5,0,.2,1)))*100}% 0 0 round 12px)`;
  } else if(motion==='panel-unfold') {
    const sx=mix(.004,1,tween(f,12,17,E.outQuart)),sy=mix(3/h,1,tween(f,17,26,E.outCubic));
    transform=`scaleX(${sx}) scaleY(${sy})`;opacity=f<12?0:1;
  } else if(motion==='content-lift') {
    transform=`translate(${110*(1-arrive)}px,${-60*(1-arrive)}px) scale(${mix(.62,1,arrive)})`;
  } else if(motion==='pull-back') {
    transform=`scale(${mix(1.08,1,tween(f,0,90,E.inOutCubic))})`;
  } else if(motion==='paired-slide') {
    transform=`translateX(${-120*(1-arrive)}px) rotate(${-3*(1-arrive)}deg)`;
  }
  if(motion==='filmstrip' && tiles?.length) {
    const count=tiles.length,last=Math.max(60,duration-45),per=last/count;
    let shift=0;
    for(let i=1;i<count;i++)shift+=tween(f,i*per,i*per+24,Easing.bezier(.6,0,.4,1));
    return <div style={{position:'absolute',left:box[0],top:box[1],width:box[2],height:box[3],overflow:'hidden'}}>
      <div style={{position:'absolute',inset:0,transform:`translateX(${-shift*(box[2]+100)}px)`}}>
        {tiles.map((im,i)=>{const b=fit(im,[0,0,box[2],box[3]]);return <div key={i} style={{position:'absolute',left:b[0]+i*(box[2]+100),top:b[1],width:b[2],height:b[3],borderRadius:12,overflow:'hidden',boxShadow:shadow}}><Photo image={im}/></div>})}
      </div>
    </div>;
  }
  if(motion==='card-flip' && before) {
    // Shotcraft card-flip-reveal: 18f turn to 192 degrees, then 8f settle to 180.
    const angle=f<36?mix(0,192,tween(f,18,36,Easing.bezier(.55,0,.3,1))):mix(192,180,tween(f,36,44,E.outQuint));
    return <div style={{position:'absolute',left:x,top:y,width:w,height:h,perspective:1800}}><div style={{position:'absolute',inset:0,transformStyle:'preserve-3d',transform:`rotateY(${angle}deg)`}}>
      {[before,image].map((im,i)=><div key={i} style={{position:'absolute',inset:0,backfaceVisibility:'hidden',transform:i?'rotateY(180deg)':undefined,background:'#171515',borderRadius:12,boxShadow:shadow}}><Photo image={im}/></div>)}
    </div></div>;
  }
  const sliced=motion==='row-embed'||motion==='panel-assemble';
  return <div style={{position:'absolute',left:x,top:y,width:w,height:h,transform,filter,clipPath,opacity,transformOrigin:'50% 50%',borderRadius:12,
    overflow:sliced&&f<60?'visible':'hidden',boxShadow:shadowed&&!sliced?shadow:undefined}}>
    {sliced?<Slices image={image} w={w} h={h} vertical={motion==='panel-assemble'} cuts={slices}/>:<Photo image={image}/>}
    {motion==='panel-unfold'&&<div style={{position:'absolute',inset:0,background:'var(--pv-accent)',opacity:1-tween(f,23,34,E.outQuad)}}/>}
  </div>;
}


type TileBox={x:number;y:number;w:number;h:number};
function tileGrid(i:number,count:number):TileBox {
  const cols=count<=3?count:count===4?2:3,rows=Math.ceil(count/cols),w=(1744-(cols-1)*20)/cols,h=rows===1?560:320;
  return {x:88+i%cols*(w+20),y:(rows===1?285:235)+Math.floor(i/cols)*(h+20),w,h};
}
function featureBox(i:number,active:number,count:number):TileBox {
  if(active<0)return tileGrid(i,count);
  if(i===active)return {x:88,y:235,w:1100,h:650};
  const row=i<active?i:i-1,h=(650-(count-2)*12)/(count-1);
  return {x:1230,y:235+row*(h+12),w:602,h};
}
const boxMix=(a:TileBox,b:TileBox,t:number):TileBox=>({x:mix(a.x,b.x,t),y:mix(a.y,b.y,t),w:mix(a.w,b.w,t),h:mix(a.h,b.h,t)});

export function FeatureOverview({tiles,focusAt,duration,portal=false}:{tiles:Screen[];focusAt?:number[];duration:number;portal?:boolean}) {
  const f=useFrame30(),highlights=focusAt??tiles.map((_,i)=>.08+i*.72/tiles.length);
  const returnAt=Math.max(duration-53,(highlights[highlights.length-1]??0)*duration+1);
  const stages=[{at:0,active:-1},...highlights.map((at,active)=>({at:at*duration,active})),{at:returnAt,active:-1}];
  let stage=0;
  for(let i=0;i<stages.length;i++)if(f>=stages[i].at)stage=i;
  const current=stages[stage],previous=stages[Math.max(0,stage-1)],travel=tween(f,18,63,Easing.bezier(.5,0,.2,1));
  return <>{tiles.map((image,i)=>{
    const available=Math.max(.01,(stages[stage+1]?.at??duration)-current.at);
    const delay=i*Math.min(2,available/(tiles.length*5));
    const u=tween(f,current.at+delay,current.at+delay+Math.min(40,available-delay),t=>t*t*(3-2*t));
    let b=boxMix(featureBox(i,previous.active,tiles.length),featureBox(i,current.active,tiles.length),u);
    if(portal)b=i===0?boxMix(tileGrid(0,tiles.length),{x:80,y:250,w:1760,h:650},travel):tileGrid(i,tiles.length);
    const compact=Math.max(0,Math.min(1,(250-b.h)/128)),appear=portal?1:tween(f,i*3,i*3+22);
    return <div key={i} style={{position:'absolute',left:b.x,top:b.y,width:b.w,height:b.h,opacity:appear*(portal&&i!==0?1-travel:1),zIndex:portal&&i===0?20:current.active===i?10:1,
      transform:`scale(${mix(.9,1,appear)})`,borderRadius:14,overflow:'hidden',background:'var(--pv-surface)',boxShadow:shadow,border:current.active===i&&!portal?'1px solid var(--pv-accent)':'1px solid #ffffff18'}}>
      <div style={{position:'absolute',left:10*compact,top:9*compact,bottom:portal&&i===0?47*(1-travel):mix(47,9,compact),width:mix(b.w,180,compact)}}><Photo image={image}/></div>
      <div style={{position:'absolute',left:mix(20,212,compact),right:14,bottom:mix(14,45,compact),fontSize:25,fontWeight:600,lineHeight:1.25,opacity:portal&&i===0?1-travel:1}}>{image.label}</div>
    </div>;
  })}</>;
}

export function CardFan({tiles}:{tiles:Screen[]}) {
  const f=useFrame30(),t=Math.min(f/126,1);
  return <div style={{position:'absolute',inset:0,perspective:1800}}>{tiles.map((image,i)=>{
    const k=i-(tiles.length-1)/2,inT=seg(t,.02+i*.033,.32+i*.033),fan=seg(t,.55,.8,E.inOutCubic);
    const y=1200*(1-E.spring(inT,.3)),w=720,h=Math.min(650,w*image.height/image.width);
    return <div key={i} style={{position:'absolute',left:1225-w/2,top:540-h/2,width:w,height:h,opacity:Math.min(1,inT*4),borderRadius:14,overflow:'hidden',boxShadow:shadow,background:'var(--pv-surface)',
      transformOrigin:'50% 130%',transform:`translate3d(${k*150*fan}px,${y}px,${-40*Math.abs(k)*fan}px) rotate(${k*8*fan}deg)`,zIndex:20-Math.abs(k*2)}}><Photo image={image}/></div>;
  })}</div>;
}

export function ThemeWipe({first,second,box,duration}:{first:Screen;second:Screen;box:Box;duration:number}) {
  const f=useFrame30(),[x,y,w,h]=fit(first,box);
  const enter=tween(f,20,85,E.inOutCubic),settle=tween(f,Math.min(duration-60,130),Math.min(duration-30,160),E.inOutCubic);
  const edge=mix(1,0,enter)+settle*.5;
  return <div style={{position:'absolute',left:x,top:y,width:w,height:h,borderRadius:12,overflow:'hidden',boxShadow:shadow}}>
    <Photo image={first}/><div style={{position:'absolute',inset:0,clipPath:`inset(0 0 0 ${edge*100}%)`}}><Photo image={second}/></div>
    <div style={{position:'absolute',left:edge*w,top:0,bottom:0,width:3,background:'var(--pv-accent)'}}/>
  </div>;
}
