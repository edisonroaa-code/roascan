// roascan_c_api.cpp
// RoaScan clean-room native C-ABI export implementation.

#ifndef ROASCAN_CORE_EXPORTS
#define ROASCAN_CORE_EXPORTS
#endif

#include "roascan_c_api.h"
#include "roascan_image.hpp"
#include "roascan_preprocess.hpp"
#include "roascan_segmentation.hpp"
#include "roascan_fontmetrics.hpp"
#include "roascan_lexicon.hpp"

#include <cmath>
#include <cstring>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

struct roascan_native_image_s {
    roascan::GrayImage img;
};

struct roascan_native_lexicon_s {
    roascan::Lexicon lex;
    std::string last_suggestion;
};

struct roascan_word_s {
    std::string text;
    roascan_native_rect_t rect{};
    float confidence = 1.0f;
    roascan_word_s* next = nullptr;
};

struct roascan_engine_s {
    roascan::GrayImage gray;
    int32_t dpi_x = 300;
    int32_t dpi_y = 300;
    int16_t alphabet_id = 0;
    bool auto_alphabet = true;
    bool auto_orientation = true;
    int32_t num_threads = 4;
    std::vector<std::unique_ptr<roascan_word_s>> words;
};

struct roascan_prepro_s {
    uint8_t brightness = 128;
    uint8_t contrast = 128;
    uint8_t threshold = 0; // 0 = adaptive Sauvola
    int32_t num_threads = 4;
};

struct roascan_docout_s {
    int32_t format = 2;
    std::string output_path;
    int32_t pdf_version = 15;
    int32_t text_over_image = 1;
    int32_t embedded_fonts = 1;
};

const char* roascan_native_version(void) {
    return "2.0.0-roascan-native";
}

// --- Low-Level Native Primitives -------------------------------------------

HROASCAN_NATIVE_IMAGE roascan_native_image_create(int32_t width, int32_t height, const uint8_t* pixels) {
    if (width <= 0 || height <= 0) return nullptr;
    auto wrapper = new roascan_native_image_s();
    wrapper->img = roascan::GrayImage(width, height);
    if (pixels) {
        std::memcpy(wrapper->img.data.data(), pixels, static_cast<std::size_t>(width) * height);
    }
    return wrapper;
}

void roascan_native_image_destroy(HROASCAN_NATIVE_IMAGE img) {
    delete img;
}

int32_t roascan_native_image_width(HROASCAN_NATIVE_IMAGE img) {
    return img ? img->img.width : 0;
}

int32_t roascan_native_image_height(HROASCAN_NATIVE_IMAGE img) {
    return img ? img->img.height : 0;
}

const uint8_t* roascan_native_image_data(HROASCAN_NATIVE_IMAGE img) {
    return img ? img->img.data.data() : nullptr;
}

HROASCAN_NATIVE_IMAGE roascan_native_adjust_brightness_contrast(
    HROASCAN_NATIVE_IMAGE img,
    int32_t brightness,
    int32_t contrast
) {
    if (!img) return nullptr;
    auto result = new roascan_native_image_s();
    result->img = roascan::adjust_brightness_contrast(img->img, brightness, contrast);
    return result;
}

HROASCAN_NATIVE_IMAGE roascan_native_binarize_sauvola(HROASCAN_NATIVE_IMAGE img, int32_t window, double k) {
    if (!img) return nullptr;
    auto result = new roascan_native_image_s();
    result->img = roascan::binarize_sauvola(img->img, window, k);
    return result;
}

HROASCAN_NATIVE_IMAGE roascan_native_binarize_otsu(HROASCAN_NATIVE_IMAGE img) {
    if (!img) return nullptr;
    auto result = new roascan_native_image_s();
    result->img = roascan::binarize_otsu(img->img, -1);
    return result;
}

HROASCAN_NATIVE_IMAGE roascan_native_binarize_threshold(HROASCAN_NATIVE_IMAGE img, int32_t threshold) {
    if (!img) return nullptr;
    auto result = new roascan_native_image_s();
    result->img = roascan::binarize_otsu(img->img, threshold);
    return result;
}

double roascan_native_detect_skew(HROASCAN_NATIVE_IMAGE binary_img) {
    if (!binary_img) return 0.0;
    return roascan::detect_skew_degrees(binary_img->img);
}

HROASCAN_NATIVE_IMAGE roascan_native_rotate(HROASCAN_NATIVE_IMAGE img, double angle_deg) {
    if (!img) return nullptr;
    auto result = new roascan_native_image_s();
    result->img = roascan::rotate(img->img, angle_deg, 0);
    return result;
}

