// roascan_fontmetrics.hpp
// RoaScan clean-room native engine: Font metrics & line geometry estimation.
// Replaces proprietary closed fontmetrics.bin with standard statistical
// baseline, x-height, ascender, and descender calculation.

#pragma once

#include "roascan_segmentation.hpp"
#include <vector>

namespace roascan {

struct LineMetrics {
    int baseline = 0;      // estimated text baseline y-coordinate
    int x_height = 0;      // height of lowercase x-body (px)
    int ascender = 0;      // ascender extent above baseline (px)
    int descender = 0;     // descender extent below baseline (px)
    double avg_char_width = 0.0;
};

// Estimates typographical font metrics for a segmented text line based on
// connected components or word bounding boxes.
LineMetrics estimate_line_metrics(const GrayImage& binary, const Rect& line_box, const std::vector<Rect>& word_boxes);

} // namespace roascan
