'use strict';
// Display-only volume ray casting. The PNG atlas contains the actual acquired Z planes
// at a bounded XY sampling resolution; GPU trilinear interpolation smooths navigation.
const atlasCache=new Map();
async function volumeAtlas(url,depth){
 if(!atlasCache.has(url)){
  if(atlasCache.size>=12)atlasCache.delete(atlasCache.keys().next().value);
  atlasCache.set(url,(async()=>{const image=await bitmap(url),canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
   if(image.height%depth)throw Error('Invalid 3D atlas depth');const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0);
   const rgba=context.getImageData(0,0,canvas.width,canvas.height).data,gray=new Uint8Array(image.width*image.height);
   for(let i=0;i<gray.length;i++)gray[i]=rgba[i*4];
   return {data:gray,width:image.width,height:image.height/depth,depth}})());
 }
 return atlasCache.get(url);
}
const volumeVertex=`#version 300 es
in vec2 position;
void main(){gl_Position=vec4(position,0.,1.);}`;
const volumeFragment=`#version 300 es
precision highp float;
precision highp sampler3D;
uniform sampler3D voxels;
uniform vec2 resolution;
uniform vec2 pan;
uniform float scale;
uniform vec3 halfSize;
uniform vec3 texel;
uniform vec3 horizontal;
uniform vec3 vertical;
uniform vec3 depthAxis;
uniform vec3 colors[4];
uniform vec4 enabled;
uniform vec4 brightness;
uniform vec4 contrast;
uniform vec4 blackPoint;
uniform vec4 whitePoint;
uniform float sampleCount;
uniform int mode;
uniform float threshold;
uniform float ramp;
uniform float maxOpacity;
out vec4 fragment;
// Display window, then brightness/contrast: identical to the 2D channel controls.
vec4 signalAt(vec3 p){
 vec4 raw=texture(voxels,p/(halfSize*2.)+.5);
 vec4 s=clamp((raw-blackPoint)/max(whitePoint-blackPoint,vec4(.004)),0.,1.);
 return clamp((s*brightness-.5)*contrast+.5,0.,1.)*enabled;
}
float strongest(vec4 s){return max(max(s.r,s.g),max(s.b,s.a));}
vec3 tintOf(vec4 s){return (s.r*colors[0]+s.g*colors[1]+s.b*colors[2]+s.a*colors[3])/max(s.r+s.g+s.b+s.a,.001);}
// Transfer function: transparent below threshold, rising over the ramp to maximum opacity.
float transfer(float v){return smoothstep(threshold,threshold+max(ramp,.004),v)*maxOpacity;}
vec3 shade(vec3 p,vec3 tint,vec3 view){
 vec3 g=vec3(
  strongest(signalAt(p+vec3(texel.x,0.,0.)))-strongest(signalAt(p-vec3(texel.x,0.,0.))),
  strongest(signalAt(p+vec3(0.,texel.y,0.)))-strongest(signalAt(p-vec3(0.,texel.y,0.))),
  strongest(signalAt(p+vec3(0.,0.,texel.z)))-strongest(signalAt(p-vec3(0.,0.,texel.z))))/(2.*texel);
 if(length(g)<1e-5)return tint*.75;
 vec3 n=-normalize(g),light=normalize(view+vertical*.55-horizontal*.35),h=normalize(light+view);
 float diffuse=abs(dot(n,light)),specular=pow(max(abs(dot(n,h)),0.),28.)*.38;
 return tint*(.24+.76*diffuse)+vec3(specular);
}
void main(){
 vec2 screen=vec2(gl_FragCoord.x-resolution.x*.5-pan.x,resolution.y*.5-gl_FragCoord.y-pan.y)/scale;
 vec3 direction=-depthAxis;
 vec3 origin=horizontal*screen.x+vertical*screen.y+depthAxis*length(halfSize)*2.;
 vec3 t0=(-halfSize-origin)/direction,t1=(halfSize-origin)/direction;
 vec3 nearFace=min(t0,t1),farFace=max(t0,t1);
 float start=max(max(nearFace.x,nearFace.y),max(nearFace.z,0.));
 float finish=min(min(farFace.x,farFace.y),farFace.z);
 if(finish<=start){fragment=vec4(0.);return;}
 float stepSize=(finish-start)/sampleCount;
 // Opacity is defined per 1/160 of the volume diagonal so results do not depend on sample count.
 float stepScale=stepSize/(length(halfSize)*2./160.);
 vec3 color=vec3(0.);float alpha=0.;vec4 peak=vec4(0.);bool wasInside=false;
 for(int i=0;i<480;i++){
  if(float(i)>=sampleCount||alpha>.985)break;
  vec3 p=origin+direction*(start+(float(i)+.5)*stepSize);
  vec4 s=signalAt(p);float v=strongest(s);
  if(mode==1){peak=max(peak,s);continue;}
  if(mode==0){
   float a=1.-pow(1.-clamp(transfer(v)*.32,0.,.98),stepScale);
   color+=(1.-alpha)*a*tintOf(s);alpha+=(1.-alpha)*a;continue;
  }
  // Surface modes shade each crossing of the threshold isosurface.
  bool inside=v>=threshold;
  if(inside&&!wasInside){
   float lo=0.,hi=1.;vec3 q=p;
   for(int k=0;k<5;k++){float m=(lo+hi)*.5;q=p-direction*stepSize*(1.-m);if(strongest(signalAt(q))>=threshold)hi=m;else lo=m;}
   q=p-direction*stepSize*(1.-hi);
   vec3 lit=shade(q,tintOf(signalAt(q)),depthAxis);
   float layer=mode==2?1.:clamp(maxOpacity*.55,0.,1.);
   color+=(1.-alpha)*layer*lit;alpha+=(1.-alpha)*layer;
  }
  if(mode==3&&inside){float a=1.-pow(1.-clamp(transfer(v)*.06,0.,.9),stepScale);color+=(1.-alpha)*a*tintOf(s);alpha+=(1.-alpha)*a;}
  wasInside=inside;
 }
 if(mode==1){
  vec4 shown=peak*smoothstep(threshold*.5,threshold*.5+max(ramp,.004),peak);
  vec3 sum=shown.r*colors[0]+shown.g*colors[1]+shown.b*colors[2]+shown.a*colors[3];
  float a=clamp(max(max(sum.r,sum.g),sum.b),0.,1.);
  fragment=vec4(min(sum,vec3(a)),a);return;
 }
 fragment=vec4(color,alpha);
}`;
function volumeProgram(gl){
 const compile=(type,source)=>{const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(shader));return shader};
 const program=gl.createProgram();gl.attachShader(program,compile(gl.VERTEX_SHADER,volumeVertex));gl.attachShader(program,compile(gl.FRAGMENT_SHADER,volumeFragment));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
 const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
 gl.useProgram(program);const location=gl.getAttribLocation(program,'position');gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,2,gl.FLOAT,false,0,0);
 return program;
}
async function renderVolume3D(v,ctx,w,h,params){
 const {run,overlay,result,bounds,scale,angle,ticket}=params;
 if(!window.WebGL2RenderingContext)return false;
 if(!state.focusObject&&displayChannels().length>4)return false;
 try{
  const channels=state.focusObject?[state.channel]:displayChannels().slice(0,4),depth=bounds[1][2]-bounds[0][2];
  const atlases=await Promise.all(channels.map(ch=>{const setting=channelSettings()[ch];const url='/api/volume-atlas?'+query({dataset:state.dataset,size:renderSettings().quality==='precise'?512:256,channel:ch,run:ch===state.channel?run:'',kind:state.image==='ridge-response'?'ridge-response':'processed',overlay:ch===state.channel?(state.focusObject?.run||overlay):'',object:ch===state.channel?state.focusObject?.id:'',bounds:state.focusObject?'':state.region3d?.join(','),background:setting.background});return volumeAtlas(url,depth)}));
  if(ticket!==v.ticket||!v.isConnected)return true;
  const first=atlases[0];if(atlases.some(a=>a.width!==first.width||a.height!==first.height||a.depth!==first.depth))throw Error('Channels have mismatched 3D grids');
  const moving=performance.now()<(v.camera.movingUntil||0),precise=renderSettings().quality==='precise',ratio=Math.min(devicePixelRatio||1,moving?.7:precise?2:1.5,(moving?480:precise?1600:960)/Math.max(w,h));
  const cw=Math.max(1,Math.round(w*ratio)),ch=Math.max(1,Math.round(h*ratio));
  if(!v.volumeCanvas){v.volumeCanvas=document.createElement('canvas');v.volumeGL=v.volumeCanvas.getContext('webgl2',{alpha:true,preserveDrawingBuffer:true,premultipliedAlpha:true});if(!v.volumeGL)return false;v.volumeProgram=volumeProgram(v.volumeGL)}
  const gl=v.volumeGL,program=v.volumeProgram;if(v.volumeCanvas.width!==cw)v.volumeCanvas.width=cw;if(v.volumeCanvas.height!==ch)v.volumeCanvas.height=ch;gl.viewport(0,0,cw,ch);gl.useProgram(program);
  const key=channels.map((c,i)=>c+':'+atlases[i].width+'x'+atlases[i].height+'x'+atlases[i].depth+':'+(state.focusObject?.id||'')+':'+(state.region3d||[]).join(',')+':'+run+':'+channelSettings()[c].background).join('|')+':'+renderSettings().quality;
  if(v.volumeTextureKey!==key){
   if(v.volumeTexture)gl.deleteTexture(v.volumeTexture);
   const packed=new Uint8Array(first.width*first.height*first.depth*4);
   atlases.forEach((atlas,j)=>{for(let i=0;i<atlas.data.length;i++)packed[4*i+j]=atlas.data[i]});
   const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_3D,texture);gl.pixelStorei(gl.UNPACK_ALIGNMENT,1);gl.texParameteri(gl.TEXTURE_3D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_3D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_3D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_3D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_3D,gl.TEXTURE_WRAP_R,gl.CLAMP_TO_EDGE);
   gl.texImage3D(gl.TEXTURE_3D,0,gl.RGBA8,first.width,first.height,first.depth,0,gl.RGBA,gl.UNSIGNED_BYTE,packed);
   v.volumeTexture=texture;v.volumeTextureKey=key;
  }
  gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_3D,v.volumeTexture);
  const loc=name=>gl.getUniformLocation(program,name),vector=(name,values)=>gl.uniform4fv(loc(name),values);
  gl.uniform1i(loc('voxels'),0);gl.uniform2f(loc('resolution'),cw,ch);gl.uniform2f(loc('pan'),v.pan[0]*ratio,v.pan[1]*ratio);gl.uniform1f(loc('scale'),scale*ratio);
  const [sx,sy,sz]=result.spacing,[start,end]=bounds,half=[(end[0]-start[0])*sx/2,(end[1]-start[1])*sy/2,(end[2]-start[2])*sz/2];gl.uniform3fv(loc('halfSize'),half);gl.uniform3f(loc('texel'),half[0]*2/first.width,half[1]*2/first.height,half[2]*2/Math.max(1,first.depth));
  const c=Math.cos(angle),s=Math.sin(angle),cp=Math.cos(v.camera.pitch),sp=Math.sin(v.camera.pitch);
  gl.uniform3f(loc('horizontal'),c,0,s);gl.uniform3f(loc('vertical'),s*sp,cp,-c*sp);gl.uniform3f(loc('depthAxis'),-s*cp,sp,c*cp);
  const colors=new Float32Array(12),enabled=[0,0,0,0],brightness=[1,1,1,1],contrast=[1,1,1,1],black=[0,0,0,0],white=[1,1,1,1];
  channels.forEach((index,j)=>{const setting=channelSettings()[index],rgb=channelRGB(index);for(let k=0;k<3;k++)colors[j*3+k]=rgb[k]/255;enabled[j]=1;brightness[j]=setting.brightness/100;contrast[j]=setting.contrast/100;black[j]=(setting.blackPoint??0)/255;white[j]=(setting.whitePoint??255)/255});
  gl.uniform3fv(loc('colors[0]'),colors);vector('enabled',enabled);vector('brightness',brightness);vector('contrast',contrast);vector('blackPoint',black);vector('whitePoint',white);
  const render=renderSettings(),modes={volume:0,maximum:1,surface:2,mixed:3};
  gl.uniform1i(loc('mode'),modes[render.mode]??0);gl.uniform1f(loc('threshold'),render.threshold);gl.uniform1f(loc('ramp'),render.ramp);gl.uniform1f(loc('maxOpacity'),render.maxOpacity);
  gl.uniform1f(loc('sampleCount'),moving?96:render.quality==='precise'?448:224);
  gl.disable(gl.DEPTH_TEST);gl.disable(gl.BLEND);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
  ctx.drawImage(v.volumeCanvas,0,0,w,h);return true;
 }catch(error){console.warn('3D volume renderer unavailable; using sampled points',error);return false}
}