HROASCAN_NATIVE_IMAGE roascan_native_rotate_ex(
    HROASCAN_NATIVE_IMAGE img,
    double angle_deg,
    uint8_t fill,
    int32_t bilinear
) {
    if (!img) return nullptr;
    auto result = new roascan_native_image_s();
    if (bilinear) {
        result->img = roascan::rotate_bilinear(img->img, angle_deg, fill);
    } else {
        result->img = roascan::rotate(img->img, angle_deg, fill);
    }
    return result;
}

HROASCAN_NATIVE_IMAGE roascan_native_despeckle(HROASCAN_NATIVE_IMAGE binary_img, int32_t min_area) {
    if (!binary_img) return nullptr;
    auto result = new roascan_native_image_s();
    result->img = roascan::despeckle(binary_img->img, min_area);
    return result;
}

HROASCAN_NATIVE_IMAGE roascan_native_enhance_document(
    HROASCAN_NATIVE_IMAGE gray_img,
    HROASCAN_NATIVE_IMAGE clean_binary_img
) {
    if (!gray_img || !clean_binary_img) return nullptr;
    auto result = new roascan_native_image_s();
    result->img = roascan::enhance_document(gray_img->img, clean_binary_img->img);
    return result;
}

HROASCAN_NATIVE_IMAGE roascan_native_remove_grid_lines(
    HROASCAN_NATIVE_IMAGE binary_img,
    int32_t min_horiz_len,
    int32_t min_vert_len
) {
    if (!binary_img) return nullptr;
    auto result = new roascan_native_image_s();
    result->img = roascan::remove_table_grid_lines(binary_img->img, min_horiz_len, min_vert_len);
    return result;
}

HROASCAN_NATIVE_IMAGE roascan_native_rotate_orthogonal(
    HROASCAN_NATIVE_IMAGE img,
    int32_t degrees
) {
    if (!img) return nullptr;
    auto result = new roascan_native_image_s();
    result->img = roascan::rotate_orthogonal(img->img, degrees);
    return result;
}

int32_t roascan_native_detect_sideways(
    HROASCAN_NATIVE_IMAGE binary_img
) {
    if (!binary_img) return 0;
    return roascan::detect_sideways_orientation(binary_img->img);
}

int32_t roascan_native_segment_lines(
    HROASCAN_NATIVE_IMAGE binary_img,
    roascan_native_rect_t* out_boxes,
    int32_t max_boxes
) {
    if (!binary_img) return 0;
    auto lines = roascan::segment_lines(binary_img->img);
    int32_t count = 0;
    for (const auto& ln : lines) {
        if (out_boxes && count < max_boxes) {
            out_boxes[count].left = ln.left;
            out_boxes[count].top = ln.top;
            out_boxes[count].right = ln.right;
            out_boxes[count].bottom = ln.bottom;
        }
        ++count;
    }
    return count;
}

int32_t roascan_native_segment_words(
    HROASCAN_NATIVE_IMAGE binary_img,
    roascan_native_rect_t* out_boxes,
    int32_t max_boxes
) {
    if (!binary_img) return 0;
    auto lines = roascan::segment_lines(binary_img->img);
    int32_t count = 0;
    for (const auto& line : lines) {
        auto words = roascan::segment_words(binary_img->img, line);
        for (const auto& w : words) {
            if (out_boxes && count < max_boxes) {
                out_boxes[count].left = w.left;
                out_boxes[count].top = w.top;
                out_boxes[count].right = w.right;
                out_boxes[count].bottom = w.bottom;
            }
            ++count;
        }
    }
    return count;
}

HROASCAN_NATIVE_LEXICON roascan_native_lexicon_create(void) {
    return new roascan_native_lexicon_s();
}

void roascan_native_lexicon_destroy(HROASCAN_NATIVE_LEXICON lex) {
    delete lex;
}

void roascan_native_lexicon_insert(HROASCAN_NATIVE_LEXICON lex, const char* word) {
    if (lex && word) {
        lex->lex.insert(word);
    }
}

int32_t roascan_native_lexicon_contains(HROASCAN_NATIVE_LEXICON lex, const char* word) {
    if (lex && word) {
        return lex->lex.contains(word) ? 1 : 0;
    }
    return 0;
}

int32_t roascan_native_lexicon_load_file(HROASCAN_NATIVE_LEXICON lex, const char* filepath) {
    if (lex && filepath) {
        return lex->lex.load_from_file(filepath) ? 1 : 0;
    }
    return 0;
}

const char* roascan_native_lexicon_suggest_best(
    HROASCAN_NATIVE_LEXICON lex,
    const char* word,
    int32_t max_distance
) {
    if (!lex || !word) return nullptr;
    auto suggestions = lex->lex.suggest(word, max_distance);
    if (suggestions.empty()) return nullptr;
    lex->last_suggestion = std::move(suggestions.front());
    return lex->last_suggestion.c_str();
}

// --- High-Level Session C-ABI Implementation -------------------------------

