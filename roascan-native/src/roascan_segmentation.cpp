// roascan_segmentation.cpp
// RoaScan clean-room native engine: recursive XY-Cut block segmentation,
// line segmentation, and typographic metric-aware word segmentation.

#include "roascan_segmentation.hpp"
#include "roascan_fontmetrics.hpp"

#include <algorithm>
#include <cmath>
#include <vector>

namespace roascan {
namespace {

// Tightens a rectangle to its actual foreground (ink != 0) bounds.
Rect tighten_rect(const GrayImage& binary, const Rect& r) {
    const int x0 = std::max(0, r.left);
    const int y0 = std::max(0, r.top);
    const int x1 = std::min(binary.width, r.right);
    const int y1 = std::min(binary.height, r.bottom);

    int min_x = x1, max_x = x0 - 1;
    int min_y = y1, max_y = y0 - 1;

    for (int y = y0; y < y1; ++y) {
        const std::uint8_t* row = binary.data.data() + static_cast<std::size_t>(y) * binary.width;
        for (int x = x0; x < x1; ++x) {
            if (row[x] != 0) {
                if (x < min_x) min_x = x;
                if (x > max_x) max_x = x;
                if (y < min_y) min_y = y;
                if (y > max_y) max_y = y;
            }
        }
    }

    if (max_x < min_x || max_y < min_y) {
        return Rect{0, 0, 0, 0};
    }
    return Rect{min_x, min_y, max_x + 1, max_y + 1};
}

// Raw horizontal band extraction within a specific bounding region 'r'.
std::vector<Rect> extract_horizontal_bands(const GrayImage& binary, const Rect& r, int min_height) {
    const int x0 = std::max(0, r.left);
    const int y0 = std::max(0, r.top);
    const int x1 = std::min(binary.width, r.right);
    const int y1 = std::min(binary.height, r.bottom);
    const int h = y1 - y0;
    if (h <= 0 || x1 <= x0) return {};

    std::vector<int> proj(h, 0);
    for (int y = y0; y < y1; ++y) {
        const std::uint8_t* row = binary.data.data() + static_cast<std::size_t>(y) * binary.width;
        int count = 0;
        for (int x = x0; x < x1; ++x) {
            if (row[x] != 0) ++count;
        }
        proj[y - y0] = count;
    }

    std::vector<Rect> bands;
    int start = -1;
    for (int i = 0; i <= h; ++i) {
        const bool ink = (i < h) && (proj[i] > 0);
        if (ink && start < 0) {
            start = i;
        } else if (!ink && start >= 0) {
            if (i - start >= min_height) {
                Rect band = tighten_rect(binary, Rect{x0, y0 + start, x1, y0 + i});
                if (band.valid() && band.height() >= min_height) {
                    bands.push_back(band);
                }
            }
            start = -1;
        }
    }
    return bands;
}

// Recursive XY-Cut block decomposition.
void xy_cut_recursive(const GrayImage& binary,
                      const Rect& region,
                      int min_col_gap,
                      int min_block_vgap,
                      int depth,
                      std::vector<Rect>& out_blocks) {
    Rect r = tighten_rect(binary, region);
    if (!r.valid() || r.width() < 4 || r.height() < 4) return;
    if (depth > 12) {
        out_blocks.push_back(r);
        return;
    }

    // Check how many horizontal text lines exist in this region
    auto bands = extract_horizontal_bands(binary, r, 4);
    const bool has_multiple_lines = (bands.size() >= 2);

    // 1. Try Vertical Column Split (if region has >= 2 lines or wide layout)
    // Look for a vertical valley (all-zero column projection) of width >= min_col_gap.
    if (has_multiple_lines && r.width() >= min_col_gap * 3) {
        const int rw = r.width();
        std::vector<int> vproj(rw, 0);
        for (int y = r.top; y < r.bottom; ++y) {
            const std::uint8_t* row = binary.data.data() + static_cast<std::size_t>(y) * binary.width;
            for (int x = r.left; x < r.right; ++x) {
                if (row[x] != 0) ++vproj[x - r.left];
            }
        }

        int best_gap_start = -1;
        int best_gap_len = 0;
        int cur_start = -1;
        for (int i = 0; i < rw; ++i) {
            if (vproj[i] == 0) {
                if (cur_start < 0) cur_start = i;
            } else if (cur_start >= 0) {
                int len = i - cur_start;
                if (len >= min_col_gap && len > best_gap_len) {
                    best_gap_len = len;
                    best_gap_start = cur_start;
                }
                cur_start = -1;
            }
        }

        if (best_gap_start > 0 && best_gap_len >= min_col_gap) {
            const int split_x0 = r.left + best_gap_start;
            const int split_x1 = split_x0 + best_gap_len;
            Rect left_region{r.left, r.top, split_x0, r.bottom};
            Rect right_region{split_x1, r.top, r.right, r.bottom};
            xy_cut_recursive(binary, left_region, min_col_gap, min_block_vgap, depth + 1, out_blocks);
            xy_cut_recursive(binary, right_region, min_col_gap, min_block_vgap, depth + 1, out_blocks);
            return;
        }
    }

    // 2. Try Horizontal Block Split along the largest vertical gap between bands
    // (Separates headers/titles from multi-column bodies so subsequent recursive
    // calls can split the body vertically into columns).
    if (bands.size() >= 2) {
        int best_idx = -1;
        int max_vgap = -1;
        for (std::size_t i = 0; i + 1 < bands.size(); ++i) {
            const int vgap = bands[i + 1].top - bands[i].bottom;
            if (vgap > max_vgap) {
                max_vgap = vgap;
                best_idx = static_cast<int>(i);
            }
        }

        if (best_idx >= 0 && max_vgap >= min_block_vgap) {
            const int split_y0 = bands[best_idx].bottom;
            const int split_y1 = bands[best_idx + 1].top;
            Rect top_region{r.left, r.top, r.right, split_y0};
            Rect bot_region{r.left, split_y1, r.right, r.bottom};
            xy_cut_recursive(binary, top_region, min_col_gap, min_block_vgap, depth + 1, out_blocks);
            xy_cut_recursive(binary, bot_region, min_col_gap, min_block_vgap, depth + 1, out_blocks);
            return;
        }
    }

    out_blocks.push_back(r);
}

} // namespace

std::vector<Rect> segment_blocks(const GrayImage& binary) {
    if (binary.width <= 0 || binary.height <= 0) return {};

    // Minimum vertical column gutter: ~4.5% of page width, clamped >= 48 px.
    // Normal inter-word spacing at 300 DPI is 10..22 px, whereas column gutters
    // are typically >= 55..150 px.
    const int min_col_gap = std::max(48, binary.width / 22);
    const int min_block_vgap = std::max(28, binary.height / 30);

    std::vector<Rect> blocks;
    xy_cut_recursive(binary, Rect{0, 0, binary.width, binary.height},
                     min_col_gap, min_block_vgap, 0, blocks);
    return blocks;
}

std::vector<Rect> segment_lines(const GrayImage& binary, int min_height) {
    auto blocks = segment_blocks(binary);
    std::vector<Rect> all_lines;

    for (const auto& blk : blocks) {
        auto lines = extract_horizontal_bands(binary, blk, min_height);
        for (const auto& ln : lines) {
            all_lines.push_back(ln);
        }
    }
    return all_lines;
}

std::vector<Rect> segment_words(const GrayImage& binary,
                                const Rect& line,
                                int gap,
                                int min_width) {
    const int x0 = std::max(0, line.left);
    const int x1 = std::min(binary.width, line.right);
    const int y0 = std::max(0, line.top);
    const int y1 = std::min(binary.height, line.bottom);
    if (x1 <= x0 || y1 <= y0) return {};

    const int rw = x1 - x0;
    const int line_h = y1 - y0;

    // Vertical projection within the line's horizontal and vertical bounds.
    std::vector<int> proj(rw, 0);
    for (int y = y0; y < y1; ++y) {
        const std::uint8_t* row = binary.data.data() + static_cast<std::size_t>(y) * binary.width;
        for (int x = x0; x < x1; ++x) {
            if (row[x] != 0) ++proj[x - x0];
        }
    }

    // 1. Initial clustering: isolate glyphs, words, and punctuation marks.
    const int initial_gap = std::min(gap, 5);
    std::vector<Rect> clusters;
    int start = -1;
    int last_ink = -1;

    for (int i = 0; i < rw; ++i) {
        if (proj[i] > 0) {
            if (start < 0) start = i;
            last_ink = i;
        } else if (start >= 0 && (i - last_ink) > initial_gap) {
            if (last_ink - start + 1 >= min_width) {
                clusters.push_back(Rect{x0 + start, y0, x0 + last_ink + 1, y1});
            }
            start = -1;
        }
    }
    if (start >= 0 && last_ink - start + 1 >= min_width) {
        clusters.push_back(Rect{x0 + start, y0, x0 + last_ink + 1, y1});
    }

    if (clusters.empty()) return {};

    // 2. Estimate typographical line metrics (baseline, x_height, ascender)
    // to scale spacing and punctuation attachment thresholds dynamically.
    const LineMetrics metrics = estimate_line_metrics(binary, line, clusters);
    const int ref_h = std::max(line_h, metrics.ascender);

    // Normal words break at inter-word gap >= max(gap, ~0.28 * line_h).
    // Punctuation (commas, periods, colons, hyphens) has narrow width and binds
    // across kerning gaps up to ~0.48 * line_h.
    const int word_space_thresh = std::max(gap, (ref_h * 28) / 100);
    const int punct_max_w = std::max(6, ref_h / 4);
    const int punct_gap_thresh = std::max(12, (ref_h * 48) / 100);

    std::vector<Rect> words;
    words.push_back(clusters[0]);

    for (std::size_t i = 1; i < clusters.size(); ++i) {
        auto& prev = words.back();
        const auto& cur = clusters[i];
        const int dist = cur.left - prev.right;

        const int prev_w = prev.width();
        const int cur_w = cur.width();
        const bool is_trailing_punct = (cur_w <= punct_max_w);
        const bool is_leading_punct = (prev_w <= punct_max_w && words.size() == 1);

        if ((is_trailing_punct && dist <= punct_gap_thresh) ||
            (is_leading_punct && dist <= punct_gap_thresh) ||
            (dist < word_space_thresh)) {
            prev.right = cur.right;
            prev.top = std::min(prev.top, cur.top);
            prev.bottom = std::max(prev.bottom, cur.bottom);
        } else {
            words.push_back(cur);
        }
    }

    return words;
}

void draw_boxes(GrayImage& img, const std::vector<Rect>& boxes) {
    const int w = img.width;
    const int h = img.height;
    for (const Rect& r : boxes) {
        for (int x = r.left; x < r.right; ++x) {
            if (r.top >= 0 && r.top < h) img.at(x, r.top) = 128;
            if (r.bottom - 1 >= 0 && r.bottom - 1 < h) img.at(x, r.bottom - 1) = 128;
        }
        for (int y = r.top; y < r.bottom; ++y) {
            if (r.left >= 0 && r.left < w) img.at(r.left, y) = 128;
            if (r.right - 1 >= 0 && r.right - 1 < w) img.at(r.right - 1, y) = 128;
        }
    }
}

} // namespace roascan
