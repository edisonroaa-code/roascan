// roascan_c_api.h
// RoaScan clean-room native C-ABI export header.
// Unifies both low-level imaging/segmentation primitives (roascan_native_*) and
// high-level session handles (roascan_*) for Python (ctypes), C# (.NET P/Invoke),
// C, C++, and Rust.

#pragma once

#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32) || defined(__CYGWIN__)
  #ifdef ROASCAN_CORE_EXPORTS
    #define ROASCAN_NATIVE_API __declspec(dllexport)
  #else
    #define ROASCAN_NATIVE_API __declspec(dllimport)
  #endif
  #define ROASCAN_NATIVE_CALL __cdecl
#else
  #define ROASCAN_NATIVE_API __attribute__((visibility("default")))
  #define ROASCAN_NATIVE_CALL
#endif

#ifdef __cplusplus
extern "C" {
#endif

// --- Low-Level Native Primitives -------------------------------------------

typedef struct roascan_native_image_s*   HROASCAN_NATIVE_IMAGE;
typedef struct roascan_native_lexicon_s* HROASCAN_NATIVE_LEXICON;

typedef struct {
    int32_t left;
    int32_t top;
    int32_t right;
    int32_t bottom;
} roascan_native_rect_t;

// Library Version
ROASCAN_NATIVE_API const char* ROASCAN_NATIVE_CALL roascan_native_version(void);

// Image Lifecycle
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_image_create(int32_t width, int32_t height, const uint8_t* pixels);
ROASCAN_NATIVE_API void ROASCAN_NATIVE_CALL roascan_native_image_destroy(HROASCAN_NATIVE_IMAGE img);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_native_image_width(HROASCAN_NATIVE_IMAGE img);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_native_image_height(HROASCAN_NATIVE_IMAGE img);
ROASCAN_NATIVE_API const uint8_t* ROASCAN_NATIVE_CALL roascan_native_image_data(HROASCAN_NATIVE_IMAGE img);

// Preprocessing Pipeline
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_adjust_brightness_contrast(
    HROASCAN_NATIVE_IMAGE img,
    int32_t brightness,
    int32_t contrast
);
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_binarize_sauvola(HROASCAN_NATIVE_IMAGE img, int32_t window, double k);
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_binarize_otsu(HROASCAN_NATIVE_IMAGE img);
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_binarize_threshold(HROASCAN_NATIVE_IMAGE img, int32_t threshold);
ROASCAN_NATIVE_API double ROASCAN_NATIVE_CALL roascan_native_detect_skew(HROASCAN_NATIVE_IMAGE binary_img);
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_rotate(HROASCAN_NATIVE_IMAGE img, double angle_deg);
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_rotate_ex(
    HROASCAN_NATIVE_IMAGE img,
    double angle_deg,
    uint8_t fill,
    int32_t bilinear
);
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_despeckle(HROASCAN_NATIVE_IMAGE binary_img, int32_t min_area);
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_enhance_document(
    HROASCAN_NATIVE_IMAGE gray_img,
    HROASCAN_NATIVE_IMAGE clean_binary_img
);
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_remove_grid_lines(
    HROASCAN_NATIVE_IMAGE binary_img,
    int32_t min_horiz_len,
    int32_t min_vert_len
);
ROASCAN_NATIVE_API HROASCAN_NATIVE_IMAGE ROASCAN_NATIVE_CALL roascan_native_rotate_orthogonal(
    HROASCAN_NATIVE_IMAGE img,
    int32_t degrees
);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_native_detect_sideways(
    HROASCAN_NATIVE_IMAGE binary_img
);

// Segmentation Pipeline
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_native_segment_lines(
    HROASCAN_NATIVE_IMAGE binary_img,
    roascan_native_rect_t* out_boxes,
    int32_t max_boxes
);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_native_segment_words(
    HROASCAN_NATIVE_IMAGE binary_img,
    roascan_native_rect_t* out_boxes,
    int32_t max_boxes
);

// Lexicon Pipeline
ROASCAN_NATIVE_API HROASCAN_NATIVE_LEXICON ROASCAN_NATIVE_CALL roascan_native_lexicon_create(void);
ROASCAN_NATIVE_API void ROASCAN_NATIVE_CALL roascan_native_lexicon_destroy(HROASCAN_NATIVE_LEXICON lex);
ROASCAN_NATIVE_API void ROASCAN_NATIVE_CALL roascan_native_lexicon_insert(HROASCAN_NATIVE_LEXICON lex, const char* word);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_native_lexicon_contains(HROASCAN_NATIVE_LEXICON lex, const char* word);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_native_lexicon_load_file(HROASCAN_NATIVE_LEXICON lex, const char* filepath);
ROASCAN_NATIVE_API const char* ROASCAN_NATIVE_CALL roascan_native_lexicon_suggest_best(
    HROASCAN_NATIVE_LEXICON lex,
    const char* word,
    int32_t max_distance
);

// --- High-Level Session C-ABI (include/roascan/ & .NET P/Invoke) -------------

typedef struct roascan_engine_s* HROASCAN_ENGINE;
typedef struct roascan_prepro_s* HROASCAN_PREPRO;
typedef struct roascan_docout_s* HROASCAN_DOCOUT;
typedef struct roascan_word_s*   HROASCAN_WORD;

ROASCAN_NATIVE_API HROASCAN_ENGINE ROASCAN_NATIVE_CALL roascan_create_engine(void* p_config, void* p_reserved);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_destroy_engine(HROASCAN_ENGINE engine);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_set_resolution(HROASCAN_ENGINE engine, int32_t dpi_x, int32_t dpi_y);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_set_alphabet(HROASCAN_ENGINE engine, int16_t alphabet_id);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_set_auto_alphabet(HROASCAN_ENGINE engine, int32_t enable);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_set_auto_orientation(HROASCAN_ENGINE engine, int32_t enable);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_set_threads(HROASCAN_ENGINE engine, int32_t num_threads);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_set_image(HROASCAN_ENGINE engine, const uint8_t* p_image, int32_t width, int32_t height, int32_t bpp, int32_t stride);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_set_image_grey(HROASCAN_ENGINE engine, const uint8_t* p_image, int32_t width, int32_t height, int32_t stride);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_set_image_color(HROASCAN_ENGINE engine, const uint8_t* p_image, int32_t width, int32_t height, int32_t stride);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_recognize(HROASCAN_ENGINE engine);
ROASCAN_NATIVE_API HROASCAN_WORD ROASCAN_NATIVE_CALL roascan_get_first_word(HROASCAN_ENGINE engine);
ROASCAN_NATIVE_API HROASCAN_WORD ROASCAN_NATIVE_CALL roascan_get_next_word(HROASCAN_ENGINE engine, HROASCAN_WORD current_word);
ROASCAN_NATIVE_API const char* ROASCAN_NATIVE_CALL roascan_get_word_text(HROASCAN_WORD word);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_get_word_rect(HROASCAN_WORD word, roascan_native_rect_t* p_rect);
ROASCAN_NATIVE_API float ROASCAN_NATIVE_CALL roascan_get_word_confidence(HROASCAN_WORD word);
ROASCAN_NATIVE_API const char* ROASCAN_NATIVE_CALL roascan_get_language_name(int32_t language_id);

ROASCAN_NATIVE_API HROASCAN_PREPRO ROASCAN_NATIVE_CALL roascan_prepro_setup(void* p_reserved);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_prepro_upset(HROASCAN_PREPRO prepro);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_prepro_set_brightness(HROASCAN_PREPRO prepro, uint8_t brightness);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_prepro_set_contrast(HROASCAN_PREPRO prepro, uint8_t contrast);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_prepro_set_threshold(HROASCAN_PREPRO prepro, uint8_t threshold);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_prepro_set_threads(HROASCAN_PREPRO prepro, int32_t num_threads);
ROASCAN_NATIVE_API const char* ROASCAN_NATIVE_CALL roascan_prepro_get_version(void);
ROASCAN_NATIVE_API const char* ROASCAN_NATIVE_CALL roascan_prepro_get_branch(void);
ROASCAN_NATIVE_API const char* ROASCAN_NATIVE_CALL roascan_prepro_get_sha(void);

ROASCAN_NATIVE_API HROASCAN_DOCOUT ROASCAN_NATIVE_CALL roascan_docout_init(void);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_docout_close(HROASCAN_DOCOUT docout);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_docout_set_format(HROASCAN_DOCOUT docout, int32_t format);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_docout_set_output_path(HROASCAN_DOCOUT docout, const char* p_path);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_docout_set_pdf_version(HROASCAN_DOCOUT docout, int32_t version);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_docout_set_text_over_image(HROASCAN_DOCOUT docout, int32_t enable);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_docout_set_embedded_fonts(HROASCAN_DOCOUT docout, int32_t enable);
ROASCAN_NATIVE_API int32_t ROASCAN_NATIVE_CALL roascan_docout_write(HROASCAN_DOCOUT docout);

#ifdef __cplusplus
}
#endif