HROASCAN_ENGINE roascan_create_engine(void* /*p_config*/, void* /*p_reserved*/) {
    return new roascan_engine_s();
}

int32_t roascan_destroy_engine(HROASCAN_ENGINE engine) {
    if (!engine) return -1;
    delete engine;
    return 0;
}

int32_t roascan_set_resolution(HROASCAN_ENGINE engine, int32_t dpi_x, int32_t dpi_y) {
    if (!engine) return -1;
    if (dpi_x <= 0 || dpi_y <= 0) return -2;
    engine->dpi_x = dpi_x;
    engine->dpi_y = dpi_y;
    return 0;
}

int32_t roascan_set_alphabet(HROASCAN_ENGINE engine, int16_t alphabet_id) {
    if (!engine) return -1;
    engine->alphabet_id = alphabet_id;
    return 0;
}

int32_t roascan_set_auto_alphabet(HROASCAN_ENGINE engine, int32_t enable) {
    if (!engine) return -1;
    engine->auto_alphabet = (enable != 0);
    return 0;
}

int32_t roascan_set_auto_orientation(HROASCAN_ENGINE engine, int32_t enable) {
    if (!engine) return -1;
    engine->auto_orientation = (enable != 0);
    return 0;
}

int32_t roascan_set_threads(HROASCAN_ENGINE engine, int32_t num_threads) {
    if (!engine) return -1;
    engine->num_threads = (num_threads > 0) ? num_threads : 1;
    return 0;
}

int32_t roascan_set_image_grey(HROASCAN_ENGINE engine, const uint8_t* p_image, int32_t width, int32_t height, int32_t stride) {
    if (!engine || !p_image) return -1;
    if (width <= 0 || height <= 0) return -2;
    const int32_t row_stride = (stride > 0) ? stride : width;
    engine->gray = roascan::GrayImage(width, height);
    for (int32_t y = 0; y < height; ++y) {
        std::memcpy(
            engine->gray.data.data() + static_cast<std::size_t>(y) * width,
            p_image + static_cast<std::size_t>(y) * row_stride,
            static_cast<std::size_t>(width)
        );
    }
    engine->words.clear();
    return 0;
}

int32_t roascan_set_image_color(HROASCAN_ENGINE engine, const uint8_t* p_image, int32_t width, int32_t height, int32_t stride) {
    if (!engine || !p_image) return -1;
    if (width <= 0 || height <= 0) return -2;
    const int32_t channels = (stride >= width * 4) ? 4 : 3;
    const int32_t row_stride = (stride > 0) ? stride : (width * channels);
    engine->gray = roascan::GrayImage(width, height);
    for (int32_t y = 0; y < height; ++y) {
        const uint8_t* src_row = p_image + static_cast<std::size_t>(y) * row_stride;
        uint8_t* dst_row = engine->gray.data.data() + static_cast<std::size_t>(y) * width;
        for (int32_t x = 0; x < width; ++x) {
            const uint32_t r = src_row[x * channels];
            const uint32_t g = src_row[x * channels + 1];
            const uint32_t b = src_row[x * channels + 2];
            dst_row[x] = static_cast<uint8_t>((r * 299u + g * 587u + b * 114u) / 1000u);
        }
    }
    engine->words.clear();
    return 0;
}

int32_t roascan_set_image(HROASCAN_ENGINE engine, const uint8_t* p_image, int32_t width, int32_t height, int32_t bpp, int32_t stride) {
    if (bpp == 8) {
        return roascan_set_image_grey(engine, p_image, width, height, stride);
    } else if (bpp == 24 || bpp == 32) {
        const int32_t default_stride = width * (bpp / 8);
        return roascan_set_image_color(engine, p_image, width, height, (stride > 0) ? stride : default_stride);
    }
    return -5;
}

int32_t roascan_recognize(HROASCAN_ENGINE engine) {
    if (!engine) return -1;
    if (engine->gray.width <= 0 || engine->gray.height <= 0) return -4;

    engine->words.clear();
    roascan::GrayImage binary = roascan::binarize_sauvola(engine->gray, 15, 0.34);

    if (engine->auto_orientation) {
        const double angle = roascan::detect_skew_degrees(binary);
        if (std::abs(angle) > 0.15) {
            binary = roascan::rotate(binary, -angle, 0);
        }
    }

    binary = roascan::despeckle(binary, 6);
    auto lines = roascan::segment_lines(binary);
    for (const auto& ln : lines) {
        auto wboxes = roascan::segment_words(binary, ln);
        for (const auto& wb : wboxes) {
            if (wb.height() < 6 || wb.width() < 2) continue;
            auto node = std::make_unique<roascan_word_s>();
            node->rect = roascan_native_rect_t{wb.left, wb.top, wb.right, wb.bottom};
            node->confidence = 1.0f;
            if (!engine->words.empty()) {
                engine->words.back()->next = node.get();
            }
            engine->words.push_back(std::move(node));
        }
    }
    return 0;
}

