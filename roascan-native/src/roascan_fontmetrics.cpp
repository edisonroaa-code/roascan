// roascan_fontmetrics.cpp
// RoaScan clean-room native engine: Font metrics implementation.

#include "roascan_fontmetrics.hpp"
#include <algorithm>
#include <cmath>
#include <numeric>

namespace roascan {

LineMetrics estimate_line_metrics(const GrayImage& binary, const Rect& line_box, const std::vector<Rect>& word_boxes) {
    LineMetrics metrics;
    if (!line_box.valid() || word_boxes.empty()) {
        metrics.baseline = line_box.bottom;
        metrics.x_height = std::max(1, line_box.height() * 2 / 3);
        metrics.ascender = line_box.height();
        metrics.descender = 0;
        return metrics;
    }

    // Collect bottom and height statistics across word boxes
    std::vector<int> bottoms;
    std::vector<int> heights;
    std::vector<int> widths;

    for (const auto& w : word_boxes) {
        if (w.valid()) {
            bottoms.push_back(w.bottom);
            heights.push_back(w.height());
            widths.push_back(w.width());
        }
    }

    if (bottoms.empty()) {
        metrics.baseline = line_box.bottom;
        return metrics;
    }

    // Baseline is estimated as median bottom
    std::sort(bottoms.begin(), bottoms.end());
    metrics.baseline = bottoms[bottoms.size() / 2];

    // Typical line height
    std::sort(heights.begin(), heights.end());
    int median_height = heights[heights.size() / 2];

    // Standard typographic proportions: x-height ~ 0.65 of full body
    metrics.x_height = std::max(1, static_cast<int>(std::round(median_height * 0.65)));
    metrics.ascender = median_height;
    metrics.descender = std::max(0, line_box.bottom - metrics.baseline);

    if (!widths.empty()) {
        double sum_w = std::accumulate(widths.begin(), widths.end(), 0.0);
        metrics.avg_char_width = sum_w / widths.size();
    }

    return metrics;
}

} // namespace roascan
