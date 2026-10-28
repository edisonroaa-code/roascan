// roascan_preprocess.cpp
// RoaScan clean-room native engine: high-performance preprocessing implementations.

#include "roascan_preprocess.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <utility>
#include <vector>

namespace roascan {
namespace {

constexpr double kPi = 3.14159265358979323846;

struct Point2f {
    float dx;
    float dy;
};

void compute_rotated_bounds(int w, int h, double cos_a, double sin_a,
                            double& min_x, double& min_y, int& out_w, int& out_h) {
    const double cx = w * 0.5;
    const double cy = h * 0.5;
    const double corners_x[4] = {-cx, w - cx, w - cx, -cx};
    const double corners_y[4] = {-cy, -cy, h - cy, h - cy};
    min_x = 0.0;
    double max_x = 0.0;
    min_y = 0.0;
    double max_y = 0.0;
    for (int i = 0; i < 4; ++i) {
        const double rx = corners_x[i] * cos_a - corners_y[i] * sin_a;
        const double ry = corners_x[i] * sin_a + corners_y[i] * cos_a;
        min_x = std::min(min_x, rx);
        max_x = std::max(max_x, rx);
        min_y = std::min(min_y, ry);
        max_y = std::max(max_y, ry);
    }
    out_w = std::max(1, static_cast<int>(std::ceil(max_x - min_x)));
    out_h = std::max(1, static_cast<int>(std::ceil(max_y - min_y)));
}

} // namespace

GrayImage adjust_brightness_contrast(const GrayImage& img, int brightness, int contrast) {
    if (brightness == 128 && contrast == 128) {
        return img;
    }

    // Precompute a 256-entry lookup table for O(N) fast evaluation.
    const double b_offset = static_cast<double>(brightness - 128) * 2.0;
    const double c_factor = (contrast <= 0)
        ? 0.0
        : std::pow(static_cast<double>(contrast) / 128.0, 2.0);

    std::array<std::uint8_t, 256> lut{};
    for (int i = 0; i < 256; ++i) {
        double v = (static_cast<double>(i) - 128.0) * c_factor + 128.0 + b_offset;
        v = std::clamp(v, 0.0, 255.0);
        lut[i] = static_cast<std::uint8_t>(std::lround(v));
    }

    GrayImage out(img.width, img.height);
    const std::size_t n = img.data.size();
    const std::uint8_t* src = img.data.data();
    std::uint8_t* dst = out.data.data();
    for (std::size_t i = 0; i < n; ++i) {
        dst[i] = lut[src[i]];
    }
    return out;
}

int otsu_threshold(const GrayImage& img) {
    std::array<long, 256> hist{};
    for (std::uint8_t p : img.data) ++hist[p];

    const long total = static_cast<long>(img.pixel_count());
    if (total == 0) return 128;

    double sum = 0.0;
    for (int i = 0; i < 256; ++i) sum += static_cast<double>(i) * hist[i];

    double sum_b = 0.0;
    long w_b = 0;
    double best_var = -1.0;
    int best_t = 128;

    for (int t = 0; t < 256; ++t) {
        w_b += hist[t];
        if (w_b == 0) continue;
        const long w_f = total - w_b;
        if (w_f == 0) break;

        sum_b += static_cast<double>(t) * hist[t];
        const double m_b = sum_b / w_b;
        const double m_f = (sum - sum_b) / w_f;
        const double var_between =
            static_cast<double>(w_b) * static_cast<double>(w_f) * (m_b - m_f) * (m_b - m_f);

        if (var_between > best_var) {
            best_var = var_between;
            best_t = t;
        }
    }
    return best_t;
}

GrayImage binarize_otsu(const GrayImage& img, int threshold) {
    if (threshold < 0) threshold = otsu_threshold(img);

    GrayImage out(img.width, img.height);
    const std::uint8_t thresh_u8 = static_cast<std::uint8_t>(std::clamp(threshold, 0, 255));
    const std::size_t n = img.data.size();
    const std::uint8_t* src = img.data.data();
    std::uint8_t* dst = out.data.data();

    for (std::size_t i = 0; i < n; ++i) {
        dst[i] = (src[i] <= thresh_u8) ? 255 : 0;
    }
    return out;
}

GrayImage binarize_sauvola(const GrayImage& img, int window, double k, double r) {
    const int w = img.width;
    const int h = img.height;
    if (w <= 0 || h <= 0) return GrayImage();
    if (window < 3 || window % 2 == 0) window = 15;
    const int half = window / 2;

    // 64-bit integer integral images: 1-indexed, size (w+1)*(h+1).
    const std::size_t stride = static_cast<std::size_t>(w) + 1;
    std::vector<std::uint64_t> integral(stride * (h + 1), 0);
    std::vector<std::uint64_t> integral_sq(stride * (h + 1), 0);

    for (int y = 0; y < h; ++y) {
        std::uint64_t row_sum = 0;
        std::uint64_t row_sq = 0;
        const std::uint8_t* src_row = img.data.data() + static_cast<std::size_t>(y) * w;
        const std::uint64_t* prev_i = integral.data() + static_cast<std::size_t>(y) * stride;
        const std::uint64_t* prev_sq = integral_sq.data() + static_cast<std::size_t>(y) * stride;
        std::uint64_t* cur_i = integral.data() + (static_cast<std::size_t>(y) + 1) * stride;
        std::uint64_t* cur_sq = integral_sq.data() + (static_cast<std::size_t>(y) + 1) * stride;

        for (int x = 0; x < w; ++x) {
            const std::uint64_t p = src_row[x];
            row_sum += p;
            row_sq += p * p;
            cur_i[x + 1] = prev_i[x + 1] + row_sum;
            cur_sq[x + 1] = prev_sq[x + 1] + row_sq;
        }
    }

    GrayImage out(w, h);
    const double inv_r = (r > 0.0) ? (1.0 / r) : (1.0 / 128.0);

    for (int y = 0; y < h; ++y) {
        const int y1 = std::max(0, y - half);
        const int y2 = std::min(h, y + half + 1);
        const int dy = y2 - y1;

        const std::uint64_t* i_y1 = integral.data() + static_cast<std::size_t>(y1) * stride;
        const std::uint64_t* i_y2 = integral.data() + static_cast<std::size_t>(y2) * stride;
        const std::uint64_t* sq_y1 = integral_sq.data() + static_cast<std::size_t>(y1) * stride;
        const std::uint64_t* sq_y2 = integral_sq.data() + static_cast<std::size_t>(y2) * stride;

        const std::uint8_t* src_row = img.data.data() + static_cast<std::size_t>(y) * w;
        std::uint8_t* dst_row = out.data.data() + static_cast<std::size_t>(y) * w;

        for (int x = 0; x < w; ++x) {
            const int x1 = std::max(0, x - half);
            const int x2 = std::min(w, x + half + 1);
            const double inv_area = 1.0 / static_cast<double>((x2 - x1) * dy);

            const std::uint64_t s = i_y2[x2] - i_y1[x2] - i_y2[x1] + i_y1[x1];
            const std::uint64_t sq = sq_y2[x2] - sq_y1[x2] - sq_y2[x1] + sq_y1[x1];

            const double mean = static_cast<double>(s) * inv_area;
            const double variance = std::max(0.0, static_cast<double>(sq) * inv_area - mean * mean);
            const double stddev = std::sqrt(variance);

            const double threshold = mean * (1.0 + k * (stddev * inv_r - 1.0));
            dst_row[x] = (src_row[x] <= threshold) ? 255 : 0;
        }
    }
    return out;
}

double detect_skew_degrees(const GrayImage& binary,
                           double min_angle,
                           double max_angle,
                           double step) {
    const int w = binary.width;
    const int h = binary.height;
    if (w <= 0 || h <= 0) return 0.0;

    const float cx = static_cast<float>(w) * 0.5f;
    const float cy = static_cast<float>(h) * 0.5f;

    // 1. Extract foreground points once with adaptive subsampling.
    // On an A4 300 DPI page (2480x3508), stride_xy = 4 reduces scan cost by 16x
    // while retaining full angular precision across horizontal text baselines.
    const int stride_xy = std::max(1, std::min(w, h) / 600);
    std::vector<Point2f> pts;
    pts.reserve(16384);

    for (int y = 0; y < h; y += stride_xy) {
        const std::uint8_t* row = binary.data.data() + static_cast<std::size_t>(y) * w;
        const float dy = static_cast<float>(y) - cy;
        for (int x = 0; x < w; x += stride_xy) {
            if (row[x] != 0) {
                pts.push_back(Point2f{static_cast<float>(x) - cx, dy});
            }
        }
    }

    if (pts.size() < 16) {
        return 0.0;
    }

    // Cap point cloud to at most ~24,000 points for guaranteed <3ms execution.
    if (pts.size() > 24000) {
        const std::size_t keep_step = pts.size() / 24000 + 1;
        std::size_t dst_idx = 0;
        for (std::size_t i = 0; i < pts.size(); i += keep_step) {
            pts[dst_idx++] = pts[i];
        }
        pts.resize(dst_idx);
    }

    std::vector<int> row_sums(h, 0);
    auto evaluate_angle = [&](double angle_deg) -> double {
        const double rad = angle_deg * kPi / 180.0;
        const float cos_a = static_cast<float>(std::cos(rad));
        const float sin_a = static_cast<float>(std::sin(rad));

        std::fill(row_sums.begin(), row_sums.end(), 0);
        for (const auto& pt : pts) {
            const float ry = -pt.dx * sin_a + pt.dy * cos_a + cy;
            const int row = static_cast<int>(ry + 0.5f);
            if (static_cast<unsigned>(row) < static_cast<unsigned>(h)) {
                row_sums[row] += 1;
            }
        }

        double sum = 0.0;
        double sum_sq = 0.0;
        for (int v : row_sums) {
            const double dv = static_cast<double>(v);
            sum += dv;
            sum_sq += dv * dv;
        }
        const double mean = sum / h;
        return (sum_sq / h) - (mean * mean);
    };

    // 2. Stage 1: Coarse search (step = 1.0 deg)
    const double coarse_step = std::max(step, 1.0);
    double best_angle = 0.0;
    double best_var = -1.0;

    for (double angle = min_angle; angle <= max_angle + 1e-9; angle += coarse_step) {
        const double var = evaluate_angle(angle);
        if (var > best_var) {
            best_var = var;
            best_angle = angle;
        }
    }

    // 3. Stage 2: Fine search around best coarse angle (down to step, default 0.1 deg)
    const double fine_step = std::clamp(step, 0.05, 0.5);
    const double fine_min = std::max(min_angle, best_angle - coarse_step);
    const double fine_max = std::min(max_angle, best_angle + coarse_step);

    for (double angle = fine_min; angle <= fine_max + 1e-9; angle += fine_step) {
        const double var = evaluate_angle(angle);
        if (var > best_var) {
            best_var = var;
            best_angle = angle;
        }
    }

    return best_angle;
}

GrayImage rotate(const GrayImage& img, double angle_deg, std::uint8_t fill) {
    const int w = img.width;
    const int h = img.height;
    if (w <= 0 || h <= 0) return GrayImage();

    const double rad = angle_deg * kPi / 180.0;
    const double cos_a = std::cos(rad);
    const double sin_a = std::sin(rad);
    const double cx = w * 0.5;
    const double cy = h * 0.5;

    double min_x = 0.0, min_y = 0.0;
    int out_w = w, out_h = h;
    compute_rotated_bounds(w, h, cos_a, sin_a, min_x, min_y, out_w, out_h);

    GrayImage out(out_w, out_h);
    std::fill(out.data.begin(), out.data.end(), fill);

    for (int oy = 0; oy < out_h; ++oy) {
        const double sy = oy + min_y;
        std::uint8_t* dst_row = out.data.data() + static_cast<std::size_t>(oy) * out_w;
        for (int ox = 0; ox < out_w; ++ox) {
            const double sx = ox + min_x;
            const double src_x = sx * cos_a + sy * sin_a + cx;
            const double src_y = -sx * sin_a + sy * cos_a + cy;
            const int ix = static_cast<int>(std::lround(src_x));
            const int iy = static_cast<int>(std::lround(src_y));
            if (img.in_bounds(ix, iy)) {
                dst_row[ox] = img.at(ix, iy);
            }
        }
    }
    return out;
}

GrayImage rotate_bilinear(const GrayImage& img, double angle_deg, std::uint8_t fill) {
    const int w = img.width;
    const int h = img.height;
    if (w <= 0 || h <= 0) return GrayImage();

    const double rad = angle_deg * kPi / 180.0;
    const double cos_a = std::cos(rad);
    const double sin_a = std::sin(rad);
    const double cx = w * 0.5;
    const double cy = h * 0.5;

    double min_x = 0.0, min_y = 0.0;
    int out_w = w, out_h = h;
    compute_rotated_bounds(w, h, cos_a, sin_a, min_x, min_y, out_w, out_h);

    GrayImage out(out_w, out_h);
    std::fill(out.data.begin(), out.data.end(), fill);

    for (int oy = 0; oy < out_h; ++oy) {
        const double sy = oy + min_y;
        std::uint8_t* dst_row = out.data.data() + static_cast<std::size_t>(oy) * out_w;
        for (int ox = 0; ox < out_w; ++ox) {
            const double sx = ox + min_x;
            const double src_x = sx * cos_a + sy * sin_a + cx;
            const double src_y = -sx * sin_a + sy * cos_a + cy;

            const int x0 = static_cast<int>(std::floor(src_x));
            const int y0 = static_cast<int>(std::floor(src_y));
            if (x0 < 0 || x0 >= w - 1 || y0 < 0 || y0 >= h - 1) {
                if (img.in_bounds(x0, y0)) {
                    dst_row[ox] = img.at(x0, y0);
                }
                continue;
            }

            const double fx = src_x - x0;
            const double fy = src_y - y0;
            const double p00 = img.at(x0, y0);
            const double p10 = img.at(x0 + 1, y0);
            const double p01 = img.at(x0, y0 + 1);
            const double p11 = img.at(x0 + 1, y0 + 1);

            const double val = p00 * (1.0 - fx) * (1.0 - fy) +
                               p10 * fx * (1.0 - fy) +
                               p01 * (1.0 - fx) * fy +
                               p11 * fx * fy;
            dst_row[ox] = static_cast<std::uint8_t>(std::clamp(std::lround(val), 0L, 255L));
        }
    }
    return out;
}

GrayImage despeckle(const GrayImage& binary, int min_area) {
    const int w = binary.width;
    const int h = binary.height;
    if (w <= 0 || h <= 0) return GrayImage();

    GrayImage out(w, h);
    std::vector<int> label(static_cast<std::size_t>(w) * h, 0);
    int next_label = 1;

    const int dx[8] = {-1, 0, 1, -1, 1, -1, 0, 1};
    const int dy[8] = {-1, -1, -1, 0, 0, 1, 1, 1};

    // Reusable buffers to avoid per-component heap allocations.
    std::vector<std::pair<int, int>> stack;
    std::vector<std::pair<int, int>> pixels;
    stack.reserve(256);
    pixels.reserve(256);

    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            const std::size_t start_idx = static_cast<std::size_t>(y) * w + x;
            if (binary.data[start_idx] == 0 || label[start_idx] != 0) continue;

            stack.clear();
            pixels.clear();
            stack.emplace_back(x, y);
            label[start_idx] = next_label;

            while (!stack.empty()) {
                auto [cx, cy] = stack.back();
                stack.pop_back();
                pixels.emplace_back(cx, cy);
                for (int n = 0; n < 8; ++n) {
                    const int nx = cx + dx[n];
                    const int ny = cy + dy[n];
                    if (static_cast<unsigned>(nx) >= static_cast<unsigned>(w) ||
                        static_cast<unsigned>(ny) >= static_cast<unsigned>(h)) {
                        continue;
                    }
                    const std::size_t idx = static_cast<std::size_t>(ny) * w + nx;
                    if (binary.data[idx] == 0 || label[idx] != 0) continue;
                    label[idx] = next_label;
                    stack.emplace_back(nx, ny);
                }
            }

            if (static_cast<int>(pixels.size()) >= min_area) {
                for (auto [px, py] : pixels) out.at(px, py) = 255;
            }
            ++next_label;
        }
    }
    return out;
}

