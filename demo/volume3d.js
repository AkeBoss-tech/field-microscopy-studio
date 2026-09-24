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
uniform vec3 horizontal;
uniform vec3 vertical;
uniform vec3 depthAxis;
uniform vec3 colors[4];
uniform vec4 enabled;
uniform vec4 brightness;
uniform vec4 contrast;
uniform vec4 blackPoint;
uniform vec4 whitePoint;
uniform float opacity;
uniform float sampleCount;
out vec4 fragment;
void main(){
 vec2 screen=vec2(gl_FragCoord.x-resolution.x*.5-pan.x,resolution.y*.5-gl_FragCoord.y-pan.y)/scale;
 vec3 direction=-depthAxis;
 vec3 origin=horizontal*screen.x+vertical*screen.y+depthAxis*length(halfSize)*2.;
 vec3 t0=(-halfSize-origin)/direction,t1=(halfSize-origin)/direction;
 vec3 nearFace=min(t0,t1),farFace=max(t0,t1);
 float start=max(max(nearFace.x,nearFace.y),max(nearFace.z,0.));
 float finish=min(min(farFace.x,farFace.y),farFace.z);
 if(finish<=start){fragment=vec4(0.);return;}
 vec3 color=vec3(0.);float alpha=0.;
 float stepSize=(finish-start)/sampleCount;
 for(int i=0;i<224;i++){
  if(float(i)>=sampleCount||alpha>.985)break;
  vec3 p=origin+direction*(start+(float(i)+.5)*stepSize);
  vec4 raw=texture(voxels,p/(halfSize*2.)+.5);
  vec4 signal=clamp((raw-blackPoint)/max(whitePoint-blackPoint,vec4(.004)),0.,1.);
  signal=clamp((signal*brightness-.5)*contrast+.5,0.,1.)*enabled;
  float strongest=max(max(signal.r,signal.g),max(signal.b,signal.a));
  vec3 tint=signal.r*colors[0]+signal.g*colors[1]+signal.b*colors[2]+signal.a*colors[3];
  tint/=max(signal.r+signal.g+signal.b+signal.a,.001);
  float voxelAlpha=clamp(pow(max(strongest-.055,0.),1.45)*.09*opacity*(144./sampleCount),0.,.3);
  color+=(1.-alpha)*voxelAlpha*tint;
  alpha+=(1.-alpha)*voxelAlpha;
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
  const atlases=await Promise.all(channels.map(ch=>{const setting=channelSettings()[ch];const url='/api/volume-atlas?'+query({dataset:state.dataset,channel:ch,run:ch===state.channel?run:'',kind:state.image==='ridge-response'?'ridge-response':'processed',overlay:ch===state.channel?(state.focusObject?.run||overlay):'',object:ch===state.channel?state.focusObject?.id:'',bounds:state.focusObject?'':state.region3d?.join(','),background:setting.background});return volumeAtlas(url,depth)}));
  if(ticket!==v.ticket||!v.isConnected)return true;
  const first=atlases[0];if(atlases.some(a=>a.width!==first.width||a.height!==first.height||a.depth!==first.depth))throw Error('Channels have mismatched 3D grids');
  const moving=performance.now()<(v.camera.movingUntil||0),ratio=Math.min(devicePixelRatio||1,moving?.7:1.5,(moving?440:840)/Math.max(w,h));
  const cw=Math.max(1,Math.round(w*ratio)),ch=Math.max(1,Math.round(h*ratio));
  if(!v.volumeCanvas){v.volumeCanvas=document.createElement('canvas');v.volumeGL=v.volumeCanvas.getContext('webgl2',{alpha:true,preserveDrawingBuffer:true,premultipliedAlpha:false});if(!v.volumeGL)return false;v.volumeProgram=volumeProgram(v.volumeGL)}
  const gl=v.volumeGL,program=v.volumeProgram;if(v.volumeCanvas.width!==cw)v.volumeCanvas.width=cw;if(v.volumeCanvas.height!==ch)v.volumeCanvas.height=ch;gl.viewport(0,0,cw,ch);gl.useProgram(program);
  const key=channels.map((c,i)=>c+':'+atlases[i].width+'x'+atlases[i].height+'x'+atlases[i].depth+':'+(state.focusObject?.id||'')+':'+(state.region3d||[]).join(',')+':'+run+':'+channelSettings()[c].background).join('|');
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
  const [sx,sy,sz]=result.spacing,[start,end]=bounds,half=[(end[0]-start[0])*sx/2,(end[1]-start[1])*sy/2,(end[2]-start[2])*sz/2];gl.uniform3fv(loc('halfSize'),half);
  const c=Math.cos(angle),s=Math.sin(angle),cp=Math.cos(v.camera.pitch),sp=Math.sin(v.camera.pitch);
  gl.uniform3f(loc('horizontal'),c,0,s);gl.uniform3f(loc('vertical'),s*sp,cp,-c*sp);gl.uniform3f(loc('depthAxis'),-s*cp,sp,c*cp);
  const colors=new Float32Array(12),enabled=[0,0,0,0],brightness=[1,1,1,1],contrast=[1,1,1,1],black=[0,0,0,0],white=[1,1,1,1];
  channels.forEach((index,j)=>{const setting=channelSettings()[index],rgb=channelRGB(index);for(let k=0;k<3;k++)colors[j*3+k]=rgb[k]/255;enabled[j]=1;brightness[j]=setting.brightness/100;contrast[j]=setting.contrast/100;black[j]=(setting.blackPoint??0)/255;white[j]=(setting.whitePoint??255)/255});
  gl.uniform3fv(loc('colors[0]'),colors);vector('enabled',enabled);vector('brightness',brightness);vector('contrast',contrast);vector('blackPoint',black);vector('whitePoint',white);
  gl.uniform1f(loc('opacity'),Math.max(.5,state.opacity*1.7));gl.uniform1f(loc('sampleCount'),moving?72:168);
  gl.disable(gl.DEPTH_TEST);gl.disable(gl.BLEND);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
  ctx.drawImage(v.volumeCanvas,0,0,w,h);return true;
 }catch(error){console.warn('3D volume renderer unavailable; using sampled points',error);return false}
}
