import 'dart:convert';
import 'dart:js_interop';
import 'dart:typed_data';
import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';
import 'package:web/web.dart' as web;

/// Web 版 3D 模型查看器：用 `HtmlElementView` + iframe(srcdoc) 嵌入 three.js。
///
/// 浏览器沙箱无法使用原生 WebView（webview_flutter 无 Web 实现），改用
/// `<iframe srcdoc="...three.js html...">` 渲染 OBJ/STL/GLTF/GLB 模型。
/// 模型数据经 base64 内嵌到 srcdoc，无需 JS 通信。
class WebThreeViewer extends StatelessWidget {
  final String ext;
  final Uint8List bytes;

  const WebThreeViewer({super.key, required this.ext, required this.bytes});

  static String? _lastViewType;

  @override
  Widget build(BuildContext context) {
    final viewType = 'web-three-viewer-$ext-${bytes.length}';
    if (_lastViewType != viewType) {
      ui_web.platformViewRegistry.registerViewFactory(viewType, (int viewId) {
        final iframe = web.document.createElement('iframe')
            as web.HTMLIFrameElement;
        iframe.style.width = '100%';
        iframe.style.height = '100%';
        iframe.style.border = '0';
        iframe.srcdoc = _buildThreeJsHtml(ext, base64Encode(bytes)).toJS;
        iframe.setAttribute('sandbox', 'allow-scripts');
        return iframe;
      });
      _lastViewType = viewType;
    }
    return HtmlElementView(viewType: viewType);
  }
}

String _buildThreeJsHtml(String ext, String base64Data) {
  final loaderName = switch (ext) {
    'stl' => 'STL',
    'gltf' || 'glb' => 'GLTF',
    _ => 'OBJ',
  };
  return """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; overflow: hidden; background: #1a1a2e; }
  #info { position: absolute; top: 10px; left: 10px; color: #fff;
          font-family: monospace; font-size: 12px; z-index: 10;
          background: rgba(0,0,0,0.5); padding: 6px 10px; border-radius: 4px; }
  #error { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
           color: #ff6b6b; font-family: monospace; font-size: 14px; display: none; }
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/OBJLoader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
</head>
<body>
<div id="info">正在加载 $loaderName 模型...</div>
<div id="error">模型加载失败</div>
<script>
const modelBase64 = "$base64Data";
const modelExt = "$ext";

function base64ToArrayBuffer(b64) {
  const bin = atob(b64);
  const len = bin.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a2e);

const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.01, 1000);
camera.position.set(3, 2, 4);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(5, 8, 6);
scene.add(dirLight);

const grid = new THREE.GridHelper(10, 10, 0x444466, 0x333355);
scene.add(grid);

const buffer = base64ToArrayBuffer(modelBase64);
let object = null;

function centerAndScale(obj) {
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  const scale = 2.0 / maxDim;
  obj.position.sub(center);
  obj.scale.setScalar(scale);
}

try {
  if (modelExt === 'stl') {
    const loader = new THREE.STLLoader();
    const geometry = loader.parse(buffer);
    object = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0x4a9eff, metalness: 0.3, roughness: 0.4 }));
  } else if (modelExt === 'gltf' || modelExt === 'glb') {
    const loader = new THREE.GLTFLoader();
    loader.parse(buffer, '', (gltf) => {
      object = gltf.scene;
      centerAndScale(object);
      scene.add(object);
      document.getElementById('info').textContent = '模型加载完成';
    }, (err) => {
      document.getElementById('error').style.display = 'block';
      document.getElementById('info').textContent = 'GLTF 加载失败';
    });
    return;
  } else {
    const loader = new THREE.OBJLoader();
    const text = new TextDecoder().decode(new Uint8Array(buffer));
    object = loader.parse(text);
  }
  centerAndScale(object);
  scene.add(object);
  document.getElementById('info').textContent = '模型加载完成';
} catch (e) {
  document.getElementById('error').style.display = 'block';
  document.getElementById('info').textContent = '加载失败: ' + e.message;
}

let isDragging = false, prevX = 0, prevY = 0;
renderer.domElement.addEventListener('mousedown', (e) => { isDragging = true; prevX = e.clientX; prevY = e.clientY; });
window.addEventListener('mouseup', () => isDragging = false);
window.addEventListener('mousemove', (e) => {
  if (!isDragging) return;
  const dx = e.clientX - prevX;
  const dy = e.clientY - prevY;
  prevX = e.clientX; prevY = e.clientY;
  if (object) {
    object.rotation.y += dx * 0.01;
    object.rotation.x += dy * 0.01;
  }
});
renderer.domElement.addEventListener('wheel', (e) => {
  e.preventDefault();
  camera.position.multiplyScalar(e.deltaY > 0 ? 1.1 : 0.9);
});

function animate() {
  requestAnimationFrame(animate);
  renderer.render(scene, camera);
}
animate();
</script>
</body>
</html>
""";
}
