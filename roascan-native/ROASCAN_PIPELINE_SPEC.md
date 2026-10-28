# RoaScan Native Core (`roascan-native`) — Especificación de Arquitectura C++17

Este documento describe la arquitectura interna del núcleo nativo C++17 de **RoaScan** (`roascan_core.dll` / `libroascan_core.so`), diseñado sin dependencias externas para lograr máxima velocidad en CPU local.

---

## 1. Módulos del Núcleo C++17 (`roascan-native/src/`)

| Archivo | Rol Técnico | Complejidad / Rendimiento |
| :--- | :--- | :--- |
| `roascan_preprocess.hpp/.cpp` | Binarización Otsu y Sauvola (imágenes integrales 64-bit), Deskew *Coarse-to-Fine*, rotación bilineal, *despeckle* y restauración documental (`enhance_document`). | Deskew A4 300 DPI en `1.96 ms` (`0.1°` precisión). |
| `roascan_segmentation.hpp/.cpp` | Segmentación recursiva de bloques multi-columna (`XY-Cut`) y perfiles de proyección horizontal/vertical para líneas y palabras. | $O(W \times H)$ lineal. |
| `roascan_fontmetrics.hpp/.cpp` | Estimación estadística de *baseline*, *x-height*, *ascender* y *descender* por línea para escalado tipográfico en PDF y detección de encabezados Markdown (`#`/`##`). | $O(N_{\text{palabras}})$. |
| `roascan_lexicon.hpp/.cpp` | Árbol Trie con programación dinámica Levenshtein incremental y poda temprana de subárboles. | `5.94 ms` sobre 57,000 lemas. |
| `roascan_c_api.h/.cpp` | Interfaz C-ABI estable (`roascan_native_*` y sesiones `roascan_*`) consumida por Python (`ctypes`) y .NET (`P/Invoke`). | C-ABI zero-copy. |

---

## 2. Flujo del Pipeline Documental

```text
Documento Escaneado (PDF / TIFF / PNG / JPEG)
  │
  ├─► 1. Detección de Inclinación Coarse-to-Fine (roascan_native_detect_skew)
  ├─► 2. Rotación Bilineal Sincronizada (roascan_native_rotate_bilinear)
  ├─► 3. Restauración Visual de Papel y Tinta (roascan_native_enhance_document)
  ├─► 4. Binarización Adaptativa Sauvola 64-bit + Despeckle
  ├─► 5. Segmentación XY-Cut (Columnas -> Líneas -> Palabras)
  ├─► 6. Reconocimiento Neuronal ONNX por Línea + Alineación CTC (PP-OCRv5 Latin)
  └─► 7. Exportación Dual:
         ├── PDF Buscable Restaurado y Comprimido (.pdf)
         └── Markdown Semántico con Títulos y Tablas (.md)
```