GrayImage enhance_document(const GrayImage& gray, const GrayImage& clean_binary) {
    const int w = gray.width;
    const int h = gray.height;
    if (w <= 0 || h <= 0 || clean_binary.width != w || clean_binary.height != h) {
        return gray;
    }

    GrayImage out(w, h);
    std::fill(out.data.begin(), out.data.end(), 255);

    for (int y = 0; y < h; ++y) {
        const int y0 = std::max(0, y - 1);
        const int y1 = std::min(h - 1, y + 1);
        const std::uint8_t* g_row = gray.data.data() + static_cast<std::size_t>(y) * w;
        const std::uint8_t* b_row = clean_binary.data.data() + static_cast<std::size_t>(y) * w;
        std::uint8_t* dst_row = out.data.data() + static_cast<std::size_t>(y) * w;

        for (int x = 0; x < w; ++x) {
            if (b_row[x] != 0) {
                // Core ink pixel: darken faded ink while keeping subtle tonal gradation
                const int v = static_cast<int>(g_row[x]);
                const int darkened = std::clamp((v * 65) / 100, 0, 180);
                dst_row[x] = static_cast<std::uint8_t>(darkened);
            } else {
                // Check 4-neighborhood for 1px anti-aliased halo around glyph strokes
                const int x0 = std::max(0, x - 1);
                const int x1 = std::min(w - 1, x + 1);
                const bool near_ink =
                    (clean_binary.at(x0, y) != 0) ||
                    (clean_binary.at(x1, y) != 0) ||
                    (clean_binary.at(x, y0) != 0) ||
                    (clean_binary.at(x, y1) != 0);
                if (near_ink) {
                    // Blend soft edge toward white to avoid jagged binary staircasing
                    const int v = static_cast<int>(g_row[x]);
                    dst_row[x] = static_cast<std::uint8_t>(std::clamp(v + (255 - v) / 3, 140, 255));
                }
            }
        }
    }
    return out;
}

