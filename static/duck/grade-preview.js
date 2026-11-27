// The core sends a blue-major RGB cube. Use the same tetrahedra as FFmpeg lut3d.
const vertex = `#version 300 es
out vec2 uv;
void main() {
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  uv = vec2(p.x, 1.0-p.y);
  gl_Position = vec4(p*2.0-1.0,0,1);
}`;

const fragment = `#version 300 es
precision highp float;
precision highp sampler3D;
uniform sampler2D picture;
uniform sampler3D cube;
in vec2 uv;
out vec4 pixel;
void main() {
  int n = textureSize(cube,0).x-1;
  vec3 p = clamp(texture(picture,uv).rgb,0.0,1.0)*float(n);
  ivec3 low = min(ivec3(p),ivec3(n-1));
  vec3 f = p-vec3(low);
  int a=0,b=1,c=2,t;
  if (f[a]<f[b]) { t=a;a=b;b=t; }
  if (f[b]<f[c]) { t=b;b=c;c=t; }
  if (f[a]<f[b]) { t=a;a=b;b=t; }
  ivec3 first=low; first[a]++;
  ivec3 second=first; second[b]++;
  pixel=vec4((1.0-f[a])*texelFetch(cube,low,0).rgb+
    (f[a]-f[b])*texelFetch(cube,first,0).rgb+
    (f[b]-f[c])*texelFetch(cube,second,0).rgb+
    f[c]*texelFetch(cube,low+1,0).rgb,1.0);
}`;

export function gradePainter(canvas, payload) {
  const gl = canvas.getContext('webgl2', {alpha:false, antialias:false, depth:false});
  if (!gl) throw Error('WebGL 2 unavailable');
  const program = gl.createProgram();
  const release = () => gl.getExtension('WEBGL_lose_context')?.loseContext();
  try {
    for (const [type, source] of [[gl.VERTEX_SHADER,vertex],[gl.FRAGMENT_SHADER,fragment]]) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader,source);
      gl.compileShader(shader);
      gl.attachShader(program,shader);
      gl.deleteShader(shader);
    }
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program,gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);
    function texture(unit,target,name) {
      gl.activeTexture(gl.TEXTURE0+unit);
      gl.bindTexture(target,gl.createTexture());
      gl.texParameteri(target,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
      gl.texParameteri(target,gl.TEXTURE_MIN_FILTER,gl.NEAREST);
      gl.uniform1i(gl.getUniformLocation(program,name),unit);
    }
    texture(1,gl.TEXTURE_3D,'cube');
    const bytes = Uint8Array.from(atob(payload.data), c=>c.charCodeAt(0));
    const n = payload.size;
    if (bytes.length !== n*n*n*12) throw Error('Incomplete grade cube');
    gl.texImage3D(gl.TEXTURE_3D,0,gl.RGB32F,n,n,n,0,gl.RGB,gl.FLOAT,new Float32Array(bytes.buffer));
    texture(0,gl.TEXTURE_2D,'picture');
    gl.disable(gl.DITHER);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL,gl.NONE);
    if (gl.getError() !== gl.NO_ERROR) throw Error('Could not load the cube');
    return {
      draw(frame) {
        const width = frame.videoWidth || frame.naturalWidth || frame.width;
        const height = frame.videoHeight || frame.naturalHeight || frame.height;
        if (canvas.width !== width || canvas.height !== height) {
          canvas.width=width; canvas.height=height;
        }
        gl.viewport(0,0,width,height);
        gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,frame);
        gl.drawArrays(gl.TRIANGLES,0,3);
        if (gl.getError() !== gl.NO_ERROR) throw Error('Could not grade this frame');
      }, release,
    };
  } catch (error) { release(); throw error; }
}
