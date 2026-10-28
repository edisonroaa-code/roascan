// ============================================================================
// RoaScan .NET Interop Bindings (C# 10 / .NET 6+) — Experimental Native Bridge
// Namespace: RoaScan
// Clean-Room Native C-ABI Bindings to roascan_core.dll.
// NOTE: roascan_core.dll executes C++17 preprocessing, Sauvola binarization,
// deskew, document enhancement, XY-Cut word/line segmentation, and Trie lexicon
// lookup. Neural ONNX character recognition is executed by the Python SDK/CLI
// (or requires integrating Microsoft.ML.OnnxRuntime over the segmented boxes).
// ============================================================================

using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace RoaScan
{
    [StructLayout(LayoutKind.Sequential)]
    public struct RoaScanRect
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;

        public int Width => Right - Left;
        public int Height => Bottom - Top;

        public override string ToString() => $"[L:{Left}, T:{Top}, R:{Right}, B:{Bottom}]";
    }

    public class RoaScanWord
    {
        public string Text { get; set; } = string.Empty;
        public RoaScanRect BoundingBox { get; set; }
        public float Confidence { get; set; }
    }

    /// <summary>
    /// RoaScan Core Recognition Engine (100% Clean-Room Native Core)
    /// </summary>
    public class RoaScanEngine : IDisposable
    {
        private IntPtr _handle;
        private bool _disposed;
        private GCHandle? _pinnedImageHandle;

        public RoaScanEngine(string? dllDirectory = null)
        {
            if (!string.IsNullOrEmpty(dllDirectory))
            {
                NativeMethods.SetDllDirectory(dllDirectory);
            }

            _handle = NativeMethods.roascan_create_engine(IntPtr.Zero, IntPtr.Zero);
            if (_handle == IntPtr.Zero)
            {
                throw new InvalidOperationException("Failed to allocate native RoaScan engine instance (roascan_core.dll).");
            }

            SetResolution(300, 300);
            SetAutoOrientation(true);
            SetAutoAlphabet(true);
        }

        public static string NativeVersion
        {
            get
            {
                IntPtr ptr = NativeMethods.roascan_native_version();
                return ptr != IntPtr.Zero ? Marshal.PtrToStringAnsi(ptr) ?? "2.0.0-roascan-native" : "2.0.0-roascan-native";
            }
        }

        public void SetResolution(int dpiX, int dpiY)
        {
            CheckDisposed();
            NativeMethods.roascan_set_resolution(_handle, dpiX, dpiY);
        }

        public void SetAlphabet(short alphabetId)
        {
            CheckDisposed();
            NativeMethods.roascan_set_alphabet(_handle, alphabetId);
        }

        public void SetAutoAlphabet(bool enabled)
        {
            CheckDisposed();
            NativeMethods.roascan_set_auto_alphabet(_handle, enabled ? 1 : 0);
        }

        public void SetAutoOrientation(bool enabled)
        {
            CheckDisposed();
            NativeMethods.roascan_set_auto_orientation(_handle, enabled ? 1 : 0);
        }

        public void SetThreadCount(int numThreads)
        {
            CheckDisposed();
            NativeMethods.roascan_set_threads(_handle, numThreads);
        }

        public void SetImage(byte[] rawPixels, int width, int height, int bpp = 8, int? stride = null)
        {
            CheckDisposed();

            if (_pinnedImageHandle.HasValue && _pinnedImageHandle.Value.IsAllocated)
            {
                _pinnedImageHandle.Value.Free();
                _pinnedImageHandle = null;
            }

            int rowStride = stride ?? (width * (bpp <= 8 ? 1 : (bpp == 24 ? 3 : 4)));

            _pinnedImageHandle = GCHandle.Alloc(rawPixels, GCHandleType.Pinned);
            IntPtr pBuffer = _pinnedImageHandle.Value.AddrOfPinnedObject();

            int res;
            if (bpp == 8)
                res = NativeMethods.roascan_set_image_grey(_handle, pBuffer, width, height, rowStride);
            else if (bpp == 24 || bpp == 32)
                res = NativeMethods.roascan_set_image_color(_handle, pBuffer, width, height, rowStride);
            else
                res = NativeMethods.roascan_set_image(_handle, pBuffer, width, height, bpp, rowStride);

            if (res != 0)
                throw new InvalidOperationException($"roascan_set_image returned error code {res}");
        }

        public int Recognize()
        {
            CheckDisposed();
            return NativeMethods.roascan_recognize(_handle);
        }

        public List<RoaScanWord> ExtractWords()
        {
            CheckDisposed();
            var words = new List<RoaScanWord>();
            IntPtr wPtr = NativeMethods.roascan_get_first_word(_handle);

            while (wPtr != IntPtr.Zero)
            {
                IntPtr textPtr = NativeMethods.roascan_get_word_text(wPtr);
                string text = textPtr != IntPtr.Zero ? Marshal.PtrToStringAnsi(textPtr) ?? "" : "";

                RoaScanRect rect = default;
                NativeMethods.roascan_get_word_rect(wPtr, ref rect);
                float conf = NativeMethods.roascan_get_word_confidence(wPtr);

                words.Add(new RoaScanWord
                {
                    Text = text,
                    BoundingBox = rect,
                    Confidence = conf
                });

                wPtr = NativeMethods.roascan_get_next_word(_handle, wPtr);
            }

            return words;
        }

        public string GetText()
        {
            var words = ExtractWords();
            var sb = new StringBuilder();
            foreach (var w in words)
            {
                if (!string.IsNullOrEmpty(w.Text))
                {
                    if (sb.Length > 0) sb.Append(' ');
                    sb.Append(w.Text);
                }
            }
            return sb.ToString();
        }

        public static Dictionary<int, string> GetSupportedLanguages()
        {
            var dict = new Dictionary<int, string>();
            for (int i = 0; i < 32; i++)
            {
                IntPtr namePtr = NativeMethods.roascan_get_language_name(i);
                if (namePtr != IntPtr.Zero)
                {
                    string? name = Marshal.PtrToStringAnsi(namePtr);
                    if (!string.IsNullOrWhiteSpace(name))
                    {
                        dict[i] = name.Trim();
                    }
                }
            }
            return dict;
        }

        private void CheckDisposed()
        {
            if (_disposed) throw new ObjectDisposedException(nameof(RoaScanEngine));
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                if (_pinnedImageHandle.HasValue && _pinnedImageHandle.Value.IsAllocated)
                {
                    _pinnedImageHandle.Value.Free();
                    _pinnedImageHandle = null;
                }

                if (_handle != IntPtr.Zero)
                {
                    NativeMethods.roascan_destroy_engine(_handle);
                    _handle = IntPtr.Zero;
                }
                _disposed = true;
            }
            GC.SuppressFinalize(this);
        }

        ~RoaScanEngine() => Dispose();
    }

    /// <summary>
    /// RoaScan Image Preprocessor (Clean-Room Native Core)
    /// </summary>
    public class RoaScanPreprocessor : IDisposable
    {
        private IntPtr _context;
        private bool _disposed;

        public RoaScanPreprocessor(string? dllDirectory = null)
        {
            if (!string.IsNullOrEmpty(dllDirectory))
                NativeMethods.SetDllDirectory(dllDirectory);

            _context = NativeMethods.roascan_prepro_setup(IntPtr.Zero);
            if (_context == IntPtr.Zero)
                throw new InvalidOperationException("Failed to allocate preprocessor context.");
        }

        public void SetBrightness(byte value)
        {
            CheckDisposed();
            NativeMethods.roascan_prepro_set_brightness(_context, value);
        }

        public void SetContrast(byte value)
        {
            CheckDisposed();
            NativeMethods.roascan_prepro_set_contrast(_context, value);
        }

        public void SetThreshold(byte threshold)
        {
            CheckDisposed();
            NativeMethods.roascan_prepro_set_threshold(_context, threshold);
        }

        public void SetThreads(int numThreads)
        {
            CheckDisposed();
            NativeMethods.roascan_prepro_set_threads(_context, numThreads);
        }

        public string GetVersion()
        {
            IntPtr ptr = NativeMethods.roascan_prepro_get_version();
            return ptr != IntPtr.Zero ? Marshal.PtrToStringAnsi(ptr) ?? "2.0.0-roascan-native" : "2.0.0-roascan-native";
        }

        private void CheckDisposed()
        {
            if (_disposed) throw new ObjectDisposedException(nameof(RoaScanPreprocessor));
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                if (_context != IntPtr.Zero)
                {
                    NativeMethods.roascan_prepro_upset(_context);
                    _context = IntPtr.Zero;
                }
                _disposed = true;
            }
            GC.SuppressFinalize(this);
        }

        ~RoaScanPreprocessor() => Dispose();
    }

    /// <summary>
    /// RoaScan Document and Searchable PDF Writer (Clean-Room Native Core)
    /// </summary>
    public class RoaScanDocumentWriter : IDisposable
    {
        public const int FormatPdfMRC = 1; // Mixed Raster Content (ISO 16497)
        public const int FormatPdfStd = 2;
        public const int FormatRtf    = 3;
        public const int FormatDocx   = 4;
        public const int FormatTxt    = 5;
        public const int FormatHtml   = 6;
        public const int FormatXml    = 7;

        private IntPtr _handle;
        private bool _disposed;

        public RoaScanDocumentWriter(string? dllDirectory = null)
        {
            if (!string.IsNullOrEmpty(dllDirectory))
                NativeMethods.SetDllDirectory(dllDirectory);

            _handle = NativeMethods.roascan_docout_init();
            if (_handle == IntPtr.Zero)
                throw new InvalidOperationException("Failed to initialize document output session.");
        }

        public void ConfigurePdf(string outputPath, int format = FormatPdfStd, int pdfVersion = 15, bool textOverImage = true, bool embedFonts = true)
        {
            CheckDisposed();
            string fullPath = Path.GetFullPath(outputPath);
            NativeMethods.roascan_docout_set_format(_handle, format);
            NativeMethods.roascan_docout_set_output_path(_handle, fullPath);
            NativeMethods.roascan_docout_set_pdf_version(_handle, pdfVersion);
            NativeMethods.roascan_docout_set_text_over_image(_handle, textOverImage ? 1 : 0);
            NativeMethods.roascan_docout_set_embedded_fonts(_handle, embedFonts ? 1 : 0);
        }

        public int Write()
        {
            CheckDisposed();
            return NativeMethods.roascan_docout_write(_handle);
        }

        private void CheckDisposed()
        {
            if (_disposed) throw new ObjectDisposedException(nameof(RoaScanDocumentWriter));
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                if (_handle != IntPtr.Zero)
                {
                    NativeMethods.roascan_docout_close(_handle);
                    _handle = IntPtr.Zero;
                }
                _disposed = true;
            }
            GC.SuppressFinalize(this);
        }

        ~RoaScanDocumentWriter() => Dispose();
    }

    internal static class NativeMethods
    {
        public const string LibCore = "roascan_core";

        static NativeMethods()
        {
            NativeLibrary.SetDllImportResolver(typeof(NativeMethods).Assembly, (libraryName, assembly, searchPath) =>
            {
                string baseDir = AppContext.BaseDirectory;
                string? envDir = Environment.GetEnvironmentVariable("ROASCAN_NATIVE_DIR");

                var searchDirs = new List<string>();
                if (!string.IsNullOrEmpty(envDir)) searchDirs.Add(envDir);
                searchDirs.Add(baseDir);
                searchDirs.Add(Path.Combine(baseDir, "roascan-native", "build", "Release"));
                searchDirs.Add(Path.Combine(baseDir, "..", "roascan-native", "build", "Release"));
                searchDirs.Add(Path.Combine(baseDir, "..", "..", "roascan-native", "build", "Release"));

                string[] candidateFiles = new[] { "roascan_core.dll", "libroascan_core.so", "libroascan_core.dylib" };

                foreach (var dir in searchDirs)
                {
                    foreach (var file in candidateFiles)
                    {
                        string candidatePath = Path.Combine(dir, file);
                        if (File.Exists(candidatePath) && NativeLibrary.TryLoad(candidatePath, out IntPtr handle))
                        {
                            return handle;
                        }
                    }
                }

                return IntPtr.Zero;
            });
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        public static extern bool SetDllDirectory(string lpPathName);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_native_version();

        // Core OCR Pipeline (roascan_core.dll)
        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_create_engine(IntPtr pConfig, IntPtr pReserved);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_destroy_engine(IntPtr engine);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_set_resolution(IntPtr engine, int dpiX, int dpiY);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_set_alphabet(IntPtr engine, short alphabetId);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_set_auto_alphabet(IntPtr engine, int enable);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_set_auto_orientation(IntPtr engine, int enable);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_set_threads(IntPtr engine, int numThreads);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_set_image(IntPtr engine, IntPtr pImage, int width, int height, int bpp, int stride);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_set_image_grey(IntPtr engine, IntPtr pImage, int width, int height, int stride);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_set_image_color(IntPtr engine, IntPtr pImage, int width, int height, int stride);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_recognize(IntPtr engine);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_get_first_word(IntPtr engine);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_get_next_word(IntPtr engine, IntPtr currentWord);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_get_word_text(IntPtr word);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_get_word_rect(IntPtr word, ref RoaScanRect pRect);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern float roascan_get_word_confidence(IntPtr word);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_get_language_name(int languageId);

        // Preprocessor Pipeline (roascan_core.dll)
        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_prepro_setup(IntPtr pReserved);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_prepro_upset(IntPtr prepro);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_prepro_set_brightness(IntPtr prepro, byte brightness);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_prepro_set_contrast(IntPtr prepro, byte contrast);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_prepro_set_threshold(IntPtr prepro, byte threshold);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_prepro_set_threads(IntPtr prepro, int numThreads);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_prepro_get_version();

        // Document Serialization Pipeline (roascan_core.dll)
        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_docout_init();

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_docout_close(IntPtr docout);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_docout_set_format(IntPtr docout, int format);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        public static extern int roascan_docout_set_output_path(IntPtr docout, string path);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_docout_set_pdf_version(IntPtr docout, int version);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_docout_set_text_over_image(IntPtr docout, int enable);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_docout_set_embedded_fonts(IntPtr docout, int enable);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_docout_write(IntPtr docout);

        // Low-Level Native Primitives (roascan_core.dll)
        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_native_enhance_document(IntPtr grayImg, IntPtr cleanBinaryImg);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_native_remove_grid_lines(IntPtr binaryImg, int minHorizLen, int minVertLen);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr roascan_native_rotate_orthogonal(IntPtr img, int degrees);

        [DllImport(LibCore, CallingConvention = CallingConvention.Cdecl)]
        public static extern int roascan_native_detect_sideways(IntPtr binaryImg);
    }
}