GrayImage remove_table_grid_lines(const GrayImage& binary,
                                  int min_horiz_len,
                                  int min_vert_len) {
    const int w = binary.width;
    const int h = binary.height;
    if (w <= 0 || h <= 0) return binary;

    // Table grid lines span multiple columns/rows (>= 180 px horiz, >= 130 px vert),
    // well above the height of any single capital letter stem (30..80 px).
    if (min_horiz_len <= 0) min_horiz_len = std::max(180, w / 6);
    if (min_vert_len <= 0) min_vert_len = std::max(130, h / 6);

    GrayImage out = binary;
    std::vector<std::uint8_t> erase_mask(static_cast<std::size_t>(w) * h, 0);

    // 1. Detect horizontal grid line segments
    for (int y = 0; y < h; ++y) {
        int run_start = -1;
        for (int x = 0; x <= w; ++x) {
            const bool ink = (x < w) && (binary.at(x, y) != 0);
            if (ink) {
                if (run_start < 0) run_start = x;
            } else if (run_start >= 0) {
                const int run_len = x - run_start;
                if (run_len >= min_horiz_len) {
                    for (int rx = run_start; rx < x; ++rx) {
                        const bool has_above = (y >= 3 && binary.at(rx, y - 3) != 0) ||
                                               (y >= 4 && binary.at(rx, y - 4) != 0);
                        const bool has_below = (y + 3 < h && binary.at(rx, y + 3) != 0) ||
                                               (y + 4 < h && binary.at(rx, y + 4) != 0);
                        if (!(has_above && has_below)) {
                            erase_mask[static_cast<std::size_t>(y) * w + rx] = 1;
                        }
                    }
                }
                run_start = -1;
            }
        }
    }

    // 2. Detect vertical grid line segments
    for (int x = 0; x < w; ++x) {
        int run_start = -1;
        for (int y = 0; y <= h; ++y) {
            const bool ink = (y < h) && (binary.at(x, y) != 0);
            if (ink) {
                if (run_start < 0) run_start = y;
            } else if (run_start >= 0) {
                const int run_len = y - run_start;
                if (run_len >= min_vert_len) {
                    for (int ry = run_start; ry < y; ++ry) {
                        const bool has_left = (x >= 3 && binary.at(x - 3, ry) != 0) ||
                                              (x >= 4 && binary.at(x - 4, ry) != 0);
                        const bool has_right = (x + 3 < w && binary.at(x + 3, ry) != 0) ||
                                               (x + 4 < w && binary.at(x + 4, ry) != 0);
                        if (!(has_left && has_right)) {
                            erase_mask[static_cast<std::size_t>(ry) * w + x] = 1;
                        }
                    }
                }
                run_start = -1;
            }
        }
    }

    for (std::size_t i = 0; i < out.data.size(); ++i) {
        if (erase_mask[i]) {
            out.data[i] = 0;
        }
    }
    return out;
}

