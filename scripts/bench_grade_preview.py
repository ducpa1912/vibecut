"""Compare the production grade shader and FFmpeg on a synthetic RGB chart."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from html import unescape
import re

from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from duckcore import grade


def main():
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    ffmpeg = ROOT / "build/ffmpeg-lgpl/bin/ffmpeg"
    shader = (ROOT / "static/duck/grade-preview.js").read_text()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        image = root / "chart.png"
        pixels = np.rint(255 * grade.grid(17)).astype(np.uint8).reshape(289, 17, 3)
        Image.fromarray(pixels).save(image)
        cases = []
        for settings in [{"exposure": 50}, {"temperature": -60, "tint": 30},
                         {"look": "Teal and orange", "look_strength": 70}]:
            cube = grade.bake(settings, root)
            raw = subprocess.check_output([ffmpeg, "-v", "error", "-i", image, "-vf",
                                          grade.filter_for(cube), "-frames:v", "1", "-pix_fmt",
                                          "rgb24", "-f", "rawvideo", "-"])
            cases.append([settings, grade.payload(cube), base64.b64encode(raw).decode()])
        html = root / "proof.html"
        html.write_text('<body><pre id="result">pending</pre><script type="module">' + shader
                        + '\nconst cases=' + json.dumps(cases) + ';\n' + """
            try {
              const img = new Image();
              img.src = 'chart.png';
              await img.decode();
              const results=[];
              for(const [settings,payload,expected] of cases) {
                const canvas=document.createElement('canvas'), painter=gradePainter(canvas,payload);
                painter.draw(img);
                const gl=canvas.getContext('webgl2'), w=canvas.width,h=canvas.height;
                const rgba=new Uint8Array(w*h*4);
                gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,rgba);
                const rgb=atob(expected); let max=0;
                for(let y=0;y<h;y++) for(let x=0;x<w;x++) for(let c=0;c<3;c++)
                  max=Math.max(max,Math.abs(rgba[((h-1-y)*w+x)*4+c]-rgb.charCodeAt((y*w+x)*3+c)));
                results.push({settings,max}); painter.release();
              }
              document.querySelector('pre').textContent=JSON.stringify(results);
            } catch(e) {document.querySelector('pre').textContent=String(e);}
            </script>""")
        page = subprocess.run([chrome, "--headless", "--no-first-run", "--allow-file-access-from-files",
                               "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                               "--user-data-dir=" + str(root / "chrome"), "--virtual-time-budget=10000",
                               "--dump-dom", html.as_uri()], capture_output=True, text=True, timeout=60, check=True)
        result = unescape(re.search(r'<pre id="result">(.*?)</pre>', page.stdout).group(1))
        print(result)
        return int(any(row["max"] > 2 for row in json.loads(result)))


if __name__ == "__main__":
    sys.exit(main())
