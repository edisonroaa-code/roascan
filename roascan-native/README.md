# RoaScan Native Engine (Clean-Room C++17)

Reimplementación **100% nativa y original** de arquitectura limpia (Clean-Room) para el motor **RoaScan**.
No envuelve ni tiene dependencia alguna de binarios cerrados o licencias propietarias heredadas.
Sustituye completamente todas las herramientas y recursos auxiliares por implementaciones C++17 modernas de alto rendimiento con C-ABI interoperable.

---

## Estado del Proyecto - Etapa 1: Esqueleto Nativo Concluido

| Módulo / Herramienta | Recurso Original Reemplazado | Estado Clean-Room | Rendimiento / Método |
| :--- | :--- | :---: | :--- |
| **Biblioteca Núcleo C-ABI** | N/A (Nueva base abierta) |  Completado | `roascan_core.dll` & `roascan_core_static.lib` |
| **Binarización & Filtros** | Algoritmos propietarios 1989 |  Completado | Otsu & Sauvola adaptativo con imágenes integrales |
| **Deskew & Despeckle** | Filtros cerrados |  Completado | Proyección horizontal de varianza + CCL 8-conectividad |
| **Segmentación de Líneas y Palabras** | `SingleLineSegmentor` legacy |  Completado | Perfil de proyección ortogonal dinámico |
| **Diccionarios & Lexicon** | `*.ilex` & `*.dic` binarios |  Completado | `roascan-tool-lexicon` (Trie / Damerau-Levenshtein) |
| **Métricas Tipográficas** | `fontmetrics.bin` & `*.arr` |  Completado | `roascan-tool-fontmetrics` (Estimación estadística) |
| **Motor Matemático / LUT** | `fast_invert_x_power_y.bin` |  Completado | `roascan-tool-lut` (IEEE-754 FPU / SIMD nativo C++17) |
| **Bridge Interop Python** | C-ABI nativo directo |  Completado | `roascan.native` carga `roascan_core.dll` automáticamente |

---

## Estructura del Repositorio

```
roascan-native/
├── CMakeLists.txt
├── README.md
├── ROASCAN_PIPELINE_SPEC.md
├── build/Release/
│   ├── roascan_core.dll              # Biblioteca compartida C-ABI para Python/.NET
│   ├── roascan_core.lib              # Import library para compiladores C/C++
│   ├── roascan_core_static.lib       # Biblioteca estática completa
│   ├── roascan-preprocess.exe        # CLI de binarización y segmentación
│   ├── roascan-tool-lut.exe          # Herramienta de curvas y matemáticas
│   ├── roascan-tool-lexicon.exe      # Compilador y evaluador de diccionarios
│   └── roascan-tool-fontmetrics.exe  # Estimador de tipografía y líneas
└── src/
    ├── roascan_c_api.h               # Cabecera pura C-ABI exportable
    ├── roascan_c_api.cpp             # Implementación de exportaciones C-ABI
    ├── roascan_image.hpp             # Búfer de imagen en escala de grises
    ├── roascan_preprocess.hpp/.cpp   # Sauvola, Otsu, deskew, despeckle
    ├── roascan_segmentation.hpp/.cpp # Detección de líneas y palabras
    ├── roascan_fontmetrics.hpp/.cpp  # Estimación tipográfica (baseline, x-height)
    ├── roascan_lexicon.hpp/.cpp      # Trie de prefijos y corrección ortográfica
    ├── main.cpp                    # CLI principal
    └── tools/
        ├── roascan_tool_lut.cpp
        ├── roascan_tool_lexicon.cpp
        └── roascan_tool_fontmetrics.cpp
```

---

## Compilación y Ejecución

Compilar todo el conjunto en Windows con MSVC o MinGW:

```powershell
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

### Ejecutar las herramientas de higienización y conversión:

1. **Herramienta Matemática (reemplazo de `fast_invert_x_power_y.bin`):**
   ```powershell
   ./build/Release/roascan-tool-lut.exe
   ```

2. **Herramienta de Léxico (reemplazo de `.ilex` / `.dic`):**
   ```powershell
   ./build/Release/roascan-tool-lexicon.exe
   ```

3. **Herramienta de Métricas de Fuente (reemplazo de `fontmetrics.bin`):**
   ```powershell
   ./build/Release/roascan-tool-fontmetrics.exe
   ```

4. **CLI de Preprocesamiento de Imágenes:**
   ```powershell
   ./build/Release/roascan-preprocess.exe input.pgm output.pgm --binarize sauvola
   ```

---

## Interoperabilidad con Python / C#

El motor se carga directamente sin pasos manuales desde Python:

```python
from roascan.native import get_native_driver

drv = get_native_driver()
print("Core DLL cargado:", drv.core)
print("Versión del motor:", drv.core.roascan_native_version().decode())
```