GrayImage rotate_orthogonal(const GrayImage& img, int degrees) {
    const int w = img.width;
    const int h = img.height;
    if (w <= 0 || h <= 0) return img;

    int norm = ((degrees % 360) + 360) % 360;
    if (norm == 0) return img;

    if (norm == 90) {
        GrayImage out(h, w);
        for (int y = 0; y < h; ++y) {
            for (int x = 0; x < w; ++x) {
                out.at(y, w - 1 - x) = img.at(x, y);
            }
        }
        return out;
    }
    if (norm == 180) {
        GrayImage out(w, h);
        for (int y = 0; y < h; ++y) {
            for (int x = 0; x < w; ++x) {
                out.at(w - 1 - x, h - 1 - y) = img.at(x, y);
            }
        }
        return out;
    }
    if (norm == 270) {
        GrayImage out(h, w);
        for (int y = 0; y < h; ++y) {
            for (int x = 0; x < w; ++x) {
                out.at(h - 1 - y, x) = img.at(x, y);
            }
        }
        return out;
    }
    return rotate(img, static_cast<double>(degrees), 0);
}

int detect_sideways_orientation(const GrayImage& binary) {
    const int w = binary.width;
    const int h = binary.height;
    if (w <= 16 || h <= 16) return 0;

    std::vector<double> row_proj(h, 0.0);
    std::vector<double> col_proj(w, 0.0);

    for (int y = 0; y < h; ++y) {
        const std::uint8_t* row = binary.data.data() + static_cast<std::size_t>(y) * w;
        int rsum = 0;
        for (int x = 0; x < w; ++x) {
            if (row[x] != 0) {
                ++rsum;
                col_proj[x] += 1.0;
            }
        }
        row_proj[y] = static_cast<double>(rsum) / w;
    }
    for (int x = 0; x < w; ++x) {
        col_proj[x] /= h;
    }

    // Measure high-frequency line-to-gap transitions (step=4 px) along Y vs X
    auto calc_grad_energy = [](const std::vector<double>& v) {
        if (v.size() <= 4) return 0.0;
        double energy = 0.0;
        for (std::size_t i = 4; i < v.size(); ++i) {
            const double d = v[i] - v[i - 4];
            energy += d * d;
        }
        return energy / static_cast<double>(v.size() - 4);
    };

    const double grad_h = calc_grad_energy(row_proj);
    const double grad_v = calc_grad_energy(col_proj);

    if (grad_v > grad_h * 1.6 && grad_v > 1e-5) {
        return 90;
    }
    return 0;
}

} // namespace roascan