HROASCAN_WORD roascan_get_first_word(HROASCAN_ENGINE engine) {
    if (!engine || engine->words.empty()) return nullptr;
    return engine->words.front().get();
}

HROASCAN_WORD roascan_get_next_word(HROASCAN_ENGINE /*engine*/, HROASCAN_WORD current_word) {
    if (!current_word) return nullptr;
    return current_word->next;
}

const char* roascan_get_word_text(HROASCAN_WORD word) {
    if (!word) return "";
    return word->text.c_str();
}

int32_t roascan_get_word_rect(HROASCAN_WORD word, roascan_native_rect_t* p_rect) {
    if (!word || !p_rect) return -1;
    *p_rect = word->rect;
    return 0;
}

float roascan_get_word_confidence(HROASCAN_WORD word) {
    if (!word) return 0.0f;
    return word->confidence;
}

const char* roascan_get_language_name(int32_t language_id) {
    switch (language_id) {
        case 0:  return "English";
        case 1:  return "Spanish";
        case 2:  return "French";
        case 3:  return "German";
        case 4:  return "Italian";
        case 5:  return "Portuguese";
        case 6:  return "Dutch";
        case 7:  return "Polish";
        case 8:  return "Catalan";
        case 9:  return "Latin";
        default: return nullptr;
    }
}

// --- Preprocessor Session Implementation -----------------------------------

HROASCAN_PREPRO roascan_prepro_setup(void* /*p_reserved*/) {
    return new roascan_prepro_s();
}

int32_t roascan_prepro_upset(HROASCAN_PREPRO prepro) {
    if (!prepro) return -1;
    delete prepro;
    return 0;
}

int32_t roascan_prepro_set_brightness(HROASCAN_PREPRO prepro, uint8_t brightness) {
    if (!prepro) return -1;
    prepro->brightness = brightness;
    return 0;
}

int32_t roascan_prepro_set_contrast(HROASCAN_PREPRO prepro, uint8_t contrast) {
    if (!prepro) return -1;
    prepro->contrast = contrast;
    return 0;
}

int32_t roascan_prepro_set_threshold(HROASCAN_PREPRO prepro, uint8_t threshold) {
    if (!prepro) return -1;
    prepro->threshold = threshold;
    return 0;
}

int32_t roascan_prepro_set_threads(HROASCAN_PREPRO prepro, int32_t num_threads) {
    if (!prepro) return -1;
    prepro->num_threads = (num_threads > 0) ? num_threads : 1;
    return 0;
}

const char* roascan_prepro_get_version(void) {
    return "2.0.0-roascan-native";
}

const char* roascan_prepro_get_branch(void) {
    return "main";
}

const char* roascan_prepro_get_sha(void) {
    return "clean-room-2026";
}

// --- Document Output Session Implementation --------------------------------

HROASCAN_DOCOUT roascan_docout_init(void) {
    return new roascan_docout_s();
}

int32_t roascan_docout_close(HROASCAN_DOCOUT docout) {
    if (!docout) return -1;
    delete docout;
    return 0;
}

int32_t roascan_docout_set_format(HROASCAN_DOCOUT docout, int32_t format) {
    if (!docout) return -1;
    docout->format = format;
    return 0;
}

int32_t roascan_docout_set_output_path(HROASCAN_DOCOUT docout, const char* p_path) {
    if (!docout || !p_path) return -1;
    docout->output_path = p_path;
    return 0;
}

int32_t roascan_docout_set_pdf_version(HROASCAN_DOCOUT docout, int32_t version) {
    if (!docout) return -1;
    docout->pdf_version = version;
    return 0;
}

int32_t roascan_docout_set_text_over_image(HROASCAN_DOCOUT docout, int32_t enable) {
    if (!docout) return -1;
    docout->text_over_image = enable;
    return 0;
}

int32_t roascan_docout_set_embedded_fonts(HROASCAN_DOCOUT docout, int32_t enable) {
    if (!docout) return -1;
    docout->embedded_fonts = enable;
    return 0;
}

int32_t roascan_docout_write(HROASCAN_DOCOUT docout) {
    if (!docout || docout->output_path.empty()) return -1;
    // Write a minimal valid PDF 1.5 document if called directly from C/C#
    std::ofstream f(docout->output_path, std::ios::binary);
    if (!f) return -6;
    const char* min_pdf =
        "%PDF-1.5\n"
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\n"
        "xref\n0 4\n0000000000 65535 f \n"
        "0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        "trailer << /Size 4 /Root 1 0 R >>\nstartxref\n186\n%%EOF\n";
    f.write(min_pdf, std::strlen(min_pdf));
    return 0;
}
